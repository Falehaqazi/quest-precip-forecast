import pytest

from pipeline.grid import Grid, grid_from_keys, normalise_lon

# The layout read from real ECMWF 0.25 degree files (see SPEC 5.5).
G = Grid(ni=1440, nj=721, lat0=90.0, lon0=-180.0, dlat=-0.25, dlon=0.25)


@pytest.mark.parametrize("lat, lon, row, col", [
    (90.0, -180.0, 0, 0),          # first value in the file: north pole, antimeridian
    (90.0, 180.0, 0, 0),           # +180 is the same meridian as -180
    (-90.0, 179.75, 720, 1439),    # last value in the file
    (0.0, 0.0, 360, 720),          # equator / Greenwich is mid-row, NOT column 0
    (51.5, 0.0, 154, 720),
    (-41.25, 174.75, 525, 1419),
    (24.75, 67.0, 261, 988),
    (-0.25, -78.5, 361, 406),
    (0.0, 360.0, 360, 720),        # longitudes given in 0..360 work too
    (0.0, 190.0, 360, 40),         # 190E == -170
])
def test_index_of_known_points(lat, lon, row, col):
    assert G.index_of(lat, lon) == (row, col)


def test_longitude_just_west_of_antimeridian_wraps_to_column_zero():
    # 179.9 is 0.1 from the 180 column and 0.15 from the 179.75 column.
    assert G.index_of(0.0, 179.9) == (360, 0)
    assert G.index_of(0.0, 179.8) == (360, 1439)


def test_nearest_rounding():
    assert G.index_of(24.86, 67.01) == (261, 988)   # -> 24.75 N, 67.00 E
    assert G.index_of(51.5, -0.12) == (154, 720)    # -0.12 is nearer 0.0 than -0.25
    assert G.index_of(51.5, -0.13) == (154, 719)


def test_center_of_is_inverse_of_index_of():
    for row, col in [(0, 0), (720, 1439), (360, 720), (525, 1419), (1, 1)]:
        lat, lon = G.center_of(row, col)
        assert -180.0 <= lon < 180.0
        assert G.index_of(lat, lon) == (row, col)
    assert G.center_of(0, 0) == (90.0, -180.0)
    assert G.center_of(360, 720) == (0.0, 0.0)
    assert G.center_of(720, 1439) == (-90.0, 179.75)


def test_flat_index_is_row_major():
    assert G.flat_index(0, 0) == 0
    assert G.flat_index(0, 720) == 720
    assert G.flat_index(1, 0) == 1440
    assert G.flat_index(525, 1419) == 757419   # value ecCodes' own nearest lookup returned
    assert G.flat_index(720, 1439) == 1440 * 721 - 1


def test_out_of_range():
    with pytest.raises(ValueError):
        G.index_of(90.5, 0)
    with pytest.raises(IndexError):
        G.center_of(721, 0)


def test_image_bounds_are_cell_edges():
    b = G.image_bounds()
    assert b == {"north": 90.125, "south": -90.125, "west": -180.125, "east": 179.875}
    assert b["east"] - b["west"] == 360.0


def test_normalise_lon():
    assert normalise_lon(180.0) == -180.0
    assert normalise_lon(-180.0) == -180.0
    assert normalise_lon(359.75) == -0.25
    assert normalise_lon(0.0) == 0.0


KEYS = {"gridType": "regular_ll", "Ni": 1440, "Nj": 721, "iScansNegatively": 0,
        "jScansPositively": 0, "jPointsAreConsecutive": 0,
        "latitudeOfFirstGridPointInDegrees": 90.0, "longitudeOfFirstGridPointInDegrees": 180.0,
        "latitudeOfLastGridPointInDegrees": -90.0, "longitudeOfLastGridPointInDegrees": 179.75,
        "iDirectionIncrementInDegrees": 0.25, "jDirectionIncrementInDegrees": 0.25}


def test_grid_from_keys_matches_expected_layout():
    assert grid_from_keys(KEYS) == G


@pytest.mark.parametrize("override", [
    {"gridType": "reduced_gg"},
    {"jScansPositively": 1},          # south -> north would silently flip the map
    {"iScansNegatively": 1},
    {"jPointsAreConsecutive": 1},
    {"Nj": 720},
    {"longitudeOfLastGridPointInDegrees": 179.5},
])
def test_grid_from_keys_rejects_untested_layouts(override):
    with pytest.raises(ValueError):
        grid_from_keys({**KEYS, **override})
