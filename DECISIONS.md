# DECISIONS

Each entry: the choice, the alternative, why. Newest at the bottom.

## D1. Fetch single fields by HTTP byte range, not whole files
- **Choice**: read each step's `.index`, then range-request only the `tp` message.
- **Alternative**: download the full per-step GRIB (~95 MB × 85 steps ≈ 8 GB per run),
  or use the `ecmwf-opendata` client library.
- **Why**: one `tp` message is 0.3–0.55 MB. Range requests were tested against the
  live server (HTTP 206, byte count equal to the index `_length`). Doing it
  directly keeps the dependency list short and the behaviour visible; the client
  library does the same thing underneath but I have not verified that, so I am
  not relying on it.

## D2. Decode with ecCodes (Python), not a hand-written reader
- **Choice**: `eccodes` Python package (bundles the ecCodes binary and libaec).
- **Alternative**: a Node pipeline with a custom GRIB2/CCSDS decoder (Python was
  not installed on the dev machine); `cfgrib`/`xarray`.
- **Why**: the files use CCSDS packing (template 5.42). ECMWF's own decoder is the
  reference; a custom decoder would be the riskiest code in the project. xarray
  and cfgrib add nothing needed for one field per message.

## D3. Use `tp` differences for interval amounts; do not use `tprate`
- **Choice**: interval precipitation = `tp(step k) − tp(step k−1)`, in mm.
- **Alternative**: integrate `tprate` (instantaneous, kg m⁻² s⁻¹) over the interval.
- **Why**: `tp` is the model's own accumulation, so the difference is the exact
  interval total (up to packing precision). `tprate` is a snapshot every 3–6 h;
  multiplying it by the window length would invent a number.

## D4. 00z and 12z runs only
- **Choice**: ignore 06z/18z.
- **Alternative**: always show the newest of the four runs.
- **Why**: 06z/18z stop at 144 h, so the horizon would alternate between 15 and
  6 days. Cost: the page can be up to ~12 h + publication delay behind.

## D5. Static site + scheduled pipeline; API later
- **Choice**: GitHub Actions cron runs the pipeline and publishes static files to
  GitHub Pages.
- **Alternative**: an always-on API service.
- **Why**: agreed with Faleha. Fewer things that can be down during review; a
  live URL sooner. The data files are the contract; an API can be added on top.

## D6. Data format is a manifest of generic "layers"
- **Choice**: `manifest.json` lists layers; each has units, value encoding, legend
  and per-interval files. v1 has one layer (`tp_interval`).
- **Alternative**: hard-code "precipitation in mm" in file names and frontend.
- **Why**: ensemble probability of exceedance is the committed next step (SPEC E1).
  It is a different quantity (0–100 %) with a different legend; it should be a
  new manifest entry, not a rewrite.

## D7. Rasters are PNGs carrying a 16-bit integer in the R and G channels
- **Choice**: value = `offset + scale × (R·256 + G)`, alpha always 255, B unused.
  For `tp_interval`, scale = 0.05 mm.
- **Alternative**: pre-coloured PNG tiles (values lost, no click-to-read);
  raw binary + gzip (GitHub Pages does not reliably compress arbitrary binaries);
  Zarr/COG (heavier client).
- **Why**: lossless compression for free, decodable in any browser via canvas,
  and the client has the real numbers, so the legend and the click readout come
  from the same data. 0.05 mm rounding (≤0.025 mm error) is below the source
  packing precision (≥0.06 mm). Opaque alpha avoids premultiplied-alpha
  corruption when the browser decodes the image.

## D8. Map in plate carrée (EPSG:4326), vector coastlines, no basemap tiles
- **Choice**: Leaflet with `L.CRS.EPSG4326`, Natural Earth outlines, the data
  raster shown with one image pixel per model grid cell.
- **Alternative**: Web Mercator slippy map with a tile basemap.
- **Why**: the model grid is regular in lat/lon, so in this projection the
  overlay is exact with no resampling, and what the reviewer sees is the grid.
  Mercator would need client-side reprojection and cuts off the poles. No tile
  provider means no third-party key or outage. Cost: less familiar look, no
  street-level context.

## D9. Real ECMWF messages are committed as test fixtures
- **Choice**: three real `tp` messages (steps 0, 3, 6; ~640 KB) and one real
  `.index` file live in `tests/fixtures/`.
