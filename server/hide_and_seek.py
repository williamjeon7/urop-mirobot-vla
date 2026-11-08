"""Hide-and-Seek failure detector, reimplemented from the paper (official code not released yet).

Park et al., "Hide-and-Seek in Trajectories: Discovering Failure Signals for VLA Runtime
Monitoring", arXiv 2605.30834 (https://github.com/deeplearning-wisc/hide_and_seek: README only, 2026-11-08).

Followed from the paper:
- Sec. 4.1 / B.1: single-layer LSTM (hidden 256) -> linear -> sigmoid score s_t on each prefix.
- Eq. 2 inter loss: hinge(m_r - max_t s_t(fail) + max_t s_t(success)) over all fail x success pairs.
- Eq. 3 intra loss: t_onset = argmax_t sg(s_t - s_{t-1}), t_onset in [2, N] (1-indexed);
  hinge(m_o - mean_{t>=onset} s_t + mean_{t<onset} s_t) over failures.
- Eq. 4: L = L_inter + lambda * L_intra, L_intra only after a warm-up.
- B.1: AdamW lr 5e-4, weight decay 0.1, 300 epochs, batch 64, balanced fail/success batches.
- B.2: one-sided functional conformal threshold zeta_t = mu_t + h * sigma(t) from successful
  calibration rollouts split 30/70; alarm at the first t with s_t >= zeta_t; alpha in {0.15, 0.20, 0.25}.
Our choices where the paper gives no value (recorded in config.json):
- Time step = one policy query. Each query already pools one 16-action Cosmos chunk, which is what
  the paper's window w = chunk size does for pi0; `window` pools further over queries (default 1).
- Margins/lambda default to the paper's pi0 values (m_r 1.0, m_o 0.5, lambda 5e-3).
- Warm-up 50 epochs; features z-scored with training statistics.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path

import numpy as np

from common.failure_metrics import alarm_metrics, auroc, first_alarms

ALPHAS = (0.15, 0.20, 0.25)


@dataclass
class Config:
    window: int = 1
    hidden: int = 256
    margin_inter: float = 1.0
    margin_intra: float = 0.5
    intra_weight: float = 5e-3
    warmup_epochs: int = 50
    epochs: int = 300
    batch_size: int = 64
    lr: float = 5e-4
    weight_decay: float = 0.1
    seed: int = 0
    feature: str = "hidden_states"


def pool(features, window):
    """Non-overlapping average pooling over time: (T, D) -> (ceil(T / w), D)."""
    if window <= 1:
        return features
    return np.stack([features[i:i + window].mean(axis=0) for i in range(0, len(features), window)])


def load_dataset(directory, feature="hidden_states", window=1):
    directory = Path(directory)
    with (directory / "index.csv").open(encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    for row in rows:
        row["episode_success"] = int(row["episode_success"])
        row["features"] = pool(np.load(directory / "rollouts" / f"{row['trial_id']}.npz")[feature], window)
    return rows


def _torch():
    import torch
    return torch


def build_model(dim, hidden):
    torch = _torch()

    class Detector(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = torch.nn.LSTM(dim, hidden, num_layers=1, batch_first=True)
            self.head = torch.nn.Linear(hidden, 1)

        def forward(self, x):  # (B, T, D) -> (B, T) scores; causal, so s_t only sees the prefix
            return torch.sigmoid(self.head(self.lstm(x)[0])).squeeze(-1)

    return Detector()


def batch(sequences, mean, std, device):
    torch = _torch()
    length = max(len(s) for s in sequences)
    x = torch.zeros(len(sequences), length, sequences[0].shape[-1], device=device)
    mask = torch.zeros(len(sequences), length, dtype=torch.bool, device=device)
    for i, s in enumerate(sequences):
        x[i, :len(s)] = torch.as_tensor((s - mean) / std, dtype=torch.float32, device=device)
        mask[i, :len(s)] = True
    return x, mask


def inter_loss(scores, mask, failed, margin):
    """Eq. 2: every failure's peak score should exceed every success's peak score by `margin`."""
    peak = scores.masked_fill(~mask, -1.0).max(dim=1).values
    fail, success = peak[failed], peak[~failed]
    if not len(fail) or not len(success):
        return scores.sum() * 0
    return (margin - fail[:, None] + success[None, :]).clamp(min=0).mean()


def intra_loss(scores, mask, failed, margin):
    """Eq. 3: scores after the largest rise (proxy onset) should exceed scores before it."""
    torch = _torch()
    losses = []
    for s, m in zip(scores[failed], mask[failed]):
        s = s[m]
        if len(s) < 2:
            continue
        rise = (s[1:] - s[:-1]).detach()  # stop-gradient
        onset = int(torch.argmax(rise)) + 1  # 0-indexed, i.e. t_onset in [2, N] 1-indexed
        losses.append((margin - s[onset:].mean() + s[:onset].mean()).clamp(min=0))
    return torch.stack(losses).mean() if losses else scores.sum() * 0


def train(rows, config, device="cpu", log=print):
    torch = _torch()
    torch.manual_seed(config.seed)
    rng = np.random.default_rng(config.seed)
    stacked = np.concatenate([r["features"] for r in rows])
    mean, std = stacked.mean(axis=0), stacked.std(axis=0) + 1e-6
    model = build_model(stacked.shape[-1], config.hidden).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.lr, weight_decay=config.weight_decay)
    fail = [r for r in rows if not r["episode_success"]]
    success = [r for r in rows if r["episode_success"]]
    if not fail or not success:
        raise ValueError("학습 분할에 성공과 실패 시행이 모두 있어야 합니다.")
    half = config.batch_size // 2
    steps = max(1, math.ceil(len(rows) / config.batch_size))
    for epoch in range(config.epochs):
        for _ in range(steps):
            # Balanced sampler (B.1): equal numbers of failure and success rollouts per batch.
            chosen = ([fail[i] for i in rng.integers(len(fail), size=half)] +
                      [success[i] for i in rng.integers(len(success), size=half)])
            x, mask = batch([r["features"] for r in chosen], mean, std, device)
            failed = torch.tensor([not r["episode_success"] for r in chosen], device=device)
            scores = model(x)
            loss = inter_loss(scores, mask, failed, config.margin_inter)
            if epoch >= config.warmup_epochs:
                loss = loss + config.intra_weight * intra_loss(scores, mask, failed, config.margin_intra)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        if epoch % 50 == 0 or epoch == config.epochs - 1:
            log(f"epoch {epoch}: loss {float(loss):.4f}")
    return model, mean, std


def score(model, rows, mean, std, device="cpu"):
    torch = _torch()
    model.eval()
    with torch.no_grad():
        x, mask = batch([r["features"] for r in rows], mean, std, device)
        values = model(x).cpu().numpy()
    return [v[:len(r["features"])] for v, r in zip(values, rows)]


def _pad(scores, length):
    """Pad each score curve to `length` by repeating its last value (B.2)."""
    return np.stack([np.concatenate([s, np.full(length - len(s), s[-1])]) if len(s) < length else s[:length]
                     for s in scores])


def functional_threshold(calibration_scores, alpha, seed=0):
    """B.2 one-sided functional CP on successful calibration rollouts -> zeta_t (array over t)."""
    length = max(len(s) for s in calibration_scores)
    data = _pad(calibration_scores, length)
    order = np.random.default_rng(seed).permutation(len(data))
    cut = max(1, int(round(0.3 * len(data))))
    a, b = data[order[:cut]], data[order[cut:]]
    if not len(b):
        raise ValueError("보정용 성공 시행이 2개 이상 필요합니다.")
    mu = a.mean(axis=0)
    residual = np.abs(a - mu)
    n1 = len(a)
    rank = int(math.ceil((n1 + 1) * (1 - alpha)))
    if rank > n1:
        sigma = residual.max(axis=0)
    else:
        gamma = np.sort(residual.max(axis=1))[rank - 1]
        sigma = residual[residual.max(axis=1) <= gamma].max(axis=0)
    sigma = sigma + 1e-8
    h = np.quantile(((b - mu) / sigma).max(axis=1), 1 - alpha)
    return mu + h * sigma


def extend(threshold, length):
    return np.concatenate([threshold, np.full(max(0, length - len(threshold)), threshold[-1])])


def evaluate(scores, rows, thresholds):
    """Average bACC / wACC / TWA over alphas (as reported in the paper) plus AUROC of the peak score."""
    failed = [not r["episode_success"] for r in rows]
    lengths = [len(s) for s in scores]
    per_alpha = {}
    for alpha, zeta in thresholds.items():
        alarms = [first_alarms([s], extend(zeta, len(s))[:len(s)])[0] for s in scores]
        per_alpha[str(alpha)] = alarm_metrics(alarms, lengths, failed)
    keys = ("bacc", "wacc", "twa", "tpr", "tnr", "avg_det_time")
    mean = {k: float(np.nanmean([m[k] for m in per_alpha.values()])) for k in keys}
    mean["auroc_peak"] = auroc([float(np.max(s)) for s in scores], failed)
    mean.update(n_fail=sum(failed), n_success=len(failed) - sum(failed))
    return dict(mean_over_alpha=mean, per_alpha=per_alpha)


def run(data, out, config, device="cpu", unseen_task=None):
    torch = _torch()
    rows = load_dataset(data, config.feature, config.window)
    for row in rows:
        if unseen_task and row["task_id"] == unseen_task:
            row["split"] = "test_unseen"
    train_rows = [r for r in rows if r["split"] == "train" and r["task_id"] != unseen_task]
    calibration = [r for r in rows if r["split"] == "calibration" and r["episode_success"]]
    tests = {name: [r for r in rows if r["split"] == name] for name in ("test", "test_unseen")}
    if not calibration:
        raise ValueError("split=calibration 인 성공 시행이 필요합니다 (tools.annotate_mirobot_result --split).")
    model, mean, std = train(train_rows, config, device)
    thresholds = {a: functional_threshold(score(model, calibration, mean, std, device), a, config.seed)
                  for a in ALPHAS}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    report = dict(config=asdict(config), unseen_task=unseen_task, n_train=len(train_rows),
                  n_calibration=len(calibration), splits={})
    with (out / "scores.csv").open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["trial_id", "split", "task_id", "episode_success", "scores"])
        for name, group in tests.items():
            if not group:
                continue
            values = score(model, group, mean, std, device)
            report["splits"][name] = evaluate(values, group, thresholds)
            for r, s in zip(group, values):
                writer.writerow([r["trial_id"], name, r["task_id"], r["episode_success"],
                                 json.dumps([round(float(v), 5) for v in s])])
    torch.save(dict(state=model.state_dict(), mean=mean, std=std, config=asdict(config),
                    thresholds={str(a): t.tolist() for a, t in thresholds.items()}), out / "detector.pt")
    (out / "metrics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", type=Path, required=True, help="tools.export_failure_dataset 출력 폴더")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--unseen-task", choices=("red", "green", "blue"),
                        help="이 색을 학습에서 빼고 unseen 으로 평가")
    for field, value in asdict(Config()).items():
        parser.add_argument("--" + field.replace("_", "-"), type=type(value), default=value)
    args = parser.parse_args()
    config = Config(**{f: getattr(args, f) for f in asdict(Config())})
    report = run(args.data, args.out, config, args.device, args.unseen_task)
    for name, result in report["splits"].items():
        print(name, json.dumps(result["mean_over_alpha"], ensure_ascii=False))


if __name__ == "__main__":
    main()
