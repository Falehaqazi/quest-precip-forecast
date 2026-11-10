"""Regular lat/lon grid geometry. Single source of truth for (lat, lon) <-> (row, col).

Verified layout of ECMWF open data 0.25 degree fields (2026-11-10):
  row 0 is +90, last row is -90; column 0 is longitude 180 (== -180), increasing
  eastward; values are stored row-major (scanning mode 0).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Grid:
    ni: int      # points along a parallel (columns)
    nj: int      # points along a meridian (rows)
    lat0: float  # latitude of row 0, degrees north
    lon0: float  # longitude of column 0, degrees east, normalised to [-180, 180)
    dlat: float  # latitude step per row (negative: north -> south)
    dlon: float  # longitude step per column (positive: west -> east)

    @property
    def is_global_in_lon(self) -> bool:
        return abs(self.ni * self.dlon - 360.0) < 1e-9

    def index_of(self, lat: float, lon: float) -> tuple[int, int]:
        """Nearest (row, col) to a point. Longitude wraps; latitude must be in range."""
        if not -90.0 <= lat <= 90.0:
            raise ValueError(f"latitude out of range: {lat}")
        row = round((lat - self.lat0) / self.dlat)
        row = min(max(row, 0), self.nj - 1)
        col = round(((lon - self.lon0) % 360.0) / self.dlon)
        if self.is_global_in_lon:
            col %= self.ni  # e.g. lon 179.9 is nearest to the 180/-180 column
        elif not 0 <= col < self.ni:
            raise ValueError(f"longitude outside grid: {lon}")
        return row, col

    def center_of(self, row: int, col: int) -> tuple[float, float]:
        """(lat, lon) of a grid point, lon in [-180, 180)."""
        if not (0 <= row < self.nj and 0 <= col < self.ni):
            raise IndexError(f"({row}, {col}) outside {self.nj}x{self.ni} grid")
        lat = self.lat0 + row * self.dlat
        lon = normalise_lon(self.lon0 + col * self.dlon)
        return lat, lon

    def flat_index(self, row: int, col: int) -> int:
        return row * self.ni + col

    def image_bounds(self) -> dict[str, float]:
        """Outer edges of the raster when each grid point is drawn as a cell centred on it.

        Note the rows at +/-90 extend half a cell past the pole; that is a drawing
        convention, not data.
        """
        half_lat, half_lon = abs(self.dlat) / 2, abs(self.dlon) / 2
        lat_last = self.lat0 + (self.nj - 1) * self.dlat
        return {
            "north": max(self.lat0, lat_last) + half_lat,
            "south": min(self.lat0, lat_last) - half_lat,
            "west": self.lon0 - half_lon,
            "east": self.lon0 + (self.ni - 1) * self.dlon + half_lon,
        }

    def to_dict(self) -> dict:
        return asdict(self)


def normalise_lon(lon: float) -> float:
    """Map any longitude to [-180, 180)."""
    return (lon + 180.0) % 360.0 - 180.0


def grid_from_keys(k: dict) -> Grid:
    """Build a Grid from ecCodes keys, refusing layouts this code was not tested on."""
    if k["gridType"] != "regular_ll":
        raise ValueError(f"unsupported gridType {k['gridType']!r}")
    if k["iScansNegatively"] != 0 or k["jScansPositively"] != 0 or k["jPointsAreConsecutive"] != 0:
        raise ValueError("unsupported scanning mode (expected W->E, N->S, row-major)")
    ni, nj = int(k["Ni"]), int(k["Nj"])
    lat0 = float(k["latitudeOfFirstGridPointInDegrees"])
    lat1 = float(k["latitudeOfLastGridPointInDegrees"])
    dlon = float(k["iDirectionIncrementInDegrees"])
    dlat = float(k["jDirectionIncrementInDegrees"])
    if not abs((lat0 - lat1) - (nj - 1) * dlat) < 1e-6:
        raise ValueError("latitude range inconsistent with Nj and increment")
    lon0 = float(k["longitudeOfFirstGridPointInDegrees"])
    lon1 = float(k["longitudeOfLastGridPointInDegrees"])
    if not abs(((lon1 - lon0) % 360.0) - (ni - 1) * dlon) < 1e-6:
        raise ValueError("longitude range inconsistent with Ni and increment")
    return Grid(ni=ni, nj=nj, lat0=lat0, lon0=normalise_lon(lon0), dlat=-dlat, dlon=dlon)
