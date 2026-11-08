"""Runs with cosmos-policy/.venv/bin/python (torch); skipped in the urop venv."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

try:
    import torch  # noqa: F401
    from server import hide_and_seek as hs
except ImportError:  # urop venv has no torch
    hs = None


def synthetic_dataset(root, rng):
    """Failures carry a signal in dimension 0 that appears partway through the rollout."""
    (root / "rollouts").mkdir(parents=True)
    rows = []
    plan = [("train", 200), ("calibration", 40), ("test", 60)]
    for split, count in plan:
        for i in range(count):
            success = split == "calibration" or i % 2 == 0
            T = int(rng.integers(6, 12))
            x = rng.normal(size=(T, 8)).astype(np.float32)
            if not success:
                onset = int(rng.integers(2, T - 1))
                x[onset:, 0] += 3.0
            name = f"I{len(rows) + 1}red"
            np.savez(root / "rollouts" / f"{name}.npz", hidden_states=x)
            rows.append(dict(trial_id=name, task_id="red", episode_success=int(success), split=split))
    with (root / "index.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@unittest.skipIf(hs is None, "torch not installed")
class HideAndSeekTest(unittest.TestCase):
    def test_losses_follow_paper_equations(self):
        scores = torch.tensor([[0.1, 0.2, 0.9, 0.9], [0.3, 0.4, 0.2, 0.0]])
        mask = torch.ones_like(scores, dtype=torch.bool)
        failed = torch.tensor([True, False])
        # Eq. 2: max(0, 1 - 0.9 + 0.4)
        self.assertAlmostEqual(float(hs.inter_loss(scores, mask, failed, 1.0)), 0.5, places=5)
        # Eq. 3: onset at the largest rise (index 2); max(0, 0.5 - 0.9 + 0.15)
        self.assertAlmostEqual(float(hs.intra_loss(scores, mask, failed, 0.5)), 0.0, places=5)
        self.assertAlmostEqual(float(hs.intra_loss(scores, mask, failed, 1.0)), 0.25, places=5)

    def test_conformal_threshold_bounds_false_alarms_on_successes(self):
        rng = np.random.default_rng(0)
        calibration = [rng.uniform(0, 0.3, size=8) for _ in range(40)]
        zeta = hs.functional_threshold(calibration, 0.2)
        self.assertEqual(zeta.shape, (8,))
        fresh = [rng.uniform(0, 0.3, size=8) for _ in range(200)]
        false_alarm = np.mean([np.any(s >= zeta) for s in fresh])
        self.assertLess(false_alarm, 0.35)

    def test_detector_learns_synthetic_failure_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            synthetic_dataset(Path(tmp) / "data", np.random.default_rng(0))
            config = hs.Config(epochs=150, warmup_epochs=50, batch_size=32, hidden=64)
            report = hs.run(Path(tmp) / "data", Path(tmp) / "out", config)
            result = report["splits"]["test"]["mean_over_alpha"]
            self.assertGreater(result["auroc_peak"], 0.9)
            self.assertGreater(result["bacc"], 0.7)
            self.assertTrue((Path(tmp) / "out/detector.pt").is_file())
            self.assertIn("test", json.loads((Path(tmp) / "out/metrics.json").read_text())["splits"])


if __name__ == "__main__":
    unittest.main()
