"""Units, de-accumulation and time arithmetic. Pure functions, no I/O."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np

MM_PER_M = 1000.0
SECONDS_PER_HOUR = 3600.0


def metres_to_mm(values):
    """ECMWF `tp` is metres of water; 1 m == 1000 mm."""
    return np.asarray(values, dtype=np.float64) * MM_PER_M


def rate_to_mm_per_hour(values):
    """`tprate` is kg m-2 s-1. 1 kg of water over 1 m2 is 1 mm deep, so this is mm/s."""
    return np.asarray(values, dtype=np.float64) * SECONDS_PER_HOUR


@dataclass
class Interval:
    start_step: int          # hours since run reference time
    end_step: int
    values: np.ndarray       # amount within (start_step, end_step], clamped at >= 0
    negative_count: int      # points where the raw difference was < 0
    most_negative: float     # the most negative raw difference (0.0 if none)

    @property
    def hours(self) -> int:
        return self.end_step - self.start_step


def deaccumulate(accumulated: dict[int, np.ndarray]) -> list[Interval]:
    """Turn fields accumulated since step 0 into per-interval amounts.

    `accumulated` maps step (hours) -> field. Step 0 must be present so the first
    interval is a true difference rather than an assumption that tp(0) == 0.
    Slightly negative differences (packing noise) are clamped to 0 and reported.
    """
    steps = sorted(accumulated)
    if not steps or steps[0] != 0:
        raise ValueError("step 0 is required to de-accumulate")
    if len(set(a.shape for a in accumulated.values())) != 1:
        raise ValueError("fields have different shapes")
    out = []
    for prev, cur in zip(steps, steps[1:]):
        diff = np.asarray(accumulated[cur], dtype=np.float64) - np.asarray(accumulated[prev], dtype=np.float64)
        neg = diff < 0
        out.append(Interval(
            start_step=prev, end_step=cur,
            values=np.where(neg, 0.0, diff),
            negative_count=int(neg.sum()),
            most_negative=float(diff.min()) if neg.any() else 0.0,
        ))
    return out


def reference_time(data_date: int, data_time: int) -> datetime:
    """GRIB dataDate (YYYYMMDD) and dataTime (HHMM as an int, e.g. 0 or 1200) -> aware UTC datetime.

    GRIB reference times are UTC by definition; nothing here depends on the local zone.
    """
    y, m, d = data_date // 10000, data_date // 100 % 100, data_date % 100
    return datetime(y, m, d, data_time // 100, data_time % 100, tzinfo=timezone.utc)


def valid_time(ref: datetime, step_hours: int) -> datetime:
    if ref.tzinfo is None:
        raise ValueError("reference time must be timezone-aware")
    return ref.astimezone(timezone.utc) + timedelta(hours=step_hours)


def iso_utc(dt: datetime) -> str:
    """ISO 8601 with an explicit Z, so browsers never parse it as local time."""
    if dt.tzinfo is None:
        raise ValueError("refusing to format a naive datetime")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
