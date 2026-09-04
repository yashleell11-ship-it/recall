const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function parse(value: string): Date | null {
  const d = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T12:00:00` : value);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** 4 Sep */
export function shortDate(value: string): string {
  const d = parse(value);
  if (!d) return value;
  return `${d.getDate()} ${MONTHS[d.getMonth()]}`;
}

/** 4 Sep 2026 */
export function mediumDate(value: string): string {
  const d = parse(value);
  if (!d) return value;
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

/** Thursday, 4 September — from an ISO date, so render stays pure and the
 *  statically prerendered HTML never bakes in the build date. */
export function longDate(value: string): string {
  const d = parse(value);
  if (!d) return "";
  const weekday = [
    "Sunday",
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
  ][d.getDay()];
  const month = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
  ][d.getMonth()];
  return `${weekday}, ${d.getDate()} ${month}`;
}

export function weekdayInitial(value: string): string {
  const d = parse(value);
  if (!d) return "";
  return DAYS[d.getDay()][0];
}

export function weekdayShort(value: string): string {
  const d = parse(value);
  if (!d) return "";
  return DAYS[d.getDay()];
}

export function isWeekend(value: string): boolean {
  const d = parse(value);
  if (!d) return false;
  return d.getDay() === 0 || d.getDay() === 6;
}

export function daysAgo(value: string): number {
  const d = parse(value);
  if (!d) return 0;
  const today = new Date();
  today.setHours(12, 0, 0, 0);
  return Math.round((today.getTime() - d.getTime()) / 86400000);
}

/** $0.0412 — costs here are small enough that four places are the useful ones. */
export function usd(value: number): string {
  if (!Number.isFinite(value)) return "—";
  if (value >= 10) return `$${value.toFixed(2)}`;
  return `$${value.toFixed(4)}`;
}

export function percent(value: number, digits = 0): string {
  if (!Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return n === 1 ? one : many;
}

export function formatDuration(ms: number): string {
  const secs = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  if (m === 0) return `${s}s`;
  return `${m}m ${String(s).padStart(2, "0")}s`;
}
