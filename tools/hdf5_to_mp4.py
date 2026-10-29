#!/usr/bin/env python3
"""W9 4-4 되돌려 보기 — LIBERO 형식 HDF5 에피소드를 mp4 로 꺼낸다. (conda `libero` 또는 `.venv`)

배경 — `pickup_to_hdf5` 는 렌더링한 프레임을 바로 HDF5 에 넣어 사람이 볼 영상이 따로 없다. 학습에 들어가는
바로 그 프레임을 눈으로 확인하려고 만들었다. 설명은 `docs/W9/DATASET_HDF5.md`.

    python -m tools.hdf5_to_mp4 data/hdf5/panda_sim/*.hdf5 --random 2 --out docs/W9/hdf5_check
    python -m tools.hdf5_to_mp4 <파일> --demos 0 5 --out <폴더>

왼쪽 외부(agentview), 오른쪽 손목(eye_in_hand) — HDF5 에 든 256×256 그대로를 `--scale` 배 늘린다(픽셀 그대로).
**프레임 위에는 아무것도 그리지 않는다.** 칸 번호 · 단계 · action · robot_states 는 아래 띠에 적는다.
20 fps = 0.05 s 한 칸 — 로봇 시간 그대로 재생된다.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import h5py
import imageio
import numpy as np
from PIL import Image, ImageDraw

FPS = 20  # LIBERO 제어 주기 — 한 칸 0.05 s
GAP = 8
BAR_H = 44


def label_of(path: Path) -> str:
    """파일 이름에서 지시문의 색 — `…_pick_up_the_red_block_…` → red. 없으면 파일 이름."""
    words = path.name.split("_")
    return words[words.index("the") + 1] if "the" in words else path.stem


def frame(av, wr, scale, lines) -> np.ndarray:
    h = av.shape[0] * scale
    left = np.array(Image.fromarray(av).resize((h, h), Image.NEAREST))
    right = np.array(Image.fromarray(wr).resize((h, h), Image.NEAREST))
    top = np.hstack([left, np.full((h, GAP, 3), 255, np.uint8), right])
    bar = Image.new("RGB", (top.shape[1], BAR_H), (0, 0, 0))
    d = ImageDraw.Draw(bar)
    for i, text in enumerate(lines):
        d.text((6, 4 + 14 * i), text, fill=(255, 255, 255))
    return np.vstack([top, np.array(bar)])


def write_demo(path: Path, demo: str, out: Path, scale: int) -> Path:
    with h5py.File(path, "r") as f:
        g = f["data"][demo]
        av, wr = g["obs/agentview_rgb"][:], g["obs/eye_in_hand_rgb"][:]
        actions, states = g["actions"][:], g["robot_states"][:]
        phases = [p.decode() for p in g["phases"][:]] if "phases" in g else [""] * len(av)
        seed = g.attrs.get("seed", "?")
        instruction = f["data"].attrs.get("instruction", "")
    color = label_of(path)
    frames = []
    for t in range(len(av)):
        a, s = actions[t], states[t]
        lines = [f"{instruction} | {color} seed {seed} ({demo}) | step {t + 1}/{len(av)} {phases[t]:<8} | "
                 f"gripper action {'close' if a[6] > 0 else 'open'}",
                 f"eef xyz {s[2]:+.3f} {s[3]:+.3f} {s[4]:+.3f} m | fingers {s[0]:.4f} {s[1]:.4f} | "
                 f"action xyz {a[0]:+.2f} {a[1]:+.2f} {a[2]:+.2f}   left: agentview  right: eye_in_hand"]
        frames.append(frame(av[t], wr[t], scale, lines))
    dst = out / f"{color}_seed{seed}_{demo}.mp4"
    imageio.mimwrite(dst, frames, fps=FPS, codec="libx264", quality=8, macro_block_size=1)
    return dst


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path)
    pick = parser.add_mutually_exclusive_group(required=True)
    pick.add_argument("--random", type=int, help="파일마다 무작위로 이만큼 고른다")
    pick.add_argument("--demos", type=int, nargs="+", help="파일마다 이 번호의 demo")
    parser.add_argument("--seed", type=int, default=20261029, help="--random 의 난수 seed (같은 값이면 같은 것을 고른다)")
    parser.add_argument("--scale", type=int, default=2)
    parser.add_argument("--out", type=Path, default=Path("data/hdf5_mp4"))
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)
    for path in args.files:
        with h5py.File(path, "r") as f:
            demos = sorted(f["data"].keys(), key=lambda k: int(k.split("_")[1]))
        chosen = (sorted(rng.sample(demos, args.random), key=lambda k: int(k.split("_")[1])) if args.random
                  else [f"demo_{i}" for i in args.demos])
        for demo in chosen:
            dst = write_demo(path, demo, args.out, args.scale)
            print(f"{path.name} {demo} → {dst} ({dst.stat().st_size / 1e6:.1f} MB)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
