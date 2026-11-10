"""Decode one GRIB message with ecCodes and check it is what we think it is."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import eccodes as ec
import numpy as np

from .grid import Grid, grid_from_keys
from .process import reference_time

_GRID_KEYS = ["gridType", "Ni", "Nj", "iScansNegatively", "jScansPositively", "jPointsAreConsecutive",
              "latitudeOfFirstGridPointInDegrees", "longitudeOfFirstGridPointInDegrees",
              "latitudeOfLastGridPointInDegrees", "longitudeOfLastGridPointInDegrees",
              "iDirectionIncrementInDegrees", "jDirectionIncrementInDegrees"]


@dataclass
class Field:
    short_name: str
    units: str
    step_type: str        # "accum", "instant", ...
    start_step: int       # hours
    end_step: int         # hours
    reference: datetime   # aware, UTC
    grid: Grid
    values: np.ndarray    # shape (nj, ni), row 0 = northernmost
    quantum: float        # smallest step the packing can represent, in `units` (0 for a constant field)


def decode(message: bytes) -> Field:
    h = ec.codes_new_from_message(message)
    try:
        if ec.codes_get(h, "numberOfMissing") != 0:
            raise ValueError("field has missing values; not handled")
        grid = grid_from_keys({k: ec.codes_get(h, k) for k in _GRID_KEYS})
        if ec.codes_get(h, "stepUnits") != 1:  # 1 == hours
            raise ValueError("step units are not hours")
        values = ec.codes_get_values(h)
        # Packed value = (R + X * 2^E) / 10^D with integer X, so one step of X is 2^E / 10^D.
        if ec.codes_get(h, "bitsPerValue") == 0:
            quantum = 0.0
        else:
            quantum = 2.0 ** ec.codes_get(h, "binaryScaleFactor") / 10.0 ** ec.codes_get(h, "decimalScaleFactor")
        if values.size != grid.ni * grid.nj:
            raise ValueError("value count does not match grid")
        return Field(
            short_name=ec.codes_get(h, "shortName"),
            units=ec.codes_get(h, "units"),
            step_type=ec.codes_get(h, "stepType"),
            start_step=int(ec.codes_get(h, "startStep")),
            end_step=int(ec.codes_get(h, "endStep")),
            reference=reference_time(ec.codes_get(h, "dataDate"), ec.codes_get(h, "dataTime")),
            grid=grid,
            values=values.reshape(grid.nj, grid.ni),
            quantum=quantum,
        )
    finally:
        ec.codes_release(h)


def expect_accumulated_tp(f: Field, step: int) -> Field:
    """Fail loudly if ECMWF ever changes what `tp` means (units or accumulation window)."""
    problems = []
    if f.short_name != "tp":
        problems.append(f"shortName {f.short_name!r}")
    if f.units != "m":
        problems.append(f"units {f.units!r} (expected 'm')")
    if f.step_type != "accum":
        problems.append(f"stepType {f.step_type!r} (expected 'accum')")
    if (f.start_step, f.end_step) != (0, step):
        problems.append(f"accumulation window {f.start_step}-{f.end_step} h (expected 0-{step})")
    if problems:
        raise ValueError("unexpected tp field: " + "; ".join(problems))
    return f
