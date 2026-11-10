"""Lossless raster encoding for the browser: a 16-bit integer in the R and G channels of a PNG.

value = offset + scale * (R * 256 + G).  B is 0 and alpha is absent (opaque), so the
browser cannot alter the numbers through alpha premultiplication.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image

U16_MAX = 65535


def quantise(values: np.ndarray, scale: float, offset: float = 0.0) -> tuple[np.ndarray, int]:
    """Round to the nearest integer code. Returns (uint16 codes, number of clipped points)."""
    if not np.all(np.isfinite(values)):
        raise ValueError("non-finite values cannot be encoded")
    codes = np.rint((np.asarray(values, dtype=np.float64) - offset) / scale)
    clipped = int(((codes < 0) | (codes > U16_MAX)).sum())
    return np.clip(codes, 0, U16_MAX).astype(np.uint16), clipped


def dequantise(codes: np.ndarray, scale: float, offset: float = 0.0) -> np.ndarray:
    return offset + scale * codes.astype(np.float64)


def codes_to_png(codes: np.ndarray) -> bytes:
    if codes.dtype != np.uint16 or codes.ndim != 2:
        raise ValueError("expected a 2-D uint16 array")
    rgb = np.zeros(codes.shape + (3,), dtype=np.uint8)
    rgb[..., 0] = codes >> 8
    rgb[..., 1] = codes & 0xFF
    buf = io.BytesIO()
    # compress_level=6 measured smaller AND ~10x faster than optimize=True on a real field.
    Image.fromarray(rgb).save(buf, format="PNG", compress_level=6)
    return buf.getvalue()


def png_to_codes(png: bytes) -> np.ndarray:
    rgb = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.uint16)
    return (rgb[..., 0] << 8) | rgb[..., 1]
