"""Policy bridge checks with emulated serial and a local HTTP server, never hardware."""
from collections import deque
import base64
from http.server import ThreadingHTTPServer
import importlib.util
import threading
import time
from types import SimpleNamespace
import unittest

from robot.policy_bridge import (CommandLimits, D405Camera, PolicyBridge, RobotIO,
                                 cartesian_status, lock_camera_options, make_handler)
from server.policy_client import PolicyClient


class FakeSerial:
    def __init__(self, *, acknowledge=True, settle=True):
        self.writes, self.queue = [], deque()
        self.cart = [200., 0., 150., 0., 0., 0.]
        self.acknowledge, self.settle = acknowledge, settle

    def reset_input_buffer(self):
        self.queue.clear()

    def write(self, raw):
        command = raw.decode().strip()
        self.writes.append(command)
        if command == "?":
            self.queue.append(("<Idle,Angle(ABCDXYZ):1,2,3,4,5,6,7,Cartesian coordinate(XYZ RxRyRz):"+
                               ",".join(map(str, self.cart))+",Pump PWM:40>\n").encode())
        else:
            if command.startswith("G0") and self.settle:
                self.cart = [float(v[1:]) for v in command.split()[1:]]
            if self.acknowledge:
                self.queue.append(b"ok\n")

    def readline(self):
        if self.queue:
            return self.queue.popleft()
        time.sleep(.001)
        return b""

    @property
    def commands(self):
        return [c for c in self.writes if c != "?"]


class TestPolicySerial(unittest.TestCase):
    def test_cartesian_orientation_does_not_use_joint_angles(self):
        status = cartesian_status("<Idle,Angle(ABCDXYZ):1,2,3,4,5,6,7,Cartesian coordinate(XYZ RxRyRz):200,0,150,8,9,10>")
        self.assertEqual(status["cart6"], [200, 0, 150, 8, 9, 10])

    def test_startup_and_status_never_send_motion(self):
        ser = FakeSerial()
        robot = RobotIO(ser)
        self.assertEqual(ser.writes, [])
        self.assertEqual(robot.status()["cart6"], ser.cart)
        self.assertEqual(ser.commands, [])
        with self.assertRaises(PermissionError):
            robot.command("G90", "setup")
        self.assertEqual(ser.commands, [])

    def test_status_discards_buffered_reply_from_previous_poll(self):
        ser = FakeSerial()
        robot = RobotIO(ser)
        stale = b"<Idle,Cartesian coordinate(XYZ RxRyRz):1,2,3,4,5,6>\n"
        ser.queue.append(stale)
        robot.pending = stale
        self.assertEqual(robot.status()["cart6"], ser.cart)
        self.assertEqual(ser.commands, [])

    def test_absolute_mode_ack_and_request_id_deduplication(self):
        ser = FakeSerial()
        robot = RobotIO(ser, execute=True, timeout_s=.5)
        with self.assertRaisesRegex(ValueError, "G90"):
            robot.command("G0 X201 Y0 Z150 A0 B0 C0", "premature")
        self.assertEqual(ser.commands, [])
        robot.command("G90", "setup")
        command = "G0 X201 Y0 Z150 A0 B0 C0"
        result = robot.command(command, "move1")
        self.assertTrue(result["acknowledged"])
        self.assertEqual(result["cart6"][0], 201)
        before = ser.writes.copy()
        self.assertEqual(robot.command(command, "move1"), result)
        self.assertEqual(ser.writes, before)
        with self.assertRaisesRegex(ValueError, "different command"):
            robot.command("G90", "move1")

    def test_invalid_or_out_of_bounds_move_sends_nothing(self):
        limits = CommandLimits()
        current = [270, 0, 100, 20, 0, 0]
        invalid = ["$H", "G91", "G0 Z65", "G90\nG0 X1 Y2 Z3 A0 B0 C0",
                   "G0 X200 Y0 Z65.9 A0 B0 C0",
               "G0 X270 Y0 Z65 A20 B0 C0", "G0 X281 Y0 Z100 A20 B0 C0",
                   "G0 X144 Y0 Z100 A20 B0 C0", "G0 X200 Y176 Z100 A20 B0 C0",
               "G0 X200 Y0 Z276 A20 B0 C0",
                   "G0 X270 Y0 Z100 A31 B0 C0", "G0 X240 Y0 Z100 A20 B0 C0",
                   "G0 X270 Y0 Z100 A-20 B0 C0", "M4 S70", "M4 Snan"]
        for command in invalid:
            with self.subTest(command=command), self.assertRaises(ValueError):
                limits.validate(command, current)

    def test_missing_ack_latches_fault_and_prevents_later_commands(self):
        ser = FakeSerial(acknowledge=False)
        robot = RobotIO(ser, execute=True, timeout_s=.02)
        with self.assertRaises(TimeoutError):
            robot.command("G90", "timeout")
        self.assertTrue(robot.fault)
        before = ser.writes.copy()
        with self.assertRaisesRegex(RuntimeError, "uncertain"):
            robot.command("G90", "after-timeout")
        self.assertEqual(before, ser.writes)

    def test_ack_is_not_enough_when_move_does_not_reach_target(self):
        ser = FakeSerial(settle=False)
        robot = RobotIO(ser, execute=True, timeout_s=.3)
        robot.start_grace_s = .05  # arm never starts moving: refuse once the grace period is over
        robot.command("G90", "setup")
        with self.assertRaisesRegex(RuntimeError, "differs from target"):
            robot.command("G0 X210 Y0 Z150 A0 B0 C0", "missed")
        self.assertTrue(robot.fault)

    def test_gripper_closure_uses_initial_setting_and_calibrated_endpoints(self):
        robot = RobotIO(FakeSerial(), execute=True, initial_s=50, gripper_seconds=.01)
        self.assertEqual(robot.closure(), .5)
        result = robot.command("M4 S60", "close")
        self.assertAlmostEqual(result["closure"], 1)
        self.assertEqual(result["gripper_s"], 60)


