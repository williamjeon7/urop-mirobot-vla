"""Follow translation must preserve virtual controller targets and lag."""
from __future__ import annotations

import unittest

from common.rotation import IDENTITY, quat_wxyz_to_xyzw
from server.follow_translator import FollowTranslator


class Frame:
    settings = {"scale": 1.0}

    def to_libero(self, cart):
        return tuple(v / 1000.0 for v in cart[:3]), IDENTITY

    def to_mirobot(self, pos, q):
        return tuple(v * 1000.0 for v in pos), (0.0, 0.0, 0.0)


class LaggingPanda:
    """Each accepted step reaches half of the commanded translation."""
    def __init__(self, reset_pos=(0.0, 0.0, 0.0), gain=0.5):
        self.reset_pos = reset_pos
        self.gain = gain
        self.calls = []
        self.closed = False

    def _obs(self):
        return {"robot0_eef_pos": self.pos,
                "robot0_eef_quat": quat_wxyz_to_xyzw(IDENTITY)}

    def reset(self):
        self.pos = self.reset_pos
        return self._obs()

    def step(self, action):
        self.calls.append(tuple(action))
        self.pos = tuple(p + a * 0.05 * self.gain
                         for p, a in zip(self.pos, action[:3]))
        return self._obs(), 0.0, False, {}

    def close(self):
        self.closed = True


REFERENCE = {"start_eef_pos": (0.0, 0.0, 0.0),
             "start_eef_quat_xyzw": quat_wxyz_to_xyzw(IDENTITY)}


class FollowTranslatorTest(unittest.TestCase):
    def make_translator(self, **kwargs):
        env = LaggingPanda(**kwargs)
        translator = FollowTranslator(Frame(), REFERENCE, env_factory=lambda: env)
        self.addCleanup(translator.close)
        return translator, env

    def test_target_precedes_simulator_lag_and_preview_is_pure(self):
        translator, env = self.make_translator()
        translator.initialize((0.0,) * 6)
        action = (0.4, 0, 0, 0, 0, 0, 1)
        target = translator.target(action)
        self.assertAlmostEqual(target.cart6[0], 20.0)
        self.assertEqual(target.virtual_cart6, (0.0,) * 6)
        self.assertEqual(target.gripper_s, 60.0)
        self.assertEqual(env.calls, [])
        translator.advance(action)
        # Sending the reached pose would send 10 mm, although the label means 20.
        self.assertAlmostEqual(translator.target((0.0,) * 7).cart6[0], 10.0)
        # The next action starts from the lagging virtual state, not last target.
        self.assertAlmostEqual(translator.target(action).cart6[0], 30.0)
        self.assertAlmostEqual(translator.gap(target.cart6)["position_mm"], 10.0)

    def test_warmup_uses_label_tolerance_and_keeps_virtual_residual(self):
        translator, env = self.make_translator()
        result = translator.initialize((20.0, 0.0, 0.0, 0.0, 0.0, 0.0))
        self.assertEqual(result["warmup_steps"], 4)
        self.assertAlmostEqual(result["position_mm"], 1.25)
        self.assertAlmostEqual(translator.target((0.0,) * 7).cart6[0], 18.75)
        self.assertEqual(translator.steps, 0)
        self.assertEqual(len(env.calls), 4)

    def test_nonconverging_warmup_closes_environment(self):
        translator, env = self.make_translator(gain=0.0)
        with self.assertRaisesRegex(ValueError, "warmup failed"):
            translator.initialize((20.0, 0.0, 0.0, 0.0, 0.0, 0.0), max_warmup_steps=2)
        self.assertTrue(env.closed)
        with self.assertRaisesRegex(RuntimeError, "Initialize"):
            translator.target((0.0,) * 7)

    def test_reset_mismatch_is_not_silently_rebased(self):
        translator, env = self.make_translator(reset_pos=(0.01, 0.0, 0.0))
        with self.assertRaisesRegex(ValueError, "recorded mapping reference"):
            translator.initialize((10.0, 0, 0, 0, 0, 0))
        self.assertTrue(env.closed)

    def test_invalid_actions_do_not_step_simulator(self):
        translator, env = self.make_translator()
        translator.initialize((0.0,) * 6)
        for action in [(0.0,) * 6, (float("nan"),) * 7, (1.1,) * 7]:
            with self.assertRaises(ValueError):
                translator.target(action)
            with self.assertRaises(ValueError):
                translator.advance(action)
        self.assertEqual(env.calls, [])

    def test_gripper_overshoot_is_saturated_without_relaxing_spatial_limits(self):
        translator, env = self.make_translator()
        translator.initialize((0.0,) * 6)
        action = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -1.0033)
        self.assertEqual(translator.target(action).gripper_s, 40.0)
        translator.advance(action)
        self.assertEqual(env.calls[-1][-1], -1.0)

    def test_initialization_required_for_advance(self):
        translator, _ = self.make_translator()
        with self.assertRaises(RuntimeError):
            translator.advance((0.0,) * 7)


if __name__ == "__main__":
    unittest.main()
