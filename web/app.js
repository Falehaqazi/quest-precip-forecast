import {
  indexOf, centerOf, cellBounds, rgbaToCodes, decodeValue, displayValue, buildLut,
  seriesAddress, extractSeries,
} from './grid.js?v=__BUILD__';
import {
  SECOND_ZONE, rangeUtc, rangeSecond, shortDay, dayTime, timeOnly, indexAtTime, containsTime,
} from './time.js?v=__BUILD__';
import { render as renderChartSvg } from './chart.js?v=__BUILD__';

const DATA_DIR = 'data/';
const STALE_AFTER_HOURS = 24;   // a fresh 00z/12z run is 7-20 h old when viewed (see LIMITATIONS)
const PLAY_INTERVAL_MS = 650;
const CACHE_SIZE = 16;          // decoded intervals kept in memory (~2 MB each)
const TILE_CACHE_SIZE = 8;      // decoded series tiles kept in memory (~0.35 MB each)
const MIN_ZOOM_FLOOR = -4;      // far below any real fit; the working minimum is computed per box size

const $ = (id) => document.getElementById(id);
const state = {
  manifest: null, layers: [], layer: null, index: 0, codes: null, luts: new Map(),
  cache: new Map(), selected: null, playing: false, renderToken: 0, blobUrl: null,
  series: null, seriesToken: 0, tiles: new Map(), hoverIndex: null,
};
let map, overlay, selectionRect, selectionRing;

// ---------- formatting ----------

function formatValue(v, units) {
  const digits = v < 10 ? 2 : 1;
  return `${v.toFixed(digits)} ${units}`;
}
function formatLatLon({ lat, lon }) {
  const ns = lat >= 0 ? 'N' : 'S', ew = lon >= 0 ? 'E' : 'W';
  return `${Math.abs(lat).toFixed(2)}° ${ns}, ${Math.abs(lon).toFixed(2)}° ${ew}`;
}

// ---------- data ----------

async function loadManifest() {
  const res = await fetch(`${DATA_DIR}manifest.json`, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`manifest.json: HTTP ${res.status}`);
  const m = await res.json();
  if (m.schema !== 3) throw new Error(`unsupported manifest schema ${m.schema}`);
  return m;
}

