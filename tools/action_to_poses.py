#!/usr/bin/env python3
"""W6 ① action → Panda 손 좌표 — action 을 시뮬 Panda 에 다시 넣고 스텝마다 손 자세를 남긴다.

    python -m tools.action_to_poses --log data/follow/2026_09_28-10_36_55.jsonl
    python -m tools.action_to_poses --log data/pickup/<기록>.jsonl      # W6 RGB 블록 — meta 의 bddl · register · seed

policy 가 내는 action 은 "여기로 가라" 가 아니라 **Panda OSC 에 주는 변화량**이라, 같은 값이라도 실제로
얼마나 가는지는 컨트롤러의 강성·감쇠와 현재 속도가 정한다. 그래서 곱하기로는 좌표로 못 바꾼다.
**시뮬 Panda 를 옆에서 같이 돌려 그 답을 얻는다** (`docs/W5/ACTION_MEANING.md` 1-9).

    action ──▶ 시뮬 Panda (robosuite OSC) ──▶ 손 좌표 JSONL ──▶ tools/poses_to_gcode.py ──▶ Mirobot G-code
               ───────── 이 파일 ─────────     (넘겨주는 형식)

이 파일은 LIBERO·MuJoCo 가 필요하다. 좌표 → Mirobot 은 `tools/poses_to_gcode.py` 가 맡고 표준 라이브러리만 쓴다.
`docs/W6/rgb_blocks/pickup.py --log` 는 실행하면서 같은 형식을 바로 남기므로 이 단계 없이 넘어갈 수 있다 —
그때 이 파일은 같은 action 이 같은 좌표를 내는지 보는 **재현 확인**이 된다.

남는 것
  <--out>   손 좌표 JSONL (기본 data/poses/<날짜>-<시각>.jsonl). 형식은 `docs/W6/DIVISION.md` 3장
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys
import time
from pathlib import Path

POSES_FORMAT = "panda-poses/1"
CAMERAS = ("agentview", "frontview", "sideview", "birdview")
FPS = 10
GRIPPER_OPEN = -1.0  # LIBERO get_libero_dummy_action; common/ 없이 Python 3.8에서도 실행

# `run_libero_eval.py:601` 이 스텝마다 찍는 줄 — "t: 3\t action: [ 0.1 -0.2 … ]"
EVAL_LINE_RE = re.compile(r"^t:\s*(\d+)\s+action:\s*\[([^\]]*)\]")

# eval 은 앞 10스텝을 dummy action 으로 흘려보낸 뒤 policy action 을 넣는다 (`run_libero_eval.py` NUM_STEPS_WAIT)
EVAL_WAIT_STEPS = 10


def read_actions(path: Path, episode: int | None = None) -> tuple[dict, list[list[float]]]:
    """action 열을 읽는다. 세 형식을 받는다 — 어느 쪽이든 (meta, action 목록).

    `.jsonl`   `action` 칸이 있는 줄 (`tools/libero_follow.py` · `pickup.py --log` · 이 파일이 남기는 것)
    `.hdf5`    `run_libero_eval --data_collection True` 가 남기는 episode 파일의 `actions`
    그 밖      eval 의 화면 출력. `t: … action: [ … ]` 줄을 긁는다 — 재실행 없이 쓰려고.
               한 실행에 에피소드가 여럿이면 `t` 가 줄어드는 자리로 쪼개고 `episode`(1부터)로 하나를 고른다.
               **첫 `t` 가 대기 스텝 수**다 — eval 은 대기 중에는 찍지 않는다

    eval 기록은 meta 의 `settle` 을 채운다 — 같은 궤적을 재현하려면 대기 스텝 수가 같아야 한다.
    """
    if path.suffix == ".hdf5":
        import h5py  # eval 산출물을 읽을 때만 필요하다

        with h5py.File(path, "r") as f:
            actions = [[float(v) for v in row] for row in f["actions"][:]]
            meta = {"source_kind": "eval hdf5", "settle": EVAL_WAIT_STEPS}
            if "success" in f:
                meta["success"] = bool(f["success"][()])
        return meta, actions

    if path.suffix == ".jsonl":
        meta, out = {}, []
        with path.open(encoding="utf-8") as source:
            for line in source:
                row = json.loads(line)
                if "meta" in row:
                    meta = row["meta"]
                    continue
                if row.get("action"):
                    out.append([float(v) for v in row["action"]])
        return meta, out

    episodes: list[list[tuple[int, list[float]]]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = EVAL_LINE_RE.match(line.strip())
        if not m:
            continue
        t, action = int(m.group(1)), [float(v) for v in m.group(2).split()]
        if not episodes or t <= episodes[-1][-1][0]:  # t 가 줄면 다음 에피소드
            episodes.append([])
        episodes[-1].append((t, action))
    if not episodes:
        return {"source_kind": "eval stdout"}, []
    if episode is None and len(episodes) > 1:
        raise SystemExit(f"{path} 에 에피소드가 {len(episodes)}개 있다 (길이 {[len(e) for e in episodes]}) — --episode 로 고를 것")
    k = (episode or 1) - 1
    if not 0 <= k < len(episodes):
        raise SystemExit(f"--episode 는 1~{len(episodes)}")
    chosen = episodes[k]
    meta = {"source_kind": "eval stdout", "episodes": len(episodes), "episode": k + 1, "settle": chosen[0][0]}
    return meta, [a for _, a in chosen]


def register_objects(spec: str, block_size_mm: float | None = None) -> None:
    """`파일.py:함수` 를 불러 사용자 물체를 LIBERO 에 등록한다 — BDDL 이 그 물체 이름을 쓰기 전에."""
    import importlib.util

    path, separator, func = spec.rpartition(":")
    if separator and not func:
        func = "register"
    elif not separator or not func.isidentifier():
        path, func = spec, "register"  # Windows의 C:\... 드라이브 콜론은 함수 구분자가 아니다
    module_spec = importlib.util.spec_from_file_location(Path(path).stem, path)
    if module_spec is None or module_spec.loader is None:
        raise ValueError(f"등록할 Python 파일을 불러올 수 없다: {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    register = getattr(module, func)
    if block_size_mm is not None and func == "register_blocks":
        # W6 견본은 생성 당시 크기를 기록한다. 현재 objects.py 기본값이 바뀌어도 원래 장면을 쓴다.
        register(edge_length_m=block_size_mm / 1000.0)
    else:
        register()


def _goal(row: dict) -> bool | None:
    for key in ("goal", "done"):
        value = row.get(key)
        if value is not None:
            if not isinstance(value, (bool, int)) or value not in (False, True):
                raise ValueError(f"{key} 판정은 True/False여야 한다")
            return bool(value)
    return None


def first_goal_step(path: Path, max_steps: int | None = None) -> int | None:
    """원래 action 중 Goal이 처음 뜬 순번. 짧은 재생은 그 구간만 비교한다."""
    if path.suffix != ".jsonl":
        return None
    k = 0
    with path.open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            if not row.get("action"):
                continue
            k += 1
            if max_steps is not None and k > max_steps:
                break
            if _goal(row):
                return k
    return None


def _vector(values, length: int) -> list[float]:
    result = [float(v) for v in values]
    if len(result) != length or not all(math.isfinite(v) for v in result):
        raise ValueError(f"좌표/자세는 유한한 숫자 {length}개여야 한다")
    return result


def position_error_mm(original, replayed) -> float:
    """LIBERO world의 절대 위치 차이 (3차원 거리, mm). 변위끼리 비교하지 않는다."""
    a, b = _vector(original, 3), _vector(replayed, 3)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b))) * 1000.0


def orientation_error_deg(original, replayed) -> float:
    """xyzw 쿼터니언의 최단 회전각. q와 -q는 같은 자세이고 작은 오차도 보존한다."""
    a, b = _vector(original, 4), _vector(replayed, 4)
    na, nb = math.hypot(*a), math.hypot(*b)
    if na == 0 or nb == 0:
        raise ValueError("길이가 0인 쿼터니언은 자세가 아니다")
    a, b = [v / na for v in a], [v / nb for v in b]
    if sum(x * y for x, y in zip(a, b)) < 0:
        b = [-v for v in b]
    difference = math.hypot(*(x - y for x, y in zip(a, b)))
    total = math.hypot(*(x + y for x, y in zip(a, b)))
    return math.degrees(4.0 * math.atan2(difference, total))


def compare_replay(path: Path, replay_meta: dict, replay_rows: list[dict]) -> dict | None:
    """원래 기록의 n번째 action 결과와 재생의 n번째 결과를 비교한다.

    원래 step 라벨이 0부터이거나 중간에 result 줄이 있어도 read_actions와 같은 순번으로 맞춘다.
    없는 좌표는 0 오차로 취급하지 않고 비교 개수를 따로 남긴다.
    """
    if path.suffix != ".jsonl":
        return None  # action만 담긴 eval stdout/HDF5에는 손 자세 기준값이 없다
    original_meta, original_rows = {}, []
    with path.open(encoding="utf-8") as source:
        for line in source:
            row = json.loads(line)
            if "meta" in row:
                original_meta = row["meta"]
            elif row.get("action"):
                original_rows.append(row)
    if len(replay_rows) > len(original_rows):
        raise ValueError("재생 action 수가 원래 기록보다 많다")
    summary = {"source_actions": len(original_rows), "replayed_actions": len(replay_rows),
               "position_compared": 0, "orientation_compared": 0,
               "max_position_mm": None, "max_position_step": None,
               "max_orientation_deg": None, "max_orientation_step": None,
               "mean_position_mm": None, "last_position_mm": None,
               "mean_orientation_deg": None, "last_orientation_deg": None,
               "start_position_mm": None, "start_orientation_deg": None,
               "goal_compared": 0, "goal_mismatch_steps": []}
    errors = {"eef_pos": [], "eef_quat_xyzw": []}
    for key, metric, name in (("start_eef_pos", position_error_mm, "start_position_mm"),
                              ("start_eef_quat_xyzw", orientation_error_deg, "start_orientation_deg")):
        if original_meta.get(key) is not None and replay_meta.get(key) is not None:
            summary[name] = metric(original_meta[key], replay_meta[key])
    for k, (original, replayed) in enumerate(zip(original_rows, replay_rows), 1):
        for key, metric, count, maximum, at in (
                ("eef_pos", position_error_mm, "position_compared", "max_position_mm", "max_position_step"),
                ("eef_quat_xyzw", orientation_error_deg, "orientation_compared",
                 "max_orientation_deg", "max_orientation_step")):
            if original.get(key) is None or replayed.get(key) is None:
                continue
            error = metric(original[key], replayed[key])
            errors[key].append(error)
            summary[count] += 1
            if summary[maximum] is None or error > summary[maximum]:
                summary[maximum], summary[at] = error, k
            if k == len(replay_rows):
                summary["last_position_mm" if key == "eef_pos" else "last_orientation_deg"] = error
        original_goal, replayed_goal = _goal(original), _goal(replayed)
        if original_goal is not None and replayed_goal is not None:
            summary["goal_compared"] += 1
            if original_goal != replayed_goal:
                summary["goal_mismatch_steps"].append(k)
    for key, mean in (("eef_pos", "mean_position_mm"), ("eef_quat_xyzw", "mean_orientation_deg")):
        if errors[key]:
            summary[mean] = math.fsum(errors[key]) / len(errors[key])
    return summary


def _simulation_imports():
    """시뮬 의존성은 실행할 때만 불러온다. 수치 비교는 표준 라이브러리만 쓴다."""
    os.environ.setdefault("MUJOCO_GL", "wgl" if sys.platform == "win32" else "egl")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    if sys.platform == "win32":
        os.environ.setdefault("NUMBA_DISABLE_JIT", "1")
    file_handler = logging.FileHandler

    def no_robosuite_file(filename, *args, **kwargs):
        if str(filename).replace("\\", "/") == "/tmp/robosuite.log":
            return logging.NullHandler()
        return file_handler(filename, *args, **kwargs)

    if sys.platform == "win32":
        logging.FileHandler = no_robosuite_file
    try:
        from libero.libero import benchmark, get_libero_path
        from libero.libero.envs import OffScreenRenderEnv
    finally:
        logging.FileHandler = file_handler
    return benchmark, get_libero_path, OffScreenRenderEnv


def grid_frame(obs, caption: str):
    """기존 --video의 네 카메라 격자. 영상 요청 때만 영상 의존성을 불러온다."""
    import numpy as np
    from PIL import Image, ImageDraw

    tiles = []
    for camera in CAMERAS:
        tile = Image.fromarray(np.flipud(obs[f"{camera}_image"]).copy())
        draw = ImageDraw.Draw(tile)
        draw.rectangle([0, tile.height - 14, 8 + 7 * len(camera), tile.height], fill=(0, 0, 0))
        draw.text((4, tile.height - 13), camera, fill=(255, 255, 0))
        tiles.append(np.array(tile))
    grid = Image.fromarray(np.vstack([np.hstack(tiles[:2]), np.hstack(tiles[2:])]))
    draw = ImageDraw.Draw(grid)
    draw.rectangle([0, 0, grid.width, 16], fill=(0, 0, 0))
    draw.text((4, 2), caption, fill=(255, 255, 255))
    return np.array(grid)


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """action 을 읽고 장면을 세우는 옵션 — `tools/action_to_gcode.py` 도 그대로 쓴다."""
    parser.add_argument("--log", type=Path, required=True,
                        help="action 기록 — jsonl, eval HDF5, eval 화면 출력 (read_actions)")
    parser.add_argument("--episode", type=int, help="eval 화면 출력에 에피소드가 여럿일 때 몇 번째인가 (1부터)")
    parser.add_argument("--settle", type=int, help="시작 전 dummy 스텝. 기본은 기록 meta 의 값 (없으면 30)")
    parser.add_argument("--max-steps", type=int, help="앞에서부터 이만큼만 (빠른 확인용)")
    parser.add_argument("--video", action="store_true", help="MP4 도 남긴다 (느리다)")
    parser.add_argument("--suite", default="libero_90")
    parser.add_argument("--task-name", default="KITCHEN_SCENE1_open_the_top_drawer_of_the_cabinet")
    parser.add_argument("--task-id", type=int, help="suite 안의 태스크 번호. 주면 --task-name 대신 쓴다 "
                        "(eval 은 태스크 0 부터 차례로 돌므로 에피소드 순서와 맞다)")
    parser.add_argument("--bddl", type=Path, help="suite 밖의 BDDL. 주면 suite·태스크·초기 상태 대신 seed 로 reset 한다. "
                        "없으면 기록 meta 의 bddl")
    parser.add_argument("--register", help="BDDL 전에 부를 물체 등록 `파일.py:함수`. 없으면 기록 meta 의 register")
    parser.add_argument("--seed", type=int, help="--bddl 장면의 reset seed. 없으면 기록 meta 의 seed (없으면 0)")
    parser.add_argument("--init-state", type=int, default=0,
                        help="초기 상태 번호. eval 은 회차 번호를 그대로 쓴다 (1회차 = 0)")
    parser.add_argument("--res", type=int, default=384)
    parser.add_argument("--video-dir", "--out-dir", dest="video_dir", type=Path,
                        default=Path("rollouts") / time.strftime("%Y_%m_%d") / "translate",
                        help="--video 를 남길 폴더 (예전 이름 --out-dir)")


def simulate(args) -> tuple[dict, list[dict]]:
    """action 을 시뮬 Panda 에 넣는다. (meta, 스텝별 행) — 형식은 `docs/W6/DIVISION.md` 3장."""
    src_meta, actions = read_actions(args.log, args.episode)
    if src_meta.get("scenario", "none") != "none":
        raise SystemExit("scenario가 none이 아닌 기록은 초기 이웃 배치 복원이 필요하다. "
                         "현재 재생 검증은 scenario=none만 지원한다")
    if args.max_steps:
        actions = actions[:args.max_steps]
    if not actions:
        raise SystemExit(f"{args.log} 에 action 칸이 있는 줄이 없다")
    settle = args.settle if args.settle is not None else src_meta.get("settle", 30)
    if settle < 0 or (args.max_steps is not None and args.max_steps < 1):
        raise SystemExit("--settle은 0 이상, --max-steps는 1 이상이어야 한다")
    benchmark, get_libero_path, OffScreenRenderEnv = _simulation_imports()

    custom_bddl = args.bddl or src_meta.get("bddl")
    seed = args.seed if args.seed is not None else src_meta.get("seed", 0)
    if custom_bddl:
        # suite 밖의 장면 — 초기 상태 파일이 없으니 원래 실행과 같은 seed 로 reset 해서 같은 배치를 만든다
        suite = task_id = None
        bddl = str(custom_bddl)
        task_name = src_meta.get("task") or Path(bddl).stem
        scene = f"{bddl} (seed {seed})"
        register = args.register or src_meta.get("register")
        if register:
            register_objects(register, src_meta.get("block_size_mm"))
    else:
        if args.task_id is not None:
            suite, task_id = benchmark.get_benchmark_dict()[args.suite](), args.task_id
        else:
            suite = benchmark.get_benchmark_dict()[args.suite]()
            task_id = next((k for k in range(suite.n_tasks)
                            if suite.get_task(k).name == args.task_name), None)
            if task_id is None:
                raise SystemExit(f"{args.suite} 에 {args.task_name!r} 이 없다")
        task = suite.get_task(task_id)
        task_name = task.name
        scene = f"{args.suite} 태스크 {task_id} ({task_name}), 초기 상태 {args.init_state}"
        bddl = os.path.join(get_libero_path("bddl_files"), task.problem_folder, task.bddl_file)

    # HORIZON — robosuite 는 `horizon` 뒤에 에피소드를 끝내고 그 다음 step 에서 죽는다 (libero_follow 와 같은 이유)
    horizon = settle + len(actions) + 10
    env = OffScreenRenderEnv(bddl_file_name=bddl, camera_names=list(CAMERAS),
                             camera_heights=args.res, camera_widths=args.res, horizon=horizon)
    rows, frames, n = [], [], 0
    try:
        if custom_bddl:
            env.seed(seed)
            obs = env.reset()
        else:
            env.seed(0)
            env.reset()
            obs = env.set_init_state(suite.get_task_init_states(task_id)[args.init_state])
        # 대기 동작은 eval 의 `get_libero_dummy_action` · libero_follow 와 같게 — 그리퍼 정확히 −1.
        # 정책 action 의 그리퍼는 −1.005 처럼 살짝 넘치므로 첫 action 에서 빌려 오면 안 된다
        dummy = [0.0] * 6 + [GRIPPER_OPEN]
        for _ in range(settle):
            obs, *_ = env.step(dummy)
            n += 1
            if args.video:
                frames.append(grid_frame(obs, f"settle {n}/{settle}"))
        # 짝의 Panda 쪽 — 첫 action 직전의 손 자세
        start_pos = obs["robot0_eef_pos"]
        start_quat_xyzw = [float(v) for v in obs["robot0_eef_quat"]]

        first_done = None
        for k, action in enumerate(actions, 1):
            obs, _, done, _ = env.step(action)
            if done and first_done is None:
                first_done = k
            n += 1
            p_grip = obs["robot0_eef_pos"]
            rows.append({"step": k, "action": list(action), "done": bool(done),
                         "eef_pos": [float(v) for v in p_grip],
                         "eef_quat_xyzw": [float(v) for v in obs["robot0_eef_quat"]]})
            if args.video:
                frames.append(grid_frame(obs, f"step {k}/{len(actions)}"))
    finally:
        env.close()

    meta = {"format": POSES_FORMAT, "producer": "tools/action_to_poses.py", "source": str(args.log),
            "scene": scene, "suite": None if custom_bddl else args.suite, "task_id": task_id,
            "bddl": bddl if custom_bddl else None, "seed": seed if custom_bddl else None,
            "init_state": None if custom_bddl else args.init_state, "source_meta": src_meta,
            "task": task_name, "actions": len(actions), "settle": settle, "horizon": horizon,
            "pos_unit": "m, world", "point": "grip (robot0_eef_pos)", "quat_order_raw": "xyzw",
            "start_eef_pos": [float(v) for v in start_pos], "start_eef_quat_xyzw": start_quat_xyzw,
            "first_done": first_done, "expected_done": first_goal_step(args.log, len(actions)),
            "custom_scene": bool(custom_bddl)}
    if custom_bddl:
        meta["register"] = register
    for key in ("mode", "instruction", "target", "scenario", "block_size_mm"):
        if key in src_meta:
            meta[key] = src_meta[key]
    meta["replay_comparison"] = compare_replay(args.log, meta, rows)
    if args.video:
        import imageio
        from PIL import Image

        args.video_dir.mkdir(parents=True, exist_ok=True)
        stem = args.video_dir / time.strftime("%H_%M_%S")
        imageio.mimwrite(f"{stem}--translate.mp4", frames, fps=FPS)
        Image.fromarray(frames[-1]).save(f"{stem}--last.png")
        print(f"saved {stem}--translate.mp4  ({len(frames)} frames)")
    return meta, rows


def report_replay(meta: dict, steps: int) -> None:
    """재현 검산 — 같은 장면·같은 action 이면 과제 성공이 같은 스텝에서 처음 떠야 한다."""
    first_done, expected = meta["first_done"], meta["expected_done"]
    comparison = meta.get("replay_comparison")
    if comparison is not None and comparison["goal_compared"]:
        # 원래 실행의 기록에 스텝마다 goal 이 있으니 같은 스텝에서 처음 뜨는지로 재현을 본다
        same = "같다" if first_done == expected else "!! 다르다 — 재현이 안 됐다"
        print(f"첫 Goal action — 재실행 {first_done} / 원래 {expected}  {same}")
    elif meta["custom_scene"]:
        print(f"과제 성공 판정 — 재실행 {first_done} / 원래 Goal 기록 없음")
    elif first_done is None:
        print(f"과제 성공 판정 — 없음 ({steps}스텝 동안)")
    else:
        # eval 은 과제 성공(done)이 뜨는 순간 멈춘다 — 마지막 action 에서 처음 떠야 같은 장면이다 (10/1 대조).
        # 대기 10 vs 30 같은 작은 차이는 못 가린다 — 자세까지 같은지는 eval 의 proprio 와 대야 안다
        same = ("  ← 마지막 action. eval 과 같은 결과 (자세 일치는 proprio 로 확인)" if first_done == steps
                else "  ← 마지막이 아니다")
        print(f"과제 성공 판정 — 스텝 {first_done} / {steps}{same}")
    if comparison is None:
        print("손 좌표 비교 — 원래 기록에 위치·자세 기준값이 없음")
        return
    print(f"재현 비교 — 원래 {comparison['source_actions']} action 중 앞 {comparison['replayed_actions']}개")
    for count, maximum, at, label, unit in (
            ("position_compared", "max_position_mm", "max_position_step", "절대 위치", "mm"),
            ("orientation_compared", "max_orientation_deg", "max_orientation_step", "자세 회전각", "°")):
        if comparison[count]:
            print(f"  {label}: {comparison[count]}/{steps}개 비교, 최대 {comparison[maximum]:.9g} {unit} "
                  f"(action {comparison[at]})")
        else:
            print(f"  {label}: 비교할 기준값 없음")
    for key, label, unit in (("start_position_mm", "시작 절대 위치", "mm"),
                             ("start_orientation_deg", "시작 자세", "°")):
        if comparison[key] is not None:
            print(f"  {label}: {comparison[key]:.9g} {unit}")
    if comparison["goal_compared"]:
        print(f"  Goal: {comparison['goal_compared']}/{steps}개 비교, "
              f"불일치 {len(comparison['goal_mismatch_steps'])}개")


def write_poses(path: Path, meta: dict, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        out.write(json.dumps({"meta": meta}, ensure_ascii=False) + "\n")
        for row in rows:
            out.write(json.dumps(row) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_arguments(parser)
    parser.add_argument("--out", type=Path, help="손 좌표 JSONL. 기본 data/poses/<날짜>-<시각>.jsonl")
    args = parser.parse_args()
    meta, rows = simulate(args)
    out = args.out or Path("data") / "poses" / f"{time.strftime('%Y_%m_%d-%H_%M_%S')}.jsonl"
    write_poses(out, meta, rows)
    print(f"action {len(rows)}개 — {args.log}  ({meta['scene']}, settle {meta['settle']})")
    print(f"시작 손 좌표 {[round(v, 4) for v in meta['start_eef_pos']]} m")
    report_replay(meta, len(rows))
    print(f"saved {out}")


if __name__ == "__main__":
    main()
