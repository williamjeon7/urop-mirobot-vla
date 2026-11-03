"""Serial-mocked regressions for preserving complete Mirobot status responses."""
import json
from pathlib import Path
import queue
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from .teleop import TeleopSession


class RawStatusTests(unittest.TestCase):
    def capture_status(self, response, fragmented=False):
        class FakeSerial:
            def __init__(self, *args, **kwargs):
                self.lines = queue.Queue()
                self.is_open = True

            def write(self, value):
                if value != b'?\n':
                    raise AssertionError(f'Unexpected command: {value!r}')
                payload = (response+'\r\n').encode('utf-8')
                if fragmented:
                    split = payload.index(b'Cartesian')+4
                    self.lines.put(payload[:split])
                    self.lines.put(payload[split:])
                else:
                    self.lines.put(payload)

            def readline(self):
                try:
                    return self.lines.get(timeout=.005)
                except queue.Empty:
                    return b''

            def close(self):
                self.is_open = False

        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            session = TeleopSession(out, time.perf_counter_ns(), threading.Event(), 40, port='FAKE')
            try:
                with patch('serial.Serial', FakeSerial):
                    session.open_serial()
                    self.assertTrue(session.send_gcode('?'))
                session.close()
                rows = [json.loads(line) for line in (out/'robot.jsonl').read_text(encoding='utf-8').splitlines()]
                return [row for row in rows if row['kind'] == 'state']
            finally:
                session.close()
                session.log.close()

    def test_full_status_keeps_joint_pwm_fields_and_existing_cartesian_values(self):
        raw = ('<Idle,Angle(ABCDXYZ):0.11,22.2,-3.3,0,40.4,-50.5,60.6,'
               'Cartesian coordinate(XYZ RxRyRz):198.67,-12.5,230.72,0,0,0,'
               'Pump PWM:60,Valve PWM:0>')
        states = self.capture_status(raw, fragmented=True)
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0]['raw'], raw)
        self.assertEqual(states[0]['cart'], [198.67, -12.5, 230.72, 0, 0, 0])
        self.assertEqual(states[0]['state'], 'Idle')
        self.assertGreaterEqual(states[0]['t_s'], states[0]['query_start_s'])
        self.assertGreaterEqual(states[0]['rtt_s'], 0)

    def test_raw_retains_line_content_but_removes_serial_line_terminator(self):
        raw = '  <Idle,Cartesian:198.67,0,230.72,0,0,0>  '
        states = self.capture_status(raw)
        self.assertEqual(states[0]['raw'], raw)
        self.assertEqual(states[0]['cart'], [198.67, 0, 230.72, 0, 0, 0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
