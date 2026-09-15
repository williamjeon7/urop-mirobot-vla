#!/usr/bin/env python3
"""W3 ① LIBERO 시뮬 동작 확인 — dummy action 몇 스텝을 MP4 로. (서버 cosmos-policy .venv 전용)

docs/W3/CHECKLIST.md 2절의 마지막 산출물. 환경이 만들어지고 렌더링되는지만 본다.
환경 생성·초기 상태·dummy action 은 cosmos-policy 의 run_libero_eval.py / libero_utils.py 와 같게 했다.
libero_utils 는 import 하지 않는다 (robot_utils 를 거쳐 torch·wandb 까지 끌려온다).

    cd ~/UROP && source cosmos-policy/.venv/bin/activate
    python -m tools.libero_dummy_mp4
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")  # 화면 없는 렌더링. libero import 전에 정해져야 한다

import imageio
import numpy as np
from libero.libero import benchmark, get_libero_path
from libero.libero.envs import OffScreenRenderEnv

DUMMY_ACTION = [0, 0, 0, 0, 0, 0, -1]  # libero_utils.py:42 — 그리퍼 -1 = 열림
FPS = 30  # libero_utils.py save_rollout_video 와 같게


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--suite", default="libero_10")
    parser.add_argument("--task", type=int, default=0)
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--res", type=int, default=256)
    parser.add_argument("--out", type=Path, default=Path("rollouts") / time.strftime("%Y_%m_%d"))
    args = parser.parse_args()

    task_suite = benchmark.get_benchmark_dict()[args.suite]()
    task = task_suite.get_task(args.task)
    bddl = os.path.join(get_libero_path("bddl_files"), task.problem_folder, task.bddl_file)
    print(f"task: {args.suite}[{args.task}] {task.language}")

    env = OffScreenRenderEnv(bddl_file_name=bddl, camera_heights=args.res, camera_widths=args.res)
    try:
        env.seed(0)
        env.reset()
        obs = env.set_init_state(task_suite.get_task_init_states(args.task)[0])
        print(f"start  eef_pos {np.round(obs['robot0_eef_pos'], 4)}  eef_quat {np.round(obs['robot0_eef_quat'], 4)}")

        # 렌더 이미지는 상하가 뒤집혀 나온다 (cosmos-policy README.md:57)
        frames = [np.flipud(obs["agentview_image"])]
        for _ in range(args.steps):
            obs, _, _, _ = env.step(DUMMY_ACTION)
            frames.append(np.flipud(obs["agentview_image"]))
        print(f"end    eef_pos {np.round(obs['robot0_eef_pos'], 4)}  eef_quat {np.round(obs['robot0_eef_quat'], 4)}")
    finally:
        env.close()

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{time.strftime('%H_%M_%S')}--dummy--{args.suite}_{args.task}--{args.steps}steps.mp4"
    imageio.mimwrite(path, frames, fps=FPS)
    print(f"saved {path}  ({len(frames)} frames, {len(frames) / FPS:.1f}s)")


if __name__ == "__main__":
    main()
