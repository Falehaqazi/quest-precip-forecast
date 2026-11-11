# LIMITATIONS

What is wrong, approximate or untested. Kept blunt on purpose.
Last updated 2026-11-11, after the ensemble layers went live
(https://falehaqazi.github.io/quest-precip-forecast/).

## Operations: what has and has not been seen to work
- **Scheduled refresh depends on GitHub starting the workflow, which it does
  late or not at all.** With the first schedule (08:05, 10:05, 20:05, 22:05
  UTC) one of two evening attempts on 2026-11-10 ran, at 00:35 UTC, and the
  08:05 attempt on 2026-11-11 had not started by 09:33. The schedule is now
  hourly with a check that skips the build when nothing is new (DECISIONS D24).
  That gives 24 chances a day instead of 4; it does not guarantee any of them.
  **Record so far: one scheduled run has ever started** (2026-11-11 00:35 UTC,
  under the old schedule). After the hourly schedule was pushed at 09:55 UTC
  on 2026-11-11, none of the 10:17, 11:17, 12:17, 13:17 or 14:17 runs had
  started by 14:23 UTC. The workflow is listed as active. I do not know why;
  the hourly schedule and its skip check have therefore **never been seen
  running on GitHub**, only tested locally. Until that changes, the site is
  refreshed by pushes and by the manual "Run workflow" button.
  The page always shows the run time and its age, and a banner after 24 h.
- **The refresh makes no commits.** It can only read the repository and deploy
  to Pages. After the commit history ends, the Actions run list and the data on
  the live site keep changing; the repository does not.
- If the hourly check itself is wrong (says "nothing to build" when there is),
  the site goes stale silently apart from the age shown on the page. The check
  has unit tests and was run once by hand against the live site.
- **One deploy timed out.** The push of the ensemble work (run #7) built in
  2 min 51 s and then the Pages deploy step gave up after 10 minutes
  ("Timeout reached, aborting!"). GitHub's API and the Pages site were also
  unreachable from the development machine at that time. The cause is unknown;
  the next run deployed the same commit without trouble. An earlier deploy
  (run #3) also took nine minutes and succeeded. A failed deploy leaves the
  previous site in place.
- **Build time with the ensemble**: 2 min 37 s to 2 min 51 s for the whole
  workflow on GitHub's runner (two runs). Locally it took 4 to 6 minutes.
- The pipeline has now processed one 00z run (locally and in CI) and one 12z
  run (in CI, unattended). The path "ensemble missing or failed its self-check,
  publish without it" has run only in unit tests, and the page's "probabilities
  could not be built" note has never been seen in a browser.
- The workflow's action versions (`checkout@v4`, `setup-python@v5`,
  `setup-node@v4`, `upload-pages-artifact@v3`, `deploy-pages@v4`) emit a
  "Node.js 20 is deprecated" warning. They work today; they will need bumping.
- Monitoring from outside is limited: GitHub's public API allows 60 requests an
  hour without a login, which the development session exhausted once while
  polling a build.

## Not done yet
- No location search, no 24 h totals of the single forecast.

## The ensemble probabilities
- **They are raw counts of 50 model runs, not calibrated probabilities.** "40 %"
  means 20 of 50 members reached the amount. Nobody has checked here whether it
  rains on 40 % of such occasions; raw ensembles are usually over-confident, but
  I have not measured that and cite no source for it.
- **0 % is not "impossible" and 100 % is not "certain".** They mean no member and
  every member. The smallest non-zero value is 2 %.
- **50 members, no control.** ECMWF's headers say the ensemble has 51 forecasts;
  the open-data files hold the 50 perturbed ones. I do not know why, and did not
  substitute the `oper` forecast for the missing one.
- **Agreement with ECMWF's own probabilities is statistical, not cell by cell.**
  Averaged over the globe the two differ by well under one percentage point at
  every threshold, but individual cells differ by tens of points along sharp
  rain edges, because ECMWF's field is smoothed in a way I could not determine.
  Where they differ I cannot say which is better.
- **No layer for light rain.** "At least 1 mm" was dropped because the packed
  data cannot resolve it (DECISIONS D20). At 5 mm the same effect remains at up
  to about 0.3 points on day 15.
- **Cell averages.** "At least 25 mm" is for the mean over a ~28 km cell. A
  gauge inside the cell can see far more; these maps understate the chance of
  local extremes.
- **Windows are fixed to the run time** (00–00 UTC or 12–12 UTC), so the same
  storm can be split across two windows in one run and sit inside one in the
  next. Consecutive runs are not directly comparable.
- **The probability and rate layers are different forecasts.** The rate map is
  the single `oper` run; it is not one of the 50 members, so a wet patch on the
  rate map can sit in a low-probability area and both are correct displays.
- The self-check needs ECMWF's `ep` files, which appear about 20 minutes after
  the member files. If a build runs in between, the probabilities are
  published unchecked and the manifest says so.
- Two runs of ensemble data have been processed (2026-11-10 00z and 12z). The
  detailed checks (recount of single cells from the raw member files, the
  1 mm analysis) were done on the 00z run only. For the 12z run only the
  automatic self-check ran: mean absolute difference from ECMWF's product
  0.59, 0.36, 0.11 and 0.03 points at 5, 10, 25 and 50 mm.

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
- **Quantisation.** Source `tp` is packed in 12 bits. In the 2026-11-10 00z run
  the packing step was 0.03 mm at +3 h, 0.06 mm from +6 h, 0.12 mm from +18 h
  and 0.24 mm from +120 h (it depends on each field's maximum, so other runs
  will differ). Interval amounts are differences of two such fields, so beyond
  +18 h nothing between 0 and 0.12 mm can exist in the data, and light amounts
  are a few steps at best. See DECISIONS D15 for what this did to the map.
- **Light precipitation is not drawn.** Mean rates below 0.1 mm/h, and any
  amount of a single packing step, are transparent. That hides about 11 % of
  the run's total precipitation (unweighted sum) spread thinly over a third of
  the globe. "No colour" means "less than 0.1 mm/h", not "dry".
- **Unexplained negatives.** 3,533 cells have `tp` one packing step *lower* at
  +288 h than at +282 h although both fields use the same step, and 866 cells
  likewise at +12 h. Accumulated precipitation should not decrease. I do not
  know the cause (interpolation to the 0.25° grid is a guess, not a finding).
  Negatives are clamped to 0 and counted per interval in the manifest.
- **Interval length changes at 144 h** from 3 h to 6 h. The map colours the
  mean rate (mm/h), so a colour means the same rate before and after the
  switch. But a 6 h mean flattens short bursts more than a 3 h mean, so peak
  colours after +144 h are systematically weaker for the same weather. The
  mean rate is also not the rain rate at any moment: 6 mm in 3 h shows as
  2 mm/h whether it fell steadily or in ten minutes.
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
- **Times are UTC and IST for everyone.** A viewer in another zone gets no local
  time, and neither zone is the clicked location's own. The chart's day ticks
  are UTC midnights, which is 05:30 in IST.
- **The chart is one grid cell of one forecast.** No uncertainty band, no
  neighbouring cells, no earlier runs. A spike on day 12 is drawn as firmly as
  one in hour 3; treat anything beyond a few days as a single scenario.
- **Bars are narrow on a phone.** At 375 px a 3 h interval is under 3 px wide,
  so a tap picks the right day reliably but not always the exact interval.
  The slider steps one interval at a time and the table lists every value.
- **Bar height is a mean rate, not a peak.** The 6 h bars after +144 h average
  over twice as long as the 3 h bars before, so the same burst looks half as
  tall there. Area (height × width) is the amount and is comparable.
- The chart's y axis rescales for each cell, so two cells cannot be compared
  by eye; read the axis.
- The map does not wrap across the antimeridian; a storm on the date line is
  split between the two edges.
- Plate carrée stretches high latitudes east–west. Cells near the poles look as
  large as tropical ones but cover far less area.
- Light theme only. On a phone the cell readout covers part of the legend.
- Country outlines are Natural Earth 1:50m de facto boundaries, for orientation
  only; small islands are missing, so some "ocean" cells are really land.
- ~29 MB of rasters per run; each interval is a ~350 KB download the first time
  it is shown. Fine on broadband, slow on a poor mobile connection.
