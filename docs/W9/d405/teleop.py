"""Optional recording adapter for the user's existing inverse_kinematics.py.

One serial reader owns all I/O. W9 can override the serial port and use Linux
terminal keys while retaining the original motion mapping and homing behavior.
No serial port opens just by importing this file.
"""
from __future__ import annotations

import json
import math
import os
from contextlib import nullcontext
import queue
import re
import threading
import time
from pathlib import Path

from tools.probe_mirobot import fields, find_field, is_error, is_ok, is_status, state_of
from tools.run_gcode import pose_of

# Position variables of robot/inverse_kinematics.py, in pose_of order.
SCRIPT_POSE = ('current_x', 'current_y', 'current_z', 'current_a', 'current_b', 'current_c')


class TeleopSession:
    def __init__(self, out, clock_ns, stop, initial_s, port=None, keyboard=None,
                 controls=None, on_start=None, on_end=None, on_reset=None, skip_homing=False, auto_stop_seconds=3.0,
                 pickup_timeout=15.0, episode_timeout=120.0, lift_mm=10.0, closed_s=60):
        self.out, self.clock_ns, self.stop = out, clock_ns, stop
        self.initial_s = initial_s
        self.port, self.keyboard = port, keyboard
        self.controls, self.on_start, self.on_end = controls, on_start, on_end
        self.on_reset, self.skip_homing = on_reset, skip_homing
        self.auto_stop_seconds, self.pickup_timeout = auto_stop_seconds, pickup_timeout
        self.episode_timeout, self.lift_mm, self.closed_s = episode_timeout, lift_mm, closed_s
        self.take_started = self.close_time = self.close_z = self.lift_command_time = None
        self.lift_stable = 0
        self.lift_motion_complete = False
        self.grasp_success = self.pickup_success = None
        self.result_lock = threading.RLock()
        self.initial_ready = False
        self.last_motion = None
        self.initial_command = None  # the original script's first G0 = initial pose
        self.script_globals = None   # set by run(); RESET re-syncs the script's position
        self.status_condition = threading.Condition()
        self.status_revision = 0
        self.latest_status = None
        self.requests = queue.Queue()
        self.started, self.ended = False, False
        self.closed = threading.Event()
        self.failure = None
        self.ser = None
        self.worker = None
        self.log = (out/'robot.jsonl').open('x', encoding='utf-8')
        self.lock = threading.Lock()

    def emit(self, kind, **data):
        with self.lock:
            self.log.write(json.dumps(dict(kind=kind, t_s=(time.perf_counter_ns()-self.clock_ns)/1e9,
                                          **data))+'\n')
            self.log.flush()

    def open_serial(self, *args, **kwargs):
        import serial
        if self.port:
            if args:
                args = (self.port, *args[1:])
                kwargs.pop('port', None)
            else:
                kwargs['port'] = self.port
        kwargs['timeout'] = 0.005
        kwargs['write_timeout'] = 1
        self.ser = serial.Serial(*args, **kwargs)
        self.worker = threading.Thread(target=self.io_loop, name='mirobot-recording')
        self.worker.start()
        self.emit('gripper_initial', s=self.initial_s)
        return self

    def io_loop(self):
        active, started = None, 0
        next_poll = time.perf_counter()+2  # original script's connection settling time
        partial = b''
        query_t = None
        try:
            while not self.closed.is_set() and not self.stop.is_set():
                now = time.perf_counter()
                self.check_auto_end(now)
                if active is None:
                    try:
                        active = self.requests.get_nowait()
                    except queue.Empty:
                        pass
                    if active:
                        cmd = active['cmd']
                        if self.started and not self.ended and cmd.upper() in ('$H', 'M30'):
                            self.end_capture()  # exclude original exit homing from saved frames too
                        self.observe_command(cmd)
                        self.emit('command', cmd=cmd)
                        if cmd != '?' or query_t is None:
                            self.ser.write((cmd+'\n').encode('ascii'))
                            if cmd == '?':
                                query_t = (time.perf_counter_ns()-self.clock_ns)/1e9
                        started = now
                if query_t is not None and (time.perf_counter_ns()-self.clock_ns)/1e9-query_t > .3:
                    self.emit('query_timeout', query_start_s=query_t)
                    query_t = None
                if now >= next_poll and query_t is None and not (active and active['cmd'] == 'M30'):
                    self.ser.write(b'?\n')
                    query_t = (time.perf_counter_ns()-self.clock_ns)/1e9
                    next_poll = now+0.05
                chunk = self.ser.readline()
                if chunk:
                    partial += chunk
                    if partial.endswith(b'\n'):
                        raw_line = partial.decode('utf-8', errors='replace').rstrip('\r\n')
                        line = raw_line.strip()
                        partial = b''
                        if is_status(line):
                            cart = find_field(fields(line), 'Cartesian')
                            if cart and len(cart) >= 6:
                                self.emit('state', cart=cart[:6], state=state_of(line), raw=raw_line,
                                          query_start_s=query_t,
                                          rtt_s=None if query_t is None else
                                          (time.perf_counter_ns()-self.clock_ns)/1e9-query_t)
                                with self.status_condition:
                                    self.status_revision += 1
                                    self.latest_status = (cart[:6], state_of(line), query_t)
                                    self.status_condition.notify_all()
                            self.observe_status(cart, state_of(line), query_t)
                            query_t = None
                            if state_of(line).lower() in ('alarm', 'error'):
                                self.end_capture('abnormal', line)
                            if active and active['cmd'].strip() == '?':
                                print(line)
                                active['ok'] = True
                                active['done'].set()
                                active = None
                        elif active and (is_ok(line) or is_error(line)):
                            active['ok'] = is_ok(line)
                            active['done'].set()
                            active = None
                            if is_error(line):
                                raise RuntimeError(line)
                if active and now-started > 120:
                    raise TimeoutError('Robot command acknowledgment timeout.')
        except BaseException as error:
            self.end_capture('timeout' if isinstance(error, TimeoutError) else 'abnormal', str(error))
            self.failure = error
            self.stop.set()
        finally:
            if active:
                active['done'].set()

    def send_gcode(self, command):
        if self.skip_homing and command.strip().upper() == '$H':
            return self.skip_home()
        if self.failure:
            raise RuntimeError('Serial recording failed') from self.failure
        if self.stop.is_set():
            raise RuntimeError('Camera capture stopped; no further commands sent.')
        request = dict(cmd=command, done=threading.Event(), ok=False)
        self.requests.put(request)
        while not request['done'].wait(.05):
            if self.stop.is_set() or self.closed.is_set() or self.failure:
                raise RuntimeError('Capture or serial worker stopped.') from self.failure
        if self.failure:
            raise RuntimeError('Serial recording failed') from self.failure
        print('send:', command, 'ok' if request['ok'] else 'error')
        if request['ok'] and pose_of(command) is not None:
            self.last_motion = pose_of(command)
            if self.initial_command is None:
                self.initial_command = command
        if command.upper() == 'M30':
            self.close()
        return request['ok']

    def skip_home(self):
        """--no-homing: replace the original script's $H at start and at q exit."""
        if self.initial_command is None:
            # Start: the original script's own initial G0 follows right after $H.
            self.emit('homing_skipped', at='start')
            print('skip: $H (--no-homing); moving to the initial pose only', flush=True)
            return True
        self.end_capture()  # q without F9: the return move stays out of the training interval
        self.emit('homing_skipped', at='exit')
        print('skip: $H (--no-homing); returning to the initial pose', flush=True)
        self.return_to_initial()
        return True

    def return_to_initial(self):
        """Rise straight up to the initial height, go to the initial pose and wait for Idle there."""
        goal = pose_of(self.initial_command)
        current = self.last_motion or goal
        if current[2] < goal[2]:
            x, y, _, a, b, c = current
            self.send_gcode(f'G0 X{x:.3f} Y{y:.3f} Z{goal[2]:.3f} A{a:.3f} B{b:.3f} C{c:.3f}')
        self.send_gcode(self.initial_command)
        return self.wait_idle_at(goal, what='Return to the initial pose')

    def wait_idle_at(self, goal, timeout=120, what='Robot motion'):
        """Return the pose once three fresh Idle statuses sit within 2 mm / 2 deg of goal."""
        deadline = time.perf_counter()+timeout
        threshold = (time.perf_counter_ns()-self.clock_ns)/1e9
        revision, stable = self.status_revision, 0
        while time.perf_counter() < deadline:
            if self.stop.is_set() or self.failure or self.closed.is_set():
                raise RuntimeError(f'{what} interrupted.') from self.failure
            with self.status_condition:
                self.status_condition.wait_for(lambda: self.status_revision != revision, timeout=.05)
                if self.status_revision == revision:
                    continue
                revision = self.status_revision
                cart, state, query_time = self.latest_status
            fresh = query_time is not None and query_time >= threshold
            at_goal = (math.dist(cart[:3], goal[:3]) <= 2 and
                       max(abs((a-b+180) % 360-180) for a, b in zip(cart[3:], goal[3:])) <= 2)
            stable = stable+1 if fresh and state.lower() == 'idle' and at_goal else 0
            if stable >= 3:
                return cart
        raise TimeoutError(f'{what} did not reach Idle within tolerance.')

    def wait_initial_ready(self, timeout=120):
        if self.last_motion is None:
            raise RuntimeError('No acknowledged initial pose; recording remains disabled.')
        try:
            cart = self.wait_idle_at(self.last_motion, timeout, what='Robot initialization')
        except TimeoutError:
            raise TimeoutError('Initial pose did not reach Idle within tolerance; recording disabled.') from None
        self.initial_ready = True
        self.emit('initial_ready', cart=cart)
        self.controls.set_state('ready')
        print('=== HOMING / INITIAL MOVE COMPLETE - click START REC or press F8 ===', flush=True)

    def start_capture(self):
        if self.started or (self.controls is not None and not self.initial_ready):
            return
        if self.controls:
            self.controls.set_state('starting')
        if self.on_start:
            self.on_start()
        self.take_started = time.perf_counter()
        self.emit('capture_start')
        self.started = True
        if self.controls:
            self.controls.set_state('recording')
        print('=== TRAINING EPISODE START ===', flush=True)

    def observe_command(self, command):
        if self.started and not self.ended and self.close_time is not None and self.lift_command_time is None:
            goal = pose_of(command)
            baseline = self.last_motion[2] if self.last_motion else self.close_z
            if goal is not None and baseline is not None and goal[2] > baseline:
                self.lift_command_time = time.perf_counter()
                self.emit('pickup_lift_command', cmd=command, delay_s=self.auto_stop_seconds)
        match = re.fullmatch(r'M4\s+S(\d+(?:\.\d+)?)', command.strip(), re.I)
        if not (self.started and not self.ended and match):
            return
        if float(match[1]) == self.closed_s and self.close_time is None:
            self.close_time = time.perf_counter()
            self.close_z = self.latest_status[0][2] if self.latest_status else None
            self.emit('pickup_close', baseline_z=self.close_z)
        elif float(match[1]) != self.closed_s and self.close_time is not None:
            self.end_capture('task_failed', 'Gripper reopened before pickup completed.')

    def observe_status(self, cart, state, query_time):
        if self.close_time is None or self.close_z is None or not cart or len(cart) < 3:
            return
        fresh = query_time is not None and query_time >= self.close_time-self.clock_ns/1e9
        lifted = cart[2] >= self.close_z+self.lift_mm
        self.lift_stable = self.lift_stable+1 if fresh and lifted and state.lower() == 'idle' else 0
        self.lift_motion_complete = self.lift_stable >= 3

    def check_auto_end(self, now=None):
        if not self.started or self.ended:
            return
        now = time.perf_counter() if now is None else now
        if self.close_time is not None:
            elapsed = now-self.close_time
            if self.lift_command_time is not None and now-self.lift_command_time >= self.auto_stop_seconds:
                self.end_capture('normal', 'Three-second recording tail after upward Z command.')
            elif self.lift_command_time is None and elapsed >= self.pickup_timeout:
                self.end_capture('timeout', 'Pickup lift did not complete before deadline.')
        if not self.ended and now-self.take_started >= self.episode_timeout:
            self.end_capture('timeout', 'Episode deadline exceeded.')

    def record_pickup_result(self, grasp_success, pickup_success):
        """Operator observation; robot pose alone cannot prove a block was lifted."""
        if type(grasp_success) is not bool or type(pickup_success) is not bool:
            raise ValueError('Grasp and pickup results must be booleans.')
        if pickup_success and not grasp_success:
            raise ValueError('Successful pickup requires successful grasp.')
        with self.result_lock:
            self.grasp_success, self.pickup_success = grasp_success, pickup_success
            self.emit('pickup_result', grasp_success=grasp_success, pickup_success=pickup_success)
            if self.started and not self.ended and not pickup_success:
                self.end_capture('task_failed', 'Operator reported pickup failure.')
            self.save_result()

    def save_result(self, status=None, reason=None):
        if status is not None:
            self.termination_status, self.termination_reason = status, reason
        document = dict(termination_status=getattr(self, 'termination_status', 'recording'),
                        termination_reason=getattr(self, 'termination_reason', None),
                        grasp_success=self.grasp_success, pickup_success=self.pickup_success,
                        outcome_source='operator' if self.pickup_success is not None else 'unreviewed',
                        lift_motion_complete=self.lift_motion_complete)
        (self.out/'capture_result.json').write_text(json.dumps(document, indent=2), encoding='utf-8')

    def end_capture(self, status='manual', reason=None):
        with self.result_lock:
            if not self.started or self.ended:
                return
            self.ended = True
            self.emit('capture_end', status=status, reason=reason)
            if self.on_end:
                self.on_end()
            self.save_result(status, reason)
            if self.controls:
                self.controls.set_state('ended')
            print(f'=== RECORDING STOPPED ({status}) - q saves; RESET discards ===', flush=True)

    def reset_take(self):
        """RESET: discard the current take, return to the initial pose, allow F8 again."""
        if self.script_globals is None or self.initial_command is None:
            print('RESET unavailable: the controller position cannot be re-synced.', flush=True)
            return
        if self.controls:
            self.controls.set_state('resetting')
        discarded = self.started
        if discarded and self.on_reset:
            self.on_reset()  # stop saving frames before the reset mark
        self.emit('capture_reset', discarded_take=discarded, ended=self.ended)
        self.started = self.ended = False
        self.take_started = self.close_time = self.close_z = self.lift_command_time = None
        self.lift_stable = 0
        self.lift_motion_complete = False
        self.grasp_success = self.pickup_success = None
        (self.out/'capture_result.json').unlink(missing_ok=True)
        print('=== RESET - take discarded, returning to the initial pose ===', flush=True)
        self.return_to_initial()
        # The original script keeps its own position variables; without this the
        # next key press would jump back to where the arm was before RESET.
        for name, value in zip(SCRIPT_POSE, pose_of(self.initial_command)):
            self.script_globals[name] = value
        self.initial_ready = True
        if self.controls:
            self.controls.set_state('ready')
        print('=== READY again - open the gripper, then START REC / F8 ===', flush=True)

    def tick(self):
        if self.controls is not None and not self.initial_ready:
            self.wait_initial_ready()
        keyboard = self.keyboard
        if keyboard is None:
            import keyboard
        else:
            keyboard.poll()
        if self.stop.is_set():
            raise RuntimeError('Capture stopped.') from self.failure
        self.check_auto_end()
        if keyboard.is_pressed('f'):
            self.record_pickup_result(False, False)
        if keyboard.is_pressed('v'):
            self.record_pickup_result(True, True)
        if keyboard.is_pressed('g'):
            self.record_pickup_result(True, False)
        actions = self.controls.pending() if self.controls else []
        if keyboard.is_pressed('f8'):
            actions.append('start')
        if keyboard.is_pressed('f9'):
            actions.append('end')
        for action in actions:
            if action == 'start':
                self.start_capture()
            elif action == 'end':
                self.end_capture()
            elif action == 'reset':
                self.reset_take()

    def close(self):
        self.closed.set()
        if self.worker:
            self.worker.join(timeout=2)
        if self.ser and self.ser.is_open:
            self.ser.close()

    def finish(self):
        self.close()
        if self.failure:
            raise RuntimeError('Serial recording failed') from self.failure
        if not self.started or not self.ended:
            raise RuntimeError('No complete F8/F9 training interval. Capture retained for review only.')
        self.emit('complete')


def run(out, clock_ns, stop, initial_s, port=None, controls=None, on_start=None, on_end=None,
        on_reset=None, skip_homing=False, **pickup_options):
    if os.name == 'posix':
        from .terminal_keyboard import TerminalKeyboard
        keyboard_context = TerminalKeyboard()
    else:
        keyboard_context = nullcontext(None)
    with keyboard_context as keyboard:
        session = TeleopSession(out, clock_ns, stop, initial_s, port=port, keyboard=keyboard,
                                controls=controls, on_start=on_start, on_end=on_end,
                                on_reset=on_reset, skip_homing=skip_homing, **pickup_options)
        try:
            path = Path(__file__).resolve().parents[3]/'robot/inverse_kinematics.py'
            # Run the unchanged script in globals we own (runpy keeps a private copy)
            # so RESET can put its position variables back on the initial pose.
            script = {'__name__': '__main__', '__file__': str(path),
                      '_w9_session': session, '_w9_keyboard': keyboard}
            session.script_globals = script
            exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), script)
            session.finish()
        except BaseException as error:
            session.end_capture('timeout' if isinstance(error, TimeoutError) else 'abnormal', str(error))
            raise
        finally:
            session.close()
            session.log.close()
