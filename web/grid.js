// Grid geometry and value decoding for the browser. Mirrors pipeline/grid.py and
// pipeline/encode.py; tests/js/grid.test.mjs checks both sides agree on known points.

/** Map any longitude to [-180, 180). */
export function normaliseLon(lon) {
  return ((((lon + 180) % 360) + 360) % 360) - 180;
}

/** Nearest {row, col} to a point, or null if the latitude is outside the grid's drawn area. */
export function indexOf(grid, lat, lon) {
  if (lat > grid.bounds.north || lat < grid.bounds.south) return null;
  let row = Math.round((lat - grid.lat0) / grid.dlat);
  row = Math.min(Math.max(row, 0), grid.nj - 1);
  const dLon = (((lon - grid.lon0) % 360) + 360) % 360;
  const col = Math.round(dLon / grid.dlon) % grid.ni; // wraps: 179.9 E belongs to the 180/-180 column
  return { row, col };
}

/** {lat, lon} of a grid point, lon in [-180, 180). */
export function centerOf(grid, row, col) {
  return { lat: grid.lat0 + row * grid.dlat, lon: normaliseLon(grid.lon0 + col * grid.dlon) };
}

/** South-west and north-east corners of the cell drawn for a grid point. */
export function cellBounds(grid, row, col) {
  const lat = grid.lat0 + row * grid.dlat;
  const lon = grid.lon0 + col * grid.dlon; // not normalised: stays inside the image bounds
  const hLat = Math.abs(grid.dlat) / 2, hLon = Math.abs(grid.dlon) / 2;
  return [[lat - hLat, lon - hLon], [lat + hLat, lon + hLon]];
}

/** RGBA bytes of a decoded PNG -> Uint16 codes (R is the high byte, G the low byte). */
export function rgbaToCodes(rgba, count) {
  const codes = new Uint16Array(count);
  for (let i = 0, j = 0; i < count; i++, j += 4) codes[i] = (rgba[j] << 8) | rgba[j + 1];
  return codes;
}

export function decodeValue(encoding, code) {
  return encoding.offset + encoding.scale * code;
}

/**
 * Index of the legend class a value falls in, or -1 if below the first stop.
 * Stops are lower bounds, ascending; a value equal to a bound belongs to that class.
 */
export function legendClass(stops, value) {
  let k = -1;
  for (let i = 0; i < stops.length; i++) {
    if (value >= stops[i].from - 1e-9) k = i; else break;
  }
  return k;
}

/** Hours (possibly fractional) between two ISO instants. */
export function hoursBetween(isoA, isoB) {
  return (Date.parse(isoB) - Date.parse(isoA)) / 3600000;
}
