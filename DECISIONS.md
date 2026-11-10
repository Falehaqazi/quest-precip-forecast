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

## D11. Scheduled builds at 08:05/10:05 and 20:05/22:05 UTC
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