- **Alternative**: synthetic arrays only, or downloading during tests.
- **Why**: units, accumulation window, grid layout and CCSDS decoding are exactly
  the things that can be wrong without anyone noticing. Tests that decode the
  real bytes and compare with an outside value catch that; synthetic data cannot.
  Network-free, so CI does not depend on ECMWF being up. CC BY 4.0 permits it.

## D10. ecCodes is called from the main thread only
- **Choice**: download in 4 threads, decode sequentially.
- **Alternative**: decode inside the worker threads (the first version).
- **Why**: that version killed the process with no traceback on Windows. Decoding
  85 fields takes seconds, so nothing is lost. Full run: ~43 s locally.

## D11. Scheduled builds at 08:05/10:05 and 20:05/22:05 UTC (superseded by D24)
- **Choice**: two attempts per run, shortly after the observed publication time.
- **Alternative**: poll every 30 min; or trigger on ECMWF's side (not possible).
- **Why**: publication was seen at ~07:34 and ~19:34 UTC. A rebuild of the same
  run is idempotent, so the second attempt is a cheap retry. If a build fails,
  nothing is deployed and the previous run stays up with its age shown.

## D12. Cache-busting by run time in the raster URL
- **Choice**: rasters are requested as `tp_interval/006.png?run=<reference time>`.
- **Alternative**: put the run time in the file path.
- **Why**: file names repeat from run to run, and a browser or CDN cache could
  pair the new manifest with an old raster — a wrong number with nothing to show
  it. The query string avoids that without changing the layout on disk.

## D13. Deploy from `main`, not `master`
- **Choice**: rename the local branch to `main` and push it.
- **Alternative**: edit the `github-pages` environment on GitHub to allow `master`.
- **Why**: the first deploy was rejected because the environment's branch policy
  lists only `main`. Renaming needed no change to repository settings (which only
  the owner can make) and matches GitHub's default. The workflow already
  triggered on both names. Cost: an orphan `master` branch remains on GitHub
  until the owner deletes it and switches the default branch.

## D14. The colour scale is mean rate in mm/h, not mm per interval
- **Choice**: the map colours `amount / interval length`. The legend is in mm/h
  with one set of class bounds (0.1, 0.2, 0.5, 1, 2, 5, 10, 20) for the whole
  forecast. Stored values stay amounts per interval (mm); the readout shows
  both the amount ("4.90 mm in 6 h") and the mean rate.
- **Alternative A**: keep mm per interval (the first version). Rejected: the
  interval doubles from 3 h to 6 h at +144 h, so the same blue meant twice the
  rain rate before the switch as after it. Day 1 and day 10 were not comparable
  (reported by Faleha from the live site).
- **Alternative B**: a 24 h total view. Comparable across the whole forecast and
  arguably the more useful quantity at long leads, but it is a second layer with
  its own time axis and pipeline output. It stays on the list (SPEC S1); it was
  not needed to remove the inconsistency.
- **Why**: dividing by the interval length removes the inconsistency exactly,
  needs no new data, and keeps full time resolution.
- **What it does not fix**: a 6 h mean smooths short bursts more than a 3 h mean.
  A 1-hour downpour of 12 mm is 4 mm/h in a 3 h interval and 2 mm/h in a 6 h one.
  So peaks still look weaker after +144 h for a reason that is about averaging,
  not weather. This is stated in LIMITATIONS.
- **Where it lives**: the manifest's `display` block says `normalise: per_hour`;
  the browser does the division. The pipeline does not store rates, so the
  amounts remain exactly what was derived from `tp`.

## D15. Nothing below 0.1 mm/h is drawn, and never a single source packing step
- **What was checked** (run 2026-11-10 00z, raw `tp` values, all 84 intervals):
  the faint lowest class seen on the first version (0.1–0.5 mm per interval).
  - ECMWF packs each accumulated field in 12 bits. The step ("quantum") was
    0.03 mm at +3 h, 0.06 mm from +6 h, **0.12 mm from +18 h and 0.24 mm from
    +120 h**. It depends on the field's maximum, so it will differ from run to run.
  - Up to +15 h the faint class is real model output: 0 % of it is a
    single quantum, and 16–23 % of all cells hold a positive amount below 0.1 mm.
    The model does put trace precipitation over about half the globe.
  - From +18 h the quantum is larger than the 0.1 mm threshold. The data can no
    longer hold anything between 0 and one quantum (the count of such cells drops
    to exactly 0), and 40–63 % of everything drawn was exactly one quantum. A
    one-quantum difference means the true increment was somewhere between
    almost nothing and that step; which cells get it is rounding. Over the whole
    run, **38.5 % of drawn cell-intervals were a single quantum.**
  - It was mostly not salt-and-pepper: only 2–8 % of faint cells had no wet
    neighbour. It is trace precipitation regions with a dithered edge and
    interior, not random dots over dry areas.
