"""Collect labelled Mirobot trials into a SAFE-style rollout set for failure-detection experiments.

Reads only saved trial folders (never the robot). Each output rollout has one row per policy
query, matching vla-safe/SAFE `Rollout.hidden_states` (T, D) and `action_vectors` (T, H*A).
Unlabelled trials and trials without features are listed in the summary and skipped.

    urop/bin/python -m tools.export_failure_dataset Mirobot_data/W10 --out outputs/failure_dataset
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np

from common.recording_names import COLORS, valid_recording_name
from server.experiment_log import _rows, write_json


def load_trial(root: Path):
    result_path = root / "result.json"
    if not result_path.is_file():
        return None, "no result.json"
    result = json.loads(result_path.read_text())
    record = result.get("failure_detection") or {}
    if record.get("episode_success") is None:
        return None, "not labelled (ground_truth.json task_success)"
    predictions = [e for e in _rows(root / "policy/events.jsonl") if e.get("kind") == "prediction"]
    final, by_step, actions = [], [], []
    for event in predictions:
        if not event.get("features"):
            return None, f"query {event.get('query')} has no features"
        data = np.load(root / "policy" / event["features"])
        final.append(data["action_spatial_tokens"][0].mean(axis=(0, 1)))
        if "action_token_mean_by_step" in data:
            by_step.append(data["action_token_mean_by_step"][:, 0])
        actions.append(np.asarray(event["actions"], dtype=np.float32).reshape(-1))
    if not final:
        return None, "no policy queries"
    arrays = dict(hidden_states=np.stack(final).astype(np.float32),
                  action_vectors=np.stack(actions),
                  query_rollout_t_s=np.array([e.get("rollout_t_s") or np.nan for e in predictions], dtype=float))
    if len(by_step) == len(final):
        arrays["hidden_states_by_step"] = np.stack(by_step).astype(np.float32)  # (T, denoise, D)
    return (result, record, arrays), None


def export(source: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    (out / "rollouts").mkdir(exist_ok=True)
    rows, skipped = [], {}
    for root in sorted(p for p in Path(source).iterdir() if p.is_dir() and valid_recording_name(p.name)):
        trial, reason = load_trial(root)
        if trial is None:
            skipped[root.name] = reason
            continue
        result, record, arrays = trial
        np.savez_compressed(out / "rollouts" / f"{root.name}.npz", **arrays)
        nearest = record.get("nearest_training_layout") or {}
        rows.append(dict(trial_id=root.name, task_id=record["task_id"], task_description=record["task_description"],
                         episode_success=record["episode_success"], split=record.get("split"),
                         T=len(arrays["hidden_states"]), exec_horizon=record.get("exec_horizon"),
                         pred_horizon=record.get("pred_horizon"), failure_type=record.get("failure_type"),
                         failure_onset_query=record.get("failure_onset_query"),
                         runtime_reason=result.get("runtime_reason"),
                         nearest_layout=nearest.get("layout_id"),
                         nearest_layout_max_cm=nearest.get("max_block_distance_cm"),
                         video=(result.get("video") or {}).get("path")))
    # SAFE evaluates time quantiles against the shortest rollout of each task.
    min_length = defaultdict(lambda: None)
    for row in rows:
        current = min_length[row["task_id"]]
        min_length[row["task_id"]] = row["T"] if current is None else min(current, row["T"])
    for row in rows:
        row["task_min_T"] = min_length[row["task_id"]]
    columns = list(rows[0]) if rows else ["trial_id"]
    with (out / "index.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    write_json(out / "skipped.json", skipped)
    (out / "summary.md").write_text(summary(rows, skipped), encoding="utf-8")
    return rows, skipped


def summary(rows, skipped):
    lines = ["# 실패 탐지용 시행 모음\n", "## 정책 성공률 (색별)\n",
             "| 색 | 시행 | 성공 | 실패 | 성공률 |", "| --- | --- | --- | --- | --- |"]
    for color in COLORS:
        group = [r for r in rows if r["task_id"] == color]
        if group:
            ok = sum(r["episode_success"] for r in group)
            lines.append(f"| {color} | {len(group)} | {ok} | {len(group) - ok} | {ok / len(group):.1%} |")
    lines += ["", "## 분할별 시행 수 (Hide-and-Seek Table 15 형식)\n",
              "| 분할 | 시행 | 성공 | 실패 |", "| --- | --- | --- | --- |"]
    for split in sorted({r["split"] for r in rows}):
        group = [r for r in rows if r["split"] == split]
        ok = sum(r["episode_success"] for r in group)
        lines.append(f"| {split} | {len(group)} | {ok} | {len(group) - ok} |")
    types = Counter(r["failure_type"] for r in rows if not r["episode_success"])
    lines += ["", "## 실패 유형\n", "| 유형 | 시행 |", "| --- | --- |"]
    lines += [f"| {k} | {v} |" for k, v in sorted(types.items(), key=lambda kv: str(kv[0]))]
    lines += ["", f"제외한 시행 {len(skipped)}개는 `skipped.json` 에 이유와 함께 적었다.\n"]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="I1red, I2blue, ... 시행 폴더가 있는 상위 폴더")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows, skipped = export(args.source, args.out)
    print(f"{len(rows)} rollouts exported, {len(skipped)} skipped → {args.out}")


if __name__ == "__main__":
    main()
