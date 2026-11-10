"""Point time series for a static site: the same codes as the map rasters, re-cut by place.

The grid is split into square tiles of TILE x TILE cells. One PNG per tile holds every
interval for those cells, so a click costs one small download (measured on a real run:
~30 KB on average, ~90 KB worst case, ~31 MB for all 1035 tiles) instead of 84 rasters.

Layout "frames-stacked": the image is TILE wide and n_intervals * TILE high. Interval k
occupies rows k*TILE .. (k+1)*TILE-1, so

    pixel(x, k*TILE + y) = code of interval k at grid (row = ty*TILE + y, col = tx*TILE + x)

Cells past the grid edge (the last tile row is only partly filled) are 0.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .encode import codes_to_png, png_to_codes

TILE = 32
LAYOUT = "frames-stacked"


def tile_counts(nj: int, ni: int, tile: int = TILE) -> tuple[int, int]:
    return -(-nj // tile), -(-ni // tile)


def tile_name(ty: int, tx: int) -> str:
    return f"{ty}_{tx}.png"


def address(row: int, col: int, tile: int = TILE) -> tuple[int, int, int, int]:
    """(ty, tx, y, x): which tile a grid cell is in and where inside each frame."""
    return row // tile, col // tile, row % tile, col % tile


def tile_image(stack: np.ndarray, ty: int, tx: int, tile: int = TILE) -> np.ndarray:
    """uint16 image for one tile from a (n_intervals, nj, ni) stack of codes."""
    n = stack.shape[0]
    block = np.zeros((n, tile, tile), dtype=np.uint16)
    src = stack[:, ty * tile:(ty + 1) * tile, tx * tile:(tx + 1) * tile]
    block[:, :src.shape[1], :src.shape[2]] = src
    return block.reshape(n * tile, tile)


def cell_series(image: np.ndarray, y: int, x: int, tile: int = TILE) -> np.ndarray:
    """Codes of one cell across all intervals, read back from a tile image."""
    return image[y::tile, x]


def write_tiles(out_dir: Path, stack: np.ndarray, tile: int = TILE) -> dict:
    """Write every tile; return the description that goes into the manifest."""
    if stack.dtype != np.uint16 or stack.ndim != 3:
        raise ValueError("expected a (n_intervals, nj, ni) uint16 stack")
    out_dir.mkdir(parents=True, exist_ok=True)
    tiles_y, tiles_x = tile_counts(stack.shape[1], stack.shape[2], tile)
    total = 0
    largest = 0
    for ty in range(tiles_y):
        for tx in range(tiles_x):
            png = codes_to_png(tile_image(stack, ty, tx, tile))
            (out_dir / tile_name(ty, tx)).write_bytes(png)
            total += len(png)
            largest = max(largest, len(png))
    return {"layout": LAYOUT, "tile": tile, "tiles_y": tiles_y, "tiles_x": tiles_x,
            "intervals": int(stack.shape[0]), "total_bytes": total, "largest_bytes": largest}


def read_cell(out_dir: Path, row: int, col: int, tile: int = TILE) -> np.ndarray:
    ty, tx, y, x = address(row, col, tile)
    return cell_series(png_to_codes((out_dir / tile_name(ty, tx)).read_bytes()), y, x, tile)
