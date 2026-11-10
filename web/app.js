import { indexOf, centerOf, cellBounds, rgbaToCodes, decodeValue, legendClass } from './grid.js';

const DATA_DIR = 'data/';
const STALE_AFTER_HOURS = 24;   // a fresh 00z/12z run is 7-20 h old when viewed (see LIMITATIONS)
const PLAY_INTERVAL_MS = 650;
const CACHE_SIZE = 16;          // decoded intervals kept in memory (~2 MB each)

const $ = (id) => document.getElementById(id);
const state = {
  manifest: null, layer: null, index: 0, codes: null, lut: null,
  cache: new Map(), selected: null, playing: false, renderToken: 0, blobUrl: null,
};
let map, overlay, selectionRect;

// ---------- formatting ----------

const utcDay = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' });
const utcTime = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'UTC' });
const locDay = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
const locTime = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
const localZone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'local time';

function formatRange(startIso, endIso, day, time) {
  const a = new Date(startIso), b = new Date(endIso);
  const sameDay = day.format(a) === day.format(b);
  return `${day.format(a)} ${time.format(a)} – ${sameDay ? '' : day.format(b) + ' '}${time.format(b)}`;
}
const rangeUtc = (iv) => `${formatRange(iv.start_utc, iv.end_utc, utcDay, utcTime)} UTC`;
const rangeLocal = (iv) => `${formatRange(iv.start_utc, iv.end_utc, locDay, locTime)} (${localZone})`;

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
  if (m.schema !== 1) throw new Error(`unsupported manifest schema ${m.schema}`);
  return m;
}

