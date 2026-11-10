# SPEC — Precipitation forecast web app from ECMWF Open Data

Status: **v0.2, 2026-11-10** — scope questions answered by Faleha (see §8).
Items under "Verified data facts" were read from the live ECMWF servers on
2026-11-10 ~11:20 UTC, not from memory.

## 1. Purpose

A public web page that shows where and how much precipitation ECMWF's IFS model
forecasts over the coming days, on a map, with the forecast for any clicked
point as a time series. Built and deployed inside one 72-hour session.

## 2. Users

Global map, reviewer-first. Two kinds of reader, in priority order:

1. A technically literate reviewer (QUEST Lab) who wants to see that the numbers
   are right and traceable: which model run, which field, what units, what was
   done to it.
2. A general user who wants "how much rain, where, when" without knowing what
   GRIB is.

Consequence: every displayed number carries its unit and its accumulation
window, and the page states the model run it came from.

## 3. Features

### Must have (v1 = "done")

- F1. World map with a precipitation overlay for one forecast interval at a time.
- F2. Time control (slider + play) across all forecast intervals of the run.
- F3. Values are **accumulated precipitation in mm per interval** (3 h or 6 h,
  whatever the source step is; the window length is always shown).
- F4. Click/tap a point → time series of precipitation for that grid cell, plus
  the cell's actual lat/lon (the grid cell centre, not the click position).
- F5. Visible run metadata: model, run date/time (UTC), valid time of the shown
  interval in UTC and in the browser's local time zone.
- F6. Data refreshes automatically when a new run is published; the page never
  silently shows a stale run (age of run is displayed).
- F7. Colour legend with units. ECMWF attribution and CC BY 4.0 notice
  (required by the terms of use, see §5.6).

### Next after v1 is live and tested (committed, not a stretch goal)

- E1. Ensemble **probability of exceedance** (P[precip > X mm] per interval)
  from the `enfo` stream, as a second map layer and a second series in the
  point chart. v1 must be built so this plugs in without a rewrite:
  - the manifest describes a list of **layers** (`id`, `kind`, `units`,
    value encoding, legend, per-interval files); v1 ships exactly one layer;
  - the frontend renders "a layer" generically (legend, units and colour scale
    come from the manifest, not from code that assumes mm);
  - the pipeline's fetch/decode/grid code takes stream and parameter as
    arguments rather than hard-coding `oper`/`tp`.
  The `enfo` files have not been inspected yet (§5.7); E1 starts with that.

### Should have (if time allows, in this order)

- S1. Accumulation presets: 24 h totals, whole-run total.
- S2. Location search (place name → point).
- S3. Instantaneous rate layer (`tprate`, mm/h) as an alternative to accumulation.
- S4. A small server-side API for point queries (see §7).

### Out of scope

- Any forecast skill claim, verification against observations, bias correction,
  downscaling or nowcasting. The app displays model output, nothing more.
- Other variables (temperature, wind, …), snow/rain type split (`sf`, `ptype`).
- The 0.1° product (exists, see §5.5; unverified grid, ~4–5× the bytes).
- AIFS models (`aifs-single`, `aifs-ens` directories exist; not inspected).
- User accounts, alerts/notifications, saved locations, native mobile app.
- Historical archive: the ECMWF portal itself only keeps ~4 days; we keep only
  the latest run.
- Time zone *of the clicked location*. Times are UTC and browser-local only.

## 4. What "done" means

1. A public URL loads the map on desktop and phone without login.
2. It shows a run no older than the newest 00z/12z run + its publication delay
   (or says clearly that it is stale and why).
3. For a known grid point and step, the value on the page equals the value
   decoded independently from the source GRIB (to within packing precision).
4. Automated tests pass for: unit conversion (m → mm, kg m⁻² s⁻¹ → mm/h),
   de-accumulation, valid-time / time-zone arithmetic, lat/lon ↔ grid index
   (including the 180° start and the wrap), and at least one check against a
   value obtained from an independent source.
5. `DECISIONS.md` and `LIMITATIONS.md` are current. Commit history is small,
   readable steps.
6. The refresh runs unattended at least twice in a row.

## 5. Data source — verified facts

Source: ECMWF Open Data, `https://data.ecmwf.int/forecasts/`.

### 5.1 Catalogue layout (verified by listing directories)

```
/forecasts/YYYYMMDD/HHz/{ifs,aifs-single,aifs-ens}/
/forecasts/YYYYMMDD/HHz/ifs/{0p25,0p1}/{oper,enfo,wave,waef}/
/forecasts/YYYYMMDD/HHz/ifs/0p25/oper/YYYYMMDDHH0000-{step}h-oper-fc.grib2
/forecasts/YYYYMMDD/HHz/ifs/0p25/oper/YYYYMMDDHH0000-{step}h-oper-fc.index
```

- Dates present today: 20261107 … 20261110 (rolling, ~4 days).
- Runs: 00z, 06z, 12z, 18z. All four are under stream `oper` (there was no
  `scda` directory for 06z/18z).
- Each step is one ~93–97 MB GRIB2 file with **all** variables, plus a JSON-lines
  `.index` giving `_offset`/`_length` per field. HTTP range requests work
  (got `206` with exactly the indexed byte count), so one field can be fetched
  without the other ~95 MB.

### 5.2 Steps (verified from file names)

| Run | Steps | Count |
|---|---|---|
| 00z, 12z | 0–144 h every 3 h, then 150–360 h every 6 h | 85 |
| 06z, 18z | 0–144 h every 3 h | 49 |

Listing timestamps of the files: 00z → 07:34, 06z → 12:27, 12z → 19:34,
18z → 00:27 (+1 day). The portal does not label the time zone of that column;
I am **assuming UTC**. So data appears roughly 6.5–7.5 h after run time.

