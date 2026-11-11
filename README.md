# Precipitation forecast from ECMWF Open Data

**Live: https://falehaqazi.github.io/quest-precip-forecast/**

A web map of forecast precipitation for the next 15 days, built from the public
forecast files of the European Centre for Medium-Range Weather Forecasts
(ECMWF). It shows two things, both on the model's own 0.25° grid:

- **Chance of a wet day**: the share of ECMWF's 50 ensemble forecasts in which at
  least 5, 10, 25 or 50 mm falls in a 24-hour window.
- **Forecast rate**: the mean precipitation rate (mm/h) in each 3- or 6-hour
  interval of the single high-resolution forecast.

Tap any grid cell for its full 15-day series, with times in UTC and IST. Every
number carries its unit, its time window and the model run it came from.

This is raw model output shown as it is. It is not a warning service and has
not been checked against observations.

Companion documents:

- [SPEC.md](SPEC.md): what was to be built, what the data actually looks like, what "done" means
- [DECISIONS.md](DECISIONS.md): each non-obvious choice, the alternative, and why (D1–D25)
- [LIMITATIONS.md](LIMITATIONS.md): what is wrong, approximate or untested

## Architecture

There is no application server. A scheduled job turns ECMWF files into static
files; the browser does the rest.

```
 data.ecmwf.int                    GitHub Actions (hourly)                GitHub Pages
┌──────────────────┐   byte      ┌──────────────────────────┐  deploy  ┌───────────────────┐
│ oper: 1 forecast │   ranges    │ pipeline/  (Python)      │ artifact │ web/  static site │
│ enfo: 50 members │ ──────────> │  fetch only `tp` fields  │ ───────> │  index.html, JS   │
│ ~95 MB – 4 GB    │  ~430 MB    │  decode with ecCodes     │  ~86 MB  │  data/manifest    │
│ per step file    │  per run    │  units, differences,     │          │  data/*.png       │
└──────────────────┘             │  member counts, PNGs     │          └─────────┬─────────┘
                                 └──────────────────────────┘                    │ fetch
                                                                           ┌─────┴─────┐
                                                                           │  browser  │
                                                                           └───────────┘
```

**Pipeline** (`pipeline/`, Python 3.12, ecCodes, numpy, Pillow):

| Module | Job |
|---|---|
| `catalogue.py` | ECMWF URL layout, index files, byte-range downloads, choosing the newest complete run |
| `gribio.py` | Decode one GRIB message and refuse it if units, accumulation window or grid are not as expected |
| `grid.py` | The only place that maps latitude/longitude to grid row/column |
| `process.py` | Unit conversion, de-accumulation, time arithmetic |
| `probability.py` | Counting ensemble members that reach a threshold |
| `ensemble.py` | Fetching the 50 members, 24 h windows, self-check against ECMWF's own probabilities |
| `encode.py`, `series.py` | Lossless PNG encoding; per-place tiles for the time series |
| `run.py` | Builds everything for one model run and writes `manifest.json` last |
| `check.py` | Decides whether a scheduled run has anything to build |

**Data format**: each map is a PNG whose red and green channels hold a 16-bit
integer (`value = scale × code`), so the browser has the real numbers and the
legend, hover value and chart all come from the same data. `manifest.json`
lists the layers with their units, encodings, legends and time windows. For the
time series, the same codes are stored a second time in 32 × 32-cell tiles so a
tap costs one small download.

**Frontend** (`web/`, plain JavaScript modules, no build step): Leaflet in
plate carrée projection, so one image pixel is one model grid cell with no
resampling. Coastlines are vendored Natural Earth data; there is no tile server
or other third-party service at run time.

## Data source and licence

- **Source**: [ECMWF Open Data](https://www.ecmwf.int/en/forecasts/datasets/open-data),
  IFS model, 0.25°, 00 and 12 UTC runs, read from `https://data.ecmwf.int/forecasts/`.
- **Fields used**: total precipitation `tp` (paramId 228; metres, accumulated
  since the start of the forecast) from the deterministic forecast (`oper`) and
  from each of the 50 perturbed ensemble members (`enfo`). ECMWF's own
  probability product is read only to check ours.
- **Licence**: ECMWF publishes this data under
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) with additional
  terms of use. © European Centre for Medium-Range Weather Forecasts. This app
  is based on data and products of ECMWF. **The data has been modified**:
  accumulations were differenced into intervals and 24 h windows, converted from
  m to mm, rounded to 0.05 mm, and ensemble members were counted into
  probabilities. ECMWF does not endorse this app.
- **Other material**: country outlines from Natural Earth (public domain);
  Leaflet (BSD-2-Clause) and topojson-client (ISC), vendored in `web/vendor/`.
- The test fixtures in `tests/fixtures/` are unmodified ECMWF messages under the
  same licence.

SPEC.md §5 records what was read from the real files before anything was
designed: file layout, steps, units, grid, packing, ensemble contents.

## How it was verified

Nothing about the data was taken from memory; each fact was read from the
server or a decoded file. The checks that matter:

1. **Cross-check against Open-Meteo.** Open-Meteo processes the same ECMWF files
   independently. For three points and the first two intervals of the
   2026-11-10 00z run, this pipeline's values match it to its 0.1 mm rounding
   (near Wellington: 4.24 and 7.78 mm here, 4.2 and 7.8 mm there). That confirms
   units, de-accumulation, grid indexing and timing together. It is an
   independent calculation on the same data, not independent data. The recorded
   values are a test (`tests/test_real_data.py`, `tests/fixtures/README.md`).
