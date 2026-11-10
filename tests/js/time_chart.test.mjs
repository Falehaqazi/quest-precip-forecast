import test from 'node:test';
import assert from 'node:assert/strict';
import { SECOND_ZONE, formatRange, rangeUtc, rangeSecond, shortDay, dayTime } from '../../web/time.js';
import { niceMax, layoutBars, intervalAt, utcDayStarts } from '../../web/chart.js';

test('the second zone is IST, UTC+05:30 with no daylight saving', () => {
  assert.deepEqual(SECOND_ZONE, { id: 'Asia/Kolkata', label: 'IST' });
  const iv = { start_utc: '2026-11-10T00:00:00Z', end_utc: '2026-11-10T03:00:00Z' };
  assert.equal(rangeUtc(iv), 'Tue 10 Nov 00:00 – 03:00 UTC');
  assert.equal(rangeSecond(iv), 'Tue 10 Nov 05:30 – 08:30 IST');
  // same offset in northern summer: India has no DST
  assert.equal(dayTime('2026-06-21T12:00:00Z', 'Asia/Kolkata'), 'Sun 21 Jun 17:30');
});

test('IST rolls over to the next day 5.5 h before UTC does', () => {
  const iv = { start_utc: '2026-11-10T18:00:00Z', end_utc: '2026-11-10T21:00:00Z' };
  assert.equal(rangeUtc(iv), 'Tue 10 Nov 18:00 – 21:00 UTC');
  assert.equal(rangeSecond(iv), 'Tue 10 Nov 23:30 – Wed 11 Nov 02:30 IST');
  // an interval ending exactly at UTC midnight shows the end date in UTC but not in IST
  const iv2 = { start_utc: '2026-11-15T21:00:00Z', end_utc: '2026-11-16T00:00:00Z' };
  assert.equal(rangeUtc(iv2), 'Sun 15 Nov 21:00 – Mon 16 Nov 00:00 UTC');
  assert.equal(rangeSecond(iv2), 'Mon 16 Nov 02:30 – 05:30 IST');
});

test('formatting does not depend on the machine time zone and crosses the year', () => {
  assert.equal(formatRange('2026-12-31T21:00:00Z', '2027-01-01T03:00:00Z', 'UTC'), 'Thu 31 Dec 21:00 – Fri 1 Jan 03:00');
  assert.equal(shortDay('2026-11-12T00:00:00Z'), '12 Nov');
  assert.equal(shortDay('2026-11-11T20:00:00Z', 'Asia/Kolkata'), '12 Nov');
});

test('niceMax', () => {
  assert.equal(niceMax(0), 0.5);
  assert.equal(niceMax(0.5), 0.5);
  assert.equal(niceMax(0.51), 1);
  assert.equal(niceMax(3.2), 5);
  assert.equal(niceMax(49.4), 50);
  assert.equal(niceMax(250), 300);
});

// the real step pattern: 3-hourly to 144 h, then 6-hourly to 360 h
const steps = [...Array(49).keys()].map((i) => i * 3).concat([...Array(36).keys()].map((i) => 150 + i * 6));
const intervals = steps.slice(1).map((end, i) => ({ start_step: steps[i], end_step: end }));

test('bars: width follows duration, bars tile the axis exactly, height follows the value', () => {
  const box = { left: 30, right: 390, top: 8, bottom: 148 };
  const values = intervals.map((_, i) => (i === 10 ? 2 : i === 60 ? 1 : 0));
  const bars = layoutBars(intervals, values, box, 2);
  assert.equal(bars.length, 84);
  assert.equal(bars[0].x, 30);
  assert.ok(Math.abs(bars[83].x + bars[83].full - 390) < 1e-9);
  assert.ok(Math.abs(bars[0].full - 3) < 1e-9);  // 360 px for 360 h: 1 px per hour
  assert.ok(Math.abs(bars[60].full - 6) < 1e-9); // a 6 h interval is twice as wide
  for (let i = 1; i < bars.length; i++) assert.ok(Math.abs(bars[i].x - (bars[i - 1].x + bars[i - 1].full)) < 1e-9);
  assert.equal(bars[10].h, 140);
  assert.equal(bars[10].y, 8);                   // value == yMax fills the plot
  assert.equal(bars[60].h, 70);
  assert.equal(bars[0].h, 0);
  // equal mean rate -> equal height, and the 6 h bar has twice the area (twice the amount)
  const same = layoutBars(intervals, intervals.map(() => 1), box, 2);
  assert.equal(same[5].h, same[70].h);
  assert.ok(Math.abs(same[70].full * same[70].h - 2 * same[5].full * same[5].h) < 1e-6);
  // values above the axis maximum are clipped to the plot, never drawn outside it
  assert.equal(layoutBars(intervals, intervals.map(() => 9), box, 2)[0].y, 8);
});

test('intervalAt maps a pixel to the interval under it', () => {
  const box = { left: 30, right: 390, top: 8, bottom: 148 };
  const bars = layoutBars(intervals, intervals.map(() => 0), box, 1);
  assert.equal(intervalAt(bars, 0), 0);
  assert.equal(intervalAt(bars, 30), 0);
  assert.equal(intervalAt(bars, 32.9), 0);
  assert.equal(intervalAt(bars, 33.1), 1);
  assert.equal(intervalAt(bars, 30 + 143.9), 47); // +141..144 h
  assert.equal(intervalAt(bars, 30 + 144.1), 48); // +144..150 h
  assert.equal(intervalAt(bars, 30 + 149.9), 48);
  assert.equal(intervalAt(bars, 30 + 150.1), 49);
  assert.equal(intervalAt(bars, 5000), 83);
});

test('utcDayStarts: midnights in UTC for 00z and 12z runs', () => {
  const a = utcDayStarts('2026-11-10T00:00:00Z', 360);
  assert.equal(a.length, 16);
  assert.deepEqual(a[0], { hours: 0, iso: '2026-11-10T00:00:00.000Z' });
  assert.deepEqual(a[15], { hours: 360, iso: '2026-11-25T00:00:00.000Z' });
  const b = utcDayStarts('2026-11-10T12:00:00Z', 360);
  assert.equal(b.length, 15);
  assert.deepEqual(b[0], { hours: 12, iso: '2026-11-11T00:00:00.000Z' });
  assert.equal(b[14].hours, 348);
});
