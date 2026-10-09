"""Panda replay comparison: absolute pose, quaternion sign, and reference coverage."""

import argparse
import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tools.action_to_poses import (
    add_arguments, compare_replay, first_goal_step, orientation_error_deg,
    position_error_mm, read_actions, register_objects, report_replay, simulate,
)


class ReplayComparisonTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "source.jsonl"
        self.meta = {"start_eef_pos": [0, 0, 1], "start_eef_quat_xyzw": [0, 0, 0, 1]}

    def write(self, rows, meta=None):
        self.path.write_text("\n".join(json.dumps(row) for row in
                             [{"meta": self.meta if meta is None else meta}] + rows
                             + [{"result": {"success": True}}]) + "\n", encoding="utf-8")

    def row(self, step, x=0.0, quaternion=None, **extra):
        return {"step": step, "action": [0.0] * 6 + [-1.0], "eef_pos": [x, 0, 1],
                "eef_quat_xyzw": quaternion or [0, 0, 0, 1], **extra}

    def test_constant_world_offset_is_not_hidden_by_equal_displacements(self):
        self.write([self.row(1, 0.01), self.row(2, 0.02)])
        replay = [self.row(1, 0.02), self.row(2, 0.03)]
        shifted_start = {**self.meta, "start_eef_pos": [0.01, 0, 1]}
        result = compare_replay(self.path, shifted_start, replay)
        self.assertAlmostEqual(result["max_position_mm"], 10.0)
        self.assertAlmostEqual(result["mean_position_mm"], 10.0)
        self.assertAlmostEqual(result["last_position_mm"], 10.0)
        self.assertAlmostEqual(result["start_position_mm"], 10.0)

    def test_quaternion_sign_and_scale_are_not_orientation_errors(self):
        q = [1, 2, 3, 4]
        self.assertEqual(orientation_error_deg(q, [-2 * v for v in q]), 0.0)

    def test_orientation_reports_shortest_known_rotation(self):
        half = math.radians(270) / 2
        self.assertAlmostEqual(orientation_error_deg([0, 0, 0, 1],
                               [0, 0, math.sin(half), math.cos(half)]), 90.0)

    def test_tiny_rotation_is_not_rounded_away_by_acos(self):
        half = math.radians(0.00000001) / 2
        self.assertAlmostEqual(orientation_error_deg([0, 0, 0, 1],
                               [math.sin(half), 0, 0, math.cos(half)]), 0.00000001, places=15)

    def test_partial_replay_compares_prefix_and_goal_within_prefix(self):
        self.write([self.row(1, goal=False), self.row(2, goal=True)])
        result = compare_replay(self.path, self.meta, [self.row(1, done=False)])
        self.assertEqual(result["source_actions"], 2)
        self.assertEqual(result["position_compared"], 1)
        self.assertEqual(first_goal_step(self.path, 1), None)
        self.assertEqual(first_goal_step(self.path), 2)
        self.assertEqual(result["goal_mismatch_steps"], [])

    def test_goal_disagreement_after_same_first_success_is_detected(self):
        self.write([self.row(1, goal=True), self.row(2, goal=True)])
        result = compare_replay(self.path, self.meta,
                                [self.row(1, done=True), self.row(2, done=False)])
        self.assertEqual(result["goal_mismatch_steps"], [2])

    def test_action_only_and_missing_last_pose_do_not_claim_zero_error(self):
        action = {"step": 2, "action": [0.0] * 7}
        self.write([self.row(1), action], meta={})
        result = compare_replay(self.path, self.meta, [self.row(1), self.row(2)])
        self.assertEqual(result["position_compared"], 1)
        self.assertEqual(result["orientation_compared"], 1)
        self.assertIsNone(result["last_position_mm"])
        self.assertIsNone(result["start_position_mm"])
        self.write([action], meta={})
        result = compare_replay(self.path, self.meta, [self.row(1)])
        self.assertIsNone(result["max_position_mm"])
        self.assertIsNone(result["max_orientation_deg"])

    def test_action_order_alignment_ignores_step_labels_and_result_lines(self):
        self.write([self.row(0, 0.01, done=False), {"result": {}}, self.row(10, 0.02, done=True)])
        _, actions = read_actions(self.path)
        self.assertEqual(len(actions), 2)
        result = compare_replay(self.path, self.meta, [self.row(1, 0.01), self.row(2, 0.021)])
        self.assertAlmostEqual(result["max_position_mm"], 1.0)
        self.assertEqual(result["max_position_step"], 2)
        self.assertEqual(first_goal_step(self.path), 2)

    def test_non_jsonl_reference_is_unavailable(self):
        self.assertIsNone(compare_replay(self.path.with_suffix(".hdf5"), self.meta, []))

    def test_null_goal_is_missing_and_can_fall_back_to_done(self):
        self.write([self.row(1, goal=None), self.row(2, goal=None, done=True)])
        result = compare_replay(self.path, self.meta,
                                [self.row(1, done=False), self.row(2, done=True)])
        self.assertEqual(result["goal_compared"], 1)
        self.assertEqual(result["goal_mismatch_steps"], [])
        self.assertEqual(first_goal_step(self.path), 2)

    def test_standard_scene_with_reference_goals_uses_the_reference(self):
        self.write([self.row(1, done=False)])
        result = compare_replay(self.path, self.meta, [self.row(1, done=True)])
        meta = {"custom_scene": False, "first_done": 1, "expected_done": None,
                "replay_comparison": result}
        output = io.StringIO()
        with redirect_stdout(output):
            report_replay(meta, 1)
        self.assertNotIn("eval 과 같은 결과", output.getvalue())
        self.assertIn("불일치 1개", output.getvalue())

    def test_invalid_pose_is_rejected_instead_of_producing_nan(self):
        for a, b in (([0, 0], [0, 0, 0]), ([0, math.nan, 0], [0, 0, 0])):
            with self.assertRaises(ValueError):
                position_error_mm(a, b)
        for q in ([0, 0, 0, 0], [0, 0, math.inf, 1], [0, 0, 1]):
            with self.assertRaises(ValueError):
                orientation_error_deg(q, [0, 0, 0, 1])

    def test_report_does_not_claim_goal_match_without_goal_reference(self):
        self.write([self.row(1)], meta={})
        result = compare_replay(self.path, self.meta, [self.row(1, done=False)])
        meta = {"custom_scene": True, "first_done": None, "expected_done": None,
                "replay_comparison": result}
        output = io.StringIO()
        with redirect_stdout(output):
            report_replay(meta, 1)
        self.assertIn("원래 Goal 기록 없음", output.getvalue())

    def test_cli_parser_loads_without_simulation_dependencies(self):
        parser = argparse.ArgumentParser()
        add_arguments(parser)
        args = parser.parse_args(["--log", str(self.path), "--max-steps", "1"])
        self.assertEqual(args.max_steps, 1)

    def test_scenario_is_rejected_before_loading_an_incorrect_scene(self):
        self.write([self.row(1)], meta={"scenario": "sandwich"})
        parser = argparse.ArgumentParser()
        add_arguments(parser)
        with self.assertRaisesRegex(SystemExit, "초기 이웃 배치 복원"):
            simulate(parser.parse_args(["--log", str(self.path)]))

    def test_registered_block_size_comes_from_record_not_current_default(self):
        output = Path(self.directory.name) / "size.txt"
        module = Path(self.directory.name) / "objects.py"
        module.write_text("from pathlib import Path\n"
                          "def register_blocks(edge_length_m=0.06):\n"
                          f"    Path({str(output)!r}).write_text(str(edge_length_m))\n", encoding="utf-8")
        register_objects(str(module) + ":register_blocks", 40.0)
        self.assertEqual(float(output.read_text()), 0.04)

    def test_absolute_registration_path_without_function_uses_register(self):
        output = Path(self.directory.name) / "registered.txt"
        module = Path(self.directory.name) / "objects.py"
        module.write_text("from pathlib import Path\n"
                          "def register():\n"
                          f"    Path({str(output)!r}).write_text('registered')\n", encoding="utf-8")
        register_objects(str(module))
        self.assertEqual(output.read_text(), "registered")
        register_objects(str(module) + ":")
        self.assertEqual(output.read_text(), "registered")


if __name__ == "__main__":
    unittest.main()