2. **Tests on real ECMWF messages.** Three real `tp` messages and a real index
   file are in the repository, so the tests decode actual bytes rather than
   synthetic arrays.
3. **Automated tests**: 90 in Python (`pytest`) and 21 in JavaScript
   (`node --test`), run on every build before anything is published.

   | Area | What is tested |
   |---|---|
   | Units | m → mm; kg m⁻² s⁻¹ → mm/h; rate and accumulation agree for constant rain |
   | Accumulation vs rate | De-accumulation, mixed 3 h / 6 h steps, negative differences clamped and counted, intervals sum back to the total |
   | Time | UTC throughout, day/month/year rollover, daylight-saving independence, naive datetimes refused, IST conversion |
   | Grid indexing | Known points, the 180° first column, antimeridian wrap, poles, round trips; the same points in Python and in the browser code |
   | Probability | No member, every member, the "at least" boundary, exactness of packed values, member order, bad input |
   | Encoding | PNG round trip, rounding error bound, clipping reported |
   | Series tiles | Tile values equal map values on real data |
   | Refresh | When a scheduled run must build and when it may skip |

4. **Ensemble self-check, every run.** Each probability field is compared with
   ECMWF's own field for the same window and threshold; the result is written
   into `manifest.json` and the layers are withheld if the mean difference
   exceeds 3 percentage points. On the runs processed so far it was 0.03–0.61
   points. Single cells differ by more, for reasons given in LIMITATIONS.md.
5. **Recount by hand.** For three cells, four thresholds and two windows, the
   member counts shown in the browser were recomputed directly from the raw
   member files without the pipeline's code. All 24 matched.
6. **Chart against map.** The page compares the chart's value with the map's
   value for the selected cell on every time step and prints a warning if they
   differ. They never have.

Things the checks found and changed: a "1 mm" probability layer was built and
dropped because the source data's packing cannot resolve it (D20); faint
speckle on the first map turned out to be packing noise (D15); the colour scale
meant different things before and after the forecast's 3 h → 6 h change (D14).

## How the refresh works

- A GitHub Actions workflow (`.github/workflows/deploy.yml`) is scheduled every
  hour. Its first step asks whether ECMWF has a newer complete run than the one
  on the site, whether the site was built from older code, or whether its
  probabilities are missing. If none of those is true the run stops there.
  Otherwise it runs the tests, builds the data and deploys.
- A push to `main` always builds and deploys.
- A run counts as complete only when the deterministic forecast, the ensemble
  members and ECMWF's probability product are all present. If the ensemble
  still fails, the deterministic forecast is published and the page says the
  probabilities are missing.
- If a build or deploy fails, the previous site stays up. The page always
  shows the model run time and its age, and a banner once it is over 24 h old.
- **The refresh never commits to the repository.** The workflow's token has
  `contents: read` only; there is no commit, push or tag step; the site is
  published as a Pages deployment artifact, not to a branch. Every commit on
  `main` is a human commit. What changes without a commit is the Actions run
  list and the data on the live site.
- **GitHub's scheduler is not punctual.** In this repository scheduled runs
  have started hours late or not at all (LIMITATIONS.md has the record). To
  refresh by hand: on GitHub open **Actions → Build forecast and deploy → Run
  workflow → Run workflow**. A manual run always builds.

## Limits

The short version; LIMITATIONS.md is longer and blunter.

- Raw model output: no bias correction, no downscaling, no check against rain
  gauges or radar. A value is an average over a grid cell of roughly 28 km.
- The probabilities are counts of 50 model runs, not calibrated probabilities.
  0 % means "no member", 100 % means "every member".
- No layer for light rain: the lowest threshold is 5 mm in 24 h, and the rate
  map does not colour anything below 0.1 mm/h.
- The rate map is one forecast. It shows day 15 as firmly as hour 3.
- Times are UTC and IST for every viewer.
- Freshness depends on GitHub starting the scheduled workflow.
- Tested in one browser engine (Chromium) at phone and desktop sizes; not in
  Firefox or Safari, and not with real touch input.

## Run it locally

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r requirements.txt
```

```bash
.venv/Scripts/python -m pytest -q
```

```bash
node --test tests/js/grid.test.mjs tests/js/series.test.mjs tests/js/time_chart.test.mjs
```

```bash
.venv/Scripts/python -m pipeline.run --out web/data
```

```bash
.venv/Scripts/python -m http.server 8765 --directory web
```

On Linux or macOS use `.venv/bin/python`. The full build downloads about
430 MB and takes 4–6 minutes locally (under 3 minutes on GitHub's runner); add
`--ensemble off` for the deterministic forecast alone (about 50 MB, under a
minute). Then open http://localhost:8765.

## Repository map

```
pipeline/      Python: fetch, decode, process, encode
tests/         pytest tests and real ECMWF fixtures; tests/js for the browser modules
web/           the static site (index.html, app.js, grid.js, chart.js, time.js, style.css, vendor/)
.github/       the build-and-deploy workflow
SPEC.md  DECISIONS.md  LIMITATIONS.md
```
