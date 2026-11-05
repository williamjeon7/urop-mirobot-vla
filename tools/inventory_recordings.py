"""실물 녹화 폴더 점검 — 학습 HDF5 로 바꿀 수 있는 녹화를 고른다 (W10, docs/W10/DATA_CHECK.md).

`Mirobot_data/<주차>/L<배치>_<색>` 폴더마다 다음을 보고, 표와 JSON 으로 남긴다. 로봇·GPU 를 쓰지 않는다.

* 녹화 — `metadata.json` complete·robot·teleop, 폴더 색 = metadata 색 = reference task, 종료 이유(`capture_result.json`)
* 기록 — PNG 수와 `frames.jsonl` 수, `robot.jsonl` 의 `?` 원문(`raw`) 유무, F8 구간(마지막 RESET 뒤 시작·끝 하나씩)
* 배치 — `layout.json` 이 있고 target = 폴더 색, layout_id = 폴더 배치, `real_success`
* 정렬 — `aligned.npz`·`alignment_report.json` 이 있고 입력 해시가 지금 원본과 같은지(`prepare.input_hashes_match`),
  카메라 최대 오차 ≤ `--max-frame-ms`(W10 기준 70), 로봇 기록 최대 간격 ≤ 150 ms

판정 `ready` = 위가 모두 맞고 `real_success` 가 true. 아니면 이유를 적는다.

    cosmos-policy/.venv/bin/python -m tools.inventory_recordings Mirobot_data/W10
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from docs.W9.d405.prepare import input_hashes_match, read_jsonl

NAME = re.compile(r"(L\d+)_(red|green|blue)(?:_\d+)?")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def inspect(ep: Path, max_frame_ms: float, max_gap_ms: float) -> dict:
    m = NAME.fullmatch(ep.name)
    layout_id, color = (m.group(1), m.group(2)) if m else (None, None)
    meta = read_json(ep / "metadata.json") or {}
    result = read_json(ep / "capture_result.json") or {}
    layout = read_json(ep / "layout.json")
    report = read_json(ep / "alignment_report.json")
    frames = read_jsonl(ep / "frames.jsonl") if (ep / "frames.jsonl").exists() else []
    events = read_jsonl(ep / "robot.jsonl") if (ep / "robot.jsonl").exists() else []
    ref = read_jsonl(ep / "reference.jsonl")[0].get("meta", {}) if (ep / "reference.jsonl").exists() else {}
    pngs = len(list((ep / "rgb").glob("*.png"))) if (ep / "rgb").is_dir() else 0
    states = [e for e in events if e.get("kind") == "state"]
    after = max((e["t_s"] for e in events if e.get("kind") == "capture_reset"), default=float("-inf"))
    starts = [e["t_s"] for e in events if e.get("kind") == "capture_start" and e["t_s"] > after]
    ends = [e["t_s"] for e in events if e.get("kind") == "capture_end" and e["t_s"] > after]
    span = (frames[-1]["t_s"] - frames[0]["t_s"]) if len(frames) > 1 else 0.0
    problems = []
    if not m:
        problems.append("folder name is not L<nn>_<color>")
    if not (meta.get("complete") and meta.get("robot") and meta.get("teleop")):
        problems.append("capture not complete")
    if color and (meta.get("color") != color or ref.get("task") != color or ref.get("seed") != meta.get("seed")):
        problems.append(f"color mismatch folder={color} metadata={meta.get('color')} reference={ref.get('task')}")
    if pngs != len(frames) or not pngs:
        problems.append(f"png {pngs} != frames.jsonl {len(frames)}")
    if len(starts) != 1 or len(ends) != 1:
        problems.append(f"F8 interval after last reset: starts {len(starts)}, ends {len(ends)}")
    if layout is None:
        problems.append("layout.json missing")
    else:
        if layout.get("target") != color or layout.get("layout_id") != layout_id:
            problems.append(f"layout.json target/id {layout.get('target')}/{layout.get('layout_id')}")
        if layout.get("real_success") is not True:
            problems.append(f"real_success {layout.get('real_success')}")
    if report is None or not (ep / "aligned.npz").exists():
        problems.append("not aligned")
    else:
        if not input_hashes_match(ep, report.get("input_sha256")):
            problems.append("inputs changed after alignment")
        if report["max_frame_error_ms"] > max_frame_ms:
            problems.append(f"camera gap {report['max_frame_error_ms']:.1f} ms > {max_frame_ms:g}")
        if report["max_robot_gap_ms"] > max_gap_ms:
            problems.append(f"robot gap {report['max_robot_gap_ms']:.1f} ms > {max_gap_ms:g}")
    return dict(
        episode=ep.name, layout_id=layout_id, color=color, recorded_at=meta.get("recorded_at"),
        termination=result.get("termination_reason") or meta.get("termination_reason"),
        discarded_takes=meta.get("discarded_takes"), resets=sum(e.get("kind") == "capture_reset" for e in events),
        pngs=pngs, camera_fps=round(len(frames) / span, 2) if span else None,
        robot_states=len(states), raw_saved=bool(states) and all("raw" in s for s in states),
        real_success=None if layout is None else layout.get("real_success"),
        steps=None if report is None else report.get("steps"),
        max_frame_error_ms=None if report is None else round(report["max_frame_error_ms"], 1),
        max_robot_gap_ms=None if report is None else round(report["max_robot_gap_ms"], 1),
        ready=not problems, problems=problems,
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("root", type=Path, help="예: Mirobot_data/W10")
    p.add_argument("--max-frame-ms", type=float, default=70.0)
    p.add_argument("--max-robot-gap-ms", type=float, default=150.0)
    p.add_argument("--report", type=Path, help="JSON (기본: docs/W10/data/inventory_<root 이름>.json)")
    a = p.parse_args()
    eps = sorted(d for d in a.root.iterdir() if d.is_dir() and (d / "metadata.json").exists())
    rows = [inspect(ep, a.max_frame_ms, a.max_robot_gap_ms) for ep in eps]
    for r in rows:
        mark = "ready" if r["ready"] else "NO   "
        print(f"{mark} {r['episode']:<12} {str(r['steps']):>4}칸 카메라 {str(r['camera_fps']):>5} fps "
              f"오차 {str(r['max_frame_error_ms']):>5} ms  raw {'O' if r['raw_saved'] else 'X'}  "
              f"{'; '.join(r['problems'])}")
    ready = [r for r in rows if r["ready"]]
    by_color = Counter(r["color"] for r in ready)
    layouts = defaultdict(set)
    for r in ready:
        layouts[r["layout_id"]].add(r["color"])
    full = sorted(k for k, v in layouts.items() if len(v) == 3)
    summary = dict(root=str(a.root), episodes=len(rows), ready=len(ready), ready_steps=sum(r["steps"] for r in ready),
                   ready_by_color=dict(by_color), layouts_with_all_three=full,
                   not_ready={r["episode"]: r["problems"] for r in rows if not r["ready"]},
                   max_frame_ms=a.max_frame_ms, max_robot_gap_ms=a.max_robot_gap_ms)
    print(json.dumps({k: v for k, v in summary.items() if k != "not_ready"}, ensure_ascii=False))
    out = a.report or Path("docs/W10/data") / f"inventory_{a.root.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(summary=summary, episodes=rows), indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"report → {out}")


if __name__ == "__main__":
    main()
