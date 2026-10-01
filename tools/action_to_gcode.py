#!/usr/bin/env python3
"""W5 ① 번역기 — action 을 시뮬 Panda 에 넣고, 그 손 자세를 Mirobot G-code 로 옮긴다. (서버 .venv 전용)

    # 기록에 남은 action 열로 끝까지 도는지 본다
    python -m tools.action_to_gcode --log data/follow/2026_09_28-10_36_55.jsonl
    python -m tools.run_gcode <나온 파일> --dry-run        # 도달 범위 경고가 있나

policy 가 내는 action 은 "여기로 가라" 가 아니라 **Panda OSC 에 주는 변화량**이라, 같은 값이라도 실제로
얼마나 가는지는 컨트롤러의 강성·감쇠와 현재 속도가 정한다. 그래서 곱하기로는 Mirobot 좌표로 못 바꾼다.

**시뮬 Panda 를 옆에서 같이 돌려 그 답을 얻는다** (`docs/W5/ACTION_MEANING.md` 1-9). robosuite OSC 는
LIBERO 학습 때와 같은 컨트롤러라 근사가 없다. Mirage 공개 코드도 실제로는 이 방식이다.

    action ──▶ 시뮬 Panda (robosuite OSC) ──▶ 손 자세 ──▶ 좌표 변환 ──▶ Mirobot G0 (절대)
                 여기가 번역기                            common/workspace.py

**이 도구는 열린 고리다** — 받은 action 을 그대로 넣고 나온 자세를 적을 뿐, 실물이 어디 있는지 보지 않는다.
실제 운용에서는 chunk 사이에 시뮬 Panda 를 Mirobot 의 실제 자세로 다시 데려다 놓아야 한다 (CHECKLIST 2-4).

남는 것
  <--out>                              Mirobot G-code (`; point` 머리말이 붙는다)
  data/translate/<날짜>-<시각>.jsonl    스텝마다 action·Panda 자세·Mirobot 명령
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import time
from pathlib import Path

from tools.libero_axis_probe import CAMERAS, FPS, find_task, grid_frame, read_pose  # 환경 변수도 여기서 정해진다
from tools.run_gcode import ANGLE_WARN_DEG, REACH_WARN_MM

import imageio
import numpy as np
from libero.libero import benchmark, get_libero_path
from libero.libero.envs import OffScreenRenderEnv
from PIL import Image

from common.rotation import (
    libero_to_mirobot_quat,
    quat_conj,
    quat_mul,
    quat_to_euler_xyz_deg,
)
from common.servo import GRIPPER_OPEN
from common.workspace import (
    DEFAULT_MAPPING,
    DEFAULT_POINT,
    MAPPINGS,
    POINTS,
    grip_to_flange,
    libero_to_mirobot_flange_mm,
    pair_marker,
    point_marker,
    resolve_mapping,
)


# `run_libero_eval.py:601` 이 스텝마다 찍는 줄 — "t: 3\t action: [ 0.1 -0.2 … ]"
EVAL_LINE_RE = re.compile(r"^t:\s*(\d+)\s+action:\s*\[([^\]]*)\]")


# eval 은 앞 10스텝을 dummy action 으로 흘려보낸 뒤 policy action 을 넣는다 (`run_libero_eval.py` NUM_STEPS_WAIT)
EVAL_WAIT_STEPS = 10


def read_actions(path: Path, episode: int | None = None) -> tuple[dict, list[list[float]]]:
    """action 열을 읽는다. 세 형식을 받는다 — 어느 쪽이든 (meta, action 목록).

    `.jsonl`   `action` 칸이 있는 줄 (`tools/libero_follow.py` · `tools/action_to_gcode.py` 가 남기는 것)
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
        for line in path.open(encoding="utf-8"):
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--log", type=Path, required=True,
                        help="action 기록 — jsonl, eval HDF5, eval 화면 출력 (read_actions)")
    parser.add_argument("--episode", type=int, help="eval 화면 출력에 에피소드가 여럿일 때 몇 번째인가 (1부터)")
    parser.add_argument("--out", type=Path, help="쓸 G-code. 기본은 trajectories/<날짜>-translated-<원본이름>.gcode")
    parser.add_argument("--orientation", choices=("absolute", "relative"), default="absolute",
                        help="Mirobot 자세를 월드 기준으로 적을지, 시작 자세로부터의 회전으로 적을지")
    parser.add_argument("--point", choices=POINTS, default=DEFAULT_POINT, help="어느 점끼리 맞추나")
    parser.add_argument("--mapping", choices=sorted(MAPPINGS), default=DEFAULT_MAPPING,
                        help="Mirobot 쪽 짝과 배율 (common/workspace.py MAPPINGS). candidate 는 10/1 후보 — 실물 확인 전")
    parser.add_argument("--scale", type=float, help="배율만 덮어쓴다 (짝은 --mapping 그대로)")
    parser.add_argument("--settle", type=int, help="시작 전 dummy 스텝. 기본은 기록 meta 의 값 (없으면 30)")
    parser.add_argument("--every", type=int, default=1,
                        help="N 스텝마다 한 줄만 적는다. Mirobot 이 20Hz 를 못 따라갈 때 (CHECKLIST 2-4)")
    parser.add_argument("--chunk", type=int, default=16, help="라벨에 쓸 chunk 길이. policy 가 한 번에 내는 수")
    parser.add_argument("--max-steps", type=int, help="앞에서부터 이만큼만 (빠른 확인용)")
    parser.add_argument("--video", action="store_true", help="MP4 도 남긴다 (느리다)")
    parser.add_argument("--suite", default="libero_90")
    parser.add_argument("--task-name", default="KITCHEN_SCENE1_open_the_top_drawer_of_the_cabinet")
    parser.add_argument("--task-id", type=int, help="suite 안의 태스크 번호. 주면 --task-name 대신 쓴다 "
                        "(eval 은 태스크 0 부터 차례로 돌므로 에피소드 순서와 맞다)")
    parser.add_argument("--init-state", type=int, default=0,
                        help="초기 상태 번호. eval 은 회차 번호를 그대로 쓴다 (1회차 = 0)")
    parser.add_argument("--res", type=int, default=384)
    parser.add_argument("--out-dir", type=Path, default=Path("rollouts") / time.strftime("%Y_%m_%d") / "translate")
    parser.add_argument("--log-dir", type=Path, default=Path("data") / "translate")
    args = parser.parse_args()

    src_meta, actions = read_actions(args.log, args.episode)
    if args.max_steps:
        actions = actions[:args.max_steps]
    if not actions:
        raise SystemExit(f"{args.log} 에 action 칸이 있는 줄이 없다")
    settle = args.settle if args.settle is not None else src_meta.get("settle", 30)
    try:
        ref_mirobot, scale = resolve_mapping(args.mapping, args.point)
    except ValueError as e:
        raise SystemExit(str(e))
    if args.scale is not None:
        scale = args.scale

    if args.task_id is not None:
        suite, task_id = benchmark.get_benchmark_dict()[args.suite](), args.task_id
    else:
        suite, task_id = find_task(args.suite, args.task_name)
    task = suite.get_task(task_id)
    bddl = os.path.join(get_libero_path("bddl_files"), task.problem_folder, task.bddl_file)
    stamp = time.strftime("%H_%M_%S")

    args.log_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.log_dir / f"{time.strftime('%Y_%m_%d')}-{stamp}.jsonl"
    out_path = args.out or Path("trajectories") / f"{time.strftime('%Y_%m_%d')}-translated-{args.log.stem}.gcode"

    # HORIZON — robosuite 는 `horizon` 뒤에 에피소드를 끝내고 그 다음 step 에서 죽는다 (libero_follow 와 같은 이유)
    horizon = settle + len(actions) + 10

    env = OffScreenRenderEnv(bddl_file_name=bddl, camera_names=list(CAMERAS),
                             camera_heights=args.res, camera_widths=args.res, horizon=horizon)
    rows, frames, n = [], [], 0
    log = log_path.open("w")
    try:
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

        p_grip, q = read_pose(obs)
        ref_flange = grip_to_flange(p_grip, q)
        ref_q = q
        log.write(json.dumps({"meta": {"source": str(args.log), "suite": args.suite, "task_id": task_id,
                                       "init_state": args.init_state, "source_meta": src_meta,
                                       "task": task.name, "actions": len(actions),
                                       "settle": settle, "orientation": args.orientation, "point": args.point,
                                       "every": args.every, "horizon": horizon, "mapping": args.mapping,
                                       "ref_mirobot_mm": list(ref_mirobot), "scale": scale,
                                       "start_flange_m": list(ref_flange),
                                       "start_quat_wxyz": list(ref_q)}}, ensure_ascii=False) + "\n")

        print(f"action {len(actions)}개 — {args.log}")
        print(f"settle {settle}, orientation {args.orientation}, point {args.point}, every {args.every}")
        print(f"짝 {args.mapping} — Mirobot 쪽 {tuple(round(v, 2) for v in ref_mirobot)} mm, 배율 {scale:g}")
        print(f"시작 플랜지 {np.round(ref_flange, 4)} m\n")

        first_done = None
        for k, action in enumerate(actions, 1):
            obs, _, done, _ = env.step(action)
            if done and first_done is None:
                first_done = k
            n += 1
            p_grip, q = read_pose(obs)
            flange = grip_to_flange(p_grip, q)
            q_mirobot = (libero_to_mirobot_quat(q) if args.orientation == "absolute"
                         else quat_mul(q, quat_conj(ref_q)))
            xyz = libero_to_mirobot_flange_mm(flange, q, q_mirobot, ref_flange, ref_q, args.point, scale, ref_mirobot)
            abc = quat_to_euler_xyz_deg(q_mirobot)
            row = {"step": k, "chunk": (k - 1) // args.chunk + 1, "action": list(action), "done": bool(done),
                   "eef_pos": [float(v) for v in p_grip],
                   "eef_quat_xyzw": [float(v) for v in obs["robot0_eef_quat"]],
                   "mirobot_xyz_mm": [round(v, 2) for v in xyz], "mirobot_abc_deg": [round(v, 2) for v in abc],
                   "reach_mm": round(math.hypot(xyz[0], xyz[1]), 2)}
            rows.append(row)
            log.write(json.dumps(row) + "\n")
            if args.video:
                frames.append(grid_frame(obs, f"step {k}/{len(actions)}  reach {row['reach_mm']:.0f}mm"))
    finally:
        env.close()
        log.close()

    kept = [r for r in rows if r["step"] % args.every == 0 or r["step"] == len(rows)]
    which = "파지점 ↔ 파지점" if args.point == "grip" else "플랜지 ↔ 플랜지"
    pair = f"{which}, Panda 시작 ↔ Mirobot {tuple(round(v, 2) for v in ref_mirobot)} (짝 {args.mapping}), 배율 {scale:g}"
    lines = [f"; 번역기 — action → 시뮬 Panda → Mirobot  (tools/action_to_gcode.py)",
             f"; action 출처 {args.log}  {args.suite} 태스크 {task_id} ({task.name}), 초기 상태 {args.init_state}",
             f"; F = x축 180°, {pair}, orientation {args.orientation}",
             f"; action {len(rows)}개 중 {len(kept)}줄 (every {args.every}), chunk {args.chunk}",
             point_marker(args.point), pair_marker(ref_mirobot, scale), "G90", "M20"]
    for r in kept:
        x, y, z = r["mirobot_xyz_mm"]
        a, b, c = r["mirobot_abc_deg"]
        lines += [f"; c{r['chunk']:02d}s{r['step']:04d}",
                  f"G0 X{x:.2f} Y{y:.2f} Z{z:.2f} A{a:.2f} B{b:.2f} C{c:.2f}"]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    reach = max(r["reach_mm"] for r in kept)
    angle = max(max(abs(v) for v in r["mirobot_abc_deg"]) for r in kept)
    z_lo = min(r["mirobot_xyz_mm"][2] for r in kept)
    over_reach = [r["step"] for r in kept if r["reach_mm"] > REACH_WARN_MM]
    over_angle = [r["step"] for r in kept if max(abs(v) for v in r["mirobot_abc_deg"]) > ANGLE_WARN_DEG]
    print(f"{'스텝':>6} {'chunk':>5} | {'X':>8} {'Y':>8} {'Z':>8} mm | {'A':>7} {'B':>7} {'C':>7} ° | {'수평':>6}")
    for r in kept[:3] + (["..."] if len(kept) > 6 else []) + kept[-3:]:
        if r == "...":
            print(f"{'...':>6}")
            continue
        x, y, z = r["mirobot_xyz_mm"]
        a, b, c = r["mirobot_abc_deg"]
        print(f"{r['step']:6d} {r['chunk']:5d} | {x:8.2f} {y:8.2f} {z:8.2f} | {a:7.2f} {b:7.2f} {c:7.2f} | {r['reach_mm']:6.1f}")
    print(f"\n{len(rows)}스텝 → G0 {len(kept)}줄.  수평 최대 {reach:.1f}mm (경고선 {REACH_WARN_MM:.0f}), "
          f"각도 최대 {angle:.1f}° (경고선 {ANGLE_WARN_DEG:.0f}), Z 최저 {z_lo:.1f}mm")
    if over_reach:
        print(f"  !! 수평 경고선 넘은 줄 {len(over_reach)}개 — 처음 {over_reach[:5]}")
    if over_angle:
        print(f"  !! 각도 경고선 넘은 줄 {len(over_angle)}개 — 처음 {over_angle[:5]}")
    if not over_reach and not over_angle:
        print("  경고 없음")
    # 재현 검산 — eval 은 과제 성공(done)이 뜨는 순간 멈춘다. 같은 장면·같은 action 이면 마지막 action 에서 처음 떠야 한다.
    # 장면이 다르면 안 뜬다(10/1 대조). 다만 대기 10 vs 30 같은 작은 차이는 못 가린다 — 자세까지 같은지는
    # eval 의 proprio(`--data_collection True`)와 대야 안다
    if first_done is None:
        print(f"과제 성공 판정 — 없음 ({len(rows)}스텝 동안)")
    else:
        same = ("  ← 마지막 action. eval 과 같은 결과 (자세 일치는 proprio 로 확인)" if first_done == len(rows)
                else "  ← 마지막이 아니다")
        print(f"과제 성공 판정 — 스텝 {first_done} / {len(rows)}{same}")
    print(f"saved {out_path}\nsaved {log_path}")

    if args.video:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        stem = args.out_dir / stamp
        imageio.mimwrite(f"{stem}--translate.mp4", frames, fps=FPS)
        Image.fromarray(frames[-1]).save(f"{stem}--last.png")
        print(f"saved {stem}--translate.mp4  ({len(frames)} frames)")


if __name__ == "__main__":
    main()
