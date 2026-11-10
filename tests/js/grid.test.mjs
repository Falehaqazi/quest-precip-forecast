// Run with: node --test tests/js
// Same known points as tests/test_grid.py, so the browser and the pipeline agree.
import test from 'node:test';
import assert from 'node:assert/strict';
import { indexOf, centerOf, cellBounds, normaliseLon, rgbaToCodes, decodeValue, legendClass } from '../../web/grid.js';

const grid = {
  ni: 1440, nj: 721, lat0: 90, lon0: -180, dlat: -0.25, dlon: 0.25,
  bounds: { north: 90.125, south: -90.125, west: -180.125, east: 179.875 },
};

test('indexOf matches the points verified against ecCodes', () => {
  const cases = [
    [90, -180, 0, 0], [90, 180, 0, 0], [-90, 179.75, 720, 1439], [0, 0, 360, 720],
    [51.5, 0, 154, 720], [-41.25, 174.75, 525, 1419], [24.75, 67, 261, 988],
    [-0.25, -78.5, 361, 406], [24.86, 67.01, 261, 988], [51.5, -0.12, 154, 720],
    [0, 190, 360, 40],
  ];
  for (const [lat, lon, row, col] of cases) {
    assert.deepEqual(indexOf(grid, lat, lon), { row, col }, `${lat},${lon}`);
  }
});

test('longitude wraps at the antimeridian, including the half cell west of -180', () => {
  assert.deepEqual(indexOf(grid, 0, 179.9), { row: 360, col: 0 });
  assert.deepEqual(indexOf(grid, 0, 179.8), { row: 360, col: 1439 });
  assert.deepEqual(indexOf(grid, 0, -180.1), { row: 360, col: 0 });   // left edge of the drawn image
  assert.deepEqual(indexOf(grid, 0, 179.874), { row: 360, col: 1439 }); // right edge of the drawn image
});

test('points outside the drawn raster return null; the polar half-cells clamp', () => {
  assert.equal(indexOf(grid, 95, 0), null);
  assert.equal(indexOf(grid, -95, 0), null);
  assert.deepEqual(indexOf(grid, 90.1, 0), { row: 0, col: 720 });
  assert.deepEqual(indexOf(grid, -90.1, 0), { row: 720, col: 720 });
});

test('centerOf and cellBounds', () => {
  assert.deepEqual(centerOf(grid, 0, 0), { lat: 90, lon: -180 });
  assert.deepEqual(centerOf(grid, 360, 720), { lat: 0, lon: 0 });
  assert.deepEqual(centerOf(grid, 720, 1439), { lat: -90, lon: 179.75 });
  assert.deepEqual(cellBounds(grid, 360, 720), [[-0.125, -0.125], [0.125, 0.125]]);
  assert.deepEqual(cellBounds(grid, 0, 0), [[89.875, -180.125], [90.125, -179.875]]);
});

test('normaliseLon', () => {
  assert.equal(normaliseLon(180), -180);
  assert.equal(normaliseLon(359.75), -0.25);
  assert.equal(normaliseLon(-190), 170);
});

test('codes: R is the high byte, G the low byte; B and A are ignored', () => {
  const rgba = Uint8ClampedArray.from([0x12, 0x34, 0, 255, 0, 0xff, 99, 255]);
  assert.deepEqual(Array.from(rgbaToCodes(rgba, 2)), [0x1234, 0x00ff]);
  const enc = { scale: 0.05, offset: 0 };
  assert.ok(Math.abs(decodeValue(enc, 156) - 7.8) < 1e-9);
  assert.equal(decodeValue(enc, 0), 0);
});

test('legend classes use lower bounds; below the first stop is transparent', () => {
  const stops = [{ from: 0.1 }, { from: 0.5 }, { from: 1 }, { from: 2 }];
  assert.equal(legendClass(stops, 0), -1);
  assert.equal(legendClass(stops, 0.05), -1);
  assert.equal(legendClass(stops, 0.1), 0);          // 2 * 0.05 in floating point still counts
  assert.equal(legendClass(stops, decodeValue({ scale: 0.05, offset: 0 }, 2)), 0);
  assert.equal(legendClass(stops, 0.45), 0);
  assert.equal(legendClass(stops, 0.5), 1);
  assert.equal(legendClass(stops, 1.95), 2);
  assert.equal(legendClass(stops, 500), 3);
});
