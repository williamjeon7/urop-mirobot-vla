import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import numpy as np

from common.failure_metrics import alarm_metrics, auroc, first_alarms
from server import experiment_log as log


class PaperXYInputTest(unittest.TestCase):
    def test_run_without_layout_never_prompts_and_passes_no_file(self):
        with tempfile.TemporaryDirectory() as tmp, unittest.mock.patch("builtins.input", side_effect=AssertionError):
            args = log.capture_trial_layout(tmp, ["--color", "red"], True)
            self.assertEqual(args, ["--color", "red"])
            saved = json.loads((Path(tmp) / "layout.json").read_text())
            self.assertEqual((saved["source"], saved["blocks"]["red"]), ("not_measured", None))

    def test_paper_xy_rejects_mat_values(self):
        self.assertEqual(log.parse_paper_xy("-9, -8"), [-9.0, -8.0])
        for text in ("21 0", "abc", "1 2 3"):
            with self.assertRaises(ValueError):
                log.parse_paper_xy(text)

    def test_minimal_layout_file_gets_paper_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "layout.json"
            path.write_text(json.dumps({"blocks": {"red": [-9, -8], "green": [-9, 0], "blue": [-8, 8]}}))
            document = log.layout_document(path)
            self.assertEqual(document["coordinate_frame"], log.PAPER_FRAME)
            self.assertEqual(document["unit"], "cm")
            path.write_text(json.dumps({"blocks": {"red": [21, -8], "green": [-9, 0], "blue": [-8, 8]}}))
            with self.assertRaisesRegex(ValueError, "red"):
                log.layout_document(path)

    def test_nearest_training_layout_finds_l13(self):
        nearest = log.nearest_training_layout({"red": [-9, -8], "green": [-9, 0], "blue": [-8, 8]})
        self.assertEqual(nearest, {"layout_id": "L13", "max_block_distance_cm": 0.0})


class OnsetTest(unittest.TestCase):
    def test_onset_maps_to_active_query_and_step(self):
        events = [dict(kind="prediction", query=0, rollout_t_s=0.0),
                  dict(kind="target", step=0, rollout_t_s=0.5),
                  dict(kind="prediction", query=1, rollout_t_s=3.0),
                  dict(kind="target", step=16, rollout_t_s=3.5)]
        self.assertEqual(log.onset_indices(events, 3.2), (1, 0))
        self.assertEqual(log.onset_indices(events, 4.0), (1, 16))
        self.assertEqual(log.onset_indices(events, None), (None, None))


class PaperMetricTest(unittest.TestCase):
    def test_hide_and_seek_definitions(self):
        # Two failures (one caught at t=1 of 4, one missed), two successes (one false alarm).
        scores = [[0, 1, 1, 1], [0, 0, 0], [0, 0, 0, 0], [1, 0]]
        alarms = first_alarms(scores, 0.5)
        self.assertEqual(alarms, [1, None, None, 0])
        m = alarm_metrics(alarms, [4, 3, 4, 2], [True, True, False, False])
        self.assertEqual((m["tpr"], m["tnr"], m["bacc"]), (0.5, 0.5, 0.5))
        self.assertAlmostEqual(m["twa"], 0.5 * ((1 - 1 / 4) / 2 + 0.5))
        self.assertAlmostEqual(m["avg_det_time"], (0.25 + 1.0) / 2)
        self.assertEqual(auroc([0.9, 0.1, 0.5], [True, False, False]), 1.0)


class ExportTest(unittest.TestCase):
    def test_labelled_trial_exports_safe_style_arrays(self):
        from tools.export_failure_dataset import export
        with tempfile.TemporaryDirectory() as tmp:
            trial = Path(tmp) / "I1red"
            (trial / "policy").mkdir(parents=True)
            np.savez(trial / "policy/features_0000.npz", action_spatial_tokens=np.ones((1, 14, 14, 8)),
                     action_token_mean_by_step=np.ones((5, 1, 8)))
            (trial / "policy/events.jsonl").write_text(json.dumps(dict(
                kind="prediction", query=0, rollout_t_s=0.0, features="features_0000.npz",
                actions=np.zeros((16, 7)).tolist())) + "\n")
            (trial / "result.json").write_text(json.dumps(dict(runtime_reason="step_limit", failure_detection=dict(
                episode_success=0, task_id="red", task_description="pick up the red block on the table",
                split="test", failure_type="wrong_object"))))
            rows, skipped = export(Path(tmp), Path(tmp) / "out")
            self.assertEqual((len(rows), skipped), (1, {}))
            data = np.load(Path(tmp) / "out/rollouts/I1red.npz")
            self.assertEqual(data["hidden_states"].shape, (1, 8))
            self.assertEqual(data["hidden_states_by_step"].shape, (1, 5, 8))
            self.assertEqual(data["action_vectors"].shape, (1, 112))



