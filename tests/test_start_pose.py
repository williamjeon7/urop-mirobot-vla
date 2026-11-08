import math
import unittest
from types import SimpleNamespace

from server import start_pose as sp


class FakeBridge:
    """Accepts only what every bridge accepts: <=25 mm / 20 deg absolute moves after G90."""
    def __init__(self, cart6, state="Idle"):
        self.cart6, self.state, self.commands, self.absolute = list(cart6), state, [], False

    def observation(self):
        return dict(state=self.state, cart6=list(self.cart6))

    def command(self, text):
        self.commands.append(text)
        if text == "G90":
            self.absolute = True
        elif text.startswith("G0 "):
            assert self.absolute
            target = [float(part[1:]) for part in text.split()[1:]]
            assert math.dist(target[:3], self.cart6[:3]) <= 25.0
            assert max(abs((a - b + 180) % 360 - 180) for a, b in zip(target[3:], self.cart6[3:])) <= 20.0
            self.cart6 = target
        return dict(ok=True, cart6=list(self.cart6), state="Idle")


class StartPoseTest(unittest.TestCase):
    def test_far_pose_reaches_start_in_small_moves_without_homing(self):
        bridge = FakeBridge([230.0, -60.0, 120.0, 5.0, -3.0, 2.0])
        events = sp.prepare_without_homing(bridge, log=lambda _: None, sleep=lambda _: None)
        self.assertNotIn("$H", bridge.commands)
        self.assertLess(bridge.commands.index("M4 S40"), next(i for i, c in enumerate(bridge.commands) if c.startswith("G0")))
        self.assertLess(math.dist(bridge.cart6[:3], sp.INITIAL_POSE[:3]), 0.01)
        self.assertEqual(events[-1]["kind"], "initial_pose_ready")

    def test_locked_robot_is_not_moved(self):
        bridge = FakeBridge(sp.INITIAL_POSE, state="Locked")
        with self.assertRaisesRegex(RuntimeError, "2-3"):
            sp.prepare_without_homing(bridge, log=lambda _: None, sleep=lambda _: None)
        self.assertEqual(bridge.commands, [])


class LegacyRecordingNameTest(unittest.TestCase):
    def test_used_windows_names_are_skipped(self):
        from server import run_policy

        class Client:
            def start_recording(self, name):
                if name in ("I1", "I2"):
                    raise RuntimeError(f"Bridge /recording/start: [Errno 17] File exists: '{name}.mp4'")
                return dict(path=f"{name}/{name}.mp4", frames=0)

        log = SimpleNamespace(rows=[], write=lambda kind, **v: log.rows.append(kind))
        summary = {}
        run_policy.start_recording(SimpleNamespace(recording_name="I1"), Client(), summary, log)
        self.assertEqual(summary["recording_name"], "I3")
        self.assertEqual(log.rows.count("recording_name_taken"), 2)



class ReturnTest(unittest.TestCase):
    def test_lifts_first_then_returns_without_touching_gripper(self):
        bridge = FakeBridge([190.0, -80.0, 66.0, 0.0, 0.0, 0.0])
        bridge.absolute = True  # the run already sent G90
        sp.return_to_initial(bridge, log=lambda _: None)
        moves = [[float(p[1:]) for p in c.split()[1:]] for c in bridge.commands]
        self.assertTrue(all(c.startswith("G0 ") for c in bridge.commands))  # no M4: gripper unchanged
        low = [m for m in moves if m[2] < sp.INITIAL_POSE[2] - 0.01]
        self.assertTrue(all(abs(m[0] - 190.0) < 1e-6 and abs(m[1] + 80.0) < 1e-6 for m in low))  # straight up
        self.assertLess(math.dist(bridge.cart6[:3], sp.INITIAL_POSE[:3]), 0.01)

    def test_not_idle_is_not_moved(self):
        bridge = FakeBridge([190.0, -80.0, 66.0, 0.0, 0.0, 0.0], state="Alarm")
        with self.assertRaises(RuntimeError):
            sp.return_to_initial(bridge, log=lambda _: None)
        self.assertEqual(bridge.commands, [])



class LegacyBridgeTest(unittest.TestCase):
    def test_old_bridge_gets_moves_under_2mm(self):
        bridge = FakeBridge([201.67, -26.983, 211.744, -0.385, -0.317, -0.267])  # I2blue step 35
        bridge.absolute = True
        bridge.health = lambda: {"ok": True}  # no move_settle_check: installed before 11/08
        goal = (201.695, -27.189, 208.768, -0.349, -0.245, -0.351)  # the 2.98 mm move that faulted
        sp.move(bridge, bridge.cart6, goal, sp.segment_mm(bridge), sleep=lambda _: None)
        moves = [[float(p[1:]) for p in c.split()[1:]] for c in bridge.commands]
        self.assertEqual(len(moves), 2)
        previous = [201.67, -26.983, 211.744]
        for m in moves:
            self.assertLess(math.dist(m[:3], previous), 2.0)
            previous = m[:3]
        self.assertLess(math.dist(bridge.cart6[:3], goal[:3]), 1e-6)

    def test_fixed_bridge_is_not_split(self):
        bridge = FakeBridge([200, 0, 200, 0, 0, 0])
        bridge.health = lambda: {"move_settle_check": "after_motion"}
        self.assertEqual(sp.segment_mm(bridge), sp.MAX_SEGMENT_MM)


if __name__ == "__main__":
    unittest.main()