/** Fetch and decode one interval raster into Uint16 codes. */
async function loadCodes(i) {
  if (state.cache.has(i)) return state.cache.get(i);
  const { grid, run } = state.manifest;
  const iv = state.layer.intervals[i];
  // File names repeat from run to run, so the run time is part of the URL to defeat caches.
  const res = await fetch(`${DATA_DIR}${iv.file}?run=${encodeURIComponent(run.reference_utc)}`);
  if (!res.ok) throw new Error(`${iv.file}: HTTP ${res.status}`);
  // No colour-space conversion and no alpha premultiplication: the bytes are data, not colour.
  const bmp = await createImageBitmap(await res.blob(), { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
  if (bmp.width !== grid.ni || bmp.height !== grid.nj) {
    throw new Error(`${iv.file} is ${bmp.width}x${bmp.height}, grid is ${grid.ni}x${grid.nj}`);
  }
  const c = document.createElement('canvas');
  c.width = grid.ni; c.height = grid.nj;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(bmp, 0, 0);
  const codes = rgbaToCodes(ctx.getImageData(0, 0, grid.ni, grid.nj).data, grid.ni * grid.nj);
  state.cache.set(i, codes);
  if (state.cache.size > CACHE_SIZE) state.cache.delete(state.cache.keys().next().value);
  return codes;
}

/** code -> packed RGBA lookup table, built from the layer's legend. */
function buildLut(layer) {
  const lut = new Uint32Array(65536);
  const stops = layer.legend.stops.map((s) => {
    const n = parseInt(s.color.slice(1), 16);
    return { from: s.from, r: n >> 16, g: (n >> 8) & 255, b: n & 255 };
  });
  for (let code = 0; code < 65536; code++) {
    const k = legendClass(stops, decodeValue(layer.encoding, code));
    if (k < 0) continue; // transparent
    const s = stops[k];
    lut[code] = (255 << 24) | (s.b << 16) | (s.g << 8) | s.r; // little-endian RGBA
  }
  return lut;
}

// ---------- map ----------

function initMap(manifest) {
  const b = manifest.grid.bounds;
  const world = [[b.south, b.west], [b.north, b.east]];
  map = L.map('map', {
    crs: L.CRS.EPSG4326, zoomSnap: 0.25, zoomDelta: 0.5, minZoom: 0, maxZoom: 7,
    attributionControl: false, maxBounds: [[-110, -220], [110, 220]], maxBoundsViscosity: 0.9,
  });
  map.createPane('land').style.zIndex = 200;
  map.createPane('raster').style.zIndex = 300;
  map.createPane('borders').style.zIndex = 350;
  map.getPane('borders').style.pointerEvents = 'none';
  map.fitBounds(world);

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
  el.textContent = formatValue(hit.value, state.layer.units);
  el.style.left = `${e.containerPoint.x}px`;
  el.style.top = `${e.containerPoint.y}px`;
  el.hidden = false;
}

function select(latlng) {
  const hit = valueAt(latlng);
  if (!hit) return;
  state.selected = { row: hit.row, col: hit.col };
  const rect = cellBounds(state.manifest.grid, hit.row, hit.col);
  if (selectionRect) selectionRect.setBounds(rect);
  else selectionRect = L.rectangle(rect, { pane: 'borders', color: '#1f1f1d', weight: 2, fill: false, interactive: false }).addTo(map);
  updateReadout();
}

function updateReadout() {
  const sel = state.selected;
  if (!sel || !state.codes) return;
  const { grid } = state.manifest;
  const iv = state.layer.intervals[state.index];
  const value = decodeValue(state.layer.encoding, state.codes[sel.row * grid.ni + sel.col]);
  $('readout-value').innerHTML = '';
  $('readout-value').append(formatValue(value, state.layer.units), Object.assign(document.createElement('small'), { textContent: ` in ${iv.hours} h` }));
  const rows = [
    ['Cell centre', formatLatLon(centerOf(grid, sel.row, sel.col))],
    ['Interval', rangeUtc(iv)],
    ['Your time', rangeLocal(iv)],
    ['Grid index', `row ${sel.row}, col ${sel.col}`],
    ['Resolution', `${state.layer.encoding.scale} ${state.layer.units} steps`],
  ];
  const dl = $('readout-details');
  dl.innerHTML = '';
  for (const [k, v] of rows) {
    dl.append(Object.assign(document.createElement('dt'), { textContent: k }),
      Object.assign(document.createElement('dd'), { textContent: v }));
  }
  $('readout').hidden = false;
}

// ---------- rendering ----------

async function show(i) {
  state.index = i;
  const iv = state.layer.intervals[i];
  $('slider').value = i;
  $('slider').setAttribute('aria-valuetext', rangeUtc(iv));
  $('interval-utc').textContent = rangeUtc(iv);
  $('interval-local').textContent = rangeLocal(iv);
  $('lead').textContent = `+${iv.start_step} h to +${iv.end_step} h`;
  $('legend-title').textContent = `${state.layer.title}: ${state.layer.units} per ${iv.hours} h`;

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
  const lut = state.lut;
  for (let k = 0; k < px.length; k++) px[k] = lut[codes[k]];
  ctx.putImageData(img, 0, 0);
  const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (token !== state.renderToken) return;
  const url = URL.createObjectURL(blob);
  overlay.setUrl(url);
  if (state.blobUrl) URL.revokeObjectURL(state.blobUrl);
  state.blobUrl = url;
  updateReadout();
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
    tick.textContent = `≥ ${s.from}`;
    cls.append(sw, tick);
    scale.append(cls);
  }
}

function describeRun(manifest, layer) {
  const ref = new Date(manifest.run.reference_utc);
  const ageH = (Date.now() - ref.getTime()) / 3600000;
  const day = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(ref);
  $('run-line').textContent =
    `${manifest.run.centre} ${manifest.run.model} ${manifest.run.resolution_deg}° · run ${day} ${utcTime.format(ref)} UTC ` +
    `(${Math.round(ageH)} h ago) · ${layer.intervals.length} intervals to +${manifest.run.last_step} h`;
  if (ageH > STALE_AFTER_HOURS) {
    $('stale').textContent = `This forecast run is ${Math.round(ageH)} h old. A newer run should exist; the update job may have failed.`;
    $('stale').hidden = false;
  }
  $('attribution').textContent = manifest.attribution.text + ' ';
  $('licence').href = manifest.attribution.licence_url;
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
    const layer = manifest.layers[0];
    if (layer.encoding.format !== 'png-rg16') throw new Error(`unsupported encoding ${layer.encoding.format}`);
    Object.assign(state, { manifest, layer, lut: buildLut(layer) });
    describeRun(manifest, layer);
    buildLegend(layer);
    initMap(manifest);
    const slider = $('slider');
    slider.max = layer.intervals.length - 1;
    slider.addEventListener('input', () => { setPlaying(false); show(Number(slider.value)).catch(fail); });
    $('play').addEventListener('click', () => setPlaying(!state.playing));
    $('readout-close').addEventListener('click', () => {
      state.selected = null; $('readout').hidden = true;
      if (selectionRect) { selectionRect.remove(); selectionRect = null; }
    });
    await show(0);
    window.__app = state; // for debugging and for checking values against the pipeline
  } catch (e) { fail(e); }
}

main();
