#!/usr/bin/env python3
"""W9 4-4 만든 HDF5 를 Cosmos LIBERO 로더로 읽어 본다. (서버 cosmos-policy .venv 전용)

    cosmos-policy/.venv/bin/python -m tools.check_cosmos_dataset --data-dir data/hdf5

학습과 같은 설정(`cosmos_policy_experiment_configs.py:41-61` — chunk 16, 이미지 증강, 손목 영상, proprio)으로
`LIBERODataset` 을 만들고 에피소드·step 수, 묶음(suite)별 step 수, 지시문, 정규화 통계, 샘플 한 칸의 모양을 찍는다.
`--data-dir` 바로 아래 폴더가 묶음 이름이다 (예: `data/hdf5/panda_sim/…hdf5` 이면 `panda_sim`).

`--t5`를 지정하면 실제 T5 임베딩과 모델 입력 배치까지 검사한다. 생략하면 0으로 채운 임베딩으로 구조만 검사하며
`training_ready`는 False다. 손목 영상 전용 데이터는 외부 카메라 입력을 끄고 25프레임/7 latent 구성을 검사한다.
`--statistics`로 체크포인트의 LIBERO 통계를 사용하면 일정한 쿼터니언 값 때문에 생기는 0 나누기를 피하고 기존 정규화 뜻을 유지한다.

**부작용** — 로더가 `<data-dir>/dataset_statistics.json` 을 만들고, 있으면 다시 계산하지 않고 읽는다
(`dataset_common.py:250-278`). 데이터를 바꾼 뒤에는 `--recompute-stats` 로 지우고 다시 만든다.
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
from collections import Counter
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # 무엇도 받지 않는다 (① 408MB 사고)
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np  # noqa: E402
import torch  # noqa: E402
import h5py  # noqa: E402

from cosmos_policy.datasets.libero_dataset import LIBERODataset  # noqa: E402
from docs.W9.d405.check_dataset import check, check_embeddings  # noqa: E402
from docs.W9.d405.train import observation_mode  # noqa: E402

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


def verify_sample(sample, mode, real_t5):
    expected_frames = 25 if mode == 'wrist_only' else 33
    if tuple(sample['video'].shape) != (3, expected_frames, 224, 224):
        raise ValueError(f'Unexpected model video shape: {sample["video"].shape}')
    if tuple(sample['actions'].shape) != (16, 7):
        raise ValueError('Unexpected action chunk shape.')
    if tuple(sample['t5_text_embeddings'].shape) != (512, 1024):
        raise ValueError('Unexpected T5 embedding shape.')
    for key, value in sample.items():
        if isinstance(value, (np.ndarray, torch.Tensor)):
            finite = torch.isfinite(value).all() if isinstance(value, torch.Tensor) else np.isfinite(value).all()
            if not bool(finite):
                raise ValueError(f'Non-finite training sample field: {key}')
    if mode == 'wrist_only' and (sample['current_image_latent_idx'] != -1 or sample['future_image_latent_idx'] != -1):
        raise ValueError('Wrist alias must never be used as a third-person camera.')
    if real_t5 and not torch.count_nonzero(sample['t5_text_embeddings']):
        raise ValueError('Real T5 embeddings must not be all zero.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=Path("data/hdf5"))
    parser.add_argument("--recompute-stats", action="store_true", help=f"{STATS_FILE} 를 지우고 다시 계산한다")
    parser.add_argument("--samples", type=int, default=3, help="모양을 찍을 샘플 수 (첫 하나만 자세히)")
    parser.add_argument('--t5', type=Path, help='Use and validate real T5 embeddings instead of temporary zero embeddings')
    parser.add_argument('--statistics', type=Path, help='Use pretrained LIBERO normalization statistics; preserves checkpoint scales')
    parser.add_argument('--report', type=Path, help='Write the actual loader validation result as JSON')
    args = parser.parse_args()
    if args.samples < 1:
        parser.error('--samples must be positive.')
    structure = check(args.data_dir)
    mode = observation_mode(args.data_dir)
    measured = {}
    for field, dataset_key in [('actions', 'actions'), ('proprio', 'robot_states')]:
        low, high = None, None
        for path in sorted(args.data_dir.glob('*/*.hdf5')):
            with h5py.File(path, 'r') as source:
                for demo in source['data'].values():
                    values = demo[dataset_key][:]
                    low = values.min(axis=0) if low is None else np.minimum(low, values.min(axis=0))
                    high = values.max(axis=0) if high is None else np.maximum(high, values.max(axis=0))
        measured[field+'_min'] = low.tolist()
        measured[field+'_max'] = high.tolist()
        measured[field+'_constant_axes'] = np.flatnonzero(high == low).tolist()
    if args.t5:
        check_embeddings(args.t5, structure['instructions'])

    stats = args.data_dir / STATS_FILE
    if args.statistics:
        values = json.loads(args.statistics.read_text(encoding='utf-8'))
        for key, width in [('actions', 7), ('proprio', 9)]:
            low, high = np.asarray(values[f'{key}_min']), np.asarray(values[f'{key}_max'])
            if low.shape != (width,) or high.shape != (width,) or not np.isfinite([low, high]).all() or np.any(high <= low):
                raise ValueError(f'Invalid normalization ranges for {key}')
        stats.write_text(json.dumps(values, indent=2), encoding='utf-8')
        (args.data_dir/'dataset_statistics_post_norm.json').unlink(missing_ok=True)
    elif args.recompute_stats:
        stats.unlink(missing_ok=True)
        (args.data_dir/'dataset_statistics_post_norm.json').unlink(missing_ok=True)
    elif stats.exists():
        newest = max(p.stat().st_mtime for p in args.data_dir.rglob("*.hdf5"))
        if stats.stat().st_mtime < newest:
            print(f"!! {stats} 가 HDF5 보다 오래됐다 — 옛 통계로 정규화된다. --recompute-stats 를 고려할 것\n")

    # 1. T5 없이 — 에피소드·지시문·통계까지
    dataset = LIBERODataset(data_dir=str(args.data_dir), chunk_size=16,
                            t5_text_embeddings_path=str(args.t5) if args.t5 else "",
                            use_image_aug=True, use_stronger_image_aug=True, use_wrist_images=True,
                            use_third_person_images=mode != 'wrist_only',
                            use_proprio=True, normalize_proprio=True, normalize_actions=True,
                            num_duplicates_per_image=4, return_value_function_returns=True, gamma=0.99,
                            demonstration_sampling_prob=1.0, success_rollout_sampling_prob=0.0)
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
        for episode in dataset.data.values():
            if not np.isfinite(episode[key]).all():
                raise ValueError(f'Non-finite normalized {key}; use nondegenerate pretrained LIBERO statistics with --statistics.')

    if not args.t5:
        zeros = torch.zeros(1, 512, 1024, dtype=torch.bfloat16)
        dataset.t5_text_embeddings = {command: zeros for command in dataset.unique_commands}
    sample_indices = set(np.linspace(0, len(dataset) - 1, args.samples).astype(int).tolist())
    offset = 0
    for episode in dataset.data.values():
        sample_indices.update([offset, offset + episode['num_steps'] - 1])
        offset += episode['num_steps']
    samples = []
    for n, idx in enumerate(sorted(sample_indices)):
        sample = dataset[int(idx)]
        verify_sample(sample, mode, bool(args.t5))
        samples.append(dict(index=int(idx), video_shape=list(sample['video'].shape),
                            actions_shape=list(sample['actions'].shape),
                            current_image_latent_idx=int(sample['current_image_latent_idx']),
                            future_image_latent_idx=int(sample['future_image_latent_idx'])))
        if n == 0:
            print(f"\n샘플 {idx} ({'실제' if args.t5 else '가짜'} T5, {mode})")
            for key, value in sample.items():
                print("  " + describe(key, value))
        else:
            print(f"샘플 {idx}: video {tuple(sample['video'].shape)}, actions {tuple(sample['actions'].shape)}")
    from torch.utils.data._utils.collate import default_collate
    batch = default_collate([dataset[index] for index in sorted(sample_indices)[:2]])
    for key, value in batch.items():
        if isinstance(value, torch.Tensor) and not torch.isfinite(value).all():
            raise ValueError(f'Non-finite collated batch field: {key}')
    result = dict(status='passed', training_ready=bool(args.t5), observation_mode=mode,
                  episodes=dataset.num_episodes, steps=dataset.num_steps,
                  instructions=sorted(dataset.unique_commands), steps_by_suite=dict(suites),
                  real_t5=bool(args.t5), t5_path=str(args.t5.resolve()) if args.t5 else None,
                  normalization_source=str(args.statistics.resolve()) if args.statistics else 'dataset-derived',
                  measured_ranges=measured,
                  normalized_values_finite=True, samples_checked=len(samples), samples=samples,
                  batch_video_shape=list(batch['video'].shape), batch_actions_shape=list(batch['actions'].shape))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in result.items() if key != 'samples'}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
