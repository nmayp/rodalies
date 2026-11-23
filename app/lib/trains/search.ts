// Which trains go from A to B soon, from the timetable alone. Times in the files are minutes after midnight of the
// service date and may pass 24:00, so yesterday's late trains are looked at too.

export type Trip = [string, string, [number, number, number][]]; // trip id, line, [[stop index, arrival min, departure min], ...]
export type Day = { date: string; trips: Trip[] };
export type Found = { tripId: string; line: string; depEpoch: number; arrEpoch: number; date: string };

const TZ = "Europe/Madrid";

/** Epoch ms for a Madrid-local date (YYYY-MM-DD) plus minutes after midnight. */
export function madridEpoch(date: string, minutes: number): number {
  const [y, m, d] = date.split("-").map(Number);
  const want = Date.UTC(y, m - 1, d, 0, minutes);
  let t = want;
  for (let i = 0; i < 3; i++) t = want - offset(t);
  return t;
}

const FMT = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hourCycle: "h23", year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric", second: "numeric" });
const HM = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const DAY = new Intl.DateTimeFormat("en-CA", { timeZone: TZ });

export function offset(ms: number): number {
  const f = FMT;
  const p = Object.fromEntries(f.formatToParts(new Date(ms)).map((x) => [x.type, +x.value]));
  return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second) - Math.floor(ms / 1000) * 1000;
}

export const madridDate = (ms: number, shiftDays = 0) =>
  DAY.format(new Date(ms + shiftDays * 86400e3));

export const hhmm = (ms: number) => HM.format(new Date(ms));

/** Trains that call at `from` and later at `to`, leaving between `now - graceMin` and `now + horizonMin`. */
/** Fast converter for one service date: a fixed offset, unless that day changes clocks, then the exact (slower) way. */
export function dayClock(date: string): (minutes: number) => number {
  const base = madridEpoch(date, 0);
  if (offset(base + 6 * 3600e3) === offset(base + 30 * 3600e3 - 1) && offset(base) === offset(base + 6 * 3600e3)) return (m) => base + m * 60e3;
  return (m) => madridEpoch(date, m);
}

export function nextTrains(days: Day[], from: number, to: number, now: number, limit = 5, graceMin = 5, horizonMin = 240): Found[] {
  const lo = now - graceMin * 60e3, hi = now + horizonMin * 60e3;
  const out: Found[] = [];
  for (const day of days) {
    const at = dayClock(day.date);
    for (const [tripId, line, stops] of day.trips) {
      const i = stops.findIndex((s) => s[0] === from);
      if (i < 0) continue;
      const j = stops.findIndex((s, k) => k > i && s[0] === to);
      if (j < 0) continue;
      const dep = at(stops[i][2]);
      if (dep < lo || dep > hi) continue;
      out.push({ tripId, line, depEpoch: dep, arrEpoch: at(stops[j][1]), date: day.date });
    }
  }
  return out.sort((a, b) => a.depEpoch - b.depEpoch).slice(0, limit);
}