### 5.3 Precipitation fields in the `oper` surface set (verified from index + GRIB headers)

| shortName | GRIB2 (discipline.category.number) | Product template | Meaning read from header |
|---|---|---|---|
| `tp` | 0.1.193 (ECMWF local table v1) | 4.8, statistical process 1 = accumulation | Accumulated from forecast time 0 to the step. At step 6 the stat range is 6 h ending 06:00; at step 150 it is 150 h. **Accumulated since run start, not per interval.** |
| `tprate` | 0.1.52 | 4.0, instantaneous | Value at the step's valid time. |

Also present and precipitation-related, not used in v1: `cp`, `sf`, `ptype`, `ro`.
`lsm` (land-sea mask) is present. `lsp` is **not** in the 0.25° oper index.

`tp` at step 0 is a 224-byte constant field (0 bits per value, no data section
payload) — i.e. all zeros, as expected for an accumulation of length 0.

### 5.4 Units — partly verified

GRIB2 does not store the unit string; it comes from parameter tables.

- `tp`: ECMWF's parameter table says **metres** (of water). Not read from the
  file. Consistency check from the header: 12 bits, reference 0, binary scale
  2⁻¹⁴ at step 6 → max representable 0.25; 2⁻¹² at step 150 → max 1.0. That is
  sensible for metres (250 mm in 6 h, 1000 mm in 150 h) and absurd for mm.
  **To be confirmed by a test against an independently known value.**
- `tprate`: WMO table 4.2 says kg m⁻² s⁻¹ (= mm/s). Scale 2⁻¹⁸ × 4095 ≈ 0.0156
  → 56 mm/h max, plausible. Same caveat.
- Packing precision of `tp` is 2^E metres: ≈0.06 mm at step 6, ≈0.24 mm at step
  150 (coarser later, not yet checked at 360 h). Per-interval amounts are a
  difference of two such fields, so late-lead intervals carry sub-mm
  quantisation noise and can come out slightly negative. This is a property of
  the source data.

### 5.5 Grid (verified from GRIB section 3 of the 0.25° file)

- Regular lat/lon (template 3.0), **1440 × 721** = 1,038,240 points, 0.25°.
- Latitude: first row **+90°**, last row **−90°** (north → south).
- Longitude: first column **180°**, last column **179.75°**, increasing eastward
  — i.e. the row runs 180, 180.25, …, 359.75, 0, …, 179.75 (same as −180 … +179.75).
  Column 0 is the antimeridian, **not** Greenwich.
- Scanning mode 0: row-major, west→east within a row, rows north→south.
- No bitmap (no missing values).
- Data packing: **CCSDS / AEC (template 5.42)**, 12 bits per value. This needs
  libaec to decode; a plain "simple packing" reader is not enough.
- 0.1° product: exists at `ifs/0p1/oper/…-oper-fc-sfc.grib2` (~87 MB surface
  file, `tp` message ≈1.4 MB at step 6). Its grid definition was **not** inspected.

### 5.6 Licence (read from the terms-of-use page linked by the portal)

CC BY 4.0 plus ECMWF terms: attribution must be displayed prominently, with a
link to the licence and a note that the data was modified. The portal states a
limit of 2000 simultaneous connections overall; no per-client rate limit found.

### 5.7 Not yet verified

- Actual decoded values (nothing has been decoded yet — only headers read).
- Whether file publication is atomic (can a run directory be listed while
  incomplete? Today's 00z shows all 85 steps with the same timestamp).
- `enfo` contents beyond file names (`-enfo-ef`, 2× `-enfo-ep`, 1× `-enfo-tf.bufr`).

## 6. Processing (what the pipeline must do)

1. Find the newest **complete** run. 00z/12z only, so the horizon is always
   360 h (06z/18z stop at 144 h and are ignored).
2. For each step, read the `.index`, range-request only the `tp` message
   (≈0.3–0.55 MB each; whole run on the order of 40 MB, estimated not measured).
3. Decode, convert m → mm.
4. De-accumulate: interval amount = `tp(step_k) − tp(step_{k−1})`. Window is 3 h
   up to 144 h and 6 h after; store the window length with each interval.
   Clamp negative differences to 0 and record how large they were.
5. Re-order longitudes to −180…180 only if the map needs it; keep one tested
   function as the single source of truth for (lat, lon) ↔ (row, col).
6. Write compact per-interval rasters + a manifest (run time, steps, valid
   times in UTC, units, scale) for the frontend.

## 7. Architecture

Static first, API later.

- **Pipeline**: Python + `eccodes` (ships libaec) + numpy, run on a schedule in
  GitHub Actions. Tests with pytest.
- **Serving**: static files (frontend + processed data) on GitHub Pages. No
  application server, so nothing to keep alive or cold-start.
- **Frontend**: plain JS with a web map library, canvas raster overlay, small
  chart for the point series. No build step unless one becomes necessary.
- **Later (S4)**: a small API service for point queries, only after v1 and E1.
  The static data format stays the source of truth; the API would read it.

Local machine facts that constrain this: Node 26 and git are installed;
Python is installed for this project via winget (approved); Docker, `gh` and
all deploy CLIs are absent; the repo has no remote yet.

## 8. Decisions taken with Faleha (2026-11-10)

| Question | Answer |
|---|---|
| Audience / default view | Global map, reviewer-first |
| Architecture | Static site + scheduled pipeline first; API later |
| Local Python | Install Python 3.12 via winget |
| Forecast scope | Deterministic IFS 0.25°, 00z/12z for v1. Ensemble probability of exceedance is the first addition after the slice is live and tested; format and UI designed for it now (E1) |

Still open: a GitHub repository (and Pages enabled on it) must be created by
Faleha; account creation and sign-in are not something the assistant does.
