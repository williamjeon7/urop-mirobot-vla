"""Serial-mocked check of the stand-alone homing command."""
import io
import queue
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from .home_robot import INITIAL_POSE, main

STATUS = (b'<Idle,Angle(ABCDXYZ):0.000,0.000,0.000,0.000,0.000,0.000,0.000,'
          b'Cartesian coordinate(XYZ RxRyRz):198.670,0.000,230.720,0.000,0.000,0.000,'
          b'Pump PWM:0,Valve PWM:0,Motion_MODE:0>\r\n')


class FakeSerial:
    instances = []

    def __init__(self, *args, reply=b'ok\r\n', **kwargs):
        self.lines, self.writes, self.is_open = queue.Queue(), [], True
        self.reply = reply
        FakeSerial.instances.append(self)

    def write(self, value):
        self.writes.append(value)
        self.lines.put(STATUS if value == b'?\n' else self.reply)

    def readline(self):
        try:
            return self.lines.get(timeout=.005)
        except queue.Empty:
            return b''

    def reset_input_buffer(self):
        pass

    def close(self):
        self.is_open = False


class HomeRobotTests(unittest.TestCase):
    def run_main(self, serial_class):
        FakeSerial.instances.clear()
        with tempfile.TemporaryDirectory() as logs, patch('tempfile.gettempdir', return_value=logs), \
                patch('serial.Serial', serial_class), patch('time.sleep'), redirect_stdout(io.StringIO()):
            main(['--port', 'FAKE'])  # logs go to the temporary folder, not the real temp dir
        return FakeSerial.instances[-1]

    def test_homes_then_parks_at_initial_pose_and_closes_port(self):
        ser = self.run_main(FakeSerial)
        sent = [w.decode().strip() for w in ser.writes if w != b'?\n']
        self.assertEqual(sent, ['$22=1', '$H', 'M20', 'G90', INITIAL_POSE])
        self.assertFalse(ser.is_open)

    def test_error_reply_stops_before_further_motion(self):
        failing = lambda *a, **k: FakeSerial(*a, reply=b'error: Alarm lock\r\n', **k)
        with self.assertRaises(SystemExit):
            self.run_main(failing)
        sent = [w.decode().strip() for w in FakeSerial.instances[-1].writes if w != b'?\n']
        self.assertEqual(sent, ['$22=1'])
        self.assertFalse(FakeSerial.instances[-1].is_open)


if __name__ == '__main__':
    unittest.main()
