#!/usr/bin/env python3
"""W3 ④ Panda 추종 루프 — 목표 자세 목록을 하나씩 찾아간다. (서버 cosmos-policy .venv 전용)

목표를 고정하고 매 스텝 `(목표 − 현재)` 로 액션을 다시 계산한다 (`docs/W3/CONTROL.md` 3절 ③).
waypoint 에 **도착하고 멈춘 것**을 확인한 뒤 다음으로 간다 — 이번 주는 시간을 보지 않기 때문이다.

    # 검증: 우리가 만든 복합 동작을 다시 따라가 본다
    python -m tools.libero_follow --rollout data/compound/2026_09_17-10_44_39.jsonl

    # 5-1: Mirobot 좌표(G-code)를 LIBERO 목표로 바꿔 따라간다
    python -m tools.libero_follow --gcode trajectories/2026_09_17-compound-relative.gcode

목표는 **플랜지 자세**로 다룬다. 컨트롤러가 움직이는 점은 파지점이라, 넣기 전에 파지점 목표로 바꾼다
(`common/workspace.py`, CONTROL.md 2절).

남는 것
  rollouts/<날짜>/follow/<시각>--follow.mp4        2×2 격자
  rollouts/<날짜>/follow/<시각>--keyframes.png     waypoint 도착 장면
  data/follow/<날짜>-<시각>.jsonl                  스텝마다 원본 값, waypoint 도착 표시
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path

from tools.libero_axis_probe import CAMERAS, FPS, find_task, grid_frame, read_pose  # 환경 변수도 여기서 정해진다
from tools.run_gcode import parse_file, pose_of

import imageio
import numpy as np
from libero.libero import get_libero_path
from libero.libero.envs import OffScreenRenderEnv
from PIL import Image

from common.rotation import euler_xyz_deg_to_quat, mirobot_to_libero_quat, quat_mul
from common.servo import GRIPPER_OPEN, pose_gap, servo_action
from common.workspace import flange_to_grip, grip_to_flange, mirobot_to_libero_xyz_m

STILL_POS_MM = 0.3   # 한 스텝에 이만큼도 안 움직이면 섰다고 본다
STILL_ROT_DEG = 0.05


def targets_from_rollout(path: Path):
    """롤아웃 기록의 waypoint → (이름, 플랜지 위치 m, 플랜지 자세 wxyz). 검증용."""
    from common.rotation import quat_xyzw_to_wxyz

    out = []
    for line in path.open():
        row = json.loads(line)
        if row.get("waypoint"):
            out.append((row["waypoint"], tuple(row["flange_pos"]), quat_xyzw_to_wxyz(tuple(row["flange_quat_xyzw"]))))
    return out


def targets_from_gcode(path: Path, ref_flange_m, ref_quat=None):
    """Mirobot G-code → LIBERO 목표. 기준점은 "Mirobot 홈 ↔ 지금 Panda 플랜지" (LIBERO_AXES.md 4절).

    `ref_quat` 를 주면 **relative** 로 읽는다 — G-code 의 자세를 "시작 자세로부터의 회전" 으로 보고
    지금 Panda 시작 자세에 얹는다. 없으면 absolute (`q ⊗ F`).
    `tools/libero_to_mirobot_gcode.py --orientation` 과 같은 뜻이고, 파일을 만든 쪽과 읽는 쪽이 어긋나면
    시작 기울기만큼(3.3°) 전체가 어긋난다.
    """
    out = []
    for label, command in parse_file(path):
        pose = pose_of(command)
        if pose is None:
            continue
        q_mirobot = euler_xyz_deg_to_quat(*pose[3:6])
        q_libero = quat_mul(q_mirobot, ref_quat) if ref_quat is not None else mirobot_to_libero_quat(q_mirobot)
        out.append((label or f"wp{len(out) + 1}", mirobot_to_libero_xyz_m(pose[:3], ref_flange_m), q_libero))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--rollout", type=Path, help="롤아웃 jsonl 의 waypoint 를 목표로 (검증용)")
    source.add_argument("--gcode", type=Path, help="Mirobot G-code 를 변환해 목표로 (5-1)")
    parser.add_argument("--orientation", choices=("absolute", "relative"), default="absolute",
                        help="--gcode 를 만들 때 쓴 것과 같은 값으로. relative 는 시작 자세로부터의 회전으로 읽는다")
    parser.add_argument("--settle", type=int, default=30, help="시작 전 dummy 스텝")
    parser.add_argument("--max-steps", type=int, default=60, help="waypoint 하나에 쓸 최대 스텝")
    parser.add_argument("--pos-tol", type=float, default=2.0, help="도착 판정 위치 오차 (mm)")
    parser.add_argument("--rot-tol", type=float, default=1.0, help="도착 판정 자세 오차 (도)")
    parser.add_argument("--suite", default="libero_90")
    parser.add_argument("--task-name", default="KITCHEN_SCENE1_open_the_top_drawer_of_the_cabinet")
    parser.add_argument("--res", type=int, default=384)
    parser.add_argument("--out", type=Path, default=Path("rollouts") / time.strftime("%Y_%m_%d") / "follow")
    parser.add_argument("--log-dir", type=Path, default=Path("data") / "follow")
    args = parser.parse_args()

    suite, task_id = find_task(args.suite, args.task_name)
    task = suite.get_task(task_id)
    bddl = os.path.join(get_libero_path("bddl_files"), task.problem_folder, task.bddl_file)
    stamp = time.strftime("%H_%M_%S")
    dummy = [0.0] * 6 + [GRIPPER_OPEN]

    args.log_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.log_dir / f"{time.strftime('%Y_%m_%d')}-{stamp}.jsonl"
    log = log_path.open("w")

    env = OffScreenRenderEnv(bddl_file_name=bddl, camera_names=list(CAMERAS),
                             camera_heights=args.res, camera_widths=args.res)
    frames, keyframes, results, n = [], [], [], 0
    try:
        env.seed(0)
        env.reset()
        obs = env.set_init_state(suite.get_task_init_states(task_id)[0])
        sim = env.env.sim
        for k in range(1, args.settle + 1):
            obs, *_ = env.step(dummy)
            n += 1
            frames.append(grid_frame(obs, f"settle {k}/{args.settle}"))
        keyframes.append(frames[-1])

        p_grip, q = read_pose(obs)
        start_flange = grip_to_flange(p_grip, q)
        targets = (targets_from_rollout(args.rollout) if args.rollout
                   else targets_from_gcode(args.gcode, start_flange,
                                           q if args.orientation == "relative" else None))
        log.write(json.dumps({"meta": {"source": str(args.rollout or args.gcode), "task": task.name,
                                       "start_flange_m": list(start_flange), "targets": len(targets),
                                       "pos_tol_mm": args.pos_tol, "rot_tol_deg": args.rot_tol,
                                       "max_steps": args.max_steps}}, ensure_ascii=False) + "\n")
        print(f"목표 {len(targets)}개 — {args.rollout or args.gcode}"
              f"{'  (orientation relative)' if args.gcode and args.orientation == 'relative' else ''}")
        print(f"시작 플랜지 {np.round(start_flange, 4)} m\n")
        print(f"{'waypoint':12} | {'스텝':>4} | {'남은 위치':>9} {'남은 자세':>9} | {'처음 거리':>9} | 결과")

        for label, t_flange, t_quat in targets:
            t_grip = flange_to_grip(t_flange, t_quat)
            first = pose_gap(read_pose(obs)[0], read_pose(obs)[1], t_grip, t_quat)
            prev_p, prev_q, steps, why = None, None, 0, "최대 스텝"
            for steps in range(1, args.max_steps + 1):
                p, q = read_pose(obs)
                action = servo_action(p, q, t_grip, t_quat)
                obs, *_ = env.step(action)
                n += 1
                p, q = read_pose(obs)
                gap_pos, gap_rot = pose_gap(p, q, t_grip, t_quat)
                moved_mm = 1e9 if prev_p is None else math.dist(p, prev_p) * 1000
                moved_deg = 1e9 if prev_q is None else pose_gap(prev_p, prev_q, prev_p, q)[1]
                log.write(json.dumps({"step": n, "waypoint": label, "action": list(action),
                                      "eef_pos": [float(v) for v in p],
                                      "eef_quat_xyzw": [float(v) for v in obs["robot0_eef_quat"]],
                                      "gap_mm": gap_pos * 1000, "gap_deg": gap_rot}) + "\n")
                frames.append(grid_frame(obs, f"{label}  step {steps}  gap {gap_pos * 1000:.1f}mm {gap_rot:.2f}deg"))
                prev_p, prev_q = p, q
                if gap_pos * 1000 <= args.pos_tol and gap_rot <= args.rot_tol:
                    if moved_mm <= STILL_POS_MM and moved_deg <= STILL_ROT_DEG:
                        why = "도착"
                        break
                    why = "도착(움직이는 중)"
            keyframes.append(frames[-1])
            p, q = read_pose(obs)
            gap_pos, gap_rot = pose_gap(p, q, t_grip, t_quat)
            results.append((label, steps, gap_pos * 1000, gap_rot, why))
            print(f"{label:12} | {steps:4d} | {gap_pos * 1000:7.2f}mm {gap_rot:7.2f}° | {first[0] * 1000:7.1f}mm | {why}")
    finally:
        env.close()
        log.close()

    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / stamp
    imageio.mimwrite(f"{stem}--follow.mp4", frames, fps=FPS)
    strip = np.hstack(keyframes)
    Image.fromarray(strip).resize((strip.shape[1] // 3, strip.shape[0] // 3)).save(f"{stem}--keyframes.png")
    worst = max((r[2] for r in results), default=0.0), max((r[3] for r in results), default=0.0)
    print(f"\n최대 남은 오차 — 위치 {worst[0]:.2f}mm, 자세 {worst[1]:.2f}°   총 {n}스텝")
    print(f"saved {stem}--follow.mp4  ({len(frames)} frames, {len(frames) / FPS:.1f}s)")
    print(f"saved {stem}--keyframes.png\nsaved {log_path}")


if __name__ == "__main__":
    main()
