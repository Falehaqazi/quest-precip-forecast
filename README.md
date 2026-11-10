# Precipitation forecast from ECMWF Open Data

A static web map of forecast precipitation per 3- or 6-hour interval from the
ECMWF IFS model (0.25°, deterministic), rebuilt twice a day from
[ECMWF open data](https://www.ecmwf.int/en/forecasts/datasets/open-data).

- [SPEC.md](SPEC.md) — what it is, what the data really looks like, what "done" means
- [DECISIONS.md](DECISIONS.md) — non-obvious choices and their alternatives
- [LIMITATIONS.md](LIMITATIONS.md) — what is wrong, approximate or untested

## How it works

```
ECMWF data.ecmwf.int ──(HTTP range, tp only)──> pipeline/ ──> web/data/ (manifest.json + PNG rasters)
                                                                   │
                                        GitHub Actions (cron) ─────┴──> GitHub Pages ──> web/ (Leaflet, no build step)
```

`pipeline/` fetches the `tp` field of every step of the newest complete 00z/12z
run, decodes it with ecCodes, converts m → mm, differences consecutive steps
into per-interval amounts and writes one lossless PNG per interval. `web/` reads
`manifest.json` and draws the rasters on the model's own lat/lon grid.

## Run locally

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt      # Windows; use .venv/bin/python elsewhere
.venv/Scripts/python -m pytest -q                            # pipeline tests
node --test tests/js/grid.test.mjs                           # browser grid code tests
.venv/Scripts/python -m pipeline.run --out web/data          # ~50 MB download, a few minutes
.venv/Scripts/python -m http.server 8765 --directory web     # open http://localhost:8765
```

## Attribution

Based on data and products of the European Centre for Medium-Range Weather
Forecasts (ECMWF). © ECMWF, published under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The data is modified
(de-accumulated, unit-converted, rounded). Country outlines: Natural Earth
(public domain). ECMWF does not endorse this app.
