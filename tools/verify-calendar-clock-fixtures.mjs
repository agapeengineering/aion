/** Fixture audit only. Do not import this as application/domain code. */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const fixtureUrl = new URL('../tests/fixtures/calendar-clock/v1.json', import.meta.url);
const spec = readFileSync(new URL('../docs/requirements/web-release-specification.md', import.meta.url), 'utf8');
const knownRequirements = new Set([...spec.matchAll(/^\| ((?:FR|NFR)-\d{3}) \|/gm)].map(m => m[1]));
const leap = y => y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
const monthDays = (y, m) => [31, leap(y) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1];
function parseDate(s) {
  if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  const [y, m, d] = s.split('-').map(Number);
  return y >= 1 && y <= 9999 && m >= 1 && m <= 12 && d >= 1 && d <= monthDays(y, m) ? { y, m, d } : null;
}
function ordinal(a) {
  const y = a.y - 1;
  let n = 365 * y + Math.floor(y / 4) - Math.floor(y / 100) + Math.floor(y / 400) + a.d - 1;
  for (let m = 1; m < a.m; m++) n += monthDays(a.y, m);
  return n;
}
const formatDate = a => `${String(a.y).padStart(4, '0')}-${String(a.m).padStart(2, '0')}-${String(a.d).padStart(2, '0')}`;
function fromOrdinal(n) {
  let lo = 1, hi = 10000;
  while (lo + 1 < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (ordinal({ y: mid, m: 1, d: 1 }) <= n) lo = mid; else hi = mid;
  }
  let m = 1, left = n - ordinal({ y: lo, m: 1, d: 1 });
  while (left >= monthDays(lo, m)) left -= monthDays(lo, m++);
  return { y: lo, m, d: left + 1 };
}
function addUnits(a, n, years) {
  const ix = (a.y - 1) * 12 + a.m - 1 + n * (years ? 12 : 1);
  const y = Math.floor(ix / 12) + 1, m = ix % 12 + 1;
  return { y, m, d: Math.min(a.d, monthDays(y, m)) };
}
// Search anniversary candidates, independently of the generator's direct estimate/correction.
function completed(a, b, years) {
  let lo = 0, hi = years ? 10000 - a.y : (10000 - a.y) * 12;
  while (lo + 1 < hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (ordinal(addUnits(a, mid, years)) <= ordinal(b)) lo = mid; else hi = mid;
  }
  return lo;
}
const error = (field, code) => ({ error: { field, code } });
function evaluate(input) {
  const c = input.clock;
  const t = c && parseDate(c.date);
  if (!t || typeof c.time !== 'string' || !/^(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d$/.test(c.time)) return error('clock', 'INVALID_CLOCK');
  const b = parseDate(input.birthDate);
  if (!b) return error('birthDate', 'INVALID_BIRTH_DATE');
  if (ordinal(b) > ordinal(t)) return error('birthDate', 'FUTURE_BIRTH_DATE');
  const l = input.lifespanYears;
  if (!Number.isSafeInteger(l) || l <= 0) return error('lifespanYears', 'INVALID_LIFESPAN');
  if (b.y + l > 9999) return error('lifespanYears', 'HORIZON_OUT_OF_RANGE');
  const h = addUnits(b, l, true), B = ordinal(b), T = ordinal(t), H = ordinal(h);
  const [hh, mm, ss] = c.time.split(':').map(Number), q = hh * 3600 + mm * 60 + ss;
  const days = T - B, ahead = Math.max(0, H - T), span = H - B, cells = Math.ceil(span / 7);
  const totals = (a, z, d, sec) => ({ years: completed(a, z, true), months: completed(a, z, false), weeks: Math.floor(d / 7), days: d, hours: Math.floor(sec / 3600), minutes: Math.floor(sec / 60), seconds: sec });
  const current = T < H ? Math.floor(days / 7) : null;
  const elapsed = current === null ? cells : current;
  const start = current === null ? null : B + current * 7;
  return {
    horizonDate: formatDate(h), horizonState: T < H ? 'before' : T === H ? 'reached' : 'passed',
    lived: totals(b, t, days, days * 86400 + q),
    remaining: T < H ? totals(t, h, ahead, Math.max(0, ahead * 86400 - q)) : { years: 0, months: 0, weeks: 0, days: 0, hours: 0, minutes: 0, seconds: 0 },
    grid: { totalCells: cells, elapsedCells: elapsed, currentIndex: current, futureCells: cells - elapsed - (current === null ? 0 : 1), currentStart: start === null ? null : formatDate(fromOrdinal(start)), currentEndExclusive: start === null ? null : formatDate(fromOrdinal(Math.min(start + 7, H))), finalCellDays: (span - 1) % 7 + 1 },
  };
}
function checkSource(c) {
  if (!c.clockSource) return;
  const { instant, timeZone, utcOffsetSeconds } = c.clockSource;
  const dt = new Date(instant);
  assert.match(instant, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$/);
  assert(Number.isFinite(dt.getTime()));
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', { timeZone, calendar: 'gregory', numberingSystem: 'latn', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).formatToParts(dt).filter(x => x.type !== 'literal').map(x => [x.type, x.value]));
  assert.equal(`${parts.year}-${parts.month}-${parts.day}`, c.input.clock.date, c.id);
  assert.equal(`${parts.hour}:${parts.minute}:${parts.second}`, c.input.clock.time, c.id);
  const utc = { y: dt.getUTCFullYear(), m: dt.getUTCMonth() + 1, d: dt.getUTCDate() };
  const q = Number(parts.hour) * 3600 + Number(parts.minute) * 60 + Number(parts.second);
  const u = dt.getUTCHours() * 3600 + dt.getUTCMinutes() * 60 + dt.getUTCSeconds();
  assert.equal((ordinal(parseDate(c.input.clock.date)) - ordinal(utc)) * 86400 + q - u, utcOffsetSeconds, c.id);
}
function verify(data) {
  assert.equal(data.formatVersion, 1); assert.equal(data.contractVersion, '1.0.0');
  assert(Array.isArray(data.cases) && data.cases.length > 0);
  assert(Array.isArray(data.traces) && data.traces.length > 0);
  const by = new Map();
  function requirements(x) {
    assert(x.requirements?.length > 0, x.id);
    for (const id of x.requirements) assert(knownRequirements.has(id), `${x.id}: unknown requirement ${id}`);
  }
  for (const c of data.cases) {
    assert(!by.has(c.id), `duplicate ${c.id}`); requirements(c);
    assert.deepEqual(evaluate(c.input), c.expected, c.id); checkSource(c); by.set(c.id, c);
    if (!c.expected.error) {
      const { grid: g, lived: l, remaining: r } = c.expected;
      assert.equal(g.elapsedCells + g.futureCells + Number(g.currentIndex !== null), g.totalCells, c.id);
      assert.equal(l.weeks, Math.floor(l.days / 7));
      assert(Object.values(r).every(x => Number.isSafeInteger(x) && x >= 0));
      if (c.expected.horizonState !== 'before') assert(Object.values(r).every(x => x === 0));
    }
  }
  const traceIds = new Set();
  for (const t of data.traces) {
    assert(!traceIds.has(t.id)); traceIds.add(t.id); requirements(t);
    assert(t.steps.length && t.steps[0].event === 'load', t.id);
    let paused = false, visible = true, frozen = null, display = null;
    for (const [index, step] of t.steps.entries()) {
      assert(by.has(step.caseId) && !by.get(step.caseId).expected.error, step.caseId);
      const id = step.caseId;
      switch (step.event) {
        case 'load': assert.equal(index, 0); visible = true; paused = false; frozen = null; break;
        case 'pause': assert(visible && !paused); paused = true; frozen = id; break;
        case 'resume': assert(visible && paused); paused = false; frozen = null; break;
        case 'hide': visible = false; break;
        case 'show': visible = true; break;
        case 'tick': break;
        case 'export': assert(visible); break;
        default: assert.fail(`unknown event: ${step.event}`);
      }
      if (visible) display = paused ? frozen : id;
      const expected = { visible, paused, displaySubdayCaseId: display };
      if (step.event === 'export') expected.exportCaseId = id;
      assert.deepEqual(step.expected, expected, `${t.id} step ${index}`);
    }
  }
  // Hand-derived anchors supplement the two independent calculation methods.
  assert.equal(by.get('one-week').expected.lived.days, 7);
  assert.equal(by.get('month-end-clamp').expected.lived.days, 28);
  assert.equal(by.get('month-direct-not-iterative').expected.lived.months, 1);
  assert.equal(by.get('ninety-year-default').expected.lived.days, 9132);
  assert.equal(by.get('ninety-year-default').expected.remaining.days, 23741);
  assert.equal(by.get('horizon-minus-one').expected.remaining.seconds, 1);
  assert.equal(by.get('whole-week-horizon').expected.grid.finalCellDays, 7);
  return { cases: by.size, traces: traceIds.size, steps: data.traces.reduce((n, x) => n + x.steps.length, 0), sourceClocks: data.cases.filter(x => x.clockSource).length };
}
const data = JSON.parse(readFileSync(fixtureUrl, 'utf8'));
const counts = verify(data);
if (process.argv.includes('--self-test')) {
  const mutations = [
    d => { d.cases[0].expected.lived.seconds += 1; },
    d => { d.cases.find(x => x.clockSource).clockSource.utcOffsetSeconds += 3600; },
    d => { d.traces[0].steps[1].expected.paused = true; },
    d => { d.cases[1].id = d.cases[0].id; },
    d => { d.cases[0].requirements = ['FR-999']; },
  ];
  for (const mutate of mutations) {
    const broken = structuredClone(data); mutate(broken);
    assert.throws(() => verify(broken), 'audit must reject a deliberately corrupted fixture');
  }
  console.log(`PASS: ${mutations.length} deliberately corrupted fixture sets rejected.`);
}
console.log(`PASS: ${counts.cases} snapshots, ${counts.traces} clock traces (${counts.steps} steps), ${counts.sourceClocks} zoned source clocks; arithmetic, invariants and requirement references checked.`);
console.log('Fixture source: tests/fixtures/calendar-clock/v1.json');
