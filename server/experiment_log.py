"""Save reproducible per-trial evidence without treating execution completion as task success."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from zoneinfo import ZoneInfo

from common.recording_names import COLORS

REPO = Path(__file__).resolve().parents[1]
PAPER_FRAME = {"id": "paper_top_border_zero_Xup_Yleft_cm", "robot_base_center_cm": [-30, 0]}


def now():
    return datetime.now(ZoneInfo("Asia/Seoul")).isoformat()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(serializable(value), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temporary.replace(path)


def serializable(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)  # e.g. a disabled limit (inf); JSON has no infinity
    if isinstance(value, dict):
        return {str(k): serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(v) for v in value]
    if hasattr(value, "tolist"):
        return serializable(value.tolist())
    return value


def identity(path, hash_limit=16 * 1024 * 1024):
    path = Path(path)
    result = {"path": str(path)}
    if path.is_dir():
        result["files"] = [identity(f, hash_limit) for f in sorted(path.glob("*")) if f.is_file()]
        if (path / "model/.metadata").is_file():
            result["model_metadata"] = identity(path / "model/.metadata")
    elif path.is_file():
        stat = path.stat()
        result.update(size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)
        if stat.st_size <= hash_limit:
            result["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        else:
            result["sha256"] = None
            result["hash_status"] = "not_hashed_large_file"
    else:
        result["missing"] = True
    return result


# The policy is end-to-end (wrist image only), so runs never ask for block positions, size or yaw.
# Paper XY can be supplied with --layout-json for result analysis only.
PAPER_LAYOUT_FIELDS = dict(unit="cm", coordinate_frame=PAPER_FRAME, source="user_reported_paper_xy",
                           estimated=False)
def parse_paper_xy(text):
    """Return (x, y) in paper cm, or raise ValueError with the reason."""
    try:
        values = [float(v) for v in text.replace(",", " ").split()]
    except ValueError:
        values = []
    if len(values) != 2 or not all(math.isfinite(v) for v in values):
        raise ValueError("X, Y 숫자 두 개가 필요합니다.")
    x, y = values
    if not -30 < x <= 5:
        # Mat 세로 readings are positive (e.g. 21); paper X = 세로 - 30 is negative.
        raise ValueError(f"X={x:g}: 종이 X는 -30보다 크고 대개 음수입니다. 매트 세로값이면 30을 빼서 넣으세요.")
    return [x, y]


def layout_document(path=None):
    """Use the data-collection paper frame, retaining measured/planned/unknown provenance."""
    if path:
        path = Path(path).absolute()
        source = json.loads(path.read_text(encoding="utf-8"))
        if source.get("unit", "cm") != "cm" or source.get("coordinate_frame", PAPER_FRAME) != PAPER_FRAME:
            raise ValueError("배치 파일은 데이터셋의 paper_top_border_zero_Xup_Yleft_cm 좌표계와 cm 단위를 사용해야 합니다.")
        points = source.get("blocks")
        if not isinstance(points, dict) or set(points) != set(COLORS):
            raise ValueError("배치 파일에 red, green, blue의 X,Y 좌표가 모두 필요합니다.")
        for color, point in points.items():
            if (not isinstance(point, (list, tuple)) or len(point) != 2 or
                    any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in point)):
                raise ValueError(f"{color}: 유한한 X,Y 좌표 두 개가 필요합니다.")
            try:
                parse_paper_xy(f"{point[0]} {point[1]}")
            except ValueError as error:
                raise ValueError(f"{color}: {error}") from None
        source = dict(PAPER_LAYOUT_FIELDS, **source)
        result = {key: source.get(key) for key in (
            "layout_id", "unit", "blocks", "blocks_mat_cm", "yaw_deg", "coordinate_frame", "source", "estimated")}
        result.update(source_file=str(path), source_file_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        result["source"] = result.get("source") or source.get("coordinate_source") or "user_supplied"
        if source.get("photo"):
            photo = path.parent / source["photo"]
            if photo.is_file():
                result["_photo_source"] = str(photo)
        return result
    return dict(unit="cm", coordinate_frame=PAPER_FRAME, blocks={c: None for c in COLORS},
                source="not_measured", missing_reason="No current-trial layout supplied; training layout was not reused")


def capture_trial_layout(directory, policy_args, execute=None):
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--layout-json", type=Path)
    options = parser.parse_known_args(policy_args)[0]
    document = layout_document(options.layout_json)
    photo = document.pop("_photo_source", None)
    if photo:
        target = Path(directory) / ("layout_photo" + Path(photo).suffix.lower())
        shutil.copyfile(photo, target)
        document["photo"] = target.name
    document["captured_at"] = now()
    path = Path(directory) / "layout.json"
    write_json(path, document)
    if options.layout_json is None:
        return list(policy_args)  # nothing measured; the policy run records the same not_measured layout
    return [*policy_args, "--layout-json", str(path)]


def manifest(directory, args, config):
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True, timeout=3).strip()
    except (OSError, subprocess.SubprocessError):
        head = None
    packages = {}
    for package in ("torch", "numpy", "opencv-python", "mujoco", "transformers"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    from dataclasses import asdict
    reference = Path(args.reference)
    return dict(schema="mirobot-experiment/1", trial_id=Path(directory).name, created_at=now(),
                git_commit=head, python=sys.version, platform=platform.platform(), packages=packages,
                arguments=serializable(vars(args)), policy=serializable(asdict(config)),
                code={str(p.relative_to(REPO)): identity(p) for p in
                      (REPO / "server/run_policy.py", REPO / "server/policy_runtime.py",
                       REPO / "server/follow_translator.py", REPO / "common/policy_io.py")},
                assets={name: identity(path) for name, path in (
                    ("checkpoint", config.checkpoint), ("statistics", config.statistics),
                    ("t5", config.t5_embeddings), ("reference", reference / "reference.jsonl"),
                    ("gcode", reference / "source.gcode"), ("color_profile", reference / "color_profile.json"))},
                detector={"method": None, "score": None, "threshold": None,
                          "status": "SAFE/Hide-and-Seek detector not trained or configured"},
                features={"status": "pending", "definition": "Cosmos final projection input; not a trained failure score"})


def trial_root(policy_directory):
    path = Path(policy_directory)
    return path.parent if path.name == "policy" else path


# Failure categories offered in the Hide-and-Seek (2026) annotation prompt, plus "none" for successes.
FAILURE_TYPES = ("none", "drop", "wrong_object", "collision", "stuck_off_track", "goal_violation", "other")
TRAINING_ROOT = REPO / "Mirobot_data/W10"


VERDICT_FIELDS = ("task_success", "language_compliance", "any_color_pickup", "selected_color", "failure_type",
                  "failure_onset_video_playback_s", "failure_onset_s", "failure_onset_step",
                  "failure_onset_query", "annotator", "reason", "updated_at")
# Who decided, in priority order: the person's final verdict always wins.
VERDICT_SLOTS = ("human", "claude_video_review", "auto")
VERDICT_LABELS = {"human": "사람의 최종 판정", "claude_video_review": "영상 검토 판정 (Claude)",
                  "auto": "자동 판정"}


def default_ground_truth():
    return dict(schema="mirobot-ground-truth/2", split="unassigned", verdict_source=None,
                verdicts={slot: None for slot in VERDICT_SLOTS}, **{f: None for f in VERDICT_FIELDS})


def slot_for(annotator):
    return ("auto" if annotator == "auto_visual_detector" else
            "claude_video_review" if annotator == "claude_video_review" else "human")


def normalize_ground_truth(ground):
    """Upgrade a v1 file (one verdict) to slots, then copy the highest-priority verdict to the top."""
    ground = dict(default_ground_truth(), **(ground or {}))
    verdicts = dict({slot: None for slot in VERDICT_SLOTS}, **(ground.get("verdicts") or {}))
    if ground.get("schema") == "mirobot-ground-truth/1" and ground.get("task_success") is not None:
        verdicts[slot_for(ground.get("annotator"))] = {f: ground.get(f) for f in VERDICT_FIELDS}
    source = next((slot for slot in VERDICT_SLOTS if (verdicts.get(slot) or {}).get("task_success") is not None), None)
    chosen = verdicts.get(source) or {}
    ground.update({f: chosen.get(f) for f in VERDICT_FIELDS}, verdicts=verdicts, verdict_source=source,
                  schema="mirobot-ground-truth/2")
    return ground


def video_offset_s(events):
    """Rollout time at which the video starts (0 when there is no recording)."""
    for event in events:
        if event.get("kind") == "recording_started" and event.get("rollout_t_s") is not None:
            return event["rollout_t_s"]
    return 0.0


def playback_to_recording_s(root, playback_s):
    """MP4 player time -> real seconds since recording start, using <trial>_frames.jsonl.

    The bridge encodes at a fixed 30 fps while the camera delivers fewer frames, so the MP4
    plays faster than real time (e.g. 110.6 s recorded as 55.3 s). Returns playback_s unchanged
    when no frame log exists.
    """
    root = Path(root)
    frames_path = root / f"{root.name}_frames.jsonl"
    meta_path = root / f"{root.name}_video.json"
    if playback_s is None or not frames_path.is_file():
        return playback_s
    fps = (json.loads(meta_path.read_text()).get("fps") if meta_path.is_file() else None) or 30
    frames = _rows(frames_path)
    if not frames:
        return playback_s
    index = min(max(int(round(playback_s * fps)), 0), len(frames) - 1)
    return float(frames[index]["t_s"])


def onset_indices(events, onset_s):
    """Map an onset seen in the video (s from video start) to the policy query and step then active."""
    if onset_s is None:
        return None, None
    onset_s = onset_s + video_offset_s(events)
    query = step = None
    for event in events:
        t = event.get("rollout_t_s")
        if t is None or t > onset_s:
            continue
        if event.get("kind") == "prediction":
            query = event.get("query")
        if event.get("kind") == "target":
            step = event.get("step")
    return query, step


def nearest_training_layout(blocks, root=TRAINING_ROOT):
    """Closest W10 demonstration layout, by the largest per-colour block distance (cm)."""
    if not blocks or any(blocks.get(c) is None for c in COLORS):
        return None
    best = None
    for path in sorted(Path(root).glob("L*/layout.json")):
        try:
            other = json.loads(path.read_text()).get("blocks") or {}
            distance = max(math.dist(blocks[c], other[c]) for c in COLORS)
        except (ValueError, KeyError, TypeError):
            continue
        if best is None or distance < best["max_block_distance_cm"]:
            best = {"layout_id": path.parent.name.split("_")[0], "max_block_distance_cm": round(distance, 3)}
    return best


def _rows(path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue  # A process killed during its final write leaves an incomplete line.
    return rows


def _csv(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list, tuple)) else v
                             for k, v in row.items() if k in columns})


MANUAL_NOTE = ("직접 잰 값을 적는 칸. 매트 인쇄 눈금 그대로 [x=세로, y=가로] cm (x -9~30, y -30~30). "
               "모르면 null 로 둔다. 적은 뒤 tools.annotate_mirobot_result 를 다시 실행하거나 "
               "--block-xy 로 넣으면 result 파일이 갱신된다.")


def _paper_from_blocks(blocks):
    from common.block_layout import PAPER_X_SHIFT_CM
    return {c: (None if p is None else [round(p[0] + PAPER_X_SHIFT_CM, 2), p[1]]) for c, p in (blocks or {}).items()}


def finalize_layout(root, events):
    """Write auto-estimated and manual block positions into layout.json in one go, after the run.

    auto   : from the saved initial wrist image (common.block_layout), recomputed only when missing.
    manual : paper [x=세로, y=가로] cm typed by a person (or from --layout-json); null until filled.
    paper_xy_cm / blocks (dataset frame) : manual where given, otherwise auto.
    """
    from common.block_layout import PAPER_X_SHIFT_CM, estimate_layout
    root = Path(root)
    path = root / "layout.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    if old.get("schema") == "mirobot-layout/2":
        auto, manual = old.get("auto"), old.get("manual") or {}
    else:  # written at launch: either not_measured or a user --layout-json (dataset frame)
        auto, manual = None, {}
        if old.get("source") not in (None, "not_measured") and any((old.get("blocks") or {}).values()):
            manual = dict(paper_xy_cm=_paper_from_blocks(old["blocks"]), source=old.get("source"),
                          source_file=old.get("source_file"), updated_at=old.get("captured_at"))
    manual.setdefault("paper_xy_cm", {c: None for c in COLORS})
    manual["note"] = MANUAL_NOTE
    if auto is None:
        initial = next((e for e in events if e.get("kind") == "observation" and e.get("image")), None)
        image = root / "policy" / initial["image"] if initial else None
        if image is not None and image.is_file():
            import cv2
            rgb = cv2.cvtColor(cv2.imread(str(image)), cv2.COLOR_BGR2RGB)
            auto = estimate_layout(rgb, (initial.get("observation") or {}).get("cart6"))
            auto.update(image=str(image.relative_to(root)), phase=initial.get("phase"))
        else:
            auto = dict(source="not_measured", estimated=False, paper_xy_cm={c: None for c in COLORS},
                        errors={"image": "no saved initial wrist image"})
    chosen, sources, difference = {}, {}, {}
    for color in COLORS:
        typed = manual["paper_xy_cm"].get(color)
        guessed = (auto.get("paper_xy_cm") or {}).get(color)
        chosen[color] = typed if typed is not None else guessed
        sources[color] = "manual" if typed is not None else "auto" if guessed is not None else "not_measured"
        if typed is not None and guessed is not None:
            difference[color] = round(math.dist(typed, guessed), 2)
    layout = dict(schema="mirobot-layout/2", unit="cm",
                  paper_frame="mat print: x=세로 (robot base centre 0, + away), y=가로 (centre 0, + left)",
                  paper_xy_cm=chosen, source_by_color=sources,
                  blocks={c: (None if p is None else [round(p[0] - PAPER_X_SHIFT_CM, 2), p[1]]) for c, p in chosen.items()},
                  coordinate_frame=PAPER_FRAME, manual_minus_auto_cm=difference,
                  manual=manual, auto=auto, updated_at=now())
    write_json(path, layout)
    return layout


def failure_detection_record(root, events, ground, predictions):
    """Per-rollout fields that SAFE (vla-safe/SAFE Rollout) and Hide-and-Seek metrics need.

    The detector's time axis is the policy query (one feature vector per inference); each query
    executes `exec_horizon` actions of a `pred_horizon` chunk. TWA uses the first alarm query / T.
    """
    manifest_path = Path(root) / "experiment.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    arguments = manifest.get("arguments") or {}
    layout_path = Path(root) / "layout.json"
    layout = json.loads(layout_path.read_text()) if layout_path.exists() else {}
    success = ground.get("task_success")
    onset_query, onset_step = onset_indices(events, ground.get("failure_onset_s"))
    actions = predictions[0].get("actions") if predictions else None
    return dict(
        episode_success=None if success is None else int(bool(success)),
        task_id=arguments.get("color"), task_description=next(
            (e.get("instruction") for e in events if e.get("kind") == "configuration"), None),
        episode_length_queries=len(predictions),
        exec_horizon=arguments.get("open_loop_steps"),
        pred_horizon=len(actions) if actions else None,
        action_dim=len(actions[0]) if actions else None,
        denoising_steps=arguments.get("denoising_steps"),
        feature_files=[e.get("features") for e in predictions],
        feature_status=sorted({(e.get("feature_metadata") or {}).get("status") for e in predictions} - {None}),
        query_rollout_t_s=[e.get("rollout_t_s") for e in predictions],
        video_start_rollout_t_s=video_offset_s(events),
        failure_type=ground.get("failure_type"), failure_onset_query=onset_query, failure_onset_step=onset_step,
        split=ground.get("split"), nearest_training_layout=nearest_training_layout(layout.get("blocks")))


def export_trial(policy_directory):
    """Rebuild human-readable and tabular artifacts from saved evidence, never hardware."""
    policy_directory = Path(policy_directory)
    root = trial_root(policy_directory)
    summary_path = policy_directory / "summary.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    launch_path = root / "launch.json"
    launch = json.loads(launch_path.read_text()) if launch_path.exists() else {}
    events = _rows(policy_directory / "events.jsonl")
    layout = finalize_layout(root, events)
    ground_path = root / "ground_truth.json"
    if not ground_path.exists():
        write_json(ground_path, default_ground_truth())
    ground = json.loads(ground_path.read_text())
    ground = normalize_ground_truth(ground)
    wrong = summary.get("wrong_pickup")
    pickup_auto = summary.get("pickup")
    if ground["verdicts"]["auto"] is None and wrong:
        # Lifting another colour is a failure (automatic; the person's verdict overrides it).
        ground["verdicts"]["auto"] = dict(
            task_success=False, selected_color=wrong.get("color"), any_color_pickup=True,
            language_compliance=False, failure_type="wrong_object", annotator="auto_visual_detector",
            reason=f"다른 색 블록({wrong.get('color')})을 들어 올림 (요청: {summary.get('instruction')})",
            updated_at=now())
    elif ground["verdicts"]["auto"] is None and summary.get("status") == "pickup_confirmed" and pickup_auto:
        color = pickup_auto.get("color")
        ground["verdicts"]["auto"] = dict(
            task_success=True, selected_color=color, any_color_pickup=True, language_compliance=True,
            failure_type="none", annotator="auto_visual_detector",
            reason=(f"자동 집기 확인: 그리퍼 닫힘, {pickup_auto.get('lifted_mm', 0):.1f} mm 상승, "
                    f"{color} 영역 {pickup_auto.get('stable_observations')}회 연속 확인"),
            updated_at=now())
    ground = normalize_ground_truth(ground)
    write_json(ground_path, ground)
    observations = [e for e in events if e["kind"] == "observation"]
    trajectory = []
    for e in observations:
        pose = e.get("observation", {}).get("cart6", [])
        if len(pose) == 6:
            trajectory.append(dict(t_s=e.get("t_s"), rollout_t_s=e.get("rollout_t_s"),
                phase=e.get("phase"), query=e.get("query"), step=e.get("step"),
                **dict(zip(("x_mm", "y_mm", "z_mm", "a_deg", "b_deg", "c_deg"), pose)),
                closure=e["observation"].get("closure"), state=e["observation"].get("state"),
                state_rtt_s=e["observation"].get("state_rtt_s"), image=e.get("image")))
    _csv(root / "robot_trajectory.csv",
         ["t_s", "rollout_t_s", "phase", "query", "step", "x_mm", "y_mm", "z_mm", "a_deg", "b_deg", "c_deg",
          "closure", "state", "state_rtt_s", "image"], trajectory)
    predictions = [e for e in events if e["kind"] == "prediction"]
    _csv(root / "predictions.csv", ["t_s", "rollout_t_s", "query", "seconds", "image", "cart6", "proprio", "actions",
                                    "virtual_gap", "features", "feature_metadata"], predictions)
    _csv(root / "commands.csv", ["t_s", "rollout_t_s", "step", "query", "command", "result"],
         [e for e in events if e["kind"] == "command_ack"])
    actual = [e for e in events if e["kind"] == "target" and e.get("executed")]
    errors = [e for e in events if e["kind"] in ("target_rejected", "arrival_check")]
    measured = [e for e in errors if "error_mm" in e]
    status = summary.get("status") or launch.get("status", "running")
    error = summary.get("error") or launch.get("error")
    pickup = summary.get("pickup")
    if error:
        explanation = f"실행 중단: {error}"
    elif wrong:
        explanation = (f"다른 색 집기로 자동 종료: {wrong.get('color')} 블록이 그리퍼에 들린 채 연속 관측됨. 실패로 기록.")
    elif pickup:
        explanation = ("자동 집기 후보 감지: 그리퍼 닫힘 추정, 로봇 Z 상승, 요청 색 영역의 연속 안정 조건 충족. "
                       "물체의 실제 들림·유지 시간은 별도 확인 필요.")
    elif status in ("completed", "finished"):
        explanation = "설정된 동작 수를 완료하고 정상 종료. 실제 집기 성공 여부는 아직 판정하지 않음."
    else:
        explanation = "실행 또는 초기화 진행 중. 최종 결과 미확인."
    if ground.get("task_success") is not None:
        who = VERDICT_LABELS[ground["verdict_source"]]
        explanation = f"{who}: {'성공' if ground['task_success'] else '실패'}. 근거: {ground.get('reason')}"
    result = dict(schema="mirobot-result/1", trial_id=root.name, updated_at=now(), status=status,
                  mode=summary.get("mode", launch.get("mode")), instruction=summary.get("instruction"),
                  runtime_reason=summary.get("termination_reason", launch.get("stage")), error=error,
                  explanation=explanation, initial_robot=observations[0]["observation"] if observations else None,
                  last_robot=observations[-1]["observation"] if observations else None,
                  queries=summary.get("queries", len(predictions)), steps=summary.get("steps", 0),
                  cartesian_commands_attempted=len(actual),
                  duration_s=summary.get("duration_s"), rollout_duration_s=summary.get("rollout_duration_s"),
                  inference_seconds=[e["seconds"] for e in predictions],
                  mean_arrival_error_mm=(sum(e["error_mm"] for e in measured) / len(measured) if measured else None),
                  max_arrival_error_mm=max((e["error_mm"] for e in measured), default=None),
                  automatic_pickup_evidence=pickup, ground_truth=ground,
                  video=summary.get("video"), video_error=summary.get("video_error"),
                  video_transfer=launch.get("video_transfer"),
                  detector_evaluation={"auroc": None, "tpr": None, "fpr": None, "balanced_accuracy": None,
                                       "reason": "Requires independently reviewed outcomes and a configured failure detector"},
                  failure_detection=failure_detection_record(root, events, ground, predictions),
                  artifacts={"manifest": "experiment.json", "layout": "layout.json",
                             "events": str(policy_directory.relative_to(root) / "events.jsonl"),
                             "trajectory": "robot_trajectory.csv", "predictions": "predictions.csv", "commands": "commands.csv"})
    write_json(root / "result.json", result)
    auto_xy = (layout["auto"].get("paper_xy_cm") or {})
    block_lines = "\n".join(
        f"| {c} | {layout['paper_xy_cm'][c]} | {layout['source_by_color'][c]} | {auto_xy.get(c)} | "
        f"{layout['manual']['paper_xy_cm'].get(c)} |" for c in COLORS)
    task = ground.get("task_success")
    outcome = "미판정" if task is None else "성공" if task else "실패"
    if task is not None and ground.get("verdict_source") != "human":
        outcome += f" ({VERDICT_LABELS[ground['verdict_source']]}, 사람의 최종 판정 전)"
    verdict_lines = "".join(
        f"| {VERDICT_LABELS[slot]} | "
        + ("미입력 |  | " if not (v := ground["verdicts"].get(slot)) or v.get("task_success") is None else
           f"{'성공' if v['task_success'] else '실패'} | {v.get('failure_type') or ''} | {v.get('reason') or ''}")
        + " |\n" for slot in VERDICT_SLOTS)
    pose = result["initial_robot"].get("cart6") if result["initial_robot"] else None
    text = (f"# {root.name} 실험 결과\n\n"
            f"- 지시문: {result['instruction']}\n- 실행 상태: {status}\n- 집기 최종 판정: {outcome}\n"
            f"- 종료·판정 근거: {explanation}\n- 초기 Mirobot XYZABC (mm, deg): {pose}\n"
            f"- 추론 횟수: {result['queries']}\n- 완료 동작 수: {result['steps']}\n"
            f"- 실행 시간 (모델 준비 포함, s): {result['duration_s']}\n"
            f"- 집기 실행 시간 (s): {result['rollout_duration_s']}\n\n"
            "## 초기 블록 배치\n\n"
            "매트 인쇄 눈금 [x=세로, y=가로] cm. 직접 적은 값이 있으면 그 값을, 없으면 자동 측정값을 쓴다. "
            "자동 측정은 실행 뒤 초기 자세 손목 사진으로 계산한다 (W10 검증 평균 오차 약 0.2 cm). "
            "직접 적는 칸은 layout.json 의 manual.paper_xy_cm.\n\n"
            "| 색 | 사용 값 | 출처 | 자동 측정 | 직접 적은 값 |\n| --- | --- | --- | --- | --- |\n" + block_lines + "\n\n"
            f"자동 측정 문제: {layout['auto'].get('errors') or '없음'}. 직접−자동 차이(cm): {layout['manual_minus_auto_cm'] or '없음'}.\n\n"
            f"가장 가까운 학습 배치: {result['failure_detection']['nearest_training_layout']} "
            "(세 블록 중 가장 먼 거리, cm).\n\n"
            "## 실패 탐지 평가용 정보\n\n"
            f"- 시간축 길이 T (추론 횟수): {result['failure_detection']['episode_length_queries']}, "
            f"추론마다 실행 action 수: {result['failure_detection']['exec_horizon']}, "
            f"chunk 길이: {result['failure_detection']['pred_horizon']}\n"
            f"- 특징 저장 상태: {result['failure_detection']['feature_status']}\n"
            f"- 실패 유형: {ground.get('failure_type')}, 실패 시작 추론 번호: "
            f"{result['failure_detection']['failure_onset_query']}, 분할: {ground.get('split')}\n\n"
            "## 판정\n\n위에서부터 처음 입력된 판정을 최종으로 쓴다. 사람의 최종 판정은 "
            "`tools.annotate_mirobot_result` 로 넣는다.\n\n"
            "| 판정 | 결과 | 실패 유형 | 근거 |\n| --- | --- | --- | --- |\n" + verdict_lines + "\n"
            "## 검토 상태\n\n"
            "ground_truth.json의 최종 성공·실패 및 이유는 영상 검토 후 입력한다. "
            "정상 종료나 자동 집기 후보를 사람의 정답으로 사용하지 않는다. "
            "SAFE/Hide-and-Seek 점수와 AUROC 등은 탐지기·정답이 확보되기 전에는 미측정이다.\n")
    (root / "result.md").write_text(text, encoding="utf-8")
    return result


def start_launch(directory, policy_args, mode):
    value = dict(schema="mirobot-launch/1", started_at=now(), mode=mode, status="starting", pid=os.getpid(),
                 stage="initialization", policy_arguments=list(map(str, policy_args)))
    write_json(Path(directory) / "launch.json", value)
    write_json(Path(directory) / "experiment.json", dict(schema="mirobot-experiment/1",
               trial_id=Path(directory).name, created_at=value["started_at"], mode=mode,
               policy_arguments=value["policy_arguments"], status="policy_not_loaded"))
    return value


def finish_launch(directory, launch, *, code=None, error=None, video_transfer=None):
    launch.update(finished_at=now(), exit_code=code, status="failed" if error or code else "finished",
                  error=str(error) if error else None)
    if video_transfer is not None:
        launch["video_transfer"] = video_transfer
    write_json(Path(directory) / "launch.json", launch)
    export_trial(Path(directory) / "policy")
