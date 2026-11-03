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
import runpy
import threading
import time
from pathlib import Path

from tools.probe_mirobot import fields, find_field, is_error, is_ok, is_status, state_of
from tools.run_gcode import pose_of


class TeleopSession:
    def __init__(self, out, clock_ns, stop, initial_s, port=None, keyboard=None,
                 controls=None, on_start=None, on_end=None):
        self.out, self.clock_ns, self.stop = out, clock_ns, stop
        self.initial_s = initial_s
        self.port, self.keyboard = port, keyboard
        self.controls, self.on_start, self.on_end = controls, on_start, on_end
        self.initial_ready = False
        self.last_motion = None
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
                if active is None:
                    try:
                        active = self.requests.get_nowait()
                    except queue.Empty:
                        pass
                    if active:
                        cmd = active['cmd']
                        if self.started and not self.ended and cmd.upper() in ('$H', 'M30'):
                            self.end_capture()  # exclude original exit homing from saved frames too
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
                            query_t = None
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
            self.failure = error
            self.stop.set()
        finally:
            if active:
                active['done'].set()

    def send_gcode(self, command):
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
        if command.upper() == 'M30':
            self.close()
        return request['ok']

    def wait_initial_ready(self, timeout=120):
        if self.last_motion is None:
            raise RuntimeError('No acknowledged initial pose; recording remains disabled.')
        deadline = time.perf_counter()+timeout
        threshold = (time.perf_counter_ns()-self.clock_ns)/1e9
        revision, stable = self.status_revision, 0
        while time.perf_counter() < deadline:
            if self.stop.is_set() or self.failure or self.closed.is_set():
                raise RuntimeError('Robot initialization interrupted.') from self.failure
            with self.status_condition:
                self.status_condition.wait_for(lambda: self.status_revision != revision, timeout=.05)
                if self.status_revision == revision:
                    continue
                revision = self.status_revision
                cart, state, query_time = self.latest_status
            fresh = query_time is not None and query_time >= threshold
            at_goal = (math.dist(cart[:3], self.last_motion[:3]) <= 2 and
                       max(abs((a-b+180) % 360-180) for a, b in zip(cart[3:], self.last_motion[3:])) <= 2)
            stable = stable+1 if fresh and state.lower() == 'idle' and at_goal else 0
            if stable >= 3:
                self.initial_ready = True
                self.emit('initial_ready', cart=cart)
                self.controls.set_state('ready')
                print('=== HOMING / INITIAL MOVE COMPLETE - click START REC or press F8 ===', flush=True)
                return
        raise TimeoutError('Initial pose did not reach Idle within tolerance; recording disabled.')

    def start_capture(self):
        if self.started or (self.controls is not None and not self.initial_ready):
            return
        if self.controls:
            self.controls.set_state('starting')
        if self.on_start:
            self.on_start()
        self.emit('capture_start')
        self.started = True
        if self.controls:
            self.controls.set_state('recording')
        print('=== TRAINING EPISODE START ===', flush=True)

    def end_capture(self):
        if not self.started or self.ended:
            return
        self.emit('capture_end')
        self.ended = True
        if self.on_end:
            self.on_end()
        if self.controls:
            self.controls.set_state('ended')
        print('=== RECORDING STOPPED - q saves and exits (original exit homing) ===', flush=True)

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


def run(out, clock_ns, stop, initial_s, port=None, controls=None, on_start=None, on_end=None):
    if os.name == 'posix':
        from .terminal_keyboard import TerminalKeyboard
        keyboard_context = TerminalKeyboard()
    else:
        keyboard_context = nullcontext(None)
    with keyboard_context as keyboard:
        session = TeleopSession(out, clock_ns, stop, initial_s, port=port, keyboard=keyboard,
                                controls=controls, on_start=on_start, on_end=on_end)
        try:
            path = Path(__file__).resolve().parents[3]/'robot/inverse_kinematics.py'
            runpy.run_path(str(path), init_globals={'_w9_session': session, '_w9_keyboard': keyboard},
                           run_name='__main__')
            session.finish()
        finally:
            session.close()
            session.log.close()
