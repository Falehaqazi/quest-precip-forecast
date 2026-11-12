# LIMITATIONS

What is wrong, approximate or untested. Kept blunt on purpose.
Last updated 2026-11-11, after the ensemble layers went live
(https://falehaqazi.github.io/quest-precip-forecast/).

## Operations: what has and has not been seen to work
- **The page does not keep itself up to date, by design.** There is no
  automatic refresh. It is rebuilt only when its owner presses "Run workflow"
  on GitHub or pushes a commit. Left alone it goes stale: the forecast shown
  gets older and, after 15 days, runs out entirely. The page says when it was
  built and shows a banner once the run is 21 h old, but nothing fixes it
  without a person.
- **Why there is no schedule.** One was built and removed (DECISIONS D30).
  GitHub started one scheduled run (2026-11-11 00:35 UTC, hours after its
  scheduled time) out of roughly 35 scheduled times across three schedules:
  four fixed times a day, then hourly, then every 15 minutes for six hours.
  The workflow was listed as active throughout and I do not know why GitHub did
  not run it. That single run built and deployed correctly.
- **The "behind" banner is a guess about ECMWF's timing.** It appears when the
  run shown is 21 h old because a newer run was complete after about 20 h on
  the two days observed. If ECMWF is late the banner is early, and the page
  cannot check.
- **Builds make no commits.** The workflow can only read the repository and
  deploy to Pages. A manual run adds an entry to the Actions run list and
  changes the data on the live site; the repository does not change.
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
  run (in CI). The path "ensemble missing or failed its self-check,
  publish without it" has run only in unit tests, and the page's "probabilities
  could not be built" note has never been seen in a browser.
- The workflow's action versions (`checkout@v4`, `setup-python@v5`,
  `setup-node@v4`, `upload-pages-artifact@v3`, `deploy-pages@v4`) emit a
  "Node.js 20 is deprecated" warning. They work today; they will need bumping.
- Monitoring from outside is limited: GitHub's public API allows 60 requests an
  hour without a login, which the development session exhausted once while
  polling a build.

## Known and not fixed
Found in a reviewer pass on the live site at 375 × 812 on 2026-11-11 and left
as they are, by decision. Numbers are measurements from that pass.

- **A third of the first screen is empty on a phone.** The map is 188 px tall
  to keep the world's 2:1 shape; the space under the footer is blank until a
  place is picked.
- **No loading feedback.** Changing the time step took 0.5–1.7 s with nothing on
  screen to show that anything was happening.
- **The lightest legend class barely shows.** Its contrast against land is about
  1.1 in both colour scales, and country borders disappear inside the darkest
  class (contrast 1.1).
- **Playing the rate map downloads about 29 MB** (84 rasters of roughly 350 KB)
  with no warning on mobile data.
- **Small tap targets.** Zoom buttons are 24 × 24 px, the slider track is 16 px
  tall, the close button 32 px, and the rate slider moves one step per 4 px.
- **A dry place shows an empty chart** with a note explaining bars that are not
  there.
- **Nothing is shareable.** Layer, time and place are not in the URL; a reload
  loses them.
- **IST for every viewer** (asked for; DECISIONS D16).
- **Light theme only**, also on a device set to dark.
- **Jargon in the panel**: "Source precision 0.98 mm (ECMWF packing step)",
  "Grid index row 246, col 1029".
- **The table of values scrolls inside a 260 px box**, which is awkward on a
  phone.
- No place names anywhere: a picked place is a pair of coordinates. No place
  search (it would need an outside service).
- No 24 h totals of the single forecast.

Introduced by the fixes made after that pass:

- Picking a place jumps the map to a view about 16° across. That is a sharp
  change from the world view and there is no animation to follow.
- Pressing Enter on the map picks the place at its centre, but nothing marks
  the centre beforehand.
- "Use my location" was tested with a simulated position and simulated refusals
  only, never on a real device.
- The "now" tag reflects the device clock when the page loaded.

