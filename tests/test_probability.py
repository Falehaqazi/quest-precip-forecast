import numpy as np
import pytest

from pipeline.catalogue import find_members
from pipeline.ensemble import POE_LEGEND, THRESHOLDS_MM, windows
from pipeline.encode import codes_to_png, dequantise, png_to_codes
from pipeline.probability import ExceedanceCounter, exceedance_count, probability_percent, window_total
from pipeline.run import TP_LEGEND

M = 50


def ensemble(values_per_cell):
    """(members, 1, cells) array from a list of per-cell member lists."""
    return np.array(values_per_cell, dtype=np.float64).T.reshape(len(values_per_cell[0]), 1, -1)


# ---------- the two edge cases: no member, every member ----------

def test_no_member_exceeds_gives_exactly_zero():
    totals = np.full((M, 3, 4), 0.9)
    count = exceedance_count(totals, 1.0)
    assert count.shape == (3, 4) and count.dtype == np.uint16
    assert (count == 0).all()
    p = probability_percent(count, M)
    assert (p == 0.0).all()                       # exactly 0, not 1e-17


def test_every_member_exceeds_gives_exactly_one_hundred():
    totals = np.full((M, 3, 4), 60.0)
    count = exceedance_count(totals, 50.0)
    assert (count == M).all()
    p = probability_percent(count, M)
    assert (p == 100.0).all()                     # exactly 100, not 99.99999


def test_a_completely_dry_ensemble_is_zero_for_every_threshold():
    counter = ExceedanceCounter(THRESHOLDS_MM, (2, 2))
    for _ in range(M):
        counter.add(np.zeros((2, 2)))
    assert counter.members == M
    assert (counter.counts == 0).all()


def test_zero_and_all_survive_the_png_round_trip_used_on_the_site():
    count = np.array([[0, 1, 25, 49, 50]], dtype=np.uint16)
    back = dequantise(png_to_codes(codes_to_png(count)), 100.0 / M)
    assert back.tolist() == [[0.0, 2.0, 50.0, 98.0, 100.0]]


# ---------- everything in between ----------

def test_counts_and_percent_for_a_known_ensemble():
    # cell 0: 17 members at 12 mm, 33 dry; cell 1: one member wet; cell 2: all but one wet
    cells = [[12.0] * 17 + [0.0] * 33, [30.0] + [0.0] * 49, [5.0] * 49 + [0.2]]
    totals = ensemble(cells)
    assert exceedance_count(totals, 10.0).ravel().tolist() == [17, 1, 0]
    assert exceedance_count(totals, 1.0).ravel().tolist() == [17, 1, 49]
    assert probability_percent(exceedance_count(totals, 1.0), M).ravel().tolist() == [34.0, 2.0, 98.0]


def test_threshold_is_at_least_not_more_than():
    totals = ensemble([[10.0] * 20 + [9.99] * 30])
    assert exceedance_count(totals, 10.0).item() == 20      # exactly 10 mm counts
    totals = ensemble([[np.nextafter(10.0, 0.0)] * 50])     # the largest double below 10
    assert exceedance_count(totals, 10.0).item() == 0


def test_probability_never_increases_with_the_threshold():
    rng = np.random.default_rng(7)
    totals = rng.gamma(0.4, 12.0, size=(M, 20, 30))
    counts = [exceedance_count(totals, t) for t in THRESHOLDS_MM]
    for lower, higher in zip(counts, counts[1:]):
        assert (higher <= lower).all()
    assert all(c.max() <= M for c in counts)


def test_probability_has_one_step_per_member():
    p = probability_percent(np.arange(M + 1), M)
    assert p[0] == 0.0 and p[-1] == 100.0
    np.testing.assert_allclose(np.diff(p), 2.0)             # 50 members -> 2 % steps
    assert probability_percent(np.array([1]), 51).item() == pytest.approx(100 / 51)


def test_member_order_does_not_matter_and_streaming_equals_batch():
    rng = np.random.default_rng(11)
    totals = rng.gamma(0.5, 10.0, size=(M, 6, 7))
    counter = ExceedanceCounter(THRESHOLDS_MM, (6, 7))
    for i in rng.permutation(M):
        counter.add(totals[i])
    for k, t in enumerate(THRESHOLDS_MM):
        np.testing.assert_array_equal(counter.counts[k], exceedance_count(totals, t))


def test_single_member_ensemble_is_all_or_nothing():
    assert probability_percent(exceedance_count(np.array([[[3.0, 0.0]]]), 1.0), 1).ravel().tolist() == [100.0, 0.0]


# ---------- window totals from accumulations ----------

def test_window_total_is_end_minus_start_per_member():
    start = np.array([[0.0, 4.0, 10.0]])
    end = np.array([[2.5, 4.0, 35.0]])
    assert window_total(start, end).tolist() == [[2.5, 0.0, 25.0]]


