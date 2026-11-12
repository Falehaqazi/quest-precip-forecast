# Precipitation forecast from ECMWF Open Data

**Live: https://falehaqazi.github.io/quest-precip-forecast/**

A web map of forecast precipitation for the next 15 days, built from the public
forecast files of the European Centre for Medium-Range Weather Forecasts
(ECMWF). It shows two things, both on the model's own 0.25° grid:

- **Share of ensemble members reaching 5, 10, 25 or 50 mm in 24 h**: how many of
  ECMWF's 50 ensemble forecasts reach that amount in a 24-hour window. It is a
  count of model runs, not a calibrated chance of rain.
- **Forecast rate**: the mean precipitation rate (mm/h) in each 3- or 6-hour
  interval of the single high-resolution forecast.

Tap any grid cell for its full 15-day series, with times in UTC and IST. Every
number carries its unit, its time window and the model run it came from.

This is raw model output shown as it is. It is not a warning service and has
not been checked against observations.

Companion documents:

- [SPEC.md](SPEC.md): what was to be built, what the data actually looks like, what "done" means
- [DECISIONS.md](DECISIONS.md): each non-obvious choice, the alternative, and why (D1–D30)
- [LIMITATIONS.md](LIMITATIONS.md): what is wrong, approximate or untested

## Architecture

There is no application server. A build job turns ECMWF files into static
files; the browser does the rest.

```
 data.ecmwf.int                 GitHub Actions (run by hand)              GitHub Pages
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
  from each of the 50 perturbed ensemble members (`enfo`). The deterministic
  forecast is also the ensemble's control member. ECMWF's own
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

1. **Cross-check against Open-Meteo, and what it is worth.** Open-Meteo is a
   separate service that processes the same ECMWF files with its own code. At
   three grid points, for the first six hours of the 2026-11-10 00z run, this
   pipeline's interval amounts equal Open-Meteo's to its 0.1 mm rounding. Only
   one of the three points had rain (near Wellington: 4.24 and 7.78 mm here,
   4.2 and 7.8 mm there); the other two were dry in both.
   - *What that confirms*: at those points and times, the unit conversion
     (m to mm), the de-accumulation, the grid indexing and the timing are right.
     A wrong unit, a shifted grid or an off-by-one step would each have shown.
   - *What it does not confirm*: that the forecast is right. Open-Meteo starts
     from the same ECMWF data, so this is an independent calculation, not
     independent data, and no observation is involved. It says nothing about
     other places, later lead times (including the 6-hourly part of the
     forecast), other runs, or the ensemble shares.
   The values were recorded once and are kept as a test
   (`tests/test_real_data.py`, `tests/fixtures/README.md`); the test does not
   contact Open-Meteo again.
2. **Tests on real ECMWF messages.** Three real `tp` messages and a real index
   file are in the repository, so the tests decode actual bytes rather than
   synthetic arrays.
3. **Automated tests**: 84 in Python (`pytest`) and 25 in JavaScript
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
   | Freshness | Which time step the page opens on; when it says it is behind |

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

7. **Accumulated totals that go down.** `tp` is accumulated since the start of
   the forecast and should never decrease, but in the raw data it does at
   0.30 % of cell-intervals (run 2026-11-12 00z, in 5 of 84 intervals, by at
   most 0.244 mm). Most of it is rounding where ECMWF's packing step doubles.
   The rest, about 5,000 cells in two intervals, is also present in ECMWF's
   separate 0.1° product at the same steps, so it comes from ECMWF's fields;
   why, I could not find out. The pipeline sets each negative difference to
   zero and records how many there were; its counts match an independent
   analysis exactly. Details in DECISIONS D32.

8. **The largest values.** The biggest amounts on the map (361, 240, 232 and
   217 mm in 6 h in the 2026-11-12 00z run, all 7 to 12 days ahead) are exactly
   what ECMWF's forecast contains, because Open-Meteo and ECMWF's separate
   0.1° product give the same numbers at the same place and time, but nothing
   says they will happen: at those places at most 5 of the 50 ensemble
   members reach even 100 mm on the day concerned, at one of them none
   reaches 50 mm, and no observation exists yet to check against.
   DECISIONS D34.

Things the checks found and changed: a "1 mm" probability layer was built and
dropped because the source data's packing cannot resolve it (D20); faint
speckle on the first map turned out to be packing noise (D15); the colour scale
meant different things before and after the forecast's 3 h → 6 h change (D14).

## How the refresh works

**The site is updated by hand.** There is no automatic refresh of any kind.

- **To refresh it**: signed in to GitHub as the repository owner, open
  [Actions → Build forecast and deploy](https://github.com/Falehaqazi/quest-precip-forecast/actions/workflows/deploy.yml),
  press **Run workflow**, then **Run workflow** again. About three minutes later
  the site shows ECMWF's newest complete run. A push to `main` does the same.
  Those are the only two things that start a build.
- **What a build does**: runs the tests, picks the newest run for which the
  deterministic forecast, the ensemble members and ECMWF's probability product
  are all present, builds the data and deploys it. If the ensemble fails, the
  deterministic forecast is published and the page says the probabilities are
  missing. If the build or deploy fails, the previous site stays up.
- **What the page shows**: always the model run time, its age, and when the page
  was last built. Once the run shown is 21 hours old, by which time ECMWF has
  normally published the next one, a banner says the page is behind. The footer
  says the page is updated by hand.
- **Why there is no schedule**: one was tried in three forms (four times a day,
  hourly, every 15 minutes). GitHub started a scheduled run once in roughly 35
  scheduled times over a day and a half, so it was removed rather than left in
  as a promise the site could not keep. An outside scheduler or an access token
  would have fixed it and was ruled out by choice. DECISIONS D24 and D28–D30
  have the record.
- **Nothing here commits to the repository.** The workflow's token has
  `contents: read` only; there is no commit, push or tag step; the site is
  published as a Pages deployment artifact, not to a branch. Every commit on
  `main` is a human commit. A manual run adds an entry to the Actions run list
  and changes the data on the live site, and nothing else.

## Limits

The short version; LIMITATIONS.md is longer and blunter.

- Raw model output: no bias correction, no downscaling, no check against rain
  gauges or radar. A value is the model's value at a grid point; points are
  roughly 28 km apart, and it is not an average over the area in between.
- The member shares are counts of 50 model runs, not calibrated probabilities.
  0 % means "no member", 100 % means "every member".
- ECMWF's ensemble has 51 members and the shares count 50 of them. The 51st is
  the control forecast, which ECMWF publishes separately as the `oper`
  forecast (since IFS Cycle 50r1, May 2026); it is the forecast the rate map
  shows. Checked against ECMWF's documentation and against its published
  ensemble mean, which matches the 50 members plus `oper`. The pipeline reads
  only the 50 perturbed members; counting the control as well would change a
  share by at most one member. DECISIONS D33.
- No layer for light rain: the lowest threshold is 5 mm in 24 h, and the rate
  map does not colour anything below 0.1 mm/h.
- The rate map is one forecast. It shows day 15 as firmly as hour 3.
- Times are UTC and IST for every viewer.
- The page is updated by hand, so it is only as fresh as its last rebuild. It
  says when that was and warns when a newer forecast has probably come out.
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
