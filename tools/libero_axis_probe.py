#!/usr/bin/env python3
"""W3 ③ LIBERO 축 확인 — 액션 한 성분만 넣고 eef 가 어디로 가는지 본다. (서버 cosmos-policy .venv 전용)

docs/W3/CHECKLIST.md ③ 의 위치 축·회전 축 표를 채우기 위한 프로브.
영상으로는 방향을, 숫자로는 어느 축이 얼마나 변했는지를 본다.

    cd ~/UROP && source cosmos-policy/.venv/bin/activate
    python -m tools.libero_axis_probe --axis x              # Δx + 0.5
    python -m tools.libero_axis_probe --axis rx --value -0.3

순서: 초기 상태 → dummy 로 안정(--settle) → 한 성분만 --steps 번.
안정 단계가 있는 이유 — 액션 0 으로도 컨트롤러가 자리 잡느라 처음 20스텝에 z 가 약 1cm 내려간다 (① 9/15).

남는 것
  rollouts/<날짜>/axis_probe/<시각>--<액션>.mp4            2×2 격자 영상
  rollouts/<날짜>/axis_probe/<시각>--<액션>--start_end.png  왼쪽 시작, 오른쪽 끝
  data/axis_probe/<시각>--<액션>.jsonl                     스텝마다 원본 값 (eef_quat 는 LIBERO 원본 xyzw 그대로)

영상 카메라 — agentview 는 정책·데이터셋이 쓰는 시점이라 **위치를 바꾸지 않는다**. 나머지 셋은 눈으로 보는 용도.
  agentview(정면·가까움) | frontview(정면·멀리)
  sideview(옆)           | birdview(위)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")  # 화면 없는 렌더링. libero import 전에 정해져야 한다
os.environ.setdefault("HF_HUB_OFFLINE", "1")  # libero 가 에셋을 찾다가 받지 못하게 막는다 (① 408MB 사고)

import imageio
import numpy as np
from libero.libero import benchmark, get_libero_path
from libero.libero.envs import OffScreenRenderEnv
from PIL import Image, ImageDraw

from common.rotation import quat_error_axis_angle, quat_xyzw_to_wxyz

AXES = ("x", "y", "z", "rx", "ry", "rz")  # OSC_POSE 액션 앞 6칸 순서
CAMERAS = ("agentview", "frontview", "sideview", "birdview")  # 2×2 격자 순서
GRIPPER_OPEN = -1.0  # libero_utils.py:42
FPS = 10  # 스텝이 수십 개라 30fps 면 1초도 안 된다


def find_task(suite_name: str, task_name: str):
    suite = benchmark.get_benchmark_dict()[suite_name]()
    for i in range(suite.n_tasks):
        if suite.get_task(i).name == task_name:
            return suite, i
    raise SystemExit(f"{suite_name} 에 {task_name!r} 이 없다")


def read_pose(obs):
    """eef 위치(m, 월드)와 자세(wxyz). LIBERO 는 xyzw 로 내보낸다 (ROTATION.md 5절)."""
    return np.array(obs["robot0_eef_pos"], dtype=float), quat_xyzw_to_wxyz(tuple(obs["robot0_eef_quat"]))


def rotation_deg(q_from, q_to) -> np.ndarray:
    """q_from → q_to 회전을 월드 프레임 axis-angle(도) 로. 성분이 곧 x·y·z 축 둘레 회전량이다."""
    return np.degrees(quat_error_axis_angle(q_from, q_to))


def grid_frame(obs, caption: str) -> np.ndarray:
    """카메라 넷을 2×2 로. 렌더 이미지는 상하가 뒤집혀 나온다 (cosmos-policy README.md:57)."""
    tiles = []
    for cam in CAMERAS:
        im = Image.fromarray(np.flipud(obs[f"{cam}_image"]).copy())
        d = ImageDraw.Draw(im)
        d.rectangle([0, im.height - 14, 8 + 7 * len(cam), im.height], fill=(0, 0, 0))
        d.text((4, im.height - 13), cam, fill=(255, 255, 0))
        tiles.append(np.array(im))
    grid = np.vstack([np.hstack(tiles[:2]), np.hstack(tiles[2:])])
    im = Image.fromarray(grid)
    ImageDraw.Draw(im).rectangle([0, 0, im.width, 16], fill=(0, 0, 0))
    ImageDraw.Draw(im).text((4, 2), caption, fill=(255, 255, 255))
    return np.array(im)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--axis", required=True, choices=AXES)
    parser.add_argument("--value", type=float, default=0.5, help="액션 값 [-1, 1]. 1.0 = 0.05m / 0.5rad")
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--settle", type=int, default=30, help="측정 전 dummy 스텝")
    parser.add_argument("--suite", default="libero_90")
    parser.add_argument("--task-name", default="KITCHEN_SCENE1_open_the_top_drawer_of_the_cabinet")
    parser.add_argument("--res", type=int, default=384, help="카메라 한 대의 해상도. 영상은 2배")
    parser.add_argument("--out", type=Path, default=Path("rollouts") / time.strftime("%Y_%m_%d") / "axis_probe")
    parser.add_argument("--log-dir", type=Path, default=Path("data") / "axis_probe")
    args = parser.parse_args()

    suite, task_id = find_task(args.suite, args.task_name)
    task = suite.get_task(task_id)
    bddl = os.path.join(get_libero_path("bddl_files"), task.problem_folder, task.bddl_file)
    tag = f"d{args.axis}{args.value:+.2f}"
    stamp = time.strftime("%H_%M_%S")
    print(f"task: {args.suite}[{task_id}] {task.language}")
    print(f"action: {tag}  × {args.steps} steps  (settle {args.settle})")

    action = [0.0] * 6 + [GRIPPER_OPEN]
    action[AXES.index(args.axis)] = args.value
    dummy = [0.0] * 6 + [GRIPPER_OPEN]

    args.log_dir.mkdir(parents=True, exist_ok=True)
    log_path = args.log_dir / f"{time.strftime('%Y_%m_%d')}-{stamp}--{tag}.jsonl"
    log = log_path.open("w")
    log.write(json.dumps({"meta": {"suite": args.suite, "task": task.name, "task_id": task_id, "axis": args.axis,
                                   "value": args.value, "steps": args.steps, "settle": args.settle,
                                   "quat_order_raw": "xyzw", "pos_unit": "m, world"}}) + "\n")

    def record(phase: str, k: int, act, obs) -> None:
        log.write(json.dumps({"phase": phase, "step": k, "action": list(act),
                              "eef_pos": [float(v) for v in obs["robot0_eef_pos"]],
                              "eef_quat_xyzw": [float(v) for v in obs["robot0_eef_quat"]]}) + "\n")

    env = OffScreenRenderEnv(bddl_file_name=bddl, camera_names=list(CAMERAS),
                             camera_heights=args.res, camera_widths=args.res)
    frames = []
    try:
        env.seed(0)
        env.reset()
        obs = env.set_init_state(suite.get_task_init_states(task_id)[0])
        record("init", 0, dummy, obs)
        p_init, q_init = read_pose(obs)

        for k in range(1, args.settle + 1):
            obs, _, _, _ = env.step(dummy)
            record("settle", k, dummy, obs)
            frames.append(grid_frame(obs, f"settle {k}/{args.settle}"))
        p0, q0 = read_pose(obs)
        print(f"\n안정 중 흔들림  Δpos {np.round((p0 - p_init) * 1000, 1)} mm   회전 {np.round(rotation_deg(q_init, q0), 2)} °")
        print(f"시작  eef_pos {np.round(p0, 4)} m   eef_quat(wxyz) {np.round(q0, 4)}")

        print(f"\n{'step':>4} | {'Δx':>7} {'Δy':>7} {'Δz':>7} mm | {'rot x':>7} {'rot y':>7} {'rot z':>7} °")
        for k in range(1, args.steps + 1):
            obs, _, _, _ = env.step(action)
            record("action", k, action, obs)
            p, q = read_pose(obs)
            d, r = (p - p0) * 1000, rotation_deg(q0, q)
            print(f"{k:4d} | {d[0]:7.1f} {d[1]:7.1f} {d[2]:7.1f}    | {r[0]:7.2f} {r[1]:7.2f} {r[2]:7.2f}")
            frames.append(grid_frame(obs, f"{tag} step {k}/{args.steps}"))
    finally:
        env.close()
        log.close()

    i_pos, i_rot = int(np.argmax(np.abs(d))), int(np.argmax(np.abs(r)))
    print(f"\n합계  Δpos {np.round(d, 1)} mm  → 가장 큰 축 {'xyz'[i_pos]} ({d[i_pos]:+.1f} mm, 스텝당 {d[i_pos] / args.steps:+.2f})")
    print(f"      회전 {np.round(r, 2)} °   → 가장 큰 축 {'xyz'[i_rot]} ({r[i_rot]:+.2f} °, 스텝당 {r[i_rot] / args.steps:+.3f})")
    # osc_pose.json 의 output_max. 컨트롤러가 받는 "스텝당 목표 오프셋" 이지 실제 이동량이 아니다
    if args.axis in ("x", "y", "z"):
        print(f"      명령  {args.value} × 0.05m = 스텝당 목표 오프셋 {args.value * 50:.1f} mm")
    else:
        print(f"      명령  {args.value} × 0.5rad = 스텝당 목표 오프셋 {math.degrees(args.value * 0.5):.2f} °")

    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"{stamp}--{tag}--{args.steps}steps"
    imageio.mimwrite(f"{stem}.mp4", frames, fps=FPS)
    Image.fromarray(np.hstack([frames[args.settle - 1], frames[-1]])).save(f"{stem}--start_end.png")
    print(f"\nsaved {stem}.mp4  ({len(frames)} frames, {len(frames) / FPS:.1f}s)")
    print(f"saved {stem}--start_end.png  (왼쪽 = 시작, 오른쪽 = 끝)")
    print(f"saved {log_path}  (스텝마다 eef_pos, eef_quat 원본 xyzw)")


if __name__ == "__main__":
    main()