## The ensemble probabilities
- **They are raw counts of 50 model runs, not calibrated probabilities.** "40 %"
  means 20 of 50 members reached the amount. Nobody has checked here whether it
  rains on 40 % of such occasions; raw ensembles are usually over-confident, but
  I have not measured that and cite no source for it.
- **0 % is not "impossible" and 100 % is not "certain".** They mean no member and
  every member. The smallest non-zero value is 2 %.
- **50 of the ensemble's 51 members are counted.** The 51st, the control
  forecast, is the `oper` forecast shown on the rate map; ECMWF publishes it
  there and not with the other members (DECISIONS D33). This pipeline reads only
  the 50 perturbed members, so every share is out of 50. Counting the control
  too would move a value by at most one member in 51 (under 2 points). It was
  left out because the feature set was frozen when this was established, not
  because it cannot be done.
- **Agreement with ECMWF's own probabilities is statistical, not cell by cell.**
  Averaged over the globe the two differ by well under one percentage point at
  every threshold, but individual cells differ by tens of points along sharp
  rain edges, because ECMWF's field is smoothed in a way I could not determine.
  Where they differ I cannot say which is better.
- **No layer for light rain.** "At least 1 mm" was dropped because the packed
  data cannot resolve it (DECISIONS D20). At 5 mm the same effect remains at up
  to about 0.3 points on day 15.
- **Cell averages.** "At least 25 mm" is for the mean over a ~28 km cell. A
  gauge inside the cell can see far more, so these maps understate local
  extremes.
- **Windows are fixed to the run time** (00–00 UTC or 12–12 UTC), so the same
  storm can be split across two windows in one run and sit inside one in the
  next. Consecutive runs are not directly comparable.
- **The rate map and the member shares come from different members of one
  ensemble.** The rate map is the control forecast, which is not among the 50
  counted. So a wet patch on the rate map can sit where few of the 50 reach the
  threshold, and both are correct displays.
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
- **Accumulated precipitation sometimes decreases, and for some of it the cause
  is unknown.** Checked on raw values of the 2026-11-12 00z run: 263,375
  cell-intervals (0.30 %) in 5 of 84 intervals. Three of those intervals are
  where the packing step doubles; there every decrease is exactly half the
  coarser step (0.03 to 0.12 mm), which rounding explains. The other two
  (+39–42 h: 2,123 cells; +246–252 h: 3,072 cells) have the same packing step in
  both fields and every decrease is exactly one step (0.06 and 0.24 mm).
  ECMWF's separate 0.1° product decreases in the same two intervals, in the
  same share of cells, and in none of the neighbouring ones, so this comes from
  ECMWF's fields, not from this pipeline or the 0.25° grid. **Why ECMWF's
  fields do it, I could not find out.** One guess (a hidden change of packing
  step upstream) was tested against the 0.1° headers and not supported.
  The pipeline sets every negative difference to 0 and writes the count and the
  largest one per interval into the manifest. Because of that, the intervals
  for a cell can add up to at most 0.43 mm more than the model's own 15-day
  total (0.06 % over the globe). DECISIONS D32.
- **Interval length changes at 144 h** from 3 h to 6 h. The map colours the
  mean rate (mm/h), so a colour means the same rate before and after the
  switch. But a 6 h mean flattens short bursts more than a 3 h mean, so peak
  colours after +144 h are systematically weaker for the same weather. The
  mean rate is also not the rain rate at any moment: 6 mm in 3 h shows as
  2 mm/h whether it fell steadily or in ten minutes.
- **Only 00z/12z runs.** Even rebuilt the moment a run is published, the page
  is 8 h behind the model's start time, and up to 20 h just before the next
  one. In practice it is as old as its last manual rebuild.

## Things assumed, not verified
- The time column in the ECMWF directory listing is UTC (it is not labelled).
  The 21 h threshold of the "behind" banner rests on this and on two days of
  listings.
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
- No retry logic beyond three attempts per file. A failed build is visible
  only in the Actions list (and GitHub's default e-mail to the owner).
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
