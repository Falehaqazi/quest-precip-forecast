// Time formatting. Every instant in the data is UTC; the page shows UTC and one second zone.

/** The second zone shown next to UTC everywhere on the page (DECISIONS D16). */
export const SECOND_ZONE = { id: 'Asia/Kolkata', label: 'IST' };

const cache = new Map();
function formatters(zoneId) {
  if (!cache.has(zoneId)) {
    cache.set(zoneId, {
      day: new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: zoneId }),
      shortDay: new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: zoneId }),
      time: new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: zoneId }),
    });
  }
  return cache.get(zoneId);
}

/** "Tue 10 Nov 21:00 – Wed 11 Nov 00:00"; the end date is omitted when it is the same day. */
export function formatRange(startIso, endIso, zoneId) {
  const f = formatters(zoneId);
  const a = new Date(startIso), b = new Date(endIso);
  const sameDay = f.day.format(a) === f.day.format(b);
  return `${f.day.format(a)} ${f.time.format(a)} – ${sameDay ? '' : f.day.format(b) + ' '}${f.time.format(b)}`;
}
export const rangeUtc = (iv) => `${formatRange(iv.start_utc, iv.end_utc, 'UTC')} UTC`;
export const rangeSecond = (iv) => `${formatRange(iv.start_utc, iv.end_utc, SECOND_ZONE.id)} ${SECOND_ZONE.label}`;

/** "12 Nov" */
export const shortDay = (iso, zoneId = 'UTC') => formatters(zoneId).shortDay.format(new Date(iso));

/** "Tue 10 Nov 05:30" */
export function dayTime(iso, zoneId) {
  const f = formatters(zoneId);
  const d = new Date(iso);
  return `${f.day.format(d)} ${f.time.format(d)}`;
}

/** "05:30" */
export const timeOnly = (iso, zoneId = 'UTC') => formatters(zoneId).time.format(new Date(iso));

/**
 * Index of the interval that contains the instant `ms`: the first whose end is after it.
 * Before the forecast starts this is the first interval; after it ends, the last.
 */
export function indexAtTime(intervals, ms) {
  for (let i = 0; i < intervals.length; i++) if (ms < Date.parse(intervals[i].end_utc)) return i;
  return intervals.length - 1;
}

/** True if the instant `ms` lies inside the interval (start inclusive, end exclusive). */
export function containsTime(iv, ms) {
  return Date.parse(iv.start_utc) <= ms && ms < Date.parse(iv.end_utc);
}

/**
 * ECMWF runs the model every 12 h, and on the two days observed a run's files (including the
 * ensemble) were complete about 8 h after its nominal time. So once the run on the page is
 * 20 h old the next one has normally been out for a while; 21 h leaves a margin.
 */
export const NEWER_RUN_LIKELY_AFTER_HOURS = 21;

/** True when a newer complete run than `referenceIso` has probably been published. */
export function newerRunLikely(referenceIso, nowMs) {
  return nowMs - Date.parse(referenceIso) >= NEWER_RUN_LIKELY_AFTER_HOURS * 3600000;
}
