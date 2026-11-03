"""Hardware-free checks for teleop recording termination."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from .teleop import TeleopSession


class AutoStopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.session = TeleopSession(self.out, time.perf_counter_ns(), threading.Event(), 40)
        self.addCleanup(self.session.log.close)
        self.session.start_capture()
        self.session.last_motion = (100, 0, 70, 0, 0, 0)

    def test_close_then_up_starts_three_second_tail(self):
        s = self.session
        s.observe_command('G0 X100 Y0 Z80 A0 B0 C0')
        self.assertIsNone(s.lift_command_time)
        s.observe_command('M4 S60')
        s.observe_command('G0 X105 Y0 Z70 A0 B0 C0')
        self.assertIsNone(s.lift_command_time)
        s.observe_command('G0 X100 Y0 Z75 A0 B0 C0')
        start = s.lift_command_time
        s.observe_command('G0 X100 Y0 Z80 A0 B0 C0')
        self.assertEqual(start, s.lift_command_time)
        s.check_auto_end(start+2.99)
        self.assertFalse(s.ended)
        s.check_auto_end(start+3)
        self.assertTrue(s.ended)
        result = json.loads((self.out/'capture_result.json').read_text())
        self.assertEqual(result['termination_status'], 'normal')
        self.assertIsNone(result['pickup_success'])
        s.record_pickup_result(True, True)
        self.assertTrue(json.loads((self.out/'capture_result.json').read_text())['pickup_success'])

    def test_missing_lift_times_out(self):
        s = self.session
        s.observe_command('M4 S60')
        s.check_auto_end(s.close_time+15)
        self.assertEqual(s.termination_status, 'timeout')

    def test_failure_and_abnormal_are_separate(self):
        self.session.record_pickup_result(True, False)
        self.assertEqual(self.session.termination_status, 'task_failed')
        self.session.end_capture('abnormal')
        self.assertEqual(self.session.termination_status, 'task_failed')

    def test_episode_without_close_times_out(self):
        self.session.check_auto_end(self.session.take_started+120)
        self.assertEqual(self.session.termination_status, 'timeout')


if __name__ == '__main__':
    unittest.main()
