from pathlib import Path

import numpy as np
import pytest

from pipeline.encode import png_to_codes, quantise
from pipeline.gribio import decode
from pipeline.process import deaccumulate, metres_to_mm
from pipeline.series import TILE, address, cell_series, read_cell, tile_counts, tile_image, tile_name, write_tiles

FIX = Path(__file__).parent / "fixtures"


def test_tile_counts_cover_the_real_grid():
    assert tile_counts(721, 1440) == (23, 45)        # 22 full tile rows + one of 17 rows
    assert 23 * TILE >= 721 and 22 * TILE < 721
    assert 45 * TILE == 1440


@pytest.mark.parametrize("row, col, expected", [
    (0, 0, (0, 0, 0, 0)),
    (31, 31, (0, 0, 31, 31)),
    (32, 32, (1, 1, 0, 0)),
    (525, 1419, (16, 44, 13, 11)),     # the Wellington cell used elsewhere in the tests
    (720, 1439, (22, 44, 16, 31)),     # last grid cell sits in the partly filled bottom tile row
])
def test_address(row, col, expected):
    assert address(row, col) == expected


def test_every_cell_round_trips_through_a_tile_image():
    rng = np.random.default_rng(3)
    n, nj, ni = 5, 70, 100                      # not multiples of the tile size on purpose
    stack = rng.integers(0, 65536, size=(n, nj, ni), dtype=np.uint16)
    tiles_y, tiles_x = tile_counts(nj, ni)
    assert (tiles_y, tiles_x) == (3, 4)
    for row in range(nj):
        for col in range(0, ni, 7):
            ty, tx, y, x = address(row, col)
            img = tile_image(stack, ty, tx)
            assert img.shape == (n * TILE, TILE)
            np.testing.assert_array_equal(cell_series(img, y, x), stack[:, row, col])


def test_cells_past_the_grid_edge_are_zero():
    stack = np.full((2, 40, 40), 7, dtype=np.uint16)
    img = tile_image(stack, 1, 1)               # covers rows/cols 32..63, only 32..39 exist
    assert cell_series(img, 7, 7).tolist() == [7, 7]
    assert cell_series(img, 8, 0).tolist() == [0, 0]
    assert cell_series(img, 0, 8).tolist() == [0, 0]


def test_written_tiles_agree_with_the_map_rasters_on_real_data(tmp_path):
    """The chart and the map must show the same number for the same cell and interval."""
    fields = {s: decode((FIX / f"tp-{s}h.grib2").read_bytes()) for s in (0, 3, 6)}
    intervals = deaccumulate({s: metres_to_mm(f.values) for s, f in fields.items()})
    stack = np.stack([quantise(iv.values, 0.05)[0] for iv in intervals])
    info = write_tiles(tmp_path, stack)
    assert (info["tiles_y"], info["tiles_x"], info["intervals"], info["tile"]) == (23, 45, 2, 32)
    assert len(list(tmp_path.glob("*.png"))) == 23 * 45
    assert info["total_bytes"] == sum(p.stat().st_size for p in tmp_path.glob("*.png"))

    # Wellington cell: 0-3 h and 3-6 h, the values checked against Open-Meteo (4.2 and 7.8 mm)
    series = read_cell(tmp_path, 525, 1419)
    assert (series * 0.05).tolist() == pytest.approx([4.25, 7.80])
    # corners, the antimeridian column, Greenwich, and the partly filled bottom tile row
    for row, col in [(0, 0), (0, 1439), (720, 0), (720, 1439), (360, 720), (704, 31), (355, 1135)]:
        np.testing.assert_array_equal(read_cell(tmp_path, row, col), stack[:, row, col])
    # a whole tile, pixel for pixel
    img = png_to_codes((tmp_path / tile_name(16, 44)).read_bytes())
    np.testing.assert_array_equal(img[:32, :], stack[0, 512:544, 1408:1440])
    np.testing.assert_array_equal(img[32:64, :], stack[1, 512:544, 1408:1440])


def test_write_tiles_rejects_wrong_input(tmp_path):
    with pytest.raises(ValueError):
        write_tiles(tmp_path, np.zeros((2, 4, 4), dtype=np.float64))
    with pytest.raises(ValueError):
        write_tiles(tmp_path, np.zeros((4, 4), dtype=np.uint16))