- **Choice**: (a) lowest class starts at 0.1 mm/h mean rate (0.3 mm per 3 h,
  0.6 mm per 6 h), which was at least 1.2 quanta everywhere in this run;
  (b) the pipeline writes each interval's quantum to the manifest
  (`source_quantum`) and the browser draws nothing whose stored amount is one
  quantum or less, so the rule still holds in a run with coarser packing.
- **Alternative**: keep 0.1 mm and accept the noise; smooth the field (invents
  data); raise the threshold only after +18 h (colours would again mean
  different things at different leads).
- **Effect, measured**: single-quantum share of drawn cells 38.5 % → 0 %. Drawn
  area roughly halves (16–21 % of cells per interval instead of 31–49 %) and no
  longer jumps when the packing changes. **Cost: 11 % of the run's total
  precipitation (plain sum over cells, not area-weighted) falls below 0.1 mm/h
  and is not coloured.** The numbers are still there on hover and click.
- **Still coarse**: between +120 h and +144 h the lowest class is exactly two
  quanta (0.49 mm in 3 h); later classes are a handful of quanta wide.

## D16. The second time zone is IST for every viewer
- **Choice**: every time on the page is shown in UTC and in India Standard Time
  (`Asia/Kolkata`, UTC+05:30, no daylight saving), labelled "IST". It is one
  constant in `web/time.js`.
- **Alternative**: UTC plus the browser's own zone (the first version); or the
  clicked location's zone (needs a time-zone boundary dataset).
- **Why**: Faleha asked for UTC and IST in the chart. Showing IST in the chart
  and the browser's zone in the slider would put two different "local" times on
  one page for anyone outside India, so the whole page uses the same pair.
- **Cost**: a viewer outside India has to convert from UTC themselves.

## D17. The time series comes from tiles cut by place, not from the map rasters
- **Choice**: the pipeline writes the same 16-bit codes a second time, as one PNG
  per 32 × 32 block of cells holding all 84 intervals (1,035 files, 32 MB,
  ~30 KB typical, 91 KB largest). A click downloads one of them.
- **Alternative A**: read the clicked pixel out of all 84 map rasters (about
  29 MB of downloads per click). **Alternative B**: a server that answers point
  queries (deferred, SPEC S4). **Alternative C**: one file per cell (a million
  files).
- **Why**: one small request per click with static hosting only. The site
  doubles to ~62 MB per run, far below the Pages limit.
- **Guard**: the two files could in principle disagree. Tests compare them on
  real data in the pipeline, and the page compares the chart's value with the
  map's value for the selected cell on every interval change and prints a
  warning under the chart if they differ.

## D18. Chart form: one bar per interval, height = mean rate, width = duration
- **Choice**: bars on a linear time axis. Height is mm/h, width is the interval
  length (3 h or 6 h), so area is the amount in mm. One colour; the interval
  shown on the map is dark; bars too small for the map to draw are pale. The
  numbers for the tapped (or hovered) interval are printed above the chart in
  mm/h and mm, with the interval in UTC and IST. A table of all 84 values is one
  tap away.
- **Alternative**: equal-width bars of mm per interval (the 6 h bars would look
  twice as wet, the problem fixed on the map in D14); a line (suggests values
  between the intervals that do not exist); a cumulative curve (hides when it
  rains); a second axis for the cumulative total (two scales on one chart).
- **Why**: it is the same quantity and unit as the map, it stays honest across
  the 3 h → 6 h change, and it needs no legend. The total is given as a number.
- **Phone**: no floating tooltip. A tap anywhere in a bar's column selects that
  interval, moves the map to it, and updates the numbers above the chart.

## D19. Ensemble probabilities are for 24 h windows, at 5, 10, 25 and 50 mm
- **Choice**: four layers, "chance of at least N mm in 24 h" for N = 5, 10, 25,
  50, in 15 back-to-back windows from the run start (+0–24 h … +336–360 h).
