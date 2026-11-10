# Test fixtures

Real ECMWF open data, IFS 0.25° `oper`, run 2026-11-10 00z, downloaded 2026-11-10
by HTTP byte range from `https://data.ecmwf.int/forecasts/20261110/00z/ifs/0p25/oper/`.
Unmodified.

| File | Content |
|---|---|
| `tp-0h.grib2` | `tp` at step 0 (224 bytes, constant zero field) |
| `tp-3h.grib2` | `tp` at step 3 (accumulated 0–3 h) |
| `tp-6h.grib2` | `tp` at step 6 (accumulated 0–6 h) |
| `20261110000000-6h-oper-fc.index` | the full index file of step 6 |

© 2026 European Centre for Medium-Range Weather Forecasts (ECMWF). Published under
CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). These tests are based on
data and products of ECMWF.

## Reference values used by the tests

Recorded on 2026-11-10 from the Open-Meteo forecast API (`models=ecmwf_ifs025`,
`cell_selection=nearest`, hourly `precipitation`, UTC), which processes the same
ECMWF files independently of this code and rounds to 0.1 mm:

| Point | 00–03 UTC (sum of hours 01,02,03) | 03–06 UTC (sum of hours 04,05,06) |
|---|---|---|
| −41.25, 174.75 (near Wellington) | 1.4+1.4+1.4 = 4.2 mm | 2.6+2.6+2.6 = 7.8 mm |
| 1.25, 103.75 (near Singapore) | 0.0 mm | 0.0 mm |
| 51.5, 0.0 (London) | 0.0 mm | 0.0 mm |

Open-Meteo spreads each 3 h total evenly over its hours, so three equal hourly
values summing to the 3 h amount is what agreement looks like. Tolerance in the
tests is ±0.15 mm (three values each rounded to 0.1).
