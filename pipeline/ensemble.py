"""Ensemble probability of exceedance from ECMWF open data `enfo` perturbed forecasts.

What is on the server (verified 2026-11-10, run 20261110 00z):
  .../ifs/0p25/enfo/YYYYMMDDHH0000-{step}h-enfo-ef.grib2   ~4 GB per step, all variables
  one `tp` message per member, type "pf", members numbered 1..50, same grid as `oper`.
  No control member ("cf") is in these files, although the headers say the ensemble has 51.

Only `tp` at the ends of each 24 h window is fetched (byte ranges), about 20-25 MB per step.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from . import catalogue, series
from .encode import codes_to_png
from .gribio import decode, expect_accumulated_tp
from .probability import ExceedanceCounter, probability_percent, window_total
from .process import iso_utc, metres_to_mm, valid_time

THRESHOLDS_MM = [5, 10, 25, 50]    # "a few"; 1 mm was tried and dropped: the source cannot resolve it (DECISIONS D19)
WINDOW_HOURS = 24
FETCH_WORKERS = 8
MAX_MEAN_ABS_DIFF = 3.0             # percentage points; self-check against ECMWF's own product

# One hue, light -> dark, and a different hue from the rate layer because it is a different
# quantity. Lower bound of each class in percent; below the first bound is transparent.
# With 50 members the first class starts at one member (2 %).
POE_LEGEND = [
    (2, "#fbd5bf"), (10, "#f6b48f"), (25, "#ee9160"), (50, "#e06c35"), (75, "#bb4c1b"), (90, "#86330e"),
]


def windows(last_step: int, hours: int = WINDOW_HOURS) -> list[tuple[int, int]]:
    """Consecutive windows from the run start: (0, 24), (24, 48), ... up to last_step."""
    if last_step % hours:
        raise ValueError(f"forecast length {last_step} h is not a whole number of {hours} h windows")
    return [(a, a + hours) for a in range(0, last_step, hours)]


def ensemble_run(run: catalogue.Run, kind: str = "ef") -> catalogue.Run:
    return catalogue.Run(run.date, run.hour, stream="enfo", type=kind)


def fetch_member_messages(session, run: catalogue.Run, step: int, cache: Path | None = None) -> dict[int, bytes]:
    """tp of every member at one step. Network only: safe to call from threads."""
    members = catalogue.find_members(catalogue.fetch_index(session, run, step), param="tp", levtype="sfc", type="pf")
    url = run.file_url(step, "grib2")

    def get(item):
        n, (offset, length) = item
        path = cache / f"tp-{run.date}{run.hour}-{step}-m{n:02d}.grib2" if cache else None
        if path and path.exists():
            return n, catalogue.check_message(path.read_bytes(), length)
        data = catalogue.fetch_range(session, url, offset, length)
        if path:
            path.write_bytes(data)
        return n, data

    with ThreadPoolExecutor(FETCH_WORKERS) as pool:
        return dict(pool.map(get, members.items()))


def decode_members(messages: dict[int, bytes], step: int, grid) -> tuple[dict[int, np.ndarray], float]:
    """{member: accumulated tp in metres (float32)} and the coarsest packing step, in metres.

    float32 is exact here: every packed value is an integer below 4096 times a power of two.
    """
    out, quantum = {}, 0.0
    for n, msg in messages.items():
        f = expect_accumulated_tp(decode(msg), step)
        if f.member != n:
            raise ValueError(f"index says member {n}, GRIB header says {f.member}")
        if f.grid != grid:
            raise ValueError("ensemble grid differs from the deterministic grid")
        out[n] = f.values.astype(np.float32)
        quantum = max(quantum, f.quantum)
    return out, quantum


def crosscheck(session, run: catalogue.Run, counts: dict, n_members: int, cache: Path | None = None) -> dict:
    """Compare with ECMWF's own probabilities (`ep`, params tpgN), which cover the same windows.

    They are not expected to match exactly: ECMWF's field is smooth (values are not multiples
    of one member) and its headers do not say how many members went in. A large mean difference
    would mean a wrong window, unit or threshold on our side.
    """
    ep = ensemble_run(run, "ep")
    entries = []
    for step in (240, 360):
        entries += [dict(e, _file_step=step) for e in catalogue.fetch_index(session, ep, step)]
    stats = {t: {"abs": 0.0, "bias": 0.0, "max": 0.0, "n": 0} for t in THRESHOLDS_MM}
    for (a, b), by_threshold in counts.items():
        for t, count in by_threshold.items():
            hits = [e for e in entries if e.get("param") == f"tpg{t}" and e.get("step") == f"{a}-{b}" and e.get("type") == "ep"]
            if len(hits) != 1:
                raise LookupError(f"tpg{t} for {a}-{b} h: found {len(hits)} messages in the ep index")
            e = hits[0]
            path = cache / f"ep-{run.date}{run.hour}-tpg{t}-{a}-{b}.grib2" if cache else None
            if path and path.exists():
                msg = path.read_bytes()
            else:
                msg = catalogue.fetch_range(session, ep.file_url(e["_file_step"], "grib2"), int(e["_offset"]), int(e["_length"]))
                if path:
                    path.write_bytes(msg)
            f = decode(msg)
            if f.units != "%" or (f.start_step, f.end_step) != (a, b):
                raise ValueError(f"unexpected ECMWF probability field: units {f.units!r}, window {f.start_step}-{f.end_step}")
            d = probability_percent(count, n_members) - f.values
            s = stats[t]
            s["abs"] += float(np.abs(d).mean()); s["bias"] += float(d.mean())
            s["max"] = max(s["max"], float(np.abs(d).max())); s["n"] += 1
    return {
        "reference": "ECMWF enfo 'ep' product, parameters tpgN (probability of at least N mm in 24 h)",
        "unit": "percentage points, ours minus ECMWF, averaged over all grid cells and windows",
        "windows_compared": len(counts),
        "by_threshold_mm": {str(t): {"mean_abs_diff": round(s["abs"] / s["n"], 3), "mean_diff": round(s["bias"] / s["n"], 3),
                                     "max_abs_diff": round(s["max"], 1)} for t, s in stats.items()},
    }


def build(out: Path, session, run: catalogue.Run, last_step: int, grid, cache: Path | None = None,
          check: bool = True, log=print) -> tuple[list[dict], dict]:
    """Write probability rasters and series tiles; return (manifest layers, ensemble summary)."""
    ens = ensemble_run(run)
    ref = run.reference_time
    wins = windows(last_step)
    if cache:
        cache.mkdir(parents=True, exist_ok=True)

    prev, quantum = decode_members(fetch_member_messages(session, ens, 0, cache), 0, grid)
    member_ids = sorted(prev)
    counts: dict[tuple[int, int], dict[int, np.ndarray]] = {}
    quanta: dict[tuple[int, int], float] = {}
    downloaded = 0
    for a, b in wins:
        messages = fetch_member_messages(session, ens, b, cache)
        downloaded += sum(map(len, messages.values()))
        cur, q = decode_members(messages, b, grid)
        if sorted(cur) != member_ids:
            raise ValueError(f"step {b} has members {sorted(cur)}, step 0 had {member_ids}")
        counter = ExceedanceCounter(THRESHOLDS_MM, (grid.nj, grid.ni))
        for n in member_ids:
            counter.add(window_total(metres_to_mm(prev[n]), metres_to_mm(cur[n])))
        counts[(a, b)] = {t: counter.counts[i].copy() for i, t in enumerate(THRESHOLDS_MM)}
        quanta[(a, b)] = 1000.0 * max(q, quantum)
        prev, quantum = cur, q
        log(f"  ensemble window +{a}..+{b} h done", flush=True)
    m = len(member_ids)
    log(f"ensemble: {m} members, {len(wins)} windows, {downloaded / 1e6:.0f} MB of tp downloaded")

    summary = {
        "status": "ok", "members": m, "member_numbers": f"{member_ids[0]}-{member_ids[-1]}",
        "member_type": "perturbed forecasts (pf); the control forecast is not in the open-data enfo files",
        "source_directory": ens.directory + "/", "window_hours": WINDOW_HOURS, "thresholds_mm": THRESHOLDS_MM,
        "method": "share of members whose window total is >= threshold; no smoothing, no calibration",
    }
    if check:
        try:
            summary["crosscheck"] = crosscheck(session, run, counts, m, cache)
        except (IOError, OSError, LookupError) as e:   # the ep files appear later than the ef files
            summary["crosscheck"] = {"status": "unavailable", "reason": repr(e)}
            log(f"::warning::ensemble self-check against ECMWF ep not possible: {e!r}")
        else:
            worst = max(v["mean_abs_diff"] for v in summary["crosscheck"]["by_threshold_mm"].values())
            log(f"ensemble self-check: {summary['crosscheck']['by_threshold_mm']}")
            if worst > MAX_MEAN_ABS_DIFF:
                raise ValueError(f"probabilities differ from ECMWF's by {worst} points on average; refusing to publish")

    # rasters: the stored code is the NUMBER OF MEMBERS; percent = code * 100 / members
    scale = 100.0 / m
    frames, layers = [], []
    for ti, t in enumerate(THRESHOLDS_MM):
        layer_dir = out / "poe24" / f"{t}mm"
        layer_dir.mkdir(parents=True, exist_ok=True)
        entries = []
        for a, b in wins:
            count = counts[(a, b)][t]
            name = f"{b:03d}.png"
            (layer_dir / name).write_bytes(codes_to_png(count))
            frames.append(count)
            entries.append({
                "start_step": a, "end_step": b, "hours": b - a,
                "start_utc": iso_utc(valid_time(ref, a)), "end_utc": iso_utc(valid_time(ref, b)),
                "file": f"poe24/{t}mm/{name}",
                "max": round(float(count.max()) * scale, 1),
                "cells_with_any_member": int((count > 0).sum()),
                "source_quantum_mm": round(quanta[(a, b)], 5),
            })
        layers.append({
            "id": f"poe24_{t}", "kind": "probability", "group": "ensemble",
            # "Share of members", not "chance": it is a count of model runs, not a calibrated
            # probability (DECISIONS D31).
            "title": f"Share of ensemble members reaching {t} mm in 24 h",
            # for the layer picker, where the full title does not fit a phone-width control
            "short_title": f"Share of members reaching {t} mm in 24 h",
            "description": f"Share of the {m} ensemble members in which total precipitation over the 24 h "
                           f"window is at least {t} mm. Derived from ECMWF parameter tp (paramId 228) of each "
                           "perturbed member. Raw ensemble frequency: not calibrated.",
            "units": "%", "threshold_mm": t, "window_hours": WINDOW_HOURS, "members": m, "axis_max": 100,
            "encoding": {"format": "png-rg16", "scale": scale, "offset": 0.0,
                         "formula": "value = offset + scale * (R * 256 + G); the code is the number of members"},
            "legend": {"type": "threshold", "transparent_below": POE_LEGEND[0][0],
                       "stops": [{"from": v, "color": c} for v, c in POE_LEGEND]},
            "series_frame_offset": ti * len(wins),
            "intervals": entries,
        })

    # one tile set for all thresholds: frame = threshold index * windows + window index
    info = series.write_tiles(out / "poe24" / "series", np.stack(frames))
    info["path"] = "poe24/series/{ty}_{tx}.png"
    for layer in layers:
        layer["series"] = dict(info, frames=info["intervals"], intervals=len(wins),
                               frame_offset=layer.pop("series_frame_offset"))
    summary["raster_bytes"] = sum(p.stat().st_size for p in (out / "poe24").glob("*mm/*.png"))
    summary["series_bytes"] = info["total_bytes"]
    return layers, summary
