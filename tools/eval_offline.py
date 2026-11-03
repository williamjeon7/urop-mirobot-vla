"""오프라인 정책 평가 — 녹화 HDF5 로 예측 action 을 라벨과 비교하고 추론 시간을 잰다 (W10, docs/W10/POLICY_RUN.md 4절).

로봇·카메라 없이, 학습 HDF5 에 든 관측(손목 영상 · proprio · 지시문)을 정책에 넣는다.
입력은 학습 로더가 본 그대로다: 영상은 뒤집지도 JPEG 압축하지도 않고, 가운데 자르기(`trained_with_image_aug`)만 한다.

두 단계다.

1. 체크포인트 합치기 (CPU) — 학습 체크포인트는 DCP 조각인데 추론 로더는 한 파일(.pt)만 읽는다 (`model_loader.py:217`)

    cosmos-policy/.venv/bin/python -m tools.eval_offline --ckpt <job>/checkpoints/iter_000002000 --convert-only

2. 평가 (GPU — 사용자가 tmux 에서)

    CUDA_VISIBLE_DEVICES=2 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \\
      cosmos-policy/.venv/bin/python -m tools.eval_offline --ckpt <job>/checkpoints/iter_000002000

지표 (Mirobot 배율 환산 mm = LIBERO m × 1000 × 0.663):
* 칸마다 위치 차 — 예측 action 과 라벨의 위치 3칸 차 × 0.05 m
* 묶음 끝 차 — 16칸 위치 차를 더한 것 (묶음을 다 실행했을 때 끝 자리의 차)
* 집게 부호 일치율, 정책 한 번 추론 시간
* 기준선 — 모두 0 을 낸다고 했을 때의 같은 지표. 정책이 이것보다 나아야 의미가 있다
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import pickle
import time
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

REPO = Path(__file__).resolve().parents[1]
CHUNK = 16
POS_SCALE_M, ROT_SCALE_RAD, MIROBOT_SCALE = 0.05, 0.5, 0.663
# 학습 때 덮어쓴 손목 전용 설정 (docs/W9/d405/train.py `wrist_only`) — 추론에도 같아야 한다
WRIST_ONLY_OPTS = ["model.config.state_t=7", "model.config.min_num_conditional_frames=3",
                   "model.config.max_num_conditional_frames=3", "model.config.tokenizer.chunk_duration=25"]
EXPERIMENT = "cosmos_predict2_2b_480p_libero__inference_only"


@dataclass
class EvalCfg:
    """`cosmos_utils.get_action` 이 읽는 설정만 (11/03 확인)."""
    suite: str = "libero"
    use_wrist_image: bool = True
    use_third_person_image: bool = False
    num_wrist_images: int = 1
    num_third_person_images: int = 1
    use_proprio: bool = True
    normalize_proprio: bool = True
    unnormalize_actions: bool = True
    chunk_size: int = CHUNK
    use_variance_scale: bool = False
    trained_with_image_aug: bool = True
    use_jpeg_compression: bool = False


def consolidated_path(ckpt: Path) -> Path:
    ckpt = ckpt / "model" if (ckpt / "model").is_dir() else ckpt
    return ckpt.parent / "model_consolidated.pt"


def convert(ckpt: Path) -> Path:
    """DCP `iter_*/model` → `iter_*/model_consolidated.pt` (이미 있으면 그대로)."""
    from torch.distributed.checkpoint.format_utils import dcp_to_torch_save
    src = ckpt / "model" if (ckpt / "model").is_dir() else ckpt
    out = consolidated_path(ckpt)
    if not out.exists():
        t0 = time.time()
        dcp_to_torch_save(str(src), str(out))
        print(f"converted {src} → {out} ({out.stat().st_size / 1e9:.2f} GB, {time.time() - t0:.0f} s)")
    return out


def load_policy(pt: Path):
    """모델을 만들고(손목 전용 설정) 가중치를 직접 넣는다 — 맞은 키 수를 확인하려고."""
    import torch
    from cosmos_policy._src.predict2.utils.model_loader import load_model_from_checkpoint
    model, _ = load_model_from_checkpoint(experiment_name=EXPERIMENT, s3_checkpoint_dir=str(pt),
                                          config_file="cosmos_policy/config/config.py", load_ema_to_reg=False,
                                          experiment_opts=WRIST_ONLY_OPTS, skip_load_model=True)
    state = torch.load(pt, map_location="cpu", weights_only=False)
    result = model.load_state_dict(state, strict=False)
    missing_net = [k for k in result.missing_keys if k.startswith("net.")]
    if result.unexpected_keys or missing_net:
        raise RuntimeError(f"checkpoint keys do not match: unexpected {result.unexpected_keys[:5]}, "
                           f"missing net.* {missing_net[:5]}")
    print(f"loaded {len(state)} keys (missing non-net {len(result.missing_keys)})")
    model.eval()
    return model.to("cuda")


def evaluate_episode(path: Path, model, cfg, stats, t5, every: int) -> dict:
    from cosmos_policy.experiments.robot.cosmos_utils import get_action
    import torch
    with h5py.File(path, "r") as f:
        instruction = f["data"].attrs["instruction"]
        demo = f["data/demo_0"]
        images = demo["obs/eye_in_hand_rgb"]
        states, labels = demo["robot_states"][:], demo["actions"][:]
        n = len(labels)
        emb = t5[instruction].float().cpu().numpy()
        step_mm, end_mm, zero_step_mm, zero_end_mm, grip_ok, rot_deg, secs = [], [], [], [], [], [], []
        for k in range(0, n, every):
            img = images[k]
            obs = {"wrist_image": img, "primary_image": img, "proprio": states[k]}
            torch.cuda.synchronize()
            t0 = time.perf_counter()
            out = get_action(cfg, model, stats, obs, emb, seed=1, randomize_seed=False,
                             num_denoising_steps_action=5)
            torch.cuda.synchronize()
            secs.append(time.perf_counter() - t0)
            pred = np.asarray(out["actions"], float)[:CHUNK]
            idx = np.minimum(np.arange(k, k + CHUNK), n - 1)  # 끝에서는 마지막 칸을 되풀이 (학습 로더와 같다)
            lab = labels[idx].astype(float)
            mm = POS_SCALE_M * 1000 * MIROBOT_SCALE
            d = (pred[:, :3] - lab[:, :3]) * mm
            step_mm.append(np.linalg.norm(d, axis=1).mean())
            end_mm.append(np.linalg.norm(d.sum(axis=0)))
            zero_step_mm.append(np.linalg.norm(lab[:, :3] * mm, axis=1).mean())
            zero_end_mm.append(np.linalg.norm(lab[:, :3].sum(axis=0) * mm))
            rot_deg.append(np.degrees(np.abs(pred[:, 3:6] - lab[:, 3:6]).max() * ROT_SCALE_RAD))
            grip_ok.append(float((np.sign(pred[:, 6]) == np.sign(lab[:, 6])).mean()))
    return dict(episode=path.name, instruction=instruction, steps=n, queries=len(secs),
                step_mm=float(np.mean(step_mm)), chunk_end_mm=float(np.mean(end_mm)),
                chunk_end_mm_max=float(np.max(end_mm)), zero_step_mm=float(np.mean(zero_step_mm)),
                zero_chunk_end_mm=float(np.mean(zero_end_mm)), rotation_deg_max=float(np.max(rot_deg)),
                gripper_agree=float(np.mean(grip_ok)), seconds=secs)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ckpt", type=Path, required=True, help="iter_* 폴더 (DCP) 또는 합친 .pt")
    p.add_argument("--hdf5", nargs="+", default=[str(REPO / "data/hdf5_mix/mirobot_real/*.hdf5")])
    p.add_argument("--stats", type=Path, default=REPO / "data/hdf5_mix/dataset_statistics.json")
    p.add_argument("--t5", type=Path, default=REPO / "data/hdf5_mix/t5_embeddings.pkl")
    p.add_argument("--every", type=int, default=CHUNK, help="몇 칸마다 물을지 (16 = 묶음마다)")
    p.add_argument("--convert-only", action="store_true")
    p.add_argument("--report", type=Path)
    a = p.parse_args()
    ckpt = a.ckpt.resolve()
    pt = ckpt if ckpt.suffix == ".pt" else convert(ckpt)
    if a.convert_only:
        return
    files = sorted({str(Path(f).resolve()) for g in a.hdf5 for f in glob.glob(g)})
    if not files:
        raise SystemExit(f"no HDF5 matched {a.hdf5}")
    stats_path, t5_path = a.stats.resolve(), a.t5.resolve()
    report_arg = a.report.resolve() if a.report else None
    os.chdir(REPO / "cosmos-policy")  # 설정 파일 경로가 이 폴더 기준이다 (학습도 여기서 돌았다)
    from cosmos_policy.experiments.robot.cosmos_utils import load_dataset_stats
    model = load_policy(pt)
    stats = load_dataset_stats(str(stats_path))
    t5 = pickle.load(open(t5_path, "rb"))
    results = []
    for f in files:
        r = evaluate_episode(Path(f), model, EvalCfg(), stats, t5, a.every)
        results.append(r)
        print(f"{r['episode'][:40]:40s} 칸 {r['step_mm']:.2f} mm (0 기준 {r['zero_step_mm']:.2f})  "
              f"묶음 끝 {r['chunk_end_mm']:.1f} mm (0 기준 {r['zero_chunk_end_mm']:.1f})  집게 {r['gripper_agree']:.2f}  "
              f"추론 중앙 {np.median(r['seconds'][1:] or r['seconds']):.2f} s")
    report = report_arg or REPO / f"docs/W10/data/eval_offline_{pt.parent.parent.parent.name}_{pt.parent.name}.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(dict(ckpt=str(pt), experiment=EXPERIMENT, opts=WRIST_ONLY_OPTS, every=a.every,
                                      results=results), indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"report → {report}")


if __name__ == "__main__":
    main()
