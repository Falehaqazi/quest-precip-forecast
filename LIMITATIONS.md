# LIMITATIONS

What is wrong, approximate or untested. Kept blunt on purpose.
Last updated 2026-11-10, after the first deployment
(https://falehaqazi.github.io/quest-precip-forecast/).

## Not done yet
- **The scheduled refresh has never fired.** The one successful build so far was
  triggered by a push (2026-11-10 12:06 UTC). SPEC's "runs unattended twice in a
  row" is unmet until the 20:05 UTC and next 08:05 UTC crons have been seen to
  work. GitHub delays or skips scheduled runs under load, and disables schedules
  in repos with no activity for 60 days.
- **The first deploy attempt failed**: the `github-pages` environment only allows
  the `main` branch and the code was on `master`. The local branch was renamed to
  `main` and pushed. A stale `master` branch is still on GitHub and is probably
  still the repo's default branch; pushes to it build but cannot deploy.
- The workflow's action versions (`checkout@v4`, `setup-python@v5`,
  `setup-node@v4`, `upload-pages-artifact@v3`) emit a "Node.js 20 is deprecated"
  warning. They work today; they will need bumping.
- **No point time series (SPEC F4).** Clicking a cell shows the value for the
  interval on screen only.
- No ensemble / uncertainty layer (SPEC E1). No location search, no 24 h totals.

## The data
- **This is raw model output.** No bias correction, no downscaling, no
  verification against gauges or radar. A 0.25° cell is roughly 28 km × 28 km at
  the equator; a value is a cell average, not the rain at a point.
- **One deterministic forecast.** No uncertainty is shown. Beyond a few days a
  single run's precipitation placement is not reliable; the map does not tell
  you that, and it shows day 15 with the same confidence as hour 3.
- **Large values are shown as they come.** The 2026-11-10 00z run contains up
  to 297 mm in one 6 h interval for one cell (15.25° N, 82.75° E, +222–228 h).
  The neighbouring cells are consistent with it, so it is model output and not
  a decoding artefact, but I have no way to say whether it is realistic.
- **Quantisation.** Source `tp` is packed in 12 bits with precision 2^E m:
  about 0.06 mm at step 6 and 0.24 mm at step 150 (measured from headers).
  Interval amounts are differences of two such fields. In the 2026-11-10 00z
  run the most negative raw difference was −0.244 mm (interval ending +288 h).
  Negatives are clamped to 0; count and size are recorded per interval in the
  manifest. The site then rounds to 0.05 mm on top of that.
- **Interval length changes at 144 h** from 3 h to 6 h. Amounts are per interval
  and the colour scale is in mm per interval, so the map looks wetter after
  144 h for the same rain rate. The legend title states the interval length.
- **Only 00z/12z runs.** The page can lag the newest model run by 12 h plus
  ECMWF's ~7 h publication delay. The "stale" banner only appears after 24 h.

## Things assumed, not verified
- The time column in the ECMWF directory listing is UTC (it is not labelled).
  The cron times in the workflow rest on this and on two days of listings.
- A run is "complete" if its last step's `.index` exists. If ECMWF publishes
  non-atomically the pipeline may hit a missing step; it then fails without
  publishing, leaving the previous run on the site.
- The check against Open-Meteo is against a service that itself derives from
  the same ECMWF files and rounds to 0.1 mm. It independently confirms units,
  de-accumulation, grid indexing and timing, but it is not independent *data*.
  Only three points and the first 6 h were compared.
- ecCodes is trusted as the reference decoder.

## The pipeline
- The pipeline has run successfully once on Linux (GitHub runner) and a few
  times on Windows, all on the same model run (2026-11-10 00z). It has never
  processed a 12z run or handled a missing/late run for real.
- **ecCodes crashed the Python process when called from worker threads**
  (Windows, eccodes 2.50.0; exit without traceback). I did not investigate the
  cause; decoding now happens on the main thread only and downloads stay
  threaded. If someone "optimises" this back, it will break.
- No retry logic beyond three attempts per file; no alerting when a scheduled
  build fails (GitHub's default e-mail only).
- Only the latest run is kept. There is no archive and no way to compare runs.

## The app
- **Tested in one browser only** (the Chromium-based preview pane), desktop and
  an emulated 375 px phone viewport. The value decoding depends on the browser
  not altering PNG bytes (`createImageBitmap` with no colour conversion); in
  Chromium the decoded values matched the pipeline exactly at the points
  checked, locally and on the live site. Firefox and Safari are untested.
- No automated browser tests. Only the grid/decoding helpers have unit tests.
- Times are shown in UTC and the browser's zone, not the clicked location's zone.
- The map does not wrap across the antimeridian; a storm on the date line is
  split between the two edges.
- Plate carrée stretches high latitudes east–west. Cells near the poles look as
  large as tropical ones but cover far less area.
- Light theme only. On a phone the cell readout covers part of the legend.
- Country outlines are Natural Earth 1:50m de facto boundaries, for orientation
  only; small islands are missing, so some "ocean" cells are really land.
- ~29 MB of rasters per run; each interval is a ~350 KB download the first time
  it is shown. Fine on broadband, slow on a poor mobile connection.
