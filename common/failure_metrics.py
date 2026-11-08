"""Failure-detection metrics as defined by SAFE (NeurIPS 2025) and Hide-and-Seek (2026).

Convention (both papers): failure rollouts are positives, successful rollouts are negatives.
A rollout is flagged when its score first reaches the threshold at any detector time step.
"""
from __future__ import annotations

import numpy as np


def first_alarms(scores, thresholds):
    """First index where score >= threshold (scalar or per-step), or None for each rollout."""
    alarms = []
    for score in scores:
        score = np.asarray(score, dtype=float)
        threshold = np.asarray(thresholds, dtype=float)
        threshold = np.full(score.shape, threshold) if threshold.ndim == 0 else threshold[:len(score)]
        hits = np.flatnonzero(score >= threshold)
        alarms.append(int(hits[0]) if hits.size else None)
    return alarms


def alarm_metrics(alarms, lengths, failed):
    """bACC, wACC, TWA (Hide-and-Seek B.3) and mean relative detection time (SAFE)."""
    failed = np.asarray(failed, dtype=bool)
    flagged = np.array([a is not None for a in alarms])
    n_pos, n_neg = int(failed.sum()), int((~failed).sum())
    tp, tn = int((flagged & failed).sum()), int((~flagged & ~failed).sum())
    tpr = tp / n_pos if n_pos else float("nan")
    tnr = tn / n_neg if n_neg else float("nan")
    beta = n_neg / len(failed) if len(failed) else float("nan")
    timely = [1 - alarms[i] / lengths[i] for i in np.flatnonzero(flagged & failed)]
    twa = 0.5 * (sum(timely) / n_pos + tnr) if n_pos and n_neg else float("nan")
    # SAFE eval_detection_time: undetected failures count as 1.0 (end of rollout).
    det = [alarms[i] / lengths[i] if alarms[i] is not None else 1.0 for i in np.flatnonzero(failed)]
    return dict(tpr=tpr, tnr=tnr, bacc=(tpr + tnr) / 2, wacc=beta * tnr + (1 - beta) * tpr, twa=twa,
                avg_det_time=float(np.mean(det)) if det else float("nan"),
                n_fail=n_pos, n_success=n_neg)


def auroc(scores, failed):
    """Rank-based ROC AUC of one score per rollout (higher = more likely failure); ties count half."""
    scores, failed = np.asarray(scores, dtype=float), np.asarray(failed, dtype=bool)
    pos, neg = scores[failed], scores[~failed]
    if not len(pos) or not len(neg):
        return float("nan")
    greater = (pos[:, None] > neg[None, :]).sum() + 0.5 * (pos[:, None] == neg[None, :]).sum()
    return float(greater / (len(pos) * len(neg)))


def scores_at_quantile(scores, min_length, q):
    """SAFE compute_roc_by_quantiles: read each rollout at round((T_min - 1) * q) of its task."""
    return [np.asarray(s)[round((m - 1) * q)] for s, m in zip(scores, min_length)]