class VideoOnsetTest(unittest.TestCase):
    def test_onset_from_video_time_is_shifted_by_recording_start(self):
        events = [dict(kind="prediction", query=0, rollout_t_s=0.0),
                  dict(kind="recording_started", rollout_t_s=1.5),
                  dict(kind="target", step=0, rollout_t_s=1.6),
                  dict(kind="prediction", query=1, rollout_t_s=20.0)]
        self.assertEqual(log.onset_indices(events, 18.0), (0, 0))   # 19.5 s rollout time
        self.assertEqual(log.onset_indices(events, 19.0), (1, 0))   # 20.5 s rollout time



class PlaybackTimeTest(unittest.TestCase):
    def test_fast_mp4_playback_time_maps_to_real_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "I1red"
            run.mkdir()
            # 15 real frames per second encoded at 30 fps: playback runs twice as fast.
            (run / "I1red_frames.jsonl").write_text("".join(
                json.dumps(dict(video_frame=i, t_s=i / 15)) + "\n" for i in range(300)))
            (run / "I1red_video.json").write_text(json.dumps(dict(fps=30)))
            self.assertAlmostEqual(log.playback_to_recording_s(run, 5.0), 10.0)
            self.assertAlmostEqual(log.playback_to_recording_s(run, 999), 299 / 15)
            self.assertEqual(log.playback_to_recording_s(Path(tmp), 5.0), 5.0)  # no frame log



class WrongColourTest(unittest.TestCase):
    def make_run(self, tmp, summary):
        run = Path(tmp) / "I1red"
        (run / "policy").mkdir(parents=True)
        (run / "policy/events.jsonl").write_text("")
        (run / "policy/summary.json").write_text(json.dumps(summary))
        (run / "experiment.json").write_text(json.dumps(dict(arguments=dict(color="red"))))
        return run

    def test_wrong_colour_run_is_recorded_as_automatic_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(tmp, dict(status="wrong_color_pickup", instruction="pick up the red block",
                                          wrong_pickup=dict(color="green")))
            result = log.export_trial(run / "policy")
            ground = json.loads((run / "ground_truth.json").read_text())
            self.assertEqual((ground["task_success"], ground["failure_type"], ground["selected_color"]),
                             (False, "wrong_object", "green"))
            self.assertEqual(result["failure_detection"]["episode_success"], 0)
            self.assertIn("자동 판정: 실패", result["explanation"])

    def test_annotating_other_colour_forces_failure(self):
        from tools.annotate_mirobot_result import annotate
        with tempfile.TemporaryDirectory() as tmp:
            run = self.make_run(tmp, dict(status="completed"))
            with self.assertRaises(ValueError):
                annotate(run, success=True, reason="x", selected_color="blue")
            result = annotate(run, success=None, reason="파랑을 집음", selected_color="blue")
            ground = result["ground_truth"]
            self.assertEqual((ground["task_success"], ground["failure_type"], ground["language_compliance"]),
                             (False, "wrong_object", False))



class AutoSuccessTest(unittest.TestCase):
    def test_confirmed_pickup_is_an_automatic_success_until_a_human_labels_it(self):
        from tools.annotate_mirobot_result import annotate
        with tempfile.TemporaryDirectory() as tmp:
            run = WrongColourTest().make_run(tmp, dict(status="pickup_confirmed", pickup=dict(
                color="red", lifted_mm=22.4, stable_observations=3)))
            result = log.export_trial(run / "policy")
            self.assertEqual((result["ground_truth"]["task_success"], result["ground_truth"]["annotator"]),
                             (True, "auto_visual_detector"))
            self.assertIn("성공 (자동 판정", (run / "result.md").read_text())
            result = annotate(run, success=False, reason="Claude 영상 검토: 떨어뜨림", failure_type="drop",
                              annotator="claude_video_review")
            self.assertEqual(result["ground_truth"]["verdict_source"], "claude_video_review")
            self.assertIn("사람의 최종 판정 전", (run / "result.md").read_text())
            result = annotate(run, success=True, reason="직접 확인: 들고 있음")  # the person's verdict
            ground = result["ground_truth"]
            self.assertEqual((ground["task_success"], ground["verdict_source"]), (True, "human"))
            self.assertIn("사람의 최종 판정: 성공", result["explanation"])
            # A later Claude review never replaces the person's verdict.
            result = annotate(run, success=False, reason="x", annotator="claude_video_review")
            self.assertEqual((result["ground_truth"]["task_success"], result["ground_truth"]["verdict_source"]),
                             (True, "human"))
            self.assertEqual(result["ground_truth"]["verdicts"]["claude_video_review"]["task_success"], False)


if __name__ == "__main__":
    unittest.main()
