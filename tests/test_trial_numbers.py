import json
import os
import tempfile
import unittest
from pathlib import Path

from common import trial_numbers as tn


def make_trial(root, name, status="finished", pid=None):
    d = Path(root) / name
    (d / "policy").mkdir(parents=True)
    (d / f"{name}.mp4").write_bytes(b"x")
    (d / "launch.json").write_text(json.dumps(dict(status=status, pid=pid, bridge_recording_name=name)))
    (d / "result.json").write_text(json.dumps(dict(trial_id=name, video=str(d / f"{name}.mp4"))))
    (d / "policy/events.jsonl").write_text(json.dumps(dict(log_dir=str(d / "policy"))) + "\n")
    return d


class TrialNumberTest(unittest.TestCase):
    def test_deleted_number_is_reused_and_later_trials_move_down(self):
        with tempfile.TemporaryDirectory() as root:
            make_trial(root, "I2red")
            make_trial(root, "I3red")
            make_trial(root, "I1blue")
            new = tn.reserve(root, "red")
            self.assertEqual(new.name, "I3red")
            self.assertTrue((Path(root) / "I1red/I1red.mp4").is_file())
            result = json.loads((Path(root) / "I1red/result.json").read_text())
            self.assertEqual(result["trial_id"], "I1red")
            self.assertIn("/I1red/I1red.mp4", result["video"])
            self.assertIn("/I1red/policy", (Path(root) / "I1red/policy/events.jsonl").read_text())
            # The Windows original keeps its name.
            launch = json.loads((Path(root) / "I1red/launch.json").read_text())
            self.assertEqual(launch["bridge_recording_name"], "I2red")
            self.assertTrue((Path(root) / "I1blue").is_dir())

    def test_active_run_blocks_renumbering(self):
        with tempfile.TemporaryDirectory() as root:
            make_trial(root, "I2red", status="starting", pid=os.getpid())
            self.assertEqual(tn.compact(root, "red"), {})
            self.assertEqual(tn.reserve(root, "red").name, "I3red")

    def test_dead_starting_run_is_renumbered(self):
        with tempfile.TemporaryDirectory() as root:
            make_trial(root, "I2red", status="starting", pid=2**22 + 12345)
            self.assertEqual(tn.compact(root, "red"), {"I2red": "I1red"})



class SaveDefaultTest(unittest.TestCase):
    def test_only_real_runs_are_saved_by_default(self):
        from argparse import Namespace
        from tools.run_mirobot_local import should_save
        self.assertFalse(should_save(Namespace(execute=False, save=False, no_save=False)))  # 3-2 preview
        self.assertTrue(should_save(Namespace(execute=False, save=True, no_save=False)))
        self.assertTrue(should_save(Namespace(execute=True, save=False, no_save=False)))   # 3-3
        self.assertFalse(should_save(Namespace(execute=True, save=False, no_save=True)))



class NeverStartedTest(unittest.TestCase):
    def test_setup_failure_frees_its_number(self):
        with tempfile.TemporaryDirectory() as root:
            make_trial(root, "I1blue")
            empty = Path(root) / "I2blue"
            empty.mkdir()  # failed before the policy started: no policy/ folder
            self.assertTrue(tn.discard_if_never_started(empty, {"error": "stale"}))
            self.assertFalse(empty.exists())
            self.assertEqual(tn.reserve(root, "blue").name, "I2blue")
            self.assertFalse(tn.discard_if_never_started(Path(root) / "I1blue", {}))  # policy ran: kept


if __name__ == "__main__":
    unittest.main()