- **How the 3 h and 6 h steps are handled**: they are not mixed at all. A
  window total for one member is `tp(window end) − tp(window start)`, and every
  window end (+24, +48, … +360 h) is a step that exists in both the 3-hourly and
  the 6-hourly part of the forecast. Nothing is interpolated in time, nothing is
  summed across steps, and a window means the same thing on day 1 and day 15.
  The change from 3 h to 6 h steps at +144 h falls exactly on a window boundary.
- **Alternative A**: probabilities per 3 h / 6 h interval, matching the map's
  time slider. Rejected: (1) it needs every step of every member — an estimated
  1.8 GB of `tp` and 4,250 range requests per run (extrapolated from two steps)
  instead of the measured 383 MB and 800;
  (2) "at least 5 mm" in a 3 h interval and in a 6 h interval are different
  events, so one threshold would mean two things across the +144 h change, the
  very problem fixed for the rate layer in D14; (3) placing rain within 3 h a
  week ahead is not something an ensemble can do, so most of the map would read
  near zero.
- **Alternative B**: overlapping windows every 12 h, as ECMWF publishes. Twice
  the download for a smoother slider; not needed for "a few".
- **Thresholds**: these four are also published by ECMWF (`tpg5/10/25/50`), so
  every layer can be checked against an outside number (D21). **1 mm was built
  first and dropped** — see D20. Not chosen: 20 mm (close to 25) and 100 mm
  (almost always zero).
- **Windows follow the run, not the calendar**: for the 00z run they are
  00–00 UTC (05:30–05:30 IST); for the 12z run 12–12 UTC.

## D20. No "at least 1 mm" layer: the source data cannot resolve it
- **What was found**: with a 1 mm threshold my probabilities were lower than
  ECMWF's own by 0.4 points on day 1, growing to 2.8 points on day 15, while
  10 mm and above agreed to within 0.06.
- **Cause, tested**: each member's `tp` is packed in 12 bits with a step that
  grows with the field's maximum. The median step over the members was 0.12 mm
  at +24 h, 0.24 mm at +120 h and 0.49 mm at +264 h; for some members it reached
  **0.98 mm**. A window total is a difference of two such fields, so it can only
  take values on that lattice, and the lattice point just under 1 mm (0.977)
  swallows members whose true total is a little over 1 mm. Lowering my cut to
  0.95 mm, which takes in that lattice point, flipped the bias to +1.7…+5.1
  points — so the truth is bracketed and the direction is explained.
- **Choice**: lowest threshold 5 mm, where the same effect is at most
  0.34 points on day 15. A "chance of any rain" layer would be the one most
  people want; it is not offered because it would be biased low by a
  lead-dependent amount that I can measure but not remove.
- **Alternative**: serve ECMWF's own `tpg1` for that one layer. Rejected for
  now: one layer would then be computed differently from the other four.

## D21. Probability = raw count of 50 perturbed members; checked against ECMWF every run
- **Choice**: P = (members with window total ≥ threshold) / 50. The comparison
  is "at least" (≥), matching ECMWF's parameter names. The stored number is the
  member count (0–50), so the page can say "17 of 50 members". No smoothing in
  space, no calibration, no control member (it is not in the open-data files).
- **Alternative**: use ECMWF's `ep` product as is (≈70 MB, no computation).
  Rejected because the calculation was asked for and because then nothing on
  the page would be traceable to member forecasts; instead `ep` is used as the
  reference. Fitting a distribution or adding a neighbourhood: more assumptions
  than I can justify here.
- **Self-check**: every run, each of the 60 fields is compared with ECMWF's
  field for the same window and threshold; the result is written into the
  manifest (`ensemble.crosscheck`) and if the mean absolute difference for any
  threshold exceeds 3 percentage points the ensemble layers are not published.
  Run 2026-11-10 00z, all 15 windows, in percentage points, mine minus ECMWF:
  ≥5 mm: mean |diff| 0.608, mean diff -0.113, max 66.1; ≥10 mm: mean |diff| 0.36, mean diff +0.009, max 58.4; ≥25 mm: mean |diff| 0.113, mean diff -0.028, max 40.5; ≥50 mm: mean |diff| 0.026, mean diff -0.005, max 33.5.
- **Why they do not match exactly**: ECMWF's field is smooth and not in steps
  of 2 %, so it was not made by counting 50 members on this grid. Single cells
  differ by up to several tens of points, mostly along sharp rain edges. The
  check is good for catching a wrong window, unit or comparison; it does not
  show that either field is right about the weather.
