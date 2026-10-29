"""Optional recording adapter for the user's existing inverse_kinematics.py.

One serial reader owns all I/O. The original key mapping and COM setting stay
in robot/inverse_kinematics.py. No serial port opens just by importing this file.
"""
from __future__ import annotations

import json
import queue
import runpy
import threading
import time
from pathlib import Path

from tools.probe_mirobot import fields, find_field, is_error, is_ok, is_status, state_of


class TeleopSession:
    def __init__(self, out, clock_ns, stop, initial_s):
        self.out, self.clock_ns, self.stop = out, clock_ns, stop
        self.initial_s = initial_s
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
                            self.emit('capture_end')  # exclude original exit homing from training interval
                            self.ended = True
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
                        line = partial.decode('utf-8', errors='replace').strip()
                        partial = b''
                        if is_status(line):
                            cart = find_field(fields(line), 'Cartesian')
                            if cart and len(cart) >= 6:
                                self.emit('state', cart=cart[:6], state=state_of(line),
                                          query_start_s=query_t,
                                          rtt_s=None if query_t is None else
                                          (time.perf_counter_ns()-self.clock_ns)/1e9-query_t)
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
        if command.upper() == 'M30':
            self.close()
        return request['ok']

    def tick(self):
        import keyboard
        if self.stop.is_set():
            raise RuntimeError('Capture stopped.') from self.failure
        if not self.started and keyboard.is_pressed('f8'):
            self.emit('capture_start')
            self.started = True
            print('=== TRAINING EPISODE START (F8) ===')
        if self.started and not self.ended and keyboard.is_pressed('f9'):
            self.emit('capture_end')
            self.ended = True
            print('=== TRAINING EPISODE END (F9); q exits the original controller ===')

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


def run(out, clock_ns, stop, initial_s):
    session = TeleopSession(out, clock_ns, stop, initial_s)
    try:
        path = Path(__file__).resolve().parents[3]/'robot/inverse_kinematics.py'
        runpy.run_path(str(path), init_globals={'_w9_session': session}, run_name='__main__')
        session.finish()
    finally:
        session.close()
        session.log.close()
