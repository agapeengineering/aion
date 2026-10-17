export type Clock = { date: string; time: string };
export type DateParts = { year: number; month: number; day: number };
export type Totals = {
  years: number;
  months: number;
  weeks: number;
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
};
export type Unit = keyof Totals;
export const units: Unit[] = ['years', 'months', 'weeks', 'days', 'hours', 'minutes', 'seconds'];
export type Snapshot = {
  horizonDate: string;
  horizonState: 'before' | 'reached' | 'passed';
  lived: Totals;
  remaining: Totals;
  grid: {
    totalCells: number;
    elapsedCells: number;
    currentIndex: number | null;
    futureCells: number;
    currentStart: string | null;
    currentEndExclusive: string | null;
    finalCellDays: number;
  };
};
export type CalculationError = {
  error: {
    field: 'clock' | 'birthDate' | 'lifespanYears';
    code:
      | 'INVALID_CLOCK'
      | 'INVALID_BIRTH_DATE'
      | 'FUTURE_BIRTH_DATE'
      | 'INVALID_LIFESPAN'
      | 'HORIZON_OUT_OF_RANGE';
  };
};
export const isLeap = (year: number) => year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
export const daysInMonth = (year: number, month: number) =>
  [31, isLeap(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
export function parseDate(value: unknown): DateParts | null {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const [year, month, day] = value.split('-').map(Number);
  return year > 0 &&
    year <= 9999 &&
    month > 0 &&
    month <= 12 &&
    day > 0 &&
    day <= daysInMonth(year, month)
    ? { year, month, day }
    : null;
}
export const dateString = (d: DateParts) =>
  `${String(d.year).padStart(4, '0')}-${String(d.month).padStart(2, '0')}-${String(d.day).padStart(2, '0')}`;
export function ordinal(d: DateParts): number {
  const y = d.year - 1;
  const prior = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334][d.month - 1];
  return (
    y * 365 +
    Math.floor(y / 4) -
    Math.floor(y / 100) +
    Math.floor(y / 400) +
    prior +
    (d.month > 2 && isLeap(d.year) ? 1 : 0) +
    d.day -
    1
  );
}
export function dateAtDay(day: number): DateParts {
  let low = 1,
    high = 10000;
  while (low + 1 < high) {
    const mid = Math.floor((low + high) / 2);
    if (ordinal({ year: mid, month: 1, day: 1 }) <= day) low = mid;
    else high = mid;
  }
  let left = day - ordinal({ year: low, month: 1, day: 1 }),
    month = 1;
  while (left >= daysInMonth(low, month)) {
    left -= daysInMonth(low, month);
    month++;
  }
  return { year: low, month, day: left + 1 };
}
function anniversary(a: DateParts, count: number, years: boolean): DateParts {
  const index = (a.year - 1) * 12 + a.month - 1 + count * (years ? 12 : 1);
  const year = Math.floor(index / 12) + 1,
    month = (index % 12) + 1;
  return { year, month, day: Math.min(a.day, daysInMonth(year, month)) };
}
function completed(a: DateParts, b: DateParts, years: boolean): number {
  const n = years ? b.year - a.year : (b.year - a.year) * 12 + b.month - a.month;
  return n - Number(ordinal(anniversary(a, n, years)) > ordinal(b));
}
export function localClock(now = new Date()): Clock {
  return {
    date: dateString({ year: now.getFullYear(), month: now.getMonth() + 1, day: now.getDate() }),
    time: [now.getHours(), now.getMinutes(), now.getSeconds()]
      .map((x) => String(x).padStart(2, '0'))
      .join(':'),
  };
}
export function calculate(input: {
  birthDate?: unknown;
  lifespanYears?: unknown;
  clock?: unknown;
}): Snapshot | CalculationError {
  const c = input.clock as Partial<Clock> | null | undefined;
  const today = c && parseDate(c.date);
  if (!today || typeof c?.time !== 'string' || !/^(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d$/.test(c.time))
    return { error: { field: 'clock', code: 'INVALID_CLOCK' } };
  const birth = parseDate(input.birthDate);
  if (!birth) return { error: { field: 'birthDate', code: 'INVALID_BIRTH_DATE' } };
  if (ordinal(birth) > ordinal(today))
    return { error: { field: 'birthDate', code: 'FUTURE_BIRTH_DATE' } };
  const lifespan = input.lifespanYears;
  if (typeof lifespan !== 'number' || !Number.isSafeInteger(lifespan) || lifespan <= 0)
    return { error: { field: 'lifespanYears', code: 'INVALID_LIFESPAN' } };
  if (birth.year + lifespan > 9999)
    return { error: { field: 'lifespanYears', code: 'HORIZON_OUT_OF_RANGE' } };
  const horizon = anniversary(birth, lifespan, true),
    B = ordinal(birth),
    T = ordinal(today),
    H = ordinal(horizon);
  const [hours, minutes, seconds] = c.time.split(':').map(Number),
    q = hours * 3600 + minutes * 60 + seconds;
  const livedDays = T - B,
    remainingDays = Math.max(0, H - T),
    span = H - B;
  const totalCells = Math.ceil(span / 7),
    elapsedCells = T < H ? Math.floor(livedDays / 7) : totalCells;
  const currentIndex = T < H ? elapsedCells : null;
  function totals(a: DateParts, z: DateParts, days: number, sec: number): Totals {
    return {
      years: completed(a, z, true),
      months: completed(a, z, false),
      weeks: Math.floor(days / 7),
      days,
      hours: Math.floor(sec / 3600),
      minutes: Math.floor(sec / 60),
      seconds: sec,
    };
  }
  return {
    horizonDate: dateString(horizon),
    horizonState: T < H ? 'before' : T === H ? 'reached' : 'passed',
    lived: totals(birth, today, livedDays, livedDays * 86400 + q),
    remaining:
      T < H
        ? totals(today, horizon, remainingDays, Math.max(0, remainingDays * 86400 - q))
        : { years: 0, months: 0, weeks: 0, days: 0, hours: 0, minutes: 0, seconds: 0 },
    grid: {
      totalCells,
      elapsedCells,
      currentIndex,
      futureCells: totalCells - elapsedCells - Number(currentIndex !== null),
      currentStart: currentIndex === null ? null : dateString(dateAtDay(B + currentIndex * 7)),
      currentEndExclusive:
        currentIndex === null
          ? null
          : dateString(dateAtDay(Math.min(B + (currentIndex + 1) * 7, H))),
      finalCellDays: ((span - 1) % 7) + 1,
    },
  };
}
export type DisplayEvent = 'load' | 'tick' | 'pause' | 'resume' | 'hide' | 'show' | 'export';
export type DisplayState = {
  live: Snapshot;
  subday: Snapshot;
  visible: boolean;
  paused: boolean;
  exportSnapshot?: Snapshot;
};
export function advanceDisplay(
  state: DisplayState | null,
  event: DisplayEvent,
  snapshot: Snapshot,
): DisplayState {
  if (!state || event === 'load')
    return { live: snapshot, subday: snapshot, visible: true, paused: false };
  const visible = event === 'hide' ? false : event === 'show' ? true : state.visible;
  const paused = event === 'pause' ? true : event === 'resume' ? false : state.paused;
  const subday = event === 'pause' || (visible && !paused) ? snapshot : state.subday;
  return {
    live: snapshot,
    subday,
    visible,
    paused,
    ...(event === 'export' ? { exportSnapshot: snapshot } : {}),
  };
}
