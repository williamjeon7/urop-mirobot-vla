#!/usr/bin/env python3
"""W9 4-1 Panda 시뮬 pick up → Cosmos LIBERO 로더가 읽는 HDF5. (conda `libero`, W6 LIBERO)

배경 — W6 pick up 은 화면 표시와 손 좌표 JSONL(`--log`)만 남겼고, Cosmos 가 학습할 때 읽는 형식으로 저장하는 기능이 없었다.
설계·결정·결과는 `docs/W9/DATASET_HDF5.md`.

    conda activate libero
    python -m tools.pickup_to_hdf5 --colors red --seeds 0-2
    python -m tools.pickup_to_hdf5 --seeds 0-29 --out data/hdf5/panda_sim

W6 `docs/W6/rgb_blocks/pickup.py` 의 `run_pickup` 을 그대로 돌리며 step 마다 두 카메라와 손 상태를 모은다.
형식은 `docs/W9/CHECKLIST.md` 0절 표 — `cosmos_policy/datasets/libero_dataset.py:173-212` 가 읽는 그대로다.

    <out>/<prefix>_SCENE1_pick_up_the_<색>_block_on_the_table_demo.hdf5   ← 파일 이름이 곧 지시문
      data/demo_<i>/obs/agentview_rgb      (T, 256, 256, 3) uint8, 위아래 바로 (np.flipud)
      data/demo_<i>/obs/eye_in_hand_rgb    (T, 256, 256, 3) uint8
      data/demo_<i>/actions                (T, 7)  OSC_POSE
      data/demo_<i>/robot_states           (T, 9)  손가락 2 + 손 위치 3 (m) + 쿼터니언 4 (xyzw)
      로더는 안 읽는 것 (상위집합 기록)     obs/joint_states (T, 7), obs/gripper_states (T, 2),
                                           obs/ee_states (T, 6) 위치 + axis-angle, phases (T,)

**짝** — 칸 t 의 관측은 action t 를 넣기 **전** 것이다 (`regenerate_libero_dataset.py:213-260` 과 같다).
`run_pickup` 의 `on_step` 은 action 뒤 관측을 주므로 한 칸씩 밀어서 짝짓는다. 마지막 관측은 버린다.

**성공한 것만** 쓴다 (`pickup_success`). 실패·예외는 건너뛰고 끝에 센다.
no-op(LIBERO 재생성이 거른 칸)은 거르지 않고 세기만 한다 — 거를지는 CHECKLIST 4-3 에서 정한다.
지시문은 LIBERO 처럼 소문자·마침표 없음 (CHECKLIST 4-3, 잠정).
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RGB_BLOCKS = REPO / "docs" / "W6" / "rgb_blocks"
W6_LIBERO_CONFIG = REPO / "docs" / "W6" / ".libero"

os.environ.setdefault("MUJOCO_GL", "egl")  # 화면 없는 렌더링. libero import 전에 정해져야 한다
os.environ.setdefault("HF_HUB_OFFLINE", "1")  # libero 가 에셋을 찾다가 받지 못하게 막는다 (① 408MB 사고)
if (W6_LIBERO_CONFIG / "config.yaml").is_file():
    os.environ.setdefault("LIBERO_CONFIG_PATH", str(W6_LIBERO_CONFIG))
sys.path.insert(0, str(RGB_BLOCKS))

import h5py  # noqa: E402
import numpy as np  # noqa: E402
from robosuite.utils.transform_utils import quat2axisangle  # noqa: E402

from objects import BLOCK_SIZE_MM  # noqa: E402
from pickup import pickup_success, run_pickup  # noqa: E402
from preview import create_env  # noqa: E402

CAMERAS = ("agentview", "robot0_eye_in_hand")
INSTRUCTION = "pick up the {} block on the table"  # LIBERO 지시문처럼 소문자·마침표 없음
NOOP_THRESHOLD = 1e-4  # regenerate_libero_dataset.py:89 is_noop
OBS_KEYS = ("agentview_rgb", "eye_in_hand_rgb", "joint_states", "gripper_states", "ee_states")


def parse_seeds(text: str) -> list:
    """`0-29` 나 `0,3,5` 나 둘을 섞은 것."""
    seeds = []
    for part in text.split(","):
        lo, _, hi = part.partition("-")
        seeds.extend(range(int(lo), int(hi or lo) + 1))
    return seeds


def file_name(prefix: str, instruction: str) -> str:
    return "{}_SCENE1_{}_demo.hdf5".format(prefix, instruction.replace(" ", "_"))


def command_from_file(name: str) -> str:
    """로더가 파일 이름에서 지시문을 되살리는 규칙 그대로 (`libero_dataset.py:203-212`)."""
    command = ""
    for word in name[:-10].split("_"):
        if "SCENE" in word:
            command = ""
            continue
        command = command + word + " "
    return command[:-1]


def snapshot(obs) -> dict:
    """한 칸의 관측. robot_states 는 `regenerate_libero_dataset.py:222`, `run_libero_eval.py:334` 와 같은 순서다."""
    return {
        "agentview_rgb": np.flipud(obs["agentview_image"]).copy(),
        "eye_in_hand_rgb": np.flipud(obs["robot0_eye_in_hand_image"]).copy(),
        "robot_states": np.concatenate([obs["robot0_gripper_qpos"], obs["robot0_eef_pos"], obs["robot0_eef_quat"]]),
        "joint_states": np.array(obs["robot0_joint_pos"]),
        "gripper_states": np.array(obs["robot0_gripper_qpos"]),
        "ee_states": np.concatenate([obs["robot0_eef_pos"], quat2axisangle(obs["robot0_eef_quat"])]),
    }


def count_noops(actions) -> int:
    """LIBERO 재생성이 거른 칸 수. 비교 대상은 바로 앞 칸이 아니라 **남긴** 앞 칸이다 (`regenerate_libero_dataset.py:207-211`)."""
    count, kept = 0, None
    for action in actions:
        still = np.linalg.norm(action[:-1]) < NOOP_THRESHOLD
        if still and (kept is None or action[-1] == kept[-1]):
            count += 1
        else:
            kept = action
    return count


def record_episode(color: str, seed: int, size: int):
    """pick up 한 번. 성공하면 (칸 목록, 정보), 아니면 (None, 이유)."""
    env = create_env(resolution=size, cameras=CAMERAS, ignore_done=True, task=color, seed=seed)
    try:
        obs = env.reset()
        frames, record = [snapshot(obs)], []
        with contextlib.redirect_stdout(io.StringIO()):  # run_pickup 은 단계마다 JSON 을 찍는다
            _, result = run_pickup(env, obs, env.rgb_task["target_object"],
                                   on_step=lambda o, *_: frames.append(snapshot(o)), record=record)
    except RuntimeError as error:
        return None, str(error)
    finally:
        env.close()
    if not pickup_success(result):
        return None, "pickup_success False"
    assert len(frames) == len(record) + 1
    actions = np.array([row["action"] for row in record])
    return {
        "frames": frames[:-1],  # 칸 t 의 관측 = action t 전. 마지막 관측은 짝이 없다
        "actions": actions,
        "phases": [row["phase"] for row in record],
        "attrs": {"seed": seed, "color": color, "steps": len(record), "noops": count_noops(actions),
                  "lift_height_m": result["lift_height_m"], "others_max_move_m": result["others_max_move_m"]},
    }, None


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "-C", str(REPO), "describe", "--always", "--dirty"],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def write_file(path: Path, instruction: str, episodes: list, meta: dict) -> None:
    with h5py.File(path, "w") as f:
        data = f.create_group("data")
        data.attrs["instruction"] = instruction
        for key, value in meta.items():
            data.attrs[key] = value
        for i, ep in enumerate(episodes):
            demo = data.create_group("demo_{}".format(i))
            obs = demo.create_group("obs")
            for key in OBS_KEYS:
                obs.create_dataset(key, data=np.stack([fr[key] for fr in ep["frames"]]))
            demo.create_dataset("actions", data=ep["actions"])
            demo.create_dataset("robot_states", data=np.stack([fr["robot_states"] for fr in ep["frames"]]))
            demo.create_dataset("phases", data=np.array(ep["phases"], dtype="S"))
            for key, value in ep["attrs"].items():
                demo.attrs[key] = value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--colors", nargs="+", choices=("red", "green", "blue"), default=["red", "green", "blue"])
    parser.add_argument("--seeds", default="0-2", help="예: 0-29, 0,3,5 (기본 0-2)")
    parser.add_argument("--out", type=Path, default=Path("data/hdf5/panda_sim"),
                        help="출력 폴더 — 로더의 data_dir 바로 아래 폴더가 묶음(suite) 이름이 된다")
    parser.add_argument("--prefix", default="PANDA_SIM", help="파일 이름 앞부분. 로더는 SCENE 앞을 버린다")
    parser.add_argument("--size", type=int, default=256, help="카메라 해상도 (LIBERO 재생성과 같은 256)")
    args = parser.parse_args()

    seeds = parse_seeds(args.seeds)
    args.out.mkdir(parents=True, exist_ok=True)
    meta = {"source": "docs/W6/rgb_blocks/pickup.py run_pickup", "commit": git_commit(),
            "created": time.strftime("%Y-%m-%d %H:%M:%S"), "block_size_mm": BLOCK_SIZE_MM,
            "cameras": ",".join(CAMERAS), "image_size": args.size, "image_orientation": "upright (np.flipud of render)",
            "robot_states": "gripper_qpos(2) eef_pos(3, m, LIBERO world) eef_quat(4, xyzw)",
            "pairing": "obs before action (regenerate_libero_dataset.py)"}
    failed = []
    for color in args.colors:
        instruction = INSTRUCTION.format(color)
        path = args.out / file_name(args.prefix, instruction)
        assert command_from_file(path.name) == instruction, path.name
        episodes = []
        for seed in seeds:
            t0 = time.time()
            ep, reason = record_episode(color, seed, args.size)
            if ep is None:
                failed.append((color, seed, reason))
                print("  {} seed {}: 건너뜀 — {}".format(color, seed, reason), flush=True)
                continue
            episodes.append(ep)
            print("  {} seed {}: {} 칸 (no-op {}), {:.1f}s".format(
                color, seed, ep["attrs"]["steps"], ep["attrs"]["noops"], time.time() - t0), flush=True)
        if episodes:
            write_file(path, instruction, episodes, dict(meta, color=color, seeds=args.seeds))
            print("{}: {} 에피소드 → {} ({:.0f} MB)".format(
                color, len(episodes), path, path.stat().st_size / 1e6), flush=True)
    print("\n실패 {} 개{}".format(len(failed), "" if not failed else ": " + ", ".join(
        "{} s{}".format(c, s) for c, s, _ in failed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
