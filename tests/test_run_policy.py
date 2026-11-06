"""Hardware-free rollout checks using real follow semantics and fake I/O."""
from __future__ import annotations

from argparse import Namespace
from contextlib import ExitStack, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from common.rotation import IDENTITY, quat_wxyz_to_xyzw
from server.follow_translator import FollowTranslator
from server import run_policy


PROFILE = {"camera_serial": "D405-test", "width": 640, "height": 480,
           "fps": 30, "camera_options": {"Exposure": 33000.0}}


class FakeFrame:
    settings = {"scale": 1.0}

    @classmethod
    def from_files(cls, *_):
        return cls()

    def to_libero(self, cart):
        return tuple(v / 1000 for v in cart[:3]), IDENTITY

    def to_mirobot(self, pos, _):
        return tuple(v * 1000 for v in pos), (0.0, 0.0, 0.0)

    def proprio(self, cart, closure):
        return [closure, -closure, *(v / 1000 for v in cart[:3]),
                *quat_wxyz_to_xyzw(IDENTITY)]


class LaggingPanda:
    def reset(self):
        self.pos = (0.2, 0.0, 0.1)
        return self.observation()

    def observation(self):
        return {"robot0_eef_pos": self.pos,
                "robot0_eef_quat": quat_wxyz_to_xyzw(IDENTITY)}

    def step(self, action):
        self.pos = tuple(p + a * 0.025 for p, a in zip(self.pos, action[:3]))
        return self.observation(), 0, False, {}

    def close(self):
        pass


class ActionChunk(list):
    shape = (16, 7)

    def tolist(self):
        return list(self)


class FakeBridge:
    def __init__(self):
        self.cart = [200.0, 0.0, 100.0, 0.0, 0.0, 0.0]
        self.calls = []
        self.observations = 0
        self.execute_enabled = True
        self.state = "Idle"
        self.arrive = True
        self.camera = dict(serial=PROFILE["camera_serial"], width=640, height=480,
                           fps=30, locked_camera_options=PROFILE["camera_options"],
                           encoding="png", color_order="RGB", preprocessing="none")

    def observation(self):
        self.observations += 1
        return dict(cart6=self.cart.copy(), closure=0.0, state=self.state,
                    gripper_s=40.0, rgb="unprocessed_rgb", camera=dict(self.camera),
                    execute_enabled=self.execute_enabled)

    def command(self, command):
        self.calls.append(command)
        if command.startswith("G0 ") and self.arrive:
            self.cart = [float(token[1:]) for token in command.split()[1:]]
        return {"acknowledged": True, "command": command}


class FakePolicy:
    load_report = {"loaded_keys": 123}
    last_inference_seconds = 0.1

    def __init__(self, bridge, action=None, during_predict=None):
        self.bridge = bridge
        self.action = action or (0.02, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0)
        self.during_predict = during_predict
        self.states = []

    def predict(self, image, state, instruction):
        self.states.append(list(state))
        if self.during_predict:
            self.during_predict()
        return ActionChunk([list(self.action) for _ in range(16)])


class RunPolicyTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bridge = FakeBridge()
        self.policy = FakePolicy(self.bridge)

    def args(self, **changes):
        values = dict(color="red", reference=self.root / "reference",
            checkpoint=self.root / "checkpoint", data_dir=self.root / "data",
            denoising_steps=5, offline_smoke=False, bridge_check=False,
            bridge_url="http://test:8891", timeout=15.0, rotate=0,
            log_dir=self.root / "logs", execute=False, max_steps=2,
            max_drift_mm=12.0, max_step_deg=5.0, open_loop_steps=1,
            max_state_change_mm=2.0, arrival_tolerance_mm=2.0,
            arrival_tolerance_deg=1.0, step_interval=0.0, z_floor=66.0,
            max_radius=280.0, max_angle=30.0, max_step_mm=10.0,
            sample_index=0)
        values.update(changes)
        return Namespace(**values)

    def run_with_fakes(self, args):
        reference = dict(start_eef_pos=(0.2, 0.0, 0.1),
                         start_eef_quat_xyzw=quat_wxyz_to_xyzw(IDENTITY))
        fake_observation_module = SimpleNamespace(MirobotFrame=FakeFrame,
            wrist_from_rgb=lambda rgb, profile, rotate: "calibrated_wrist")
        fake_color_module = SimpleNamespace(load_profile=lambda _: dict(PROFILE))
        factory = lambda frame: FollowTranslator(frame, reference,
                                                 env_factory=LaggingPanda)
        with ExitStack() as stack:
            stack.enter_context(patch.dict("sys.modules", {
                "tools.policy_obs": fake_observation_module,
                "docs.W9.d405.color_calibration": fake_color_module}))
            stack.enter_context(patch("server.follow_translator.FollowTranslator", factory))
            self.client_constructor = stack.enter_context(patch("server.policy_client.PolicyClient", return_value=self.bridge))
            self.policy_constructor = stack.enter_context(patch.object(run_policy, "CosmosPolicy", return_value=self.policy))
            stack.enter_context(patch.object(run_policy.RunLog, "image", return_value="observation.png"))
            stack.enter_context(redirect_stdout(io.StringIO()))
            run_policy.run(args)

    def summary(self):
        return json.loads((self.root / "logs/summary.json").read_text())

    def test_preview_never_sends_hardware_commands(self):
        self.run_with_fakes(self.args())
        self.assertEqual(self.bridge.calls, [])
        self.assertEqual(self.summary()["mode"], "preview")
        self.assertEqual(self.summary()["steps"], 2)
        self.assertEqual(len(self.policy.states), 1)

    def test_execute_reobserves_real_state_and_preserves_virtual_lag(self):
        self.run_with_fakes(self.args(execute=True))
        moves = [c for c in self.bridge.calls if c.startswith("G0 ")]
        self.assertEqual(len(moves), 2)
        self.assertTrue(moves[0].startswith("G0 X201.000 "))
        # The virtual robot reaches 200.5 after action 1, so target 2 is 201.5.
        self.assertTrue(moves[1].startswith("G0 X201.500 "))
        self.assertEqual([s[2] for s in self.policy.states], [0.2, 0.201])
        self.assertEqual(self.bridge.calls[:2], ["G90", "M20"])
        self.assertEqual(self.summary()["queries"], 2)
        self.assertEqual(self.summary()["status"], "completed")

    def test_motion_during_inference_rejects_action_without_cartesian_command(self):
        self.policy.during_predict = lambda: self.bridge.cart.__setitem__(0, 205.0)
        with self.assertRaisesRegex(RuntimeError, "changed position"):
            self.run_with_fakes(self.args(execute=True))
        self.assertFalse(any(c.startswith("G0 ") for c in self.bridge.calls))
        self.assertEqual(self.summary()["status"], "failed")
        self.assertEqual(self.summary()["steps"], 0)

    def test_target_outside_floor_is_rejected_before_cartesian_command(self):
        self.policy.action = (0.0, 0.0, -1.0, 0.0, 0.0, 0.0, -1.0)
        with self.assertRaisesRegex(ValueError, "below floor"):
            self.run_with_fakes(self.args(execute=True))
        self.assertFalse(any(c.startswith("G0 ") for c in self.bridge.calls))
        self.assertEqual(self.summary()["steps"], 0)

    def test_bridge_check_does_not_load_model_or_create_rollout(self):
        self.run_with_fakes(self.args(bridge_check=True))
        self.assertEqual(self.bridge.observations, 1)
        self.assertEqual(self.policy.states, [])
        self.assertEqual(self.bridge.calls, [])
        self.policy_constructor.assert_not_called()
        self.assertFalse((self.root / "logs").exists())

    def test_wrong_camera_profile_is_rejected_before_model_load(self):
        for key, value in (("serial", "different-camera"), ("width", 1280),
                           ("locked_camera_options", {"Exposure": 1000})):
            with self.subTest(key=key):
                original = self.bridge.camera[key]
                self.bridge.camera[key] = value
                with self.assertRaisesRegex(RuntimeError, "training colour profile"):
                    self.run_with_fakes(self.args())
                self.policy_constructor.assert_not_called()
                self.assertEqual(self.bridge.calls, [])
                self.bridge.camera[key] = original

    def test_read_only_bridge_rejected_before_model_load(self):
        self.bridge.execute_enabled = False
        with self.assertRaisesRegex(RuntimeError, "read-only"):
            self.run_with_fakes(self.args(execute=True))
        self.policy_constructor.assert_not_called()
        self.assertEqual(self.bridge.calls, [])

    def test_nonidle_robot_rejected_before_model_load(self):
        self.bridge.state = "Run"
        with self.assertRaisesRegex(RuntimeError, "Idle"):
            self.run_with_fakes(self.args(execute=True))
        self.policy_constructor.assert_not_called()
        self.assertEqual(self.bridge.calls, [])

    def test_unreached_command_stops_before_advancing_virtual_state(self):
        self.bridge.arrive = False
        self.policy.action = (0.1, 0, 0, 0, 0, 0, -1)
        with self.assertRaisesRegex(RuntimeError, "did not reach target"):
            self.run_with_fakes(self.args(execute=True))
        self.assertEqual(self.summary()["steps"], 0)
        self.assertEqual(len([c for c in self.bridge.calls if c.startswith("G0 ")]), 1)

    def test_offline_smoke_never_constructs_hardware_client(self):
        args = self.args(offline_smoke=True)
        episodes = args.data_dir / "mirobot_real"
        episodes.mkdir(parents=True)
        (episodes / "MIROBOT_L01_red_fake.hdf5").touch()
        observation = self.bridge.observation()
        state = FakeFrame().proprio(observation["cart6"], 0.0)
        with patch.object(run_policy, "offline_observation", return_value=(observation, "wrist", state)):
            self.run_with_fakes(args)
        self.client_constructor.assert_not_called()
        self.assertEqual(self.bridge.calls, [])
        self.assertEqual(self.summary()["mode"], "offline_smoke")

    def test_goal_validation_handles_wrapped_angles_and_nonfinite_input(self):
        args = self.args(max_angle=180)
        result = run_policy.validate_goal((200, 0, 100, -179, 0, 0),
                                          (200, 0, 100, 179, 0, 0), args)
        self.assertEqual(result["delta_deg"], 2)
        with self.assertRaisesRegex(ValueError, "finite"):
            run_policy.validate_goal((float("nan"),) * 6, (0,) * 6, args)


if __name__ == "__main__":
    unittest.main()
