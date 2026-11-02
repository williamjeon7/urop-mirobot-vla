#!/usr/bin/env python3
"""W9 — 학습에 들어가는 손목 영상을 Mirobot 실물과 Panda 시뮬로 나란히 놓은 그림을 만든다. (`cosmos-policy/.venv`)

배경 — 11/02 Mirobot 녹화를 보니 로봇이 보고한 손 자세(A·B·C)는 0° 그대로인데 손목 화면이 돌고 기울었다.
Panda 손목 영상과 무엇이 다른지 한 장으로 보려고 만들었다 ([../ISSUES.md](../ISSUES.md) 1절).

    cosmos-policy/.venv/bin/python docs/W9/wrist_camera/compare_views.py

줄마다 한 에피소드, 칸마다 한 순간이다. 영상은 HDF5 `eye_in_hand_rgb` 그대로(256×256, 정책이 보는 방향)이고,
Mirobot 칸 위에는 그 순간 로봇이 `?` 로 보고한 자세(`robot.jsonl`, 가장 가까운 시각)를 적는다.
문서의 숫자 두 가지도 찍는다 — Mirobot 10개의 녹화 구간 보고 자세 A·B·C 범위, Panda 90개의 손 방향 변화.
"""

from __future__ import annotations

import bisect
import json
from pathlib import Path

import h5py
import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial.transform import Rotation

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).with_name("compare_views.jpg")
MIROBOT = REPO / "docs/W9/data/hdf5/mirobot_real/MIROBOT_video{n}_SCENE1_pick_up_the_blue_block_on_the_table_demo.hdf5"
RAW = REPO / "docs/W9/data/raw/영상{n}/robot.jsonl"
PANDA = REPO / "data/hdf5/panda_sim/PANDA_SIM_SCENE1_pick_up_the_blue_block_on_the_table_demo.hdf5"
VIDEOS = (7, 4)  # 7: 옆으로 크게 이동 (닫을 때 Y +60 mm), 4: 거의 가운데 (Y −5 mm)
TILE, BAR = 256, 30


def mirobot_row(n: int):
    rows = [json.loads(line) for line in Path(str(RAW).format(n=n)).open(encoding="utf-8")]
    states = [r for r in rows if r["kind"] == "state"]
    times = [s["t_s"] for s in states]
    with h5py.File(str(MIROBOT).format(n=n)) as f:
        demo = f["data/demo_0"]
        images, stamps, grip = demo["obs/eye_in_hand_rgb"], demo["timestamps"][:], demo["actions"][:, 6]
        close = int(np.argmax(grip > 0))  # 처음 닫기(+1) 칸
        picks = [0, close // 3, 2 * close // 3, close, min(len(grip) - 1, close + 20)]
        tiles, worst = [], 0.0
        for k in picks:
            i = min(bisect.bisect_left(times, stamps[k]), len(states) - 1)
            if i and abs(times[i - 1] - stamps[k]) < abs(times[i] - stamps[k]):
                i -= 1
            worst = max(worst, abs(times[i] - stamps[k]))
            x, y, z, a, b, c = states[i]["cart"]
            label = f"video{n} k={k}{' CLOSE' if k == close else ''}\nxyz {x:.0f},{y:.0f},{z:.0f}  abc {a:.0f},{b:.0f},{c:.0f}"
            tiles.append((images[k], label))
    print(f"video{n}: {len(grip)} steps, close at {close}, label time gap max {worst * 1000:.0f} ms")
    return tiles


def panda_row():
    with h5py.File(PANDA) as f:
        demo = f["data/demo_0"]  # blue, seed 0
        phases = [p.decode() for p in demo["phases"][:]]
        first = {p: phases.index(p) for p in dict.fromkeys(phases)}
        lift_end = len(phases) - 1 - phases[::-1].index("lift")
        picks = [0, (first["approach"] + first["lower"]) // 2, first["lower"], first["grasp"], (first["lift"] + lift_end) // 2]
        return [(demo["obs/eye_in_hand_rgb"][k], f"panda blue s0 k={k}\n{phases[k]}") for k in picks]


def mirobot_reported_abc() -> None:
    """녹화 구간(capture_start ~ capture_end) 안의 보고 자세 A·B·C 범위 (도)."""
    for n in range(1, 11):
        rows = [json.loads(line) for line in Path(str(RAW).format(n=n)).open(encoding="utf-8")]
        t0 = next(r["t_s"] for r in rows if r["kind"] == "capture_start")
        t1 = next(r["t_s"] for r in rows if r["kind"] == "capture_end")
        abc = np.array([r["cart"][3:6] for r in rows if r["kind"] == "state" and t0 <= r["t_s"] <= t1])
        print(f"video{n}: reported A,B,C min {abc.min(0).tolist()} max {abc.max(0).tolist()}")


def panda_orientation_stats() -> None:
    """Panda 90개 — 에피소드 첫 칸 대비 손 방향 변화: 전체 회전, 접근축(손 z) 기울기, 손가락 축 방향(yaw)."""
    total, tilt, yaw = [], [], []
    for path in sorted(PANDA.parent.glob("*.hdf5")):
        with h5py.File(path) as f:
            for demo in f["data"].values():
                rot = Rotation.from_quat(demo["robot_states"][:, 5:9])  # xyzw
                total.append(np.degrees((rot * rot[0].inv()).magnitude()).max())
                z = rot.apply([0, 0, 1])
                tilt.append(np.degrees(np.arccos(np.clip(z @ z[0], -1, 1))).max())
                y = rot.apply([0, 1, 0])
                heading = np.degrees(np.arctan2(y[:, 1], y[:, 0]))
                yaw.append(np.abs((heading - heading[0] + 180) % 360 - 180).max())
    print(f"panda {len(total)} episodes: total rotation change max {max(total):.2f} deg (median {np.median(total):.2f}), "
          f"approach-axis tilt max {max(tilt):.2f} deg, finger-axis yaw change max {max(yaw):.2f} deg")


def main() -> None:
    mirobot_reported_abc()
    panda_orientation_stats()
    rows = [mirobot_row(n) for n in VIDEOS] + [panda_row()]
    sheet = Image.new("RGB", (TILE * 5, (TILE + BAR) * len(rows)), "white")
    draw = ImageDraw.Draw(sheet)
    for r, row in enumerate(rows):
        for c, (image, label) in enumerate(row):
            x, y = c * TILE, r * (TILE + BAR)
            sheet.paste(Image.fromarray(np.asarray(image)), (x, y + BAR))
            draw.multiline_text((x + 4, y + 2), label, fill=(0, 0, 0), spacing=2)
    sheet.save(OUT, quality=88)
    print(OUT.relative_to(REPO), sheet.size, f"{OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
