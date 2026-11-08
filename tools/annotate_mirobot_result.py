"""Review a saved trial without moving the robot; preserve human labels separately from detections."""
import argparse
import json
import math
from pathlib import Path

from common.recording_names import COLORS
from server.experiment_log import (FAILURE_TYPES, _rows, export_trial, normalize_ground_truth, now,
                                   onset_indices, playback_to_recording_s, slot_for, write_json)


def set_manual_blocks(run, blocks):
    """Write typed paper [x=세로, y=가로] cm into layout.json manual.paper_xy_cm."""
    from common.block_layout import PAPER_RANGE_CM
    path = Path(run) / "layout.json"
    layout = json.loads(path.read_text()) if path.exists() else {}
    if layout.get("schema") != "mirobot-layout/2":
        export_trial(Path(run) / "policy")  # creates the v2 layout with auto values first
        layout = json.loads(path.read_text())
    (lo_x, hi_x), (lo_y, hi_y) = PAPER_RANGE_CM["x"], PAPER_RANGE_CM["y"]
    for color, x, y in blocks:
        if color not in COLORS:
            raise ValueError(f"색은 {COLORS} 중 하나: {color}")
        if not (lo_x <= x <= hi_x and lo_y <= y <= hi_y):
            raise ValueError(f"{color}: x {lo_x}~{hi_x}, y {lo_y}~{hi_y} 범위 밖 ({x}, {y})")
        layout["manual"]["paper_xy_cm"][color] = [x, y]
    layout["manual"].update(source="user_typed", updated_at=now())
    write_json(path, layout)


def annotate(run, *, success=None, reason, annotator=None, selected_color=None,
             failure_type=None, failure_onset_s=None, split=None):
    run = Path(run)
    if not run.is_dir() or not (run / "experiment.json").is_file():
        raise ValueError("저장된 시행 폴더를 지정하세요.")
    if not reason or not reason.strip():
        raise ValueError("성공·실패 판정의 실제 관찰 근거가 필요합니다.")
    if failure_onset_s is not None and (not math.isfinite(failure_onset_s) or failure_onset_s < 0):
        raise ValueError("실패 시작 시각은 0 이상의 유한한 초여야 합니다.")
    if selected_color is not None and selected_color not in (*COLORS, "none", "unknown"):
        raise ValueError("Invalid selected color")
    if failure_type is not None and failure_type not in FAILURE_TYPES:
        raise ValueError(f"failure_type must be one of {FAILURE_TYPES}")
    if success is True and failure_type not in (None, "none"):
        raise ValueError("성공 시행에는 실패 유형을 넣지 않습니다.")
    target = json.loads((run / "experiment.json").read_text()).get("arguments", {}).get("color")
    if target and selected_color in COLORS and selected_color != target:
        # Picking a different colour is always a failure.
        if success is True:
            raise ValueError(f"{selected_color} 를 집었으면 {target} 지시의 성공이 아닙니다.")
        success = False
        failure_type = failure_type or "wrong_object"
    path = run / "ground_truth.json"
    previous = normalize_ground_truth(json.loads(path.read_text()) if path.exists() else None)
    real_onset = playback_to_recording_s(run, failure_onset_s)
    verdict = dict(task_success=success, reason=reason, annotator=annotator or "human",
                   selected_color=selected_color, failure_type=failure_type,
                   failure_onset_video_playback_s=failure_onset_s, failure_onset_s=real_onset,
                   updated_at=now())
    policy = run / "policy" if (run / "policy").is_dir() else run
    verdict["failure_onset_query"], verdict["failure_onset_step"] = onset_indices(
        _rows(policy / "events.jsonl"), real_onset)
    verdict["any_color_pickup"] = (selected_color in COLORS if selected_color not in (None, "unknown") else None)
    verdict["language_compliance"] = (selected_color == target if target and selected_color in COLORS else
                                      False if selected_color == "none" else None)
    # Each annotator has its own slot; the person's verdict ("human") is never overwritten by Claude.
    slot = slot_for(annotator)
    current = dict(previous, split=split or previous.get("split") or "unassigned",
                   verdicts=dict(previous["verdicts"], **{slot: verdict}))
    current = normalize_ground_truth(current)
    with (run / "annotation_history.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(dict(slot=slot, previous=previous, current=current), ensure_ascii=False) + "\n")
    write_json(path, current)
    return export_trial(run / "policy" if (run / "policy").is_dir() else run)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--success", choices=("yes", "no", "unknown"))
    parser.add_argument("--reason", help="영상 등에서 확인한 판정 근거 (--success 와 함께 필수)")
    parser.add_argument("--annotator", help="생략하면 사람의 최종 판정(human). claude_video_review 는 Claude 칸")
    parser.add_argument("--selected-color", choices=(*COLORS, "none", "unknown"))
    parser.add_argument("--failure-type", choices=FAILURE_TYPES)
    parser.add_argument("--failure-onset-s", type=float, help="영상 플레이어에 보이는 재생 시각(초). 프레임 기록으로 실제 경과 시간으로 바꿔 저장한다")
    parser.add_argument("--split", choices=("train", "calibration", "test", "unassigned"), default=None)
    parser.add_argument("--block-xy", nargs=3, action="append", metavar=("COLOR", "X", "Y"), default=[],
                        help="직접 잰 블록 좌표, 매트 눈금 x=세로 y=가로 cm. 예: --block-xy red 21 -8")
    args = parser.parse_args()
    if args.success is None and not args.block_xy:
        parser.error("--success 와 --reason, 또는 --block-xy 가 필요합니다.")
    if args.block_xy:
        set_manual_blocks(args.run, [(c, float(x), float(y)) for c, x, y in args.block_xy])
        if args.success is None:
            result = export_trial(args.run / "policy")
            print(f"{result['trial_id']}: 블록 좌표 저장")
            return
    if not args.reason:
        parser.error("--success 에는 --reason 이 필요합니다.")
    result = annotate(args.run, success={"yes": True, "no": False, "unknown": None}[args.success],
                      reason=args.reason, annotator=args.annotator, selected_color=args.selected_color,
                      failure_type=args.failure_type, failure_onset_s=args.failure_onset_s, split=args.split)
    print(f"{result['trial_id']}: {result['explanation']}")


if __name__ == "__main__":
    main()
