#!/usr/bin/env python3
"""W3 ④ LIBERO → Mirobot 용 Panda 복합 동작 롤아웃. (서버 cosmos-policy .venv 전용)

구간마다 위치와 회전을 섞어 넣고, 구간 끝에서 멈춘다. 멈춘 자세와 움직이는 중간 자세를 waypoint 로 표시해 두고,
Mirobot G-code 로 바꾸는 것은 다음 단계에서 한다.

    cd ~/UROP && source cosmos-policy/.venv/bin/activate
    python -m tools.libero_compound_rollout

남는 것
  rollouts/<날짜>/compound/<시각>--compound.mp4      2×2 격자 영상
  rollouts/<날짜>/compound/<시각>--keyframes.png     시작 + 구간 끝마다 한 장
  data/compound/<날짜>-<시각>.jsonl                   스텝마다 원본 값, waypoint 표시

위치는 두 가지를 기록한다.
  eef_pos     파지점(grip_site) — LIBERO proprio 그대로
  flange_pos  robot0_right_hand — 파지점에서 공구 축으로 9.7cm 위. Mirobot 이 보고하는 점과 같은 종류라 변환에 쓴다
              (docs/W3/LIBERO_AXES.md 0·4절)
자세는 둘이 같다 — robosuite 의 eef_quat 이 right_hand 바디 자세다 (single_arm.py:309).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from tools.libero_axis_probe import (  # 환경 변수(MUJOCO_GL, HF_HUB_OFFLINE)도 여기서 먼저 정해진다
    AXES,
    CAMERAS,
    FPS,
    GRIPPER_OPEN,
    find_task,
    grid_frame,
    read_pose,
    rotation_deg,
)

import os

import imageio
import numpy as np
from libero.libero import get_libero_path
from libero.libero.envs import OffScreenRenderEnv
from PIL import Image

# 구간 = (이름, {축: 액션 값}, 스텝 수). 축 이름과 방향은 LIBERO_AXES.md 2·3절.
#   x+ 앞 / y+ 로봇 기준 왼쪽 / z+ 위
#   rx+ 그리퍼가 왼쪽을 향해 기움 / ry+ 뒤(베이스 쪽)를 향해 기움 / rz+ 위에서 보아 반시계
# 크기는 Mirobot 에서도 안전하게 — **플랜지 기준** 위치 5~6cm, 회전 15~20°.
# 9/17 첫 실행(0.5·0.25·0.3 등)은 플랜지가 96mm·82mm 로 커서 끝 위치가 Mirobot 도달 범위 끝에 가까웠다.
# 크게 나온 이유 둘 — 멈춤 구간에서도 조금 더 가고, 기울이면 파지점 중심 회전이라 9.7cm 위의 플랜지가 휜다
# (18° 기울이면 약 3cm). 그래서 기울이는 구간은 위치 값을 더 줄였다.
SEGMENTS = [
    ("forward + tilt back", {"x": 0.27, "ry": 0.2}, 10),
    ("left + ccw", {"y": 0.37, "rz": 0.24}, 10),
    ("down + tilt left", {"z": -0.29, "rx": 0.2}, 10),
]
FLANGE_BODY = "robot0_right_hand"


def flange_pose(sim):
    """플랜지 위치(m, 월드)와 자세(xyzw). MuJoCo 바디 자세는 wxyz 라 순서를 바꿔 LIBERO 와 맞춘다."""
    w, x, y, z = sim.data.get_body_xquat(FLANGE_BODY)
    return [float(v) for v in sim.data.get_body_xpos(FLANGE_BODY)], [float(x), float(y), float(z), float(w)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--settle", type=int, default=30)
    parser.add_argument("--hold", type=int, default=15, help="구간 끝에서 멈춰 있는 스텝")
    parser.add_argument("--waypoint-every", type=int, default=5, help="움직이는 중 waypoint 간격(스텝)")
    parser.add_argument("--suite", default="libero_90")
    parser.add_argument("--task-name", default="KITCHEN_SCENE1_open_the_top_drawer_of_the_cabinet")
    parser.add_argument("--res", type=int, default=384)
    parser.add_argument("--out", type=Path, default=Path("rollouts") / time.strftime("%Y_%m_%d") / "compound")
    parser.add_argument("--log-dir", type=Path, default=Path("data") / "compound")
    args = parser.parse_args()

    suite, task_id = find_task(args.suite, args.task_name)
    task = suite.get_task(task_id)
    bddl = os.path.join(get_libero_path("bddl_files"), task.problem_folder, task.bddl_file)
    stamp = time.strftime("%H_%M_%S")
    dummy = [0.0] * 6 + [GRIPPER_OPEN]

    args.log_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.log_dir / f"{time.strftime('%Y_%m_%d')}-{stamp}.jsonl"
    log = log_path.open("w")
    log.write(json.dumps({"meta": {"suite": args.suite, "task": task.name, "segments": SEGMENTS, "settle": args.settle,
                                   "hold": args.hold, "waypoint_every": args.waypoint_every, "quat_order_raw": "xyzw",
                                   "pos_unit": "m, world", "flange_body": FLANGE_BODY}}, ensure_ascii=False) + "\n")

    env = OffScreenRenderEnv(bddl_file_name=bddl, camera_names=list(CAMERAS),
                             camera_heights=args.res, camera_widths=args.res)
    frames, keyframes, n = [], [], 0
    try:
        env.seed(0)
        env.reset()
        obs = env.set_init_state(suite.get_task_init_states(task_id)[0])
        sim = env.env.sim

        def record(phase, seg, act, obs, waypoint=None):
            nonlocal n
            fp, fq = flange_pose(sim)
            log.write(json.dumps({"step": n, "phase": phase, "segment": seg, "action": list(act),
                                  "eef_pos": [float(v) for v in obs["robot0_eef_pos"]],
                                  "eef_quat_xyzw": [float(v) for v in obs["robot0_eef_quat"]],
                                  "flange_pos": fp, "flange_quat_xyzw": fq, "waypoint": waypoint}) + "\n")

        for k in range(1, args.settle + 1):
            obs, *_ = env.step(dummy)
            n += 1
            last = k == args.settle
            record("settle", 0, dummy, obs, "start" if last else None)
            frames.append(grid_frame(obs, f"settle {k}/{args.settle}"))
        keyframes.append(frames[-1])
        p_start, q_start = read_pose(obs)
        f_start = np.array(flange_pose(sim)[0])

        print(f"\n{'구간':28} | {'플랜지 Δ x / y / z (mm)':>26} | {'회전 x / y / z (°, 월드)':>26}")
        for s, (name, parts, steps) in enumerate(SEGMENTS, start=1):
            action = [0.0] * 6 + [GRIPPER_OPEN]
            for axis, value in parts.items():
                action[AXES.index(axis)] = value
            f0, (_, q0) = np.array(flange_pose(sim)[0]), read_pose(obs)

            for k in range(1, steps + 1):
                obs, *_ = env.step(action)
                n += 1
                wp = f"seg{s}-move{k}" if k % args.waypoint_every == 0 and k != steps else None
                record("move", s, action, obs, wp)
                frames.append(grid_frame(obs, f"seg{s} {name}  move {k}/{steps}"))
            for k in range(1, args.hold + 1):
                obs, *_ = env.step(dummy)
                n += 1
                record("hold", s, dummy, obs, f"seg{s}-end" if k == args.hold else None)
                frames.append(grid_frame(obs, f"seg{s} {name}  hold {k}/{args.hold}"))
            keyframes.append(frames[-1])

            d = (np.array(flange_pose(sim)[0]) - f0) * 1000
            r = rotation_deg(q0, read_pose(obs)[1])
            print(f"{s}. {name:25} | {d[0]:+8.1f} {d[1]:+8.1f} {d[2]:+8.1f} | {r[0]:+8.2f} {r[1]:+8.2f} {r[2]:+8.2f}")

        d = (np.array(flange_pose(sim)[0]) - f_start) * 1000
        r = rotation_deg(q_start, read_pose(obs)[1])
        print(f"{'시작 → 끝 합계':28} | {d[0]:+8.1f} {d[1]:+8.1f} {d[2]:+8.1f} | {r[0]:+8.2f} {r[1]:+8.2f} {r[2]:+8.2f}")
    finally:
        env.close()
        log.close()

    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"{stamp}"
    imageio.mimwrite(f"{stem}--compound.mp4", frames, fps=FPS)
    strip = np.hstack(keyframes)
    Image.fromarray(strip).resize((strip.shape[1] // 2, strip.shape[0] // 2)).save(f"{stem}--keyframes.png")
    n_wp = sum(1 for line in log_path.open() if '"waypoint": "' in line)
    print(f"\nsaved {stem}--compound.mp4  ({len(frames)} frames, {len(frames) / FPS:.1f}s)")
    print(f"saved {stem}--keyframes.png  (시작 + 구간 끝 {len(SEGMENTS)}개)")
    print(f"saved {log_path}  (스텝 {n}개, waypoint {n_wp}개)")


if __name__ == "__main__":
    main()