- **If the ensemble cannot be built** (files late, a member missing, self-check
  failed), the deterministic forecast is still published and the page says the
  probabilities are missing. The build log carries a warning.

## D22. Cost: 383 MB more download, 28 MB more output per run
- **Measured locally** (run 2026-11-10 00z): 800 range requests, 383 MB of member
  `tp`, 251 s for the ensemble part including decoding 800 fields and the
  self-check, while ECMWF's server was busy publishing the 12z run (149 s when
  the member files were already cached, so most of it is decoding). Output:
  60 rasters = 11.1 MB and one shared set of 1,035 series tiles = 12.4 MB.
  The site is now about 90 MB per run (Pages limit 1 GB).
- **Choice**: all four thresholds of a cell live in one tile file (frames =
  threshold × window), so the chart needs one download whichever layer is
  shown, and the file count stays at 1,035 rather than 4,140.
- **Memory**: members are kept as float32 for two steps at a time (≈400 MB).
  float32 is exact for these values (integers below 4096 times a power of two).

## D23. A run is used only when its ensemble files exist too
- **Choice**: "newest complete run" now means the last-step index exists for the
  deterministic forecast, for the ensemble members and for ECMWF's probability
  product. Otherwise the previous run is used.
- **Alternative**: take the newest deterministic run and publish without
  probabilities until the next build (what `--ensemble optional` alone did).
- **Why**: this happened during development. At about 19:40 UTC on 2026-11-10
  the 12z deterministic run was complete and the 12z ensemble returned 404.
  ECMWF's listing for the 00z run shows the same order (07:34, 07:40, 08:01).
  A build in that gap would have replaced a full forecast with a partial one.
- **Cost**: the page can be up to about half an hour later than it could be.
  `--ensemble optional` still applies if something fails after the run is chosen.

## D24. The refresh runs every hour and builds only when there is something new
- **Choice**: the workflow is scheduled at minute 17 of every hour. Its first
  real step (`pipeline/check.py`) asks three things and stops the run unless one
  is true: ECMWF has a newer complete run (deterministic, ensemble members and
  ECMWF's probability product all present) than the one named in the live
  `manifest.json`; the live site was built from a different commit than the
  code now on `main`; the live site has no ensemble probabilities. Pushes and
  manual runs always build. The manifest now records the commit it was built
  from so the second question can be answered.
- **Alternative**: keep four fixed times a day (D11). Rejected on evidence: of
  two evening attempts one ran, 2.5–4.5 h late, and the next morning's first
  attempt had not started 1.5 h after its time. An outside scheduler calling
  `workflow_dispatch` would be more punctual but needs a token and another
  service to look after.
- **Why hourly with a skip**: 24 chances a day instead of 4, without 24
  downloads of 430 MB from ECMWF. A run that skips takes well under a minute
  and touches ECMWF with a handful of HEAD requests.
- **The refresh never commits.** The workflow's token has `contents: read`
  only; there is no commit, push or tag step; the site is published as a Pages
  deployment artifact, not to a branch (there is no `gh-pages` branch). After
  the first unattended run every commit on `main` was still authored and
  committed by Faleha. What does change without a commit: the Actions run
  history, and the data on the live site.
- **Side effect**: any commit, even to a `.md` file, makes the next build
  happen (on push, or at the next scheduled run if the push build was skipped
  or failed), because the site would otherwise be from older code.
- **Still true**: GitHub may start an hourly run late or drop it. Hourly makes
  a long gap unlikely; it does not make one impossible.

## D25. The page opens on "chance of at least 5 mm in 24 h"
- **Choice**: the manifest names the opening layer (`default_layer`); the
  pipeline sets it to the lowest ensemble threshold when the probabilities were
  built, and to the rate layer otherwise. The frontend just follows it.
- **Alternative**: open on the single-forecast rate map (the first version), or
  on 10 mm.
- **Why**: asked for by Faleha so the first screen shows something. On the
  2026-11-10 00z run the 5 mm layer colours 29 % of the map in its first window;
  the rate map colours about 17 % in its first interval, and the 25 and 50 mm
  layers far less. 5 mm rather than 10 because it is the lowest threshold the
  data supports (D20) and so the fullest map.
- **Cost**: the first thing a visitor sees is now a 24 h window rather than a
  3 h interval, and a probability rather than an amount. The selector above the
  legend says which, and the rate map is one tap away.
