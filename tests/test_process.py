from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from pipeline.process import (deaccumulate, iso_utc, metres_to_mm, rate_to_mm_per_hour,
                              reference_time, valid_time)


def test_metres_to_mm():
    assert metres_to_mm(0.001) == pytest.approx(1.0)
    assert metres_to_mm(np.array([0.0, 0.0254])) == pytest.approx([0.0, 25.4])


def test_rate_to_mm_per_hour():
    # 1 kg m-2 s-1 of water is 1 mm of depth per second -> 3600 mm/h
    assert rate_to_mm_per_hour(1.0) == pytest.approx(3600.0)
    # 10 mm/h expressed in SI
    assert rate_to_mm_per_hour(10 / 3600) == pytest.approx(10.0)


def test_rate_and_accumulation_agree_for_constant_rain():
    # constant 2 mm/h for 3 h must equal an accumulation of 6 mm = 0.006 m
    rate_si = 2 / 3600
    assert rate_to_mm_per_hour(rate_si) * 3 == pytest.approx(metres_to_mm(0.006))


def test_deaccumulate_basic_and_mixed_interval_lengths():
    acc = {0: np.array([0.0, 0.0]), 3: np.array([1.0, 0.0]), 6: np.array([1.5, 2.0]),
           12: np.array([4.5, 2.0])}
    out = deaccumulate(acc)
    assert [(i.start_step, i.end_step, i.hours) for i in out] == [(0, 3, 3), (3, 6, 3), (6, 12, 6)]
    assert out[0].values.tolist() == [1.0, 0.0]
    assert out[1].values.tolist() == [0.5, 2.0]
    assert out[2].values.tolist() == [3.0, 0.0]


def test_deaccumulated_intervals_sum_back_to_the_total():
    rng = np.random.default_rng(0)
    steps = list(range(0, 145, 3)) + list(range(150, 361, 6))
    increments = rng.gamma(0.3, 2.0, size=(len(steps) - 1, 50))
    acc = {0: np.zeros(50)}
    for s, inc in zip(steps[1:], increments):
        acc[s] = acc[s - (3 if s <= 144 else 6)] + inc
    out = deaccumulate(acc)
    assert len(out) == 84
    assert sum(i.hours for i in out) == 360
    assert [i.hours for i in out].count(3) == 48 and [i.hours for i in out].count(6) == 36
    np.testing.assert_allclose(sum(i.values for i in out), acc[360])


def test_deaccumulate_clamps_and_reports_negative_differences():
    acc = {0: np.array([0.0, 0.0, 0.0]), 6: np.array([1.0, 2.0, 3.0]), 12: np.array([0.75, 2.0, 5.0])}
    second = deaccumulate(acc)[1]
    assert second.values.tolist() == [0.0, 0.0, 2.0]
    assert second.negative_count == 1
    assert second.most_negative == pytest.approx(-0.25)


def test_deaccumulate_requires_step_zero_and_is_order_independent():
    with pytest.raises(ValueError):
        deaccumulate({3: np.zeros(2), 6: np.zeros(2)})
    out = deaccumulate({6: np.array([3.0]), 0: np.array([0.0]), 3: np.array([1.0])})
    assert [i.values[0] for i in out] == [1.0, 2.0]


def test_reference_time_is_utc():
    assert reference_time(20261110, 0) == datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc)
    assert reference_time(20261110, 1200) == datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def test_valid_time_crosses_day_month_and_year():
    ref = reference_time(20261110, 0)
    assert valid_time(ref, 6) == datetime(2026, 11, 10, 6, tzinfo=timezone.utc)
    assert valid_time(ref, 150) == datetime(2026, 11, 16, 6, tzinfo=timezone.utc)   # matches GRIB header
    assert valid_time(ref, 360) == datetime(2026, 11, 25, 0, tzinfo=timezone.utc)
    assert valid_time(reference_time(20261225, 1200), 360) == datetime(2027, 1, 9, 12, tzinfo=timezone.utc)
    assert valid_time(reference_time(20280227, 1200), 36) == datetime(2028, 2, 29, 0, tzinfo=timezone.utc)


def test_valid_time_is_independent_of_input_zone_and_dst():
    # 12:00 UTC expressed in Karachi time (UTC+5)
    pkt = timezone(timedelta(hours=5))
    ref_local = datetime(2026, 11, 10, 17, 0, tzinfo=pkt)
    assert valid_time(ref_local, 3) == datetime(2026, 11, 10, 15, 0, tzinfo=timezone.utc)
    # 48 h across the European DST change (2026-10-25) is still exactly 48 h in UTC
    assert valid_time(reference_time(20261024, 0), 48) == datetime(2026, 10, 26, 0, tzinfo=timezone.utc)


def test_naive_datetimes_are_refused():
    with pytest.raises(ValueError):
        valid_time(datetime(2026, 11, 10), 3)
    with pytest.raises(ValueError):
        iso_utc(datetime(2026, 11, 10))


def test_iso_utc_always_has_z():
    pkt = timezone(timedelta(hours=5))
    assert iso_utc(datetime(2026, 11, 10, 17, 0, tzinfo=pkt)) == "2026-11-10T12:00:00Z"
