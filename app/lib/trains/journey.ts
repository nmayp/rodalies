// Plan B: journeys from A to B with at most one change, never using a train in `blocked` (cancelled).
import { dayClock, type Day } from "./search.ts";

export type Leg = { tripId: string; line: string; from: number; to: number; depEpoch: number; arrEpoch: number };
export type Journey = { legs: Leg[]; depEpoch: number; arrEpoch: number };

type Call = { stop: number; arr: number; dep: number };
type T = { tripId: string; line: string; calls: Call[] };

function absolute(days: Day[], lo: number, hi: number): T[] {
  const out: T[] = [];
  for (const d of days) { const at = dayClock(d.date); for (const [tripId, line, stops] of d.trips) {
    const first = at(stops[0][2]);
    if (first > hi) continue;
    const calls = stops.map((s) => ({ stop: s[0], arr: at(s[1]), dep: at(s[2]) }));
    if (calls[calls.length - 1].arr < lo || calls[0].dep > hi) continue;
    out.push({ tripId, line, calls });
  } }
  return out;
}

export function plan(days: Day[], from: number, to: number, now: number, blocked: Set<string>, opts: { minTransfer?: number; limit?: number; horizonMin?: number; graceMin?: number } = {}): Journey[] {
  const { minTransfer = 4, limit = 4, horizonMin = 240, graceMin = 5 } = opts;
  const lo = now - graceMin * 60e3, hi = now + horizonMin * 60e3;
  const trips = absolute(days, lo, hi + 3 * 3600e3).filter((t) => !blocked.has(t.tripId));
  const byStop = new Map<number, { t: T; i: number }[]>();
  for (const t of trips) t.calls.forEach((c, i) => { const a = byStop.get(c.stop) ?? []; a.push({ t, i }); byStop.set(c.stop, a); });
  const leg = (t: T, i: number, j: number): Leg => ({ tripId: t.tripId, line: t.line, from: t.calls[i].stop, to: t.calls[j].stop, depEpoch: t.calls[i].dep, arrEpoch: t.calls[j].arr });
  const found: Journey[] = [];
  for (const { t: A, i } of byStop.get(from) ?? []) {
    const dep = A.calls[i].dep;
    if (dep < lo || dep > hi) continue;
    const j = A.calls.findIndex((c, k) => k > i && c.stop === to);
    if (j >= 0) found.push({ legs: [leg(A, i, j)], depEpoch: dep, arrEpoch: A.calls[j].arr });
    for (let k = i + 1; k < A.calls.length; k++) {
      const X = A.calls[k];
      if (X.stop === to) continue;
      let best: { B: T; bi: number; bj: number } | null = null;
      for (const { t: B, i: bi } of byStop.get(X.stop) ?? []) {
        if (B === A || B.calls[bi].dep < X.arr + minTransfer * 60e3) continue;
        const bj = B.calls.findIndex((c, q) => q > bi && c.stop === to);
        if (bj < 0) continue;
        if (!best || B.calls[bj].arr < best.B.calls[best.bj].arr) best = { B, bi, bj };
      }
      if (best) found.push({ legs: [leg(A, i, k), leg(best.B, best.bi, best.bj)], depEpoch: dep, arrEpoch: best.B.calls[best.bj].arr });
    }
  }
  // best arrival per first train, then drop journeys that leave later and arrive no earlier than another
  const bestPerFirst = new Map<string, Journey>();
  for (const j of found) {
    const key = j.legs[0].tripId;
    const cur = bestPerFirst.get(key);
    if (!cur || j.arrEpoch < cur.arrEpoch || (j.arrEpoch === cur.arrEpoch && j.legs.length < cur.legs.length)) bestPerFirst.set(key, j);
  }
  const list = [...bestPerFirst.values()].sort((a, b) => a.arrEpoch - b.arrEpoch || b.depEpoch - a.depEpoch);
  const kept: Journey[] = [];
  for (const j of list) if (!kept.some((k) => k.depEpoch >= j.depEpoch && k.arrEpoch <= j.arrEpoch)) kept.push(j);
  return kept.sort((a, b) => a.depEpoch - b.depEpoch).slice(0, limit);
}
