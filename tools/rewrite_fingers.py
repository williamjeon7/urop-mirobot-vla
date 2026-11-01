#!/usr/bin/env python3
"""W9 — Mirobot HDF5 의 손가락 2칸을 새 B' "잡음" 값으로 다시 계산한 사본을 만든다. (`cosmos-policy/.venv`)

배경 — Panda 시뮬 블록을 실물에 맞춰 30.2 mm 로 바꾸며, Panda 가 블록을 잡았을 때 손가락 값이 0.0191 → 0.0140 이 됐다 (11/01).
동료의 Mirobot HDF5 는 0.0191 로 만들어져 있고, 원본은 건드리지 않기로 했다. 손가락 값은 B' 공식
`열림 × (1 − c) + 잡음 × c` (c = 닫힌 정도 0–1, `common/proprio.py`)로 만들어져 있어 c 를 거꾸로 구할 수 있다 — 그 c 로 새 값을 다시 계산한다.

    cosmos-policy/.venv/bin/python -m tools.rewrite_fingers docs/W9/data/hdf5/mirobot_real/*.hdf5 --out data/hdf5_mix/mirobot_real

바뀌는 것은 `robot_states` 의 0·1칸뿐이다. 파일을 통째로 복사한 뒤 그 두 칸만 고치고(영상 hard link 도 그대로), demo 속성에 기록을 남긴다.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import h5py
import numpy as np

from common.proprio import FINGER_HOLD_M, FINGER_OPEN_M

OLD_HOLD_M = 0.0191  # 40 mm 블록 때 B' 잡음 값 — 동료 HDF5 가 이 값으로 만들어졌다 (11/01 확인)
TOL = 1e-5           # float32 저장 오차


def rewrite(src: Path, dst: Path, old_hold: float, new_hold: float, open_m: float) -> dict:
    shutil.copy2(src, dst)
    report = {}
    with h5py.File(dst, "r+") as f:
        for key in sorted(f["data"].keys(), key=lambda k: int(k.split("_")[1])):
            demo = f["data"][key]
            rs = demo["robot_states"][:]
            left = rs[:, 0].astype(np.float64)
            if np.abs(rs[:, 1] + rs[:, 0]).max() > TOL:
                raise SystemExit(f"{src.name} {key}: 오른쪽 손가락이 왼쪽의 부호 반대가 아니다 — B' 로 만든 값이 아니다")
            c = (open_m - left) / (open_m - old_hold)
            if c.min() < -TOL * 100 or c.max() > 1 + TOL * 100:
                raise SystemExit(f"{src.name} {key}: 닫힌 정도가 0–1 밖 ({c.min():.4f}, {c.max():.4f}) — 옛 잡음 값이 {old_hold} 가 아니다")
            c = np.clip(c, 0.0, 1.0)
            new = open_m * (1.0 - c) + new_hold * c
            rs[:, 0], rs[:, 1] = new, -new
            demo["robot_states"][...] = rs
            demo.attrs["fingers_rewritten"] = json.dumps({
                "tool": "tools/rewrite_fingers.py", "date": time.strftime("%Y-%m-%d"), "source": str(src),
                "open_m": open_m, "old_hold_m": old_hold, "new_hold_m": new_hold,
                "reason": "Panda sim block 40 mm -> 30.2 mm (real 20 mm / 0.663)"})
            report[key] = {"steps": len(rs), "closed_steps": int((c > 0.999).sum()),
                           "fingers_min": round(float(new.min()), 4), "fingers_max": round(float(new.max()), 4)}
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--old-hold", type=float, default=OLD_HOLD_M)
    parser.add_argument("--new-hold", type=float, default=FINGER_HOLD_M)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for src in args.files:
        dst = args.out / src.name
        if dst.resolve() == src.resolve():
            raise SystemExit("출력이 원본과 같다 — 원본은 고치지 않는다")
        print(src.name, json.dumps(rewrite(src, dst, args.old_hold, args.new_hold, FINGER_OPEN_M)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
