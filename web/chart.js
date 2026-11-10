// Point time series chart: one bar per forecast interval. Height is the mean rate (mm/h),
// width is the duration of the interval, so the area of a bar is the amount that fell in it.
// The geometry functions are pure and tested in tests/js; render() touches the DOM.

const NICE = [0.5, 1, 2, 5, 10, 20, 50, 100, 200];

/** Smallest "nice" axis maximum that is >= v (never below 0.5, so a dry cell still has an axis). */
export function niceMax(v) {
  for (const n of NICE) if (v <= n + 1e-9) return n;
  return Math.ceil(v / 100) * 100;
}

/**
 * Pixel rectangles for the bars. `intervals` have start_step/end_step in hours from the run
 * start; time maps linearly onto [box.left, box.right], so a 6 h bar is twice as wide as a 3 h one.
 */
export function layoutBars(intervals, values, box, yMax, gap = 1) {
  const t0 = intervals[0].start_step, t1 = intervals[intervals.length - 1].end_step;
  const sx = (box.right - box.left) / (t1 - t0);
  const sy = (box.bottom - box.top) / yMax;
  return intervals.map((iv, i) => {
    const x = box.left + (iv.start_step - t0) * sx;
    const full = (iv.end_step - iv.start_step) * sx;
    const h = Math.min(values[i], yMax) * sy;
    return { x, full, w: Math.max(full - gap, 1), y: box.bottom - h, h };
  });
}

/** Index of the interval whose time span contains pixel x (clamped to the first/last). */
export function intervalAt(bars, x) {
  if (x <= bars[0].x) return 0;
  for (let i = 0; i < bars.length; i++) if (x < bars[i].x + bars[i].full) return i;
  return bars.length - 1;
}

/** Hours from the run start at which a new UTC day begins, within the run. */
export function utcDayStarts(referenceIso, lastStep) {
  const ref = Date.parse(referenceIso);
  const out = [];
  const firstMidnight = Math.ceil(ref / 86400000) * 86400000;
  for (let t = firstMidnight; t <= ref + lastStep * 3600000; t += 86400000) {
    out.push({ hours: (t - ref) / 3600000, iso: new Date(t).toISOString() });
  }
  return out;
}

const SVG = 'http://www.w3.org/2000/svg';
const el = (name, attrs = {}, text) => {
  const e = document.createElementNS(SVG, name);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
};

/**
 * Draw the chart into `svg`.
 * model = { intervals, rates, faint: bool[], current, referenceIso, dayLabel(iso), onPick(i), onHover(i|null),
 *           yMax? }  (yMax fixes the axis, e.g. 100 for percentages; otherwise it fits the data)
 */
export function render(svg, model) {
  const width = Math.max(svg.clientWidth || 300, 220), height = 170;
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.replaceChildren();
  const box = { left: 30, right: width - 6, top: 8, bottom: height - 22 };
  const yMax = model.yMax ?? niceMax(Math.max(...model.rates));
  const bars = layoutBars(model.intervals, model.rates, box, yMax);
  const t0 = model.intervals[0].start_step, t1 = model.intervals[model.intervals.length - 1].end_step;
  const xOf = (hours) => box.left + (hours - t0) * (box.right - box.left) / (t1 - t0);

  // y grid and labels: 0, half, max
  for (const v of [0, yMax / 2, yMax]) {
    const y = box.bottom - (v / yMax) * (box.bottom - box.top);
    svg.append(el('line', { x1: box.left, x2: box.right, y1: y, y2: y, class: v === 0 ? 'axis' : 'grid' }));
    svg.append(el('text', { x: box.left - 5, y: y + 3.5, class: 'tick', 'text-anchor': 'end' }, String(v)));
  }
  // x: a tick at each 00:00 UTC, labelled as often as fits
  const days = utcDayStarts(model.referenceIso, t1);
  const perDay = (box.right - box.left) / ((t1 - t0) / 24);
  const every = Math.max(1, Math.ceil(46 / perDay));
  days.forEach((d, i) => {
    const x = xOf(d.hours);
    svg.append(el('line', { x1: x, x2: x, y1: box.bottom, y2: box.bottom + 4, class: 'axis' }));
    if (i % every === 0 && x < box.right - 16) {
      svg.append(el('text', { x, y: box.bottom + 15, class: 'tick', 'text-anchor': x < box.left + 14 ? 'start' : 'middle' }, model.dayLabel(d.iso)));
    }
  });

  // band behind the interval shown on the map, then the bars
  const cur = bars[model.current];
  svg.append(el('rect', { x: cur.x, y: box.top, width: cur.full, height: box.bottom - box.top, class: 'band' }));
  bars.forEach((b, i) => {
    if (b.h <= 0) return;
    const cls = `bar${model.faint[i] ? ' faint' : ''}${i === model.current ? ' current' : ''}`;
    svg.append(el('rect', { x: b.x, y: b.y, width: b.w, height: Math.max(b.h, 1), rx: Math.min(1.5, b.w / 2), class: cls }));
  });

  // one hit area for the whole plot: far easier to tap than 3 px bars
  const hit = el('rect', { x: box.left, y: 0, width: box.right - box.left, height, class: 'hit' });
  const index = (ev) => {
    const r = svg.getBoundingClientRect();
    return intervalAt(bars, (ev.clientX - r.left) * (width / r.width));
  };
  hit.addEventListener('click', (ev) => model.onPick(index(ev)));
  hit.addEventListener('pointermove', (ev) => { if (ev.pointerType === 'mouse') model.onHover(index(ev)); });
  hit.addEventListener('pointerleave', () => model.onHover(null));
  svg.append(hit);
  return { bars, yMax, box };
}
