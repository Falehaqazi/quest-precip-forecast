# LIMITATIONS

What is wrong, approximate or untested. Kept blunt on purpose.

## The data
- **This is raw model output.** No bias correction, no downscaling, no
  verification against gauges or radar. A 0.25° cell is roughly 28 km × 28 km at
  the equator; a value is a cell average, not the rain at a point. Convective
  extremes are smoothed away.
- **One deterministic forecast.** No uncertainty is shown in v1. Beyond a few
  days a single run's precipitation placement is not reliable; the map does not
  tell you that.
- **Quantisation.** Source `tp` is packed in 12 bits with precision 2^E m:
  about 0.06 mm at step 6 and 0.24 mm at step 150 (measured), presumably coarser
  by step 360 (not yet measured). Interval amounts are differences of two such
  fields, so late intervals have noise of that order, and can be slightly
  negative. Negatives are clamped to 0; the size of the clamp is recorded per
  interval in the manifest.
- **Interval length changes at 144 h** from 3 h to 6 h. Amounts are per interval,
  so the map looks wetter after 144 h for the same rain rate.
- **Only 00z/12z runs.** The page can lag the newest model run by 12 h plus
  ECMWF's ~7 h publication delay.

## Things assumed, not verified
- The time column in the ECMWF directory listing is UTC (it is not labelled).
- A run is "complete" if its last step's `.index` exists. If ECMWF publishes
  non-atomically the pipeline may hit a missing step; it then fails without
  publishing, leaving the previous run on the site.
- The units check against Open-Meteo is against a service that itself derives
  from the same ECMWF files and rounds to 0.1 mm. It independently confirms
  units, de-accumulation, grid indexing and timing, but it is not independent
  *data*. Only three points and the first 6 h were compared.
- ecCodes is trusted as the reference decoder.

## The app
- Nothing is deployed yet.
- No automated browser tests for the frontend.
- Times are shown in UTC and the browser's zone, not the clicked location's zone.
- The map does not wrap across the antimeridian.
