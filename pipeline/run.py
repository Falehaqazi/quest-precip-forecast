"""Build the static data for the site from the newest complete ECMWF run.

    python -m pipeline.run --out web/data
    python -m pipeline.run --out web/data --date 20261110 --hour 00 --max-step 24

Writes <out>/manifest.json last, so a failed run never leaves a manifest that
points at missing files.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import catalogue
from .encode import codes_to_png, quantise
from .gribio import Field, decode, expect_accumulated_tp
from .process import deaccumulate, iso_utc, metres_to_mm, valid_time

SCHEMA_VERSION = 1
TP_SCALE_MM = 0.05          # see DECISIONS D7
FETCH_WORKERS = 4

# Legend for per-interval precipitation: lower bound of each class in mm, and its colour.
# Values below the first bound are drawn transparent.
TP_LEGEND = [
    (0.1, "#d6e8f5"), (0.5, "#b3d3ec"), (1, "#86b8e0"), (2, "#5a9bd1"), (5, "#3a7dbd"),
    (10, "#2760a3"), (20, "#1b4585"), (50, "#6a3d9a"), (100, "#b5179e"),
]

ATTRIBUTION = {
    "text": "Based on data and products of the European Centre for Medium-Range Weather "
            "Forecasts (ECMWF). © ECMWF, published under CC BY 4.0. The data has been "
            "modified: precipitation was de-accumulated into per-interval amounts, "
            "converted from m to mm and rounded to 0.05 mm.",
    "licence_url": "https://creativecommons.org/licenses/by/4.0/",
    "source_url": "https://www.ecmwf.int/en/forecasts/datasets/open-data",
}


def fetch_tp(session, run: catalogue.Run, step: int, retries: int = 3) -> Field:
    for attempt in range(1, retries + 1):
        try:
            msg = catalogue.fetch_message(session, run, step, param="tp", levtype="sfc")
            return expect_accumulated_tp(decode(msg), step)
        except (IOError, OSError) as e:
            if attempt == retries:
                raise
            print(f"  step {step}: {e!r}; retry {attempt}", file=sys.stderr)
            time.sleep(5 * attempt)


def build(out: Path, run: catalogue.Run, steps: list[int]) -> dict:
    session = catalogue.new_session()
    t0 = time.time()
    with ThreadPoolExecutor(FETCH_WORKERS) as pool:
        fields = dict(zip(steps, pool.map(lambda s: fetch_tp(session, run, s), steps)))
    print(f"fetched and decoded {len(fields)} tp fields in {time.time() - t0:.0f}s")

    grids = {f.grid for f in fields.values()}
    refs = {f.reference for f in fields.values()}
    if len(grids) != 1 or len(refs) != 1:
        raise ValueError("fields disagree on grid or reference time")
    grid, ref = grids.pop(), refs.pop()
    if ref != run.reference_time:
        raise ValueError(f"file reference time {ref} != requested run {run.reference_time}")

    intervals = deaccumulate({s: metres_to_mm(f.values) for s, f in fields.items()})

    layer_dir = out / "tp_interval"
    layer_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for iv in intervals:
        codes, clipped = quantise(iv.values, TP_SCALE_MM)
        name = f"{iv.end_step:03d}.png"
        (layer_dir / name).write_bytes(codes_to_png(codes))
        entries.append({
            "start_step": iv.start_step, "end_step": iv.end_step, "hours": iv.hours,
            "start_utc": iso_utc(valid_time(ref, iv.start_step)),
            "end_utc": iso_utc(valid_time(ref, iv.end_step)),
            "file": f"tp_interval/{name}",
            "max": round(float(iv.values.max()), 2),
            "negative_count": iv.negative_count,
            "most_negative": round(iv.most_negative, 3),
            "clipped_count": clipped,
        })

    manifest = {
        "schema": SCHEMA_VERSION,
        "generated_utc": iso_utc(datetime.now(timezone.utc)),
        "attribution": ATTRIBUTION,
        "run": {
            "centre": "ECMWF", "model": "IFS", "stream": run.stream, "resolution_deg": abs(grid.dlon),
            "reference_utc": iso_utc(ref), "source_directory": run.directory + "/",
            "last_step": steps[-1],
        },
        "grid": {**grid.to_dict(), "bounds": grid.image_bounds(),
                 "order": "row-major; row 0 is the northernmost latitude, column 0 the westernmost longitude"},
        "layers": [{
            "id": "tp_interval",
            "kind": "amount",
            "title": "Precipitation in the interval",
            "description": "Total precipitation (rain + snow, liquid-water equivalent) that the "
                           "model accumulates between the start and end of each interval. "
                           "Derived from ECMWF parameter tp (paramId 228).",
            "units": "mm",
            "encoding": {"format": "png-rg16", "scale": TP_SCALE_MM, "offset": 0.0,
                         "formula": "value = offset + scale * (R * 256 + G)"},
            "legend": {"type": "threshold", "transparent_below": TP_LEGEND[0][0],
                       "stops": [{"from": v, "color": c} for v, c in TP_LEGEND]},
            "intervals": entries,
        }],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--date", help="YYYYMMDD (default: newest complete run)")
    p.add_argument("--hour", choices=["00", "12"])
    p.add_argument("--max-step", type=int, help="only process steps up to this hour (for quick tests)")
    a = p.parse_args(argv)

    if bool(a.date) != bool(a.hour):
        p.error("--date and --hour go together")
    if a.date:
        run = catalogue.Run(a.date, a.hour)
    else:
        run = catalogue.latest_complete_run(catalogue.new_session(), datetime.now(timezone.utc))
    steps = catalogue.expected_steps(run.hour)
    if a.max_step is not None:
        steps = [s for s in steps if s <= a.max_step]
    print(f"run {run.date} {run.hour}z, {len(steps)} steps up to {steps[-1]} h -> {a.out}")

    manifest = build(a.out, run, steps)
    layer = manifest["layers"][0]
    size = sum(f.stat().st_size for f in (a.out / "tp_interval").glob("*.png"))
    worst = min(i["most_negative"] for i in layer["intervals"])
    print(f"wrote {len(layer['intervals'])} intervals, {size / 1e6:.1f} MB of PNG; "
          f"largest interval max {max(i['max'] for i in layer['intervals'])} mm; "
          f"most negative raw difference {worst} mm; "
          f"clipped points {sum(i['clipped_count'] for i in layer['intervals'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