def test_window_total_clamps_packing_noise_but_not_real_rain():
    assert window_total(np.array([5.0]), np.array([4.9])).item() == 0.0
    with pytest.raises(ValueError):
        window_total(np.zeros((2, 2)), np.zeros((2, 3)))


def test_window_total_is_exact_for_packed_values():
    # packed fields are integers times a power of two; float32 storage must not move a
    # value across a threshold (the pipeline keeps members as float32 metres)
    q = 2.0 ** -13                                   # metres, the step seen at +24 h
    start = np.float32(100 * q)
    end = np.float32((100 + 82) * q)                 # 82 steps = 10.009765625 mm
    total_mm = window_total(np.float64(start) * 1000.0, np.float64(end) * 1000.0)
    assert total_mm == 82 * q * 1000.0
    assert exceedance_count(np.full((3, 1), total_mm), 10.0).item() == 3
    assert exceedance_count(np.full((3, 1), 81 * q * 1000.0), 10.0).item() == 0


def test_24h_windows_cover_the_run_and_avoid_the_3h_6h_change():
    w = windows(360)
    assert len(w) == 15 and w[0] == (0, 24) and w[-1] == (336, 360)
    assert all(b - a == 24 for a, b in w)
    assert all(w[i][1] == w[i + 1][0] for i in range(14))        # no gaps, no overlap
    # every window end is a step that exists both before and after the change at +144 h
    from pipeline.catalogue import expected_steps
    steps = set(expected_steps("00"))
    assert all(a in steps and b in steps for a, b in w)
    assert (144, 168) in w                                       # first window made of 6 h steps
    with pytest.raises(ValueError):
        windows(150)


# ---------- bad input ----------

def test_bad_input_is_refused():
    with pytest.raises(ValueError):
        exceedance_count(np.zeros((0, 2, 2)), 1.0)                # no members
    with pytest.raises(ValueError):
        exceedance_count(np.zeros(5), 1.0)                        # no member axis
    with pytest.raises(ValueError):
        exceedance_count(np.array([[np.nan, 1.0]]), 1.0)
    with pytest.raises(ValueError):
        exceedance_count(np.zeros((2, 2)), 0.0)                   # "at least 0 mm" is always true
    with pytest.raises(ValueError):
        probability_percent(np.array([51]), 50)                   # more exceeding members than members
    with pytest.raises(ValueError):
        probability_percent(np.array([0]), 0)
    with pytest.raises(ValueError):
        ExceedanceCounter([], (1, 1))
    c = ExceedanceCounter([1], (2, 2))
    with pytest.raises(ValueError):
        c.add(np.zeros((3, 3)))
    with pytest.raises(ValueError):
        c.add(np.full((2, 2), np.inf))


# ---------- index handling for members ----------

def entry(number, param="tp", offset=0, length=10, **extra):
    return {"type": "pf", "levtype": "sfc", "param": param, "number": str(number), "_offset": offset, "_length": length, **extra}


def test_find_members_returns_each_member_once():
    entries = [entry(2, offset=100), entry(1, offset=0), entry(1, param="2t", offset=50)]
    assert find_members(entries, param="tp", levtype="sfc") == {2: (100, 10), 1: (0, 10)}


def test_find_members_refuses_duplicates_and_missing_numbers():
    with pytest.raises(LookupError):
        find_members([entry(1), entry(1, offset=20)], param="tp")     # would double-count member 1
    with pytest.raises(LookupError):
        find_members([{"param": "tp", "_offset": 0, "_length": 1}], param="tp")
    with pytest.raises(LookupError):
        find_members([entry(1)], param="nope")


# ---------- legends ----------

def oklab_lightness(hex_colour):
    n = int(hex_colour[1:], 16)
    c = [((n >> s) & 255) / 255 for s in (16, 8, 0)]
    c = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
    l = 0.4122214708 * c[0] + 0.5363325363 * c[1] + 0.0514459929 * c[2]
    m = 0.2119034982 * c[0] + 0.6806995451 * c[1] + 0.1073969566 * c[2]
    s = 0.0883024619 * c[0] + 0.2817188376 * c[1] + 0.6299787005 * c[2]
    return 0.2104542553 * l ** (1 / 3) + 0.7936177850 * m ** (1 / 3) - 0.0040720468 * s ** (1 / 3)


@pytest.mark.parametrize("legend", [POE_LEGEND, TP_LEGEND])
def test_legends_get_darker_as_the_value_rises(legend):
    bounds = [v for v, _ in legend]
    assert bounds == sorted(bounds) and len(set(bounds)) == len(bounds)
    light = [oklab_lightness(c) for _, c in legend]
    assert all(b < a for a, b in zip(light, light[1:]))


def test_probability_legend_starts_at_one_member_of_fifty():
    assert POE_LEGEND[0][0] == 2 and POE_LEGEND[-1][0] < 100
