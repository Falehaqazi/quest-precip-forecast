"""Tests against real ECMWF messages (see tests/fixtures/README.md for provenance)."""
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from pipeline.catalogue import check_message, find_field, parse_index
from pipeline.encode import codes_to_png, dequantise, png_to_codes, quantise
from pipeline.gribio import decode, expect_accumulated_tp
from pipeline.grid import Grid
from pipeline.process import deaccumulate, metres_to_mm

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def tp():
    return {s: decode((FIX / f"tp-{s}h.grib2").read_bytes()) for s in (0, 3, 6)}


def test_header_metadata(tp):
    f = tp[6]
    assert (f.short_name, f.units, f.step_type) == ("tp", "m", "accum")
    assert (f.start_step, f.end_step) == (0, 6)          # accumulated since run start
    assert f.reference == datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc)
    assert f.grid == Grid(ni=1440, nj=721, lat0=90.0, lon0=-180.0, dlat=-0.25, dlon=0.25)
    assert f.values.shape == (721, 1440)
    for step in (0, 3, 6):
        expect_accumulated_tp(tp[step], step)


def test_expectation_check_catches_wrong_window(tp):
    with pytest.raises(ValueError):
        expect_accumulated_tp(tp[6], 3)


def test_packing_quantum_read_from_real_headers(tp):
    # 12-bit packing with binary scale 2^-15 m at step 3 and 2^-14 m at step 6 (see SPEC 5.4)
    assert tp[0].quantum == 0.0                      # constant field, nothing packed
    assert tp[3].quantum == 2.0 ** -15
    assert tp[6].quantum == 2.0 ** -14
    # every value is a whole number of quanta (reference value is 0 for these fields)
    steps = tp[6].values / tp[6].quantum
    assert np.abs(steps - np.rint(steps)).max() < 1e-9
    assert steps.max() <= 4095                       # 12 bits


def test_step_zero_is_all_zero(tp):
    assert tp[0].values.min() == 0.0 and tp[0].values.max() == 0.0


def test_values_are_plausible_metres(tp):
    v = tp[6].values
    assert v.min() >= 0.0
    # 137 mm in 6 h somewhere on Earth is plausible; 137 m or 0.137 mm would not be.
    assert 0.05 < v.max() < 0.5
    # accumulation never decreases between step 3 and step 6 by more than packing precision
    assert (tp[6].values - tp[3].values).min() > -2 ** -13


# Independent reference: Open-Meteo, recorded 2026-11-10 (fixtures/README.md).
@pytest.mark.parametrize("lat, lon, ref_0_3, ref_3_6", [
    (-41.25, 174.75, 4.2, 7.8),
    (1.25, 103.75, 0.0, 0.0),
    (51.5, 0.0, 0.0, 0.0),
])
def test_interval_amounts_match_independent_source(tp, lat, lon, ref_0_3, ref_3_6):
    grid = tp[6].grid
    row, col = grid.index_of(lat, lon)
    assert grid.center_of(row, col) == (lat, lon)
    first, second = deaccumulate({s: metres_to_mm(f.values) for s, f in tp.items()})
    assert first.values[row, col] == pytest.approx(ref_0_3, abs=0.15)
    assert second.values[row, col] == pytest.approx(ref_3_6, abs=0.15)


def test_png_round_trip_on_real_field(tp):
    first, second = deaccumulate({s: metres_to_mm(f.values) for s, f in tp.items()})
    scale = 0.05
    codes, clipped = quantise(second.values, scale)
    assert clipped == 0
    png = codes_to_png(codes)
    back = dequantise(png_to_codes(png), scale)
    assert back.shape == second.values.shape
    assert np.abs(back - second.values).max() <= scale / 2 + 1e-9
    assert len(png) < 1_000_000       # sanity: the raster is small enough to serve


def test_index_lookup_and_message_check():
    entries = parse_index((FIX / "20261110000000-6h-oper-fc.index").read_text())
    assert len(entries) == 191
    offset, length = find_field(entries, param="tp", levtype="sfc")
    assert (offset, length) == (15141642, 313960)
    data = (FIX / "tp-6h.grib2").read_bytes()
    assert check_message(data, length) is data
    with pytest.raises(IOError):
        check_message(data[:-1], length)
    with pytest.raises(LookupError):
        find_field(entries, param="does-not-exist")
    with pytest.raises(LookupError):
        find_field(entries, levtype="sfc")      # ambiguous: many surface fields
