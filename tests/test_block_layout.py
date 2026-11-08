import json
import shutil
import tempfile
import unittest
from pathlib import Path

import cv2

from common import block_layout as bl
from server.experiment_log import export_trial
from tools.annotate_mirobot_result import set_manual_blocks

REPO = Path(__file__).resolve().parents[1]
L13 = REPO / "Mirobot_data/W10/L13_red"


@unittest.skipUnless((L13 / "rgb/00000000.png").is_file(), "W10 data not present")
class BlockLayoutTest(unittest.TestCase):
    def test_auto_matches_measured_l13_in_mat_coordinates(self):
        rgb = cv2.cvtColor(cv2.imread(str(L13 / "rgb/00000000.png")), cv2.COLOR_BGR2RGB)
        doc = bl.estimate_layout(rgb, list(bl.INITIAL_POSE))
        measured = json.loads((L13 / "layout.json").read_text())["blocks_mat_cm"]  # [가로, 세로]
        for color in bl.COLORS:
            x, y = doc["paper_xy_cm"][color]
            self.assertLess(((x - measured[color][1]) ** 2 + (y - measured[color][0]) ** 2) ** 0.5, 0.6)
        self.assertEqual(doc["errors"], {})

    def test_wrong_pose_is_not_estimated(self):
        rgb = cv2.cvtColor(cv2.imread(str(L13 / "rgb/00000000.png")), cv2.COLOR_BGR2RGB)
        self.assertEqual(bl.estimate_layout(rgb, [210, 0, 230, 0, 0, 0])["source"], "not_measured")

    def test_after_run_auto_and_manual_are_written_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "I1red"
            (run / "policy").mkdir(parents=True)
            shutil.copy(L13 / "rgb/00000000.png", run / "policy/rgb_0000.png")
            (run / "policy/events.jsonl").write_text(json.dumps(dict(
                kind="observation", phase="initial", image="rgb_0000.png",
                observation=dict(cart6=[198.668, 0, 230.449, 0, 0, 0]))) + "\n")
            (run / "experiment.json").write_text("{}")
            export_trial(run / "policy")
            layout = json.loads((run / "layout.json").read_text())
            self.assertEqual(layout["source_by_color"], dict(red="auto", green="auto", blue="auto"))
            self.assertEqual(layout["manual"]["paper_xy_cm"], dict(red=None, green=None, blue=None))
            set_manual_blocks(run, [("red", 21.0, -8.0)])
            result = export_trial(run / "policy")
            layout = json.loads((run / "layout.json").read_text())
            self.assertEqual(layout["paper_xy_cm"]["red"], [21.0, -8.0])
            self.assertEqual(layout["blocks"]["red"], [-9.0, -8.0])
            self.assertEqual(layout["source_by_color"]["red"], "manual")
            self.assertEqual(result["failure_detection"]["nearest_training_layout"]["layout_id"], "L13")
            with self.assertRaises(ValueError):
                set_manual_blocks(run, [("blue", -12.0, 0.0)])  # x below -9


if __name__ == "__main__":
    unittest.main()
