"""Ensemble probability of exceedance. Pure functions, no I/O.

The probability that precipitation in a window reaches a threshold is estimated as the
fraction of ensemble members in which it does:

    P(total >= threshold) = (number of members with total >= threshold) / (number of members)

Nothing is fitted or smoothed. With M members the result can only be k/M for whole k, so
with 50 members it moves in steps of 2 %, "0 %" means "no member", not "impossible", and
"100 %" means "every member", not "certain".
"""
from __future__ import annotations

import numpy as np


def window_total(acc_start, acc_end) -> np.ndarray:
    """Precipitation inside a window from one member's accumulations at its two ends.

    Both inputs are accumulated since the start of the forecast, in the same unit. A
    slightly negative difference (packing noise in the source) is clamped to 0.
    """
    a = np.asarray(acc_start, dtype=np.float64)
    b = np.asarray(acc_end, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError("start and end fields have different shapes")
    return np.maximum(b - a, 0.0)


def exceedance_count(totals: np.ndarray, threshold: float) -> np.ndarray:
    """Number of members whose total is >= threshold, per grid cell.

    `totals` has shape (members, ...). The comparison is `>=` ("at least"): a member
    with exactly the threshold counts.
    """
    t = np.asarray(totals, dtype=np.float64)
    if t.ndim < 2:
        raise ValueError("expected an array of shape (members, ...)")
    if t.shape[0] == 0:
        raise ValueError("an ensemble needs at least one member")
    if not np.all(np.isfinite(t)):
        raise ValueError("non-finite member values")
    if not np.isfinite(threshold) or threshold <= 0:
        raise ValueError("threshold must be a positive number")
    return (t >= threshold).sum(axis=0).astype(np.uint16)


class ExceedanceCounter:
    """Same result as exceedance_count for several thresholds, one member at a time.

    Lets the pipeline hold two fields per member in memory instead of the whole ensemble.
    """

    def __init__(self, thresholds, shape):
        self.thresholds = [float(t) for t in thresholds]
        if not self.thresholds or any(not np.isfinite(t) or t <= 0 for t in self.thresholds):
            raise ValueError("thresholds must be positive numbers")
        self.counts = np.zeros((len(self.thresholds),) + tuple(shape), dtype=np.uint16)
        self.members = 0

    def add(self, total: np.ndarray) -> None:
        t = np.asarray(total, dtype=np.float64)
        if t.shape != self.counts.shape[1:]:
            raise ValueError("member field has the wrong shape")
        if not np.all(np.isfinite(t)):
            raise ValueError("non-finite member values")
        for i, thr in enumerate(self.thresholds):
            self.counts[i] += t >= thr
        self.members += 1


def probability_percent(count, members: int) -> np.ndarray:
    """Counts -> percent. Exactly 0.0 when no member exceeds and 100.0 when all do."""
    if members < 1:
        raise ValueError("an ensemble needs at least one member")
    c = np.asarray(count, dtype=np.float64)
    if c.size and (c.min() < 0 or c.max() > members):
        raise ValueError("count outside 0..members")
    return c * 100.0 / members
