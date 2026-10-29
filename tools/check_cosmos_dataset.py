#!/usr/bin/env python3
"""W9 4-4 만든 HDF5 를 Cosmos LIBERO 로더로 읽어 본다. (서버 cosmos-policy .venv 전용)

    cosmos-policy/.venv/bin/python -m tools.check_cosmos_dataset --data-dir data/hdf5

학습과 같은 설정(`cosmos_policy_experiment_configs.py:41-61` — chunk 16, 이미지 증강, 손목 영상, proprio)으로
`LIBERODataset` 을 만들고 에피소드·step 수, 묶음(suite)별 step 수, 지시문, 정규화 통계, 샘플 한 칸의 모양을 찍는다.
`--data-dir` 바로 아래 폴더가 묶음 이름이다 (예: `data/hdf5/panda_sim/…hdf5` 이면 `panda_sim`).

**T5 임베딩은 가짜다.** 진짜는 T5-11B 가 필요하다 (CHECKLIST 4-4, 받기 전 확인). 여기서는 지시문마다 0 으로 채운
(1, 512, 1024) bfloat16 — `libero_t5_embeddings.pkl` 과 같은 모양 — 을 임시 파일로 만들어 샘플 모양만 본다. 학습에 쓰면 안 된다.

**부작용** — 로더가 `<data-dir>/dataset_statistics.json` 을 만들고, 있으면 다시 계산하지 않고 읽는다
(`dataset_common.py:250-278`). 데이터를 바꾼 뒤에는 `--recompute-stats` 로 지우고 다시 만든다.
"""

from __future__ import annotations

import argparse
import os
import pickle
import tempfile
from collections import Counter
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # 무엇도 받지 않는다 (① 408MB 사고)
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np  # noqa: E402
import torch  # noqa: E402

from cosmos_policy.datasets.libero_dataset import LIBERODataset  # noqa: E402

STATS_FILE = "dataset_statistics.json"


def fake_t5(commands, path: Path) -> None:
    zeros = torch.zeros(1, 512, 1024, dtype=torch.bfloat16)
    with open(path, "wb") as f:
        pickle.dump({c: zeros for c in commands}, f)


def describe(name, value) -> str:
    if isinstance(value, (torch.Tensor, np.ndarray)):
        arr = value.float() if isinstance(value, torch.Tensor) else value
        lo, hi = float(arr.min()), float(arr.max())
        return f"{name:<22} {tuple(value.shape)}  {value.dtype}  [{lo:.3f}, {hi:.3f}]"
    return f"{name:<22} {value!r}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=Path("data/hdf5"))
    parser.add_argument("--recompute-stats", action="store_true", help=f"{STATS_FILE} 를 지우고 다시 계산한다")
    parser.add_argument("--samples", type=int, default=3, help="모양을 찍을 샘플 수 (첫 하나만 자세히)")
    args = parser.parse_args()

    stats = args.data_dir / STATS_FILE
    if args.recompute_stats and stats.exists():
        stats.unlink()
    elif stats.exists():
        newest = max(p.stat().st_mtime for p in args.data_dir.rglob("*.hdf5"))
        if stats.stat().st_mtime < newest:
            print(f"!! {stats} 가 HDF5 보다 오래됐다 — 옛 통계로 정규화된다. --recompute-stats 를 고려할 것\n")

    # 1. T5 없이 — 에피소드·지시문·통계까지
    dataset = LIBERODataset(data_dir=str(args.data_dir), chunk_size=16, t5_text_embeddings_path="",
                            use_image_aug=True, use_stronger_image_aug=True, use_wrist_images=True,
                            use_proprio=True, normalize_proprio=True, normalize_actions=True,
                            num_duplicates_per_image=4, return_value_function_returns=True, gamma=0.99)
    print(f"\n에피소드 {dataset.num_episodes}, step {dataset.num_steps}, 한 epoch {len(dataset)}")
    suites = Counter()
    for ep in dataset.data.values():
        suites[ep["suite"]] += ep["num_steps"]
    for suite, steps in sorted(suites.items()):
        print(f"  묶음 {suite}: step {steps} ({steps / dataset.num_steps:.0%})")
    print("지시문:", sorted(dataset.unique_commands))
    for key in ("actions", "proprio"):
        print(f"{key} min", np.round(dataset.dataset_stats[f"{key}_min"], 4))
        print(f"{key} max", np.round(dataset.dataset_stats[f"{key}_max"], 4))

    # 2. 가짜 T5 로 샘플 한 칸
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / "fake_t5.pkl"
        fake_t5(dataset.unique_commands, fake)
        with open(fake, "rb") as f:
            dataset.t5_text_embeddings = pickle.load(f)
    for n, idx in enumerate(np.linspace(0, len(dataset) - 1, args.samples).astype(int)):
        sample = dataset[int(idx)]
        if n == 0:
            print(f"\n샘플 {idx} (가짜 T5)")
            for key, value in sample.items():
                print("  " + describe(key, value))
        else:
            print(f"샘플 {idx}: video {tuple(sample['video'].shape)}, actions {tuple(sample['actions'].shape)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
