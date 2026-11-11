"""Build the static data for the site from the newest complete ECMWF run.

    python -m pipeline.run --out web/data
    python -m pipeline.run --out web/data --date 20261110 --hour 00 --max-step 24

Writes <out>/manifest.json last, so a failed run never leaves a manifest that
points at missing files.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from . import catalogue, ensemble, series
from .encode import codes_to_png, quantise
from .gribio import Field, decode, expect_accumulated_tp
from .process import MM_PER_M, deaccumulate, iso_utc, metres_to_mm, valid_time

SCHEMA_VERSION = 3
TP_SCALE_MM = 0.05          # see DECISIONS D7
FETCH_WORKERS = 4

# Legend for precipitation, as MEAN RATE over the interval in mm/h (lower bound of each class
# and its colour). The stored values stay amounts per interval; the browser divides by the
# interval length, so a colour means the same rate in a 3 h and in a 6 h interval (DECISIONS D14).
# One hue, light -> dark (sequential: more precipitation is darker). No rainbow.
# Rates below the first bound are drawn transparent.
TP_LEGEND = [
    (0.1, "#cde2fb"), (0.2, "#9ec5f4"), (0.5, "#6da7ec"), (1, "#3987e5"),
    (2, "#256abf"), (5, "#184f95"), (10, "#104281"), (20, "#0d366b"),
]

ATTRIBUTION = {
    "text": "Based on data and products of the European Centre for Medium-Range Weather "
            "Forecasts (ECMWF). © ECMWF, published under CC BY 4.0. The data has been "
            "modified: precipitation was de-accumulated into per-interval amounts, "
            "converted from m to mm and rounded to 0.05 mm; ensemble probabilities were "
            "computed by counting member forecasts.",
    "licence_url": "https://creativecommons.org/licenses/by/4.0/",
    "source_url": "https://www.ecmwf.int/en/forecasts/datasets/open-data",
}


def fetch_tp_bytes(session, run: catalogue.Run, step: int, retries: int = 3) -> bytes:
    """Network only. Runs in worker threads; ecCodes is NOT called here (see build)."""
    for attempt in range(1, retries + 1):
        try:
            return catalogue.fetch_message(session, run, step, param="tp", levtype="sfc")
        except (IOError, OSError) as e:
            if attempt == retries:
                raise
            print(f"  step {step}: {e!r}; retry {attempt}", file=sys.stderr)
            time.sleep(5 * attempt)


def build(out: Path, run: catalogue.Run, steps: list[int], ensemble_mode: str = "optional",
          cache: Path | None = None) -> dict:
    session = catalogue.new_session()
    t0 = time.time()
    with ThreadPoolExecutor(FETCH_WORKERS) as pool:
        messages = list(pool.map(lambda s: fetch_tp_bytes(session, run, s), steps))
    print(f"fetched {len(messages)} tp messages, {sum(map(len, messages)) / 1e6:.1f} MB, "
          f"in {time.time() - t0:.0f}s", flush=True)
    # Decode on the main thread only: calling ecCodes from the worker threads killed the
    # process without a Python traceback (observed on Windows, eccodes 2.50.0).
    fields: dict[int, Field] = {s: expect_accumulated_tp(decode(m), s) for s, m in zip(steps, messages)}

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
    stack = []
    for iv in intervals:
        codes, clipped = quantise(iv.values, TP_SCALE_MM)
        # The coarser of the two packing steps that were differenced, in mm. A difference of
        # one such step can be a true increment of almost nothing (DECISIONS D15).
        quantum_mm = MM_PER_M * max(fields[iv.start_step].quantum, fields[iv.end_step].quantum)
        stack.append(codes)
        name = f"{iv.end_step:03d}.png"
        (layer_dir / name).write_bytes(codes_to_png(codes))
        entries.append({
            "start_step": iv.start_step, "end_step": iv.end_step, "hours": iv.hours,
            "start_utc": iso_utc(valid_time(ref, iv.start_step)),
            "end_utc": iso_utc(valid_time(ref, iv.end_step)),
            "file": f"tp_interval/{name}",
            "max": round(float(iv.values.max()), 2),
            "source_quantum": round(quantum_mm, 5),
            "negative_count": iv.negative_count,
            "most_negative": round(iv.most_negative, 3),
            "clipped_count": clipped,
        })

    # The same codes re-cut by place, for the point time series (one small file per click).
    series_info = series.write_tiles(layer_dir / "series", np.stack(stack))
    series_info["path"] = "tp_interval/series/{ty}_{tx}.png"
    series_info["addressing"] = ("ty = row // tile, tx = col // tile; "
                                 "pixel(x = col % tile, y = k * tile + row % tile) is interval k")

    manifest = {
        "schema": SCHEMA_VERSION,
        "generated_utc": iso_utc(datetime.now(timezone.utc)),
        # Which code built this; pipeline/check.py uses it to notice undeployed changes.
        "build": {"commit": os.environ.get("GITHUB_SHA", "local")},
        "attribution": ATTRIBUTION,
        # The layer the page opens on. Changed below to the lowest ensemble threshold when
        # the probabilities were built (DECISIONS D25).
        "default_layer": "tp_interval",
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
            "display": {"normalise": "per_hour", "units": "mm/h",
                        "title": "Mean precipitation rate",
                        "formula": "displayed = value / interval hours"},
            "legend": {"type": "threshold", "applies_to": "displayed", "transparent_below": TP_LEGEND[0][0],
                       "also_transparent": "stored value <= the interval's source_quantum",
                       "stops": [{"from": v, "color": c} for v, c in TP_LEGEND]},
            "series": series_info,
            "intervals": entries,
        }],
    }
    # Ensemble probabilities are an addition: if they cannot be built, the deterministic
    # forecast is still published and the manifest says why they are missing.
    if ensemble_mode == "off" or steps[-1] % ensemble.WINDOW_HOURS:
        manifest["ensemble"] = {"status": "not built"}
    else:
        t0 = time.time()
        try:
            layers, summary = ensemble.build(out, session, run, steps[-1], grid, cache=cache)
        except Exception as e:  # noqa: BLE001 - anything from a missing file to a failed self-check
            if ensemble_mode == "required":
                raise
            print(f"::warning::ensemble layers not built: {e!r}", flush=True)
            manifest["ensemble"] = {"status": "unavailable", "reason": repr(e)}
        else:
            manifest["layers"] += layers
            manifest["default_layer"] = min(layers, key=lambda layer: layer["threshold_mm"])["id"]
            manifest["ensemble"] = summary
            print(f"ensemble layers built in {time.time() - t0:.0f}s: "
                  f"{summary['raster_bytes'] / 1e6:.1f} MB rasters, {summary['series_bytes'] / 1e6:.1f} MB series tiles")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--date", help="YYYYMMDD (default: newest complete run)")
    p.add_argument("--hour", choices=["00", "12"])
    p.add_argument("--max-step", type=int, help="only process steps up to this hour (for quick tests)")
    p.add_argument("--ensemble", choices=["optional", "required", "off"], default="optional",
                   help="optional: publish without probabilities if the ensemble cannot be built")
    p.add_argument("--cache", type=Path, help="keep downloaded ensemble messages here (local development)")
    a = p.parse_args(argv)

    if bool(a.date) != bool(a.hour):
        p.error("--date and --hour go together")
    if a.date:
        run = catalogue.Run(a.date, a.hour)
    else:
        run = catalogue.latest_complete_run(catalogue.new_session(), datetime.now(timezone.utc),
                                            with_ensemble=a.ensemble != "off")
    steps = catalogue.expected_steps(run.hour)
    if a.max_step is not None:
        steps = [s for s in steps if s <= a.max_step]
    print(f"run {run.date} {run.hour}z, {len(steps)} steps up to {steps[-1]} h -> {a.out}")

    manifest = build(a.out, run, steps, ensemble_mode=a.ensemble, cache=a.cache)
    layer = manifest["layers"][0]
    size = sum(f.stat().st_size for f in (a.out / "tp_interval").glob("*.png"))
    s = layer["series"]
    print(f"wrote {s['tiles_y'] * s['tiles_x']} series tiles, {s['total_bytes'] / 1e6:.1f} MB, "
          f"largest {s['largest_bytes'] / 1e3:.0f} KB")
    worst = min(i["most_negative"] for i in layer["intervals"])
    print(f"wrote {len(layer['intervals'])} intervals, {size / 1e6:.1f} MB of PNG; "
          f"largest interval max {max(i['max'] for i in layer['intervals'])} mm; "
          f"most negative raw difference {worst} mm; "
          f"clipped points {sum(i['clipped_count'] for i in layer['intervals'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
