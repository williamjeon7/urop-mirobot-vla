#!/usr/bin/env python3
"""W9 — 원본 HDF5 를 복사하지 않고, 데이터는 외부 링크로 가리키며 데모 속성만 덧붙인 얇은 HDF5 를 만든다. (`cosmos-policy/.venv`)

배경 — 11/02 Panda 90 + Mirobot 10 을 한 폴더로 합쳐 학습하려 하자, 동료 `docs/W9/d405/train.py` 의 `observation_mode` 가
`observation_mode` 속성이 없는 Panda 데모를 `two_view` 로 보고 손목 전용 Mirobot 과 섞을 수 없다며 멈췄다
(`tools/check_cosmos_dataset.py` 도 같은 함수를 쓴다). 학습은 둘 다 손목만 쓰기로 했으므로(11/01) Panda 데모에
`observation_mode=wrist_only` 를 붙이되, 원본(약 5 GB)은 고치지도 복사하지도 않는다.

    cosmos-policy/.venv/bin/python -m tools.wrap_hdf5 data/hdf5/panda_sim/*.hdf5 \\
        --out data/hdf5_mix/panda_sim --attr observation_mode=wrist_only

- 만든 파일의 데이터셋은 모두 원본을 가리키는 **외부 링크(절대 경로)** 다. 원본을 옮기거나 지우면 읽히지 않는다
- 파일·그룹 속성은 원본 것을 그대로 옮기고, `data/demo_*` 에 `--attr` 값과 `wrapped_from`(원본 경로)을 더한다
- 파일 이름은 원본과 같다 — Cosmos 로더는 파일 이름에서 지시문을 뽑는다
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import h5py
import numpy as np


def copy_structure(src_group: h5py.Group, dst_group: h5py.Group, src_file: str) -> None:
    """그룹은 새로 만들고(속성 포함), 데이터셋은 원본을 가리키는 외부 링크로 둔다."""
    for key, value in src_group.attrs.items():
        dst_group.attrs[key] = value
    for name in src_group:
        link = src_group.get(name, getlink=True)
        if not isinstance(link, h5py.HardLink):
            raise SystemExit(f"{src_file}:{src_group.name}/{name} 는 이미 링크다 — 원본 데이터만 감싼다")
        item = src_group[name]
        if isinstance(item, h5py.Group):
            copy_structure(item, dst_group.create_group(name), src_file)
        else:
            dst_group[name] = h5py.ExternalLink(src_file, item.name)


def wrap(src: Path, dst: Path, extra: dict[str, str]) -> int:
    src_file = str(src.resolve())
    with h5py.File(src_file, "r") as s, h5py.File(dst, "x") as d:
        copy_structure(s, d, src_file)
        demos = list(d["data"].values())
        for demo in demos:
            for key, value in extra.items():
                demo.attrs[key] = value
            demo.attrs["wrapped_from"] = src_file
        count = len(demos)
    # 링크가 원본과 같은 값을 주는지 — 첫·마지막 데모의 action 과 손목 영상 첫 장.
    # 쓰기 모드 파일에서는 외부 링크가 원본을 쓰기 모드로 열려다 실패하므로, 닫고 읽기 모드로 다시 연다
    with h5py.File(src_file, "r") as s, h5py.File(dst, "r") as d:
        keys = sorted(s["data"], key=lambda k: int(k.rsplit("_", 1)[1]))  # demo_9 < demo_10 (글자 순이 아니라 번호 순)
        for key in (keys[0], keys[-1]):
            for path in ("actions", "robot_states"):
                if not np.array_equal(s[f"data/{key}/{path}"][:], d[f"data/{key}/{path}"][:]):
                    raise SystemExit(f"{dst}: {key}/{path} 가 원본과 다르다")
            if not np.array_equal(s[f"data/{key}/obs/eye_in_hand_rgb"][0], d[f"data/{key}/obs/eye_in_hand_rgb"][0]):
                raise SystemExit(f"{dst}: {key} 손목 영상이 원본과 다르다")
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--attr", action="append", default=[], metavar="KEY=VALUE", help="데모마다 붙일 속성 (여러 번)")
    args = parser.parse_args()
    extra = {}
    for item in args.attr:
        key, sep, value = item.partition("=")
        if not sep or not key:
            parser.error(f"--attr 는 KEY=VALUE: {item}")
        extra[key] = value
    args.out.mkdir(parents=True, exist_ok=True)
    for src in args.files:
        dst = args.out / src.name
        if dst.resolve() == src.resolve():
            raise SystemExit("출력이 원본과 같다 — 원본은 고치지 않는다")
        print(dst, f"demos {wrap(src, dst, extra)}", f"{dst.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