class TestPolicyCamera(unittest.TestCase):
    def test_camera_frame_age_and_state_skew_are_checked(self):
        camera = D405Camera.__new__(D405Camera)
        camera.condition, camera.error = threading.Condition(), ""
        camera.metadata = {"serial": "test"}
        now = time.monotonic()
        camera.frames = deque([{"frame_monotonic_s": now-1, "png": b"png"}])
        with self.assertRaisesRegex(RuntimeError, "stale"):
            camera.snapshot(now, max_age_s=.5)
        camera.frames = deque([{"frame_monotonic_s": now, "png": b"png"}])
        with self.assertRaisesRegex(RuntimeError, "unsynchronized"):
            camera.snapshot(now-.5)
        self.assertEqual(camera.snapshot(now)["image_rgb_png_base64"], base64.b64encode(b"png").decode())

    def test_camera_options_are_set_and_read_back(self):
        names = ["enable_auto_exposure", "exposure", "enable_auto_white_balance", "white_balance",
                 "gain", "gamma", "saturation", "brightness", "contrast", "hue", "sharpness"]
        options = SimpleNamespace(**{name: name for name in names})
        settings = {name: 10 for name in names}
        sensor = SimpleNamespace(supports=lambda name: True, get_option=lambda name: settings[name],
                                 set_option=lambda name, value: settings.__setitem__(name, value))
        expected = {"exposure": 33000, "white_balance": 5200, "gain": 16}
        locked = lock_camera_options([sensor], SimpleNamespace(option=options), {"camera_options": expected})
        self.assertEqual({key: locked[key] for key in expected}, expected)
        self.assertEqual(settings["enable_auto_exposure"], 0)
        self.assertEqual(settings["enable_auto_white_balance"], 0)
        broken = SimpleNamespace(supports=lambda name: False)
        with self.assertRaisesRegex(ValueError, "Cannot reproduce"):
            lock_camera_options([broken], SimpleNamespace(option=options), {"camera_options": expected})


@unittest.skipUnless(importlib.util.find_spec("cv2") and importlib.util.find_spec("numpy"), "OpenCV/numpy required for PNG round trip")
class TestPolicyHTTP(unittest.TestCase):
    def test_lossless_rgb_and_acknowledged_command_round_trip(self):
        import cv2
        import numpy as np

        rgb = np.array([[[250, 15, 5], [10, 240, 20]], [[1, 2, 230], [6, 7, 8]]], dtype=np.uint8)
        _, png = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))

        class Camera:
            error = ""
            metadata = {"width": 2, "height": 2, "fps": 30, "encoding": "png", "color_order": "RGB", "preprocessing": "none"}

            def snapshot(self, timestamp, *args):
                return {"image_rgb_png_base64": base64.b64encode(png).decode(), "camera": self.metadata,
                        "frame_age_s": .001, "frame_state_skew_s": -.001}

        ser = FakeSerial()
        robot = RobotIO(ser, execute=True)
        bridge = PolicyBridge(robot, Camera())
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(bridge, token="test-token"))
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        thread.start()
        try:
            client = PolicyClient(f"http://127.0.0.1:{server.server_port}", token="test-token")
            self.assertTrue(client.health()["execute_enabled"])
            obs = client.observation()
            np.testing.assert_array_equal(obs["rgb"], rgb)
            self.assertEqual(obs["cart6"], ser.cart)
            self.assertEqual(obs["closure"], 0)
            result = client.command("G90", request_id="one")
            self.assertTrue(result["acknowledged"])
            client.command("G90", request_id="one")
            self.assertEqual(ser.commands, ["G90"])
            with self.assertRaisesRegex(RuntimeError, "Authentication"):
                PolicyClient(client.base_url, token="wrong").health()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
