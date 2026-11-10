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

/**
 * The number the colour scale is applied to. Layers whose display says "per_hour" store an
 * amount per interval and are coloured by the mean rate, so 3 h and 6 h intervals share one
 * scale; anything else is shown as stored.
 */
export function displayValue(layer, stored, hours) {
  return layer.display && layer.display.normalise === 'per_hour' ? stored / hours : stored;
}

/**
 * code -> packed RGBA (little-endian) lookup table for one interval length.
 * A stored value at or below `hideAtOrBelow` is transparent whatever its class.
 */
export function buildLut(layer, hours, hideAtOrBelow = -Infinity) {
  const lut = new Uint32Array(65536);
  const stops = layer.legend.stops;
  const packed = stops.map((s) => {
    const n = parseInt(s.color.slice(1), 16);
    return ((255 << 24) | ((n & 255) << 16) | (n & 0xff00) | (n >> 16)) >>> 0;
  });
  for (let code = 0; code < 65536; code++) {
    const stored = decodeValue(layer.encoding, code);
    if (stored <= hideAtOrBelow) continue;
    const k = legendClass(stops, displayValue(layer, stored, hours));
    if (k >= 0) lut[code] = packed[k];
  }
  return lut;
}

/** Hours (possibly fractional) between two ISO instants. */
export function hoursBetween(isoA, isoB) {
  return (Date.parse(isoB) - Date.parse(isoA)) / 3600000;
}
