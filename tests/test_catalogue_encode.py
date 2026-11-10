from datetime import datetime, timezone

import numpy as np
import pytest

from pipeline.catalogue import Run, candidate_runs, expected_steps
from pipeline.encode import codes_to_png, dequantise, png_to_codes, quantise


def test_url_matches_the_file_name_seen_on_the_server():
    run = Run("20261110", "00")
    assert run.file_url(6, "grib2") == (
        "https://data.ecmwf.int/forecasts/20261110/00z/ifs/0p25/oper/20261110000000-6h-oper-fc.grib2")
    assert Run("20261109", "12").file_url(360, "index").endswith(
        "/20261109/12z/ifs/0p25/oper/20261109120000-360h-oper-fc.index")
    assert run.reference_time == datetime(2026, 11, 10, 0, tzinfo=timezone.utc)


def test_expected_steps_match_listing():
    s = expected_steps("00")
    assert len(s) == 85 and s[0] == 0 and s[-1] == 360
    assert s[48] == 144 and s[49] == 150           # 3-hourly to 144 h, then 6-hourly
    assert expected_steps("12") == s
    assert expected_steps("06")[-1] == 144 and len(expected_steps("06")) == 49
    with pytest.raises(ValueError):
        expected_steps("03")


def test_candidate_runs_newest_first_and_never_in_the_future():
    now = datetime(2026, 11, 10, 11, 20, tzinfo=timezone.utc)
    runs = candidate_runs(now)
    assert [(r.date, r.hour) for r in runs[:3]] == [("20261110", "00"), ("20261109", "12"), ("20261109", "00")]
    assert all(r.reference_time <= now for r in runs)
    with pytest.raises(ValueError):
        candidate_runs(datetime(2026, 11, 10, 11, 20))


def test_quantise_round_trip_and_error_bound():
    values = np.array([[0.0, 0.024, 0.026, 1.23], [12.345, 250.0, 3276.75, 0.05]])
    codes, clipped = quantise(values, 0.05)
    assert clipped == 0 and codes.dtype == np.uint16
    assert codes[0].tolist() == [0, 0, 1, 25]
    back = dequantise(png_to_codes(codes_to_png(codes)), 0.05)
    assert np.abs(back - values).max() <= 0.025 + 1e-9


def test_quantise_reports_clipping_and_rejects_nan():
    codes, clipped = quantise(np.array([[-1.0, 5000.0, 1.0]]), 0.05)
    assert clipped == 2 and codes.tolist() == [[0, 65535, 20]]
    with pytest.raises(ValueError):
        quantise(np.array([[np.nan]]), 0.05)


def test_png_uses_high_byte_in_red_low_byte_in_green():
    from PIL import Image
    import io
    codes = np.array([[0x1234, 0x00FF]], dtype=np.uint16)
    img = Image.open(io.BytesIO(codes_to_png(codes)))
    assert img.mode == "RGB"                       # no alpha channel
    assert img.getpixel((0, 0)) == (0x12, 0x34, 0)
    assert img.getpixel((1, 0)) == (0x00, 0xFF, 0)