/** Fetch a data PNG and return its RGBA bytes, untouched by colour management. */
async function fetchRgba(file, width, height) {
  // File names repeat from run to run, so the run time is part of the URL to defeat caches.
  const res = await fetch(`${DATA_DIR}${file}?run=${encodeURIComponent(state.manifest.run.reference_utc)}`);
  if (!res.ok) throw new Error(`${file}: HTTP ${res.status}`);
  // No colour-space conversion and no alpha premultiplication: the bytes are data, not colour.
  const bmp = await createImageBitmap(await res.blob(), { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
  if (bmp.width !== width || bmp.height !== height) {
    throw new Error(`${file} is ${bmp.width}x${bmp.height}, expected ${width}x${height}`);
  }
  const c = document.createElement('canvas');
  c.width = width; c.height = height;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(bmp, 0, 0);
  return ctx.getImageData(0, 0, width, height).data;
}

function remember(cache, key, value, limit) {
  cache.set(key, value);
  if (cache.size > limit) cache.delete(cache.keys().next().value);
  return value;
}

/** One interval raster as Uint16 codes. */
async function loadCodes(i) {
  const key = `${state.layer.id}:${i}`;
  if (state.cache.has(key)) return state.cache.get(key);
  const { grid } = state.manifest;
  const rgba = await fetchRgba(state.layer.intervals[i].file, grid.ni, grid.nj);
  return remember(state.cache, key, rgbaToCodes(rgba, grid.ni * grid.nj), CACHE_SIZE);
}

/** Every interval for one grid cell, as Uint16 codes, from the cell's series tile. */
async function loadSeries(row, col) {
  const s = state.layer.series;
  const addr = seriesAddress(s, row, col);
  let rgba = state.tiles.get(addr.file);
  if (!rgba) rgba = remember(state.tiles, addr.file, await fetchRgba(addr.file, s.tile, s.tile * (s.frames ?? s.intervals)), TILE_CACHE_SIZE);
  return extractSeries(rgba, s, addr.y, addr.x);
}

/** Lookup table for an interval; intervals of the same length share one. */
function lutFor(iv) {
  // A value of one source packing step is not drawn: the true amount could be anything from
  // almost zero up to that step, so which cells show it is noise (DECISIONS D15).
  const hide = (iv.source_quantum || 0) * 1.01;
  const key = `${state.layer.id}|${iv.hours}|${hide}`;
  if (!state.luts.has(key)) state.luts.set(key, buildLut(state.layer, iv.hours, hide));
  return state.luts.get(key);
}

const isProbability = () => state.layer.kind === 'probability';
const displayUnits = () => (state.layer.display ? state.layer.display.units : state.layer.units);
/** Headline number: "0.82 mm/h" for the rate layer, "34 %" for a probability layer. */
function formatDisplay(stored, iv) {
  if (isProbability()) return `${Math.round(stored)} %`;
  return formatValue(displayValue(state.layer, stored, iv.hours), displayUnits());
}
/** What the headline is made of: "4.90 mm in 6 h", or "17 of 50 members". */
function formatAmount(stored, iv) {
  if (isProbability()) return `${Math.round(stored * state.layer.members / 100)} of ${state.layer.members} members`;
  return `${formatValue(stored, state.layer.units)} in ${iv.hours} h`;
}

// ---------- map ----------

function initMap(manifest) {
  const b = manifest.grid.bounds;
  const world = [[b.south, b.west], [b.north, b.east]];
  // zoomSnap 0: the minimum zoom is whatever makes the whole world fit this container,
  // which is not a round number (and is below 0 on a phone).
  map = L.map('map', {
    crs: L.CRS.EPSG4326, zoomSnap: 0, zoomDelta: 0.5, minZoom: MIN_ZOOM_FLOOR, maxZoom: 7,
    attributionControl: false, maxBounds: world, maxBoundsViscosity: 1,
  });
  map.createPane('land').style.zIndex = 200;
  map.createPane('raster').style.zIndex = 300;
  map.createPane('borders').style.zIndex = 350;
  map.getPane('borders').style.pointerEvents = 'none';

  // Fit the whole world and make that the zoom-out limit. Re-run whenever the map box
  // changes size (rotation, side panel opening); keep the user's view unless they were
  // already looking at the whole world.
  const fitWorld = (force) => {
    const wasWorldView = force || map.getZoom() <= map.getMinZoom() + 1e-6;
    map.invalidateSize({ animate: false });
    // getBoundsZoom clamps its answer to the current minZoom, so a box that got smaller
    // (side panel opening, phone rotated to portrait) could never zoom out further. Clear it first.
    map.options.minZoom = MIN_ZOOM_FLOOR;
    const fit = map.getBoundsZoom(world, false);
    map.setMinZoom(fit);
    if (wasWorldView) map.fitBounds(world, { animate: false });
  };
  map.setView([0, 0], 0, { animate: false });
  fitWorld(true);
  new ResizeObserver(() => fitWorld(false)).observe($('map'));

  L.rectangle(world, { pane: 'land', renderer: L.canvas({ pane: 'land' }), interactive: false,
    stroke: false, fillColor: '#f4f6f8', fillOpacity: 1 }).addTo(map); // sea, so the world's edge is visible

  const blank = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==';
  overlay = L.imageOverlay(blank, world, { pane: 'raster', className: 'data-raster', interactive: false }).addTo(map);

  fetch('vendor/geo/countries-50m.json').then((r) => r.json()).then((topo) => {
    L.geoJSON(topojson.feature(topo, topo.objects.land), {
      pane: 'land', renderer: L.canvas({ pane: 'land' }), interactive: false,
      style: { stroke: false, fillColor: '#ecebe6', fillOpacity: 1 },
    }).addTo(map);
    L.geoJSON(splitAtAntimeridian(topojson.mesh(topo, topo.objects.countries)), {
      pane: 'borders', renderer: L.canvas({ pane: 'borders' }), interactive: false,
      style: { color: '#55544f', weight: 0.7, opacity: 0.75, fill: false },
    }).addTo(map);
  }).catch((e) => console.warn('outlines failed to load', e));

  map.on('click', (e) => select(e.latlng));
  map.on('mousemove', (e) => hover(e));
  map.on('mouseout', () => { $('hover').hidden = true; });
}

/**
 * Border lines that jump from one side of the map to the other (Russia, Fiji, Antarctica)
 * would be drawn as a stroke across the whole world; break each line at such jumps.
 */
function splitAtAntimeridian(multiLine) {
  const out = [];
  for (const line of multiLine.coordinates) {
    let part = [line[0]];
    for (let i = 1; i < line.length; i++) {
      if (Math.abs(line[i][0] - line[i - 1][0]) > 180) {
        if (part.length > 1) out.push(part);
        part = [];
      }
      part.push(line[i]);
    }
    if (part.length > 1) out.push(part);
  }
  return { type: 'MultiLineString', coordinates: out };
}

function valueAt(latlng) {
  if (!state.codes) return null;
  const { grid } = state.manifest;
  const cell = indexOf(grid, latlng.lat, latlng.lng);
  if (!cell) return null;
  const value = decodeValue(state.layer.encoding, state.codes[cell.row * grid.ni + cell.col]);
  return { ...cell, value };
}

function hover(e) {
  const hit = valueAt(e.latlng);
  const el = $('hover');
  if (!hit) { el.hidden = true; return; }
  const iv = state.layer.intervals[state.index];
  el.textContent = `${formatDisplay(hit.value, iv)} · ${formatAmount(hit.value, iv)}`;
  el.style.left = `${e.containerPoint.x}px`;
  el.style.top = `${e.containerPoint.y}px`;
  el.hidden = false;
}

function select(latlng) {
  const hit = valueAt(latlng);
  if (hit) selectCell(hit.row, hit.col);
}

function selectCell(row, col) {
  state.selected = { row, col };
  state.series = null;
  state.hoverIndex = null;
  const rect = cellBounds(state.manifest.grid, row, col);
  if (selectionRect) selectionRect.setBounds(rect);
  else selectionRect = L.rectangle(rect, { pane: 'borders', color: '#1f1f1d', weight: 2, fill: false, interactive: false }).addTo(map);
  // The cell outline is a fraction of a pixel when zoomed out, so a ring of fixed screen size
  // marks the place at every zoom: white underneath, dark on top, visible on any colour.
  const c = centerOf(state.manifest.grid, row, col);
  const at = [c.lat, c.lon];
  if (selectionRing) selectionRing.forEach((r) => r.setLatLng(at));
  else {
    selectionRing = [['#ffffff', 5], ['#1f1f1d', 2]].map(([color, weight]) => L.circleMarker(at, {
      pane: 'borders', radius: 8, color, weight, opacity: 1, fill: false, interactive: false }).addTo(map));
  }
  $('readout').hidden = false;
  updatePanel();

  const token = ++state.seriesToken;
  loadSeries(row, col).then((series) => {
    if (token !== state.seriesToken) return; // another cell was selected meanwhile
    state.series = series;
    buildTable();
    updatePanel();
  }).catch((e) => {
    if (token !== state.seriesToken) return;
    console.error(e);
    $('chart-status').textContent = `The time series could not be loaded (${e.message}).`;
  });
}

function deselect() {
  state.selected = null; state.series = null; state.seriesToken++;
  $('readout').hidden = true;
  if (selectionRect) { selectionRect.remove(); selectionRect = null; }
  if (selectionRing) { selectionRing.forEach((r) => r.remove()); selectionRing = null; }
}

// ---------- selected-cell panel: numbers, chart, table ----------

/** Stored amount of the selected cell in interval i, or null while it is not loaded. */
function selectedAmount(i) {
  const { grid } = state.manifest, sel = state.selected, enc = state.layer.encoding;
  if (state.series) return decodeValue(enc, state.series[i]);
  if (i === state.index && state.codes) return decodeValue(enc, state.codes[sel.row * grid.ni + sel.col]);
  return null;
}

function updatePanel() {
  if (!state.selected) return;
  renderDetail();
  renderChart();
}

/** Headline numbers for the interval under the pointer, or else the one shown on the map. */
function renderDetail() {
  const { grid } = state.manifest, sel = state.selected;
  const i = state.hoverIndex ?? state.index;
  const iv = state.layer.intervals[i];
  const amount = selectedAmount(i);
  $('cell-title').textContent = `Grid cell centred on ${formatLatLon(centerOf(grid, sel.row, sel.col))}`;
  const big = $('readout-value');
  big.replaceChildren();
  if (amount === null) big.append('…');
  else big.append(formatDisplay(amount, iv), Object.assign(document.createElement('small'), { textContent: ` · ${formatAmount(amount, iv)}` }));
  $('readout-when').replaceChildren(rangeUtc(iv), document.createElement('br'), rangeSecond(iv));

  const quantum = iv.source_quantum ?? iv.source_quantum_mm;
  const rows = [
    ['Grid index', `row ${sel.row}, col ${sel.col}`],
    ['Source precision', quantum ? `${quantum.toFixed(2)} mm (ECMWF packing step)` : 'n/a'],
  ];
  if (isProbability()) rows.unshift(['Ensemble', `${state.layer.members} perturbed members, raw count, not calibrated`]);
  const dl = $('readout-details');
  dl.replaceChildren();
  for (const [k, v] of rows) {
    dl.append(Object.assign(document.createElement('dt'), { textContent: k }),
      Object.assign(document.createElement('dd'), { textContent: v }));
  }
}

function renderChart() {
  const { layer, manifest, series, selected } = state;
  const svg = $('chart');
  $('chart-title').textContent = `${layer.display ? layer.display.title : layer.title} at this cell, ${displayUnits()} · days in UTC`;
  const prob = isProbability();
  svg.classList.toggle('prob', prob); // bars take the hue of the layer they belong to
  if (!series) {
    svg.replaceChildren();
    $('chart-status').textContent = 'Loading the full forecast for this cell…';
    $('chart-summary').textContent = '';
    $('chart-note').textContent = '';
    return;
  }
  const ivs = layer.intervals;
  const amounts = Array.from(series, (c) => decodeValue(layer.encoding, c));
  const rates = amounts.map((a, i) => displayValue(layer, a, ivs[i].hours));
  const faint = ivs.map((iv, i) => series[i] > 0 && lutFor(iv)[series[i]] === 0);
  renderChartSvg(svg, {
    intervals: ivs, rates, faint, current: state.index, yMax: layer.axis_max,
    referenceIso: manifest.run.reference_utc, dayLabel: (iso) => shortDay(iso, 'UTC'),
    onPick: (i) => { setPlaying(false); state.hoverIndex = null; show(i).catch(fail); },
    onHover: (i) => { if (state.hoverIndex !== i) { state.hoverIndex = i; renderDetail(); } },
  });

  // The chart and the map are two files cut from the same numbers; say so if they ever differ.
  const mapCode = state.codes ? state.codes[selected.row * manifest.grid.ni + selected.col] : null;
  $('chart-status').textContent = (mapCode !== null && mapCode !== series[state.index])
    ? `Warning: the chart (${series[state.index]}) and the map (${mapCode}) disagree for this cell and interval.`
    : '';

  const total = amounts.reduce((a, b) => a + b, 0);
  let peak = 0;
  rates.forEach((r, i) => { if (r > rates[peak]) peak = i; });
  const days = (ivs[ivs.length - 1].end_step - ivs[0].start_step) / 24;
  if (prob) {
    $('chart-summary').textContent = total > 0
      ? `Highest chance: ${formatDisplay(amounts[peak], ivs[peak])} (${formatAmount(amounts[peak], ivs[peak])}), ${rangeUtc(ivs[peak])}.`
      : `No member reaches ${layer.threshold_mm} mm in any 24 h window over ${days} days.`;
    $('chart-note').textContent =
      `Each bar is one 24 h window. The chance is the share of the ${layer.members} ensemble members that reach ` +
      `${layer.threshold_mm} mm, so it moves in steps of ${+(100 / layer.members).toFixed(1)} %. ` +
      'Tap a bar to show that window on the map.';
    return;
  }
  $('chart-summary').textContent = total > 0
    ? `Total over ${days} days: ${formatValue(total, layer.units)}. Highest mean rate: ${formatDisplay(amounts[peak], ivs[peak])}, ${rangeUtc(ivs[peak])}.`
    : `No precipitation in any interval over ${days} days.`;
  $('chart-note').textContent =
    'Bar height is the mean rate in each interval; bars are 3 h wide up to +144 h and 6 h wide after. ' +
    'Tap a bar to show that interval on the map.' +
    (faint.some(Boolean) ? ' Pale bars are too small for the map to draw.' : '');
}

function buildTable() {
  const { layer } = state;
  const table = $('series-table');
  table.replaceChildren();
  const head = table.createTHead().insertRow();
  const prob = isProbability();
  for (const h of ['Starts (UTC)', `Starts (${SECOND_ZONE.label})`, 'h', displayUnits(), prob ? 'members' : layer.units]) {
    head.append(Object.assign(document.createElement('th'), { textContent: h }));
  }
  const body = table.createTBody();
  layer.intervals.forEach((iv, i) => {
    const amount = decodeValue(layer.encoding, state.series[i]);
    const row = body.insertRow();
    const cells = prob
      ? [Math.round(amount), Math.round(amount * layer.members / 100)]
      : [displayValue(layer, amount, iv.hours).toFixed(2), amount.toFixed(2)];
    for (const v of [dayTime(iv.start_utc, 'UTC'), dayTime(iv.start_utc, SECOND_ZONE.id), iv.hours, ...cells]) {
      row.insertCell().textContent = v;
    }
  });
}

// ---------- rendering ----------

async function show(i) {
  state.index = i;
  const iv = state.layer.intervals[i];
  $('slider').value = i;
  $('slider').setAttribute('aria-valuetext', rangeUtc(iv));
  $('interval-utc').textContent = rangeUtc(iv);
  $('now-tag').hidden = !containsTime(iv, Date.now());
  $('interval-local').textContent = rangeSecond(iv);
  $('lead').textContent = `+${iv.start_step} h to +${iv.end_step} h`;
  $('legend-title').textContent = legendTitle(iv);

  const token = ++state.renderToken;
  const codes = await loadCodes(i);
  if (token !== state.renderToken) return; // a newer request superseded this one
  state.codes = codes;

  const { ni, nj } = state.manifest.grid;
  const canvas = document.createElement('canvas');
  canvas.width = ni; canvas.height = nj;
  const ctx = canvas.getContext('2d');
  const img = ctx.createImageData(ni, nj);
  const px = new Uint32Array(img.data.buffer);
  const lut = lutFor(iv);
  for (let k = 0; k < px.length; k++) px[k] = lut[codes[k]];
  ctx.putImageData(img, 0, 0);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (token !== state.renderToken) return;
  const url = URL.createObjectURL(blob);
  overlay.setUrl(url);
  if (state.blobUrl) URL.revokeObjectURL(state.blobUrl);
  state.blobUrl = url;
  updatePanel();
}

function legendTitle(iv) {
  const d = state.layer.display;
  if (isProbability()) return `Share of ${state.layer.members} ensemble members, % · ${iv.hours} h window`;
  return d ? `${d.title}, ${d.units} · ${iv.hours} h interval` : `${state.layer.title}, ${state.layer.units}`;
}

function buildLegend(layer) {
  const scale = $('legend-scale');
  scale.innerHTML = '';
  for (const s of layer.legend.stops) {
    const cls = document.createElement('div');
    cls.className = 'cls';
    const sw = document.createElement('div');
    sw.className = 'swatch';
    sw.style.background = s.color;
    const tick = document.createElement('div');
    tick.className = 'tick';
    tick.textContent = String(s.from); // lower bound of this class
    cls.append(sw, tick);
    scale.append(cls);
  }
}

function describeRun(manifest, layer) {
  const ref = new Date(manifest.run.reference_utc);
  const ageH = (Date.now() - ref.getTime()) / 3600000;
  const day = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(ref);
  $('run-line').textContent =
    `${manifest.run.centre} ${manifest.run.model} ${manifest.run.resolution_deg}° · run ${day} ${timeOnly(manifest.run.reference_utc)} UTC ` +
    `(${Math.round(ageH)} h ago) · forecast to +${manifest.run.last_step} h`;
  if (ageH > STALE_AFTER_HOURS) {
    $('stale').textContent = `This forecast run is ${Math.round(ageH)} h old. A newer run should exist; the update job may have failed.`;
    $('stale').hidden = false;
  }
  $('attribution').textContent = manifest.attribution.text + ' ';
  $('licence').href = manifest.attribution.licence_url;
}

// ---------- layers ----------

function buildLayerPicker(manifest) {
  const select = $('layer');
  const single = manifest.layers.filter((l) => l.kind !== 'probability');
  const prob = manifest.layers.filter((l) => l.kind === 'probability');
  for (const l of single) {
    select.append(new Option(`${l.display ? l.display.title : l.title} (single forecast)`, l.id));
  }
  if (prob.length) {
    const group = document.createElement('optgroup');
    group.label = `Chance, from ${prob[0].members} ensemble members`;
    for (const l of prob) group.append(new Option(l.title, l.id));
    select.append(group);
    $('layer-pick').hidden = false;
    select.addEventListener('change', () => setLayer(select.value).catch(fail));
  } else if (manifest.ensemble && manifest.ensemble.status === 'unavailable') {
    $('ensemble-note').textContent = 'Ensemble probabilities could not be built for this run.';
    $('ensemble-note').hidden = false;
  }
}

/** Switch what the map and chart show, staying at the same moment of the forecast. */
async function setLayer(id) {
  const layer = state.layers.find((l) => l.id === id);
  if (!layer || layer === state.layer) return;
  setPlaying(false);
  const index = indexAtTime(layer.intervals, Date.parse(state.layer.intervals[state.index].start_utc));
  Object.assign(state, { layer, codes: null, series: null, hoverIndex: null });
  $('layer').value = id;
  buildLegend(layer);
  $('slider').max = layer.intervals.length - 1;
  await show(index);
  if (state.selected) selectCell(state.selected.row, state.selected.col);
}

// ---------- controls ----------

function setPlaying(on) {
  state.playing = on;
  $('play').textContent = on ? '❚❚' : '▶';
  $('play').setAttribute('aria-label', on ? 'Pause' : 'Play');
  if (on) tick();
}
async function tick() {
  if (!state.playing) return;
  const next = (state.index + 1) % state.layer.intervals.length;
  const started = performance.now();
  try { await show(next); } catch (e) { fail(e); setPlaying(false); return; }
  loadCodes((next + 1) % state.layer.intervals.length).catch(() => {}); // warm the next frame
  setTimeout(tick, Math.max(0, PLAY_INTERVAL_MS - (performance.now() - started)));
}

function fail(e) {
  console.error(e);
  $('error').textContent = `The forecast data could not be loaded (${e.message}).`;
  $('error').hidden = false;
}

async function main() {
  try {
    const manifest = await loadManifest();
    for (const l of manifest.layers) {
      if (l.encoding.format !== 'png-rg16') throw new Error(`unsupported encoding ${l.encoding.format}`);
      if (!l.series || l.series.layout !== 'frames-stacked') throw new Error('manifest has no usable time series');
    }
    // The manifest names the layer to open on; fall back to the first one.
    const layer = manifest.layers.find((l) => l.id === manifest.default_layer) || manifest.layers[0];
    Object.assign(state, { manifest, layer, layers: manifest.layers });
    describeRun(manifest, layer);
    buildLayerPicker(manifest);
    $('layer').value = layer.id;
    buildLegend(layer);
    initMap(manifest);
    const slider = $('slider');
    slider.max = layer.intervals.length - 1;
    slider.addEventListener('input', () => { setPlaying(false); show(Number(slider.value)).catch(fail); });
    $('play').addEventListener('click', () => setPlaying(!state.playing));
    $('readout-close').addEventListener('click', deselect);
    new ResizeObserver(() => { if (state.selected && state.series) renderChart(); }).observe($('chart'));
    // Open on the interval that contains the present moment, not on the start of the run,
    // which is already 7 to 20 hours in the past when a run is published and viewed.
    await show(indexAtTime(layer.intervals, Date.now()));
    // For debugging and for checking values against the pipeline from the console.
    window.__app = state;
    window.__map = map;
    window.__selectCell = (lat, lon) => select({ lat, lng: lon });
    window.__setLayer = setLayer;
  } catch (e) { fail(e); }
}

main();
