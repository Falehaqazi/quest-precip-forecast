// Point time series tiles: must agree with pipeline/series.py (tests/test_series.py).
import test from 'node:test';
import assert from 'node:assert/strict';
import { seriesAddress, extractSeries } from '../../web/grid.js';

const series = { tile: 32, intervals: 84, path: 'tp_interval/series/{ty}_{tx}.png' };

test('seriesAddress gives the same tile and offsets as the pipeline', () => {
  const cases = [
    [0, 0, 0, 0, 0, 0], [31, 31, 0, 0, 31, 31], [32, 32, 1, 1, 0, 0],
    [525, 1419, 16, 44, 13, 11], [720, 1439, 22, 44, 16, 31],
  ];
  for (const [row, col, ty, tx, y, x] of cases) {
    assert.deepEqual(seriesAddress(series, row, col), { ty, tx, y, x, file: `tp_interval/series/${ty}_${tx}.png` });
  }
});

test('extractSeries reads interval k from frame k of a frames-stacked tile', () => {
  const s = { tile: 4, intervals: 3 };
  const rgba = new Uint8ClampedArray(4 * 4 * 3 * 4);
  const put = (k, y, x, code) => {
    const j = ((k * 4 + y) * 4 + x) * 4;
    rgba[j] = code >> 8; rgba[j + 1] = code & 255; rgba[j + 3] = 255;
  };
  put(0, 2, 1, 85); put(1, 2, 1, 156); put(2, 2, 1, 0x1234);
  put(1, 2, 2, 999); put(1, 3, 1, 999); put(0, 0, 0, 7); // neighbours must not leak in
  assert.deepEqual(Array.from(extractSeries(rgba, s, 2, 1)), [85, 156, 0x1234]);
  assert.deepEqual(Array.from(extractSeries(rgba, s, 0, 0)), [7, 0, 0]);
  assert.throws(() => extractSeries(rgba.subarray(4), s, 0, 0));
});

test('layers that share a tile file read their own frames (frame_offset)', () => {
  // 2 thresholds x 3 windows in one file, as the ensemble layers do: frame = threshold*3 + window
  const t = 4, frames = 6;
  const rgba = new Uint8ClampedArray(t * t * frames * 4);
  for (let k = 0; k < frames; k++) {
    const j = ((k * t + 1) * t + 2) * 4;         // cell y=1, x=2 in every frame
    rgba[j + 1] = 10 + k;                         // codes 10..15
  }
  const first = { tile: t, intervals: 3, frames, frame_offset: 0 };
  const second = { tile: t, intervals: 3, frames, frame_offset: 3 };
  assert.deepEqual(Array.from(extractSeries(rgba, first, 1, 2)), [10, 11, 12]);
  assert.deepEqual(Array.from(extractSeries(rgba, second, 1, 2)), [13, 14, 15]);
  assert.throws(() => extractSeries(rgba, { tile: t, intervals: 3, frames, frame_offset: 4 }, 1, 2));
  assert.throws(() => extractSeries(rgba, { tile: t, intervals: 3 }, 1, 2)); // file holds 6 frames, not 3
});
