# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""Pure-Python classification metrics (no third-party deps) for the fatigue eval.

Kept dependency-free to match the rest of `brainlift_eval/`, so the offline run
is reproducible in CI without numpy/sklearn."""

from __future__ import annotations

import math


def accuracy(probs: list[float], labels: list[int], threshold: float) -> float:
    if not labels:
        return 0.0
    correct = sum(1 for p, y in zip(probs, labels) if (1 if p >= threshold else 0) == y)
    return correct / len(labels)


def log_loss(probs: list[float], labels: list[int], eps: float = 1e-12) -> float:
    if not labels:
        return 0.0
    total = 0.0
    for p, y in zip(probs, labels):
        p = min(1.0 - eps, max(eps, p))
        total += -(y * math.log(p) + (1 - y) * math.log(1.0 - p))
    return total / len(labels)


def auc(probs: list[float], labels: list[int]) -> float:
    """ROC-AUC via the rank-sum (Mann-Whitney U) identity, with tie handling."""
    pos = [p for p, y in zip(probs, labels) if y == 1]
    neg = [p for p, y in zip(probs, labels) if y == 0]
    if not pos or not neg:
        return 0.0
    # average-rank of all scores
    paired = sorted(zip(probs, range(len(probs))), key=lambda t: t[0])
    ranks = [0.0] * len(probs)
    i = 0
    while i < len(paired):
        j = i
        while j + 1 < len(paired) and paired[j + 1][0] == paired[i][0]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # 1-based average rank for the tie group
        for k in range(i, j + 1):
            ranks[paired[k][1]] = avg_rank
        i = j + 1
    sum_pos_ranks = sum(r for r, y in zip(ranks, labels) if y == 1)
    n_pos, n_neg = len(pos), len(neg)
    return (sum_pos_ranks - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
