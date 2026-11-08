import unittest
from unittest.mock import Mock, patch

from robot import policy_setup
from common.gcode import HOME_SEQUENCE

IDLE = "<Idle,Cartesian coordinate(XYZ RxRyRz):198.67,0,230.72,0,0,0>"


def probe(status=IDLE):
    p = Mock()
    p.send.return_value = ([(0, "ok")], .01)
    p.wait_settled.return_value = (status, .2)
    return p


class PrepareTest(unittest.TestCase):
    def test_pickup_preparation_skips_homing_and_opens_gripper_first(self):
        p = probe()
        with patch.object(policy_setup.time, "sleep"):
            policy_setup.prepare_with_probe(p, home=False)
        commands = [c.args[0] for c in p.send.call_args_list]
        self.assertNotIn("$H", commands)
        self.assertFalse((set(HOME_SEQUENCE) - {"M20", "G90"}) & set(commands))  # no $22=1, $H
        g0 = next(i for i, c in enumerate(commands) if c.startswith("G0 "))
        self.assertLess(commands.index("M4 S40"), g0)
        self.assertEqual(p.wait_settled.call_count, 2)  # idle check before moving, arrival check

    def test_locked_robot_is_not_moved_without_homing(self):
        p = probe("<Locked,Cartesian coordinate(XYZ RxRyRz):0,0,0,0,0,0>")
        with self.assertRaisesRegex(RuntimeError, "2-3"):
            policy_setup.prepare_with_probe(p, home=False)
        p.send.assert_not_called()

    def test_explicit_homing_still_homes(self):
        p = probe()
        with patch.object(policy_setup.time, "sleep"):
            policy_setup.prepare_with_probe(p)
        self.assertEqual([c.args[0] for c in p.send.call_args_list][:4], list(HOME_SEQUENCE))


if __name__ == "__main__":
    unittest.main()
