import assert from "node:assert/strict";
import { test } from "node:test";
import { hhmm, madridDate, madridEpoch, nextTrains, type Day } from "./search.ts";
import { classify, parseFeed } from "./status.ts";

test("Madrid time: winter is UTC+1, summer UTC+2", () => {
  assert.equal(madridEpoch("2026-11-21", 7 * 60), Date.UTC(2026, 10, 21, 6, 0));
  assert.equal(madridEpoch("2026-07-01", 7 * 60), Date.UTC(2026, 6, 1, 5, 0));
  assert.equal(hhmm(Date.UTC(2026, 10, 21, 6, 5)), "07:05");
  assert.equal(madridDate(Date.UTC(2026, 10, 21, 23, 30)), "2026-11-22");
});

const day = (date: string, trips: Day["trips"]): Day => ({ date, trips });

test("lists trains that call at A and later at B, in time order, within the window", () => {
  const d = day("2026-11-21", [
    ["late", "R4", [[1, 470, 470], [2, 490, 490]]],      // 07:50 from stop 1
    ["early", "R4", [[1, 450, 450], [2, 470, 470]]],     // 07:30
    ["wrong-way", "R4", [[2, 460, 460], [1, 480, 480]]], // B before A
    ["far", "R4", [[1, 900, 900], [2, 920, 920]]],       // 15:00, outside the 4 h window
  ]);
  const now = madridEpoch("2026-11-21", 7 * 60 + 25);
  const r = nextTrains([d], 1, 2, now);
  assert.deepEqual(r.map((x) => x.tripId), ["early", "late"]);
  assert.equal(hhmm(r[0].arrEpoch), "07:50");
});

test("a train from yesterday's timetable that leaves after midnight is found", () => {
  const y = day("2026-11-20", [["night", "R2", [[1, 24 * 60 + 10, 24 * 60 + 10], [2, 24 * 60 + 30, 24 * 60 + 30]]]]);
  const now = madridEpoch("2026-11-21", 0);
  assert.equal(nextTrains([y], 1, 2, now).length, 1);
});

test("a train that left 4 minutes ago still shows, one that left 10 does not", () => {
  const d = day("2026-11-21", [["a", "R1", [[1, 600, 600], [2, 620, 620]]], ["b", "R1", [[1, 594, 594], [2, 610, 610]]]]);
  const now = madridEpoch("2026-11-21", 604);
  assert.deepEqual(nextTrains([d], 1, 2, now).map((x) => x.tripId), ["a"]);
});

test("status words", () => {
  assert.equal(classify(undefined).kind, "no-update");
  assert.equal(classify({ canceled: true, delaySec: null }).kind, "cancelled");
  assert.equal(classify({ canceled: false, delaySec: 14 * 60 }).kind, "running");
  assert.equal(classify({ canceled: false, delaySec: 16 * 60 }).word, "late: the feed says 16 min");
  assert.equal(classify({ canceled: false, delaySec: 0 }).word, "running as planned");
});

type Rt = any; // eslint-disable-line
test("feed decoding: cancelled flag and delay", async () => {
  const mod = (await import("gtfs-realtime-bindings")) as unknown as { transit_realtime?: Rt; default?: { transit_realtime: Rt } };
  const rt = (mod.transit_realtime ?? mod.default!.transit_realtime) as Rt;
  const msg = rt.FeedMessage.create({
    header: { gtfsRealtimeVersion: "2.0", timestamp: 1795293739 },
    entity: [
      { id: "1", tripUpdate: { trip: { tripId: "T1", scheduleRelationship: rt.TripDescriptor.ScheduleRelationship.CANCELED } } },
      { id: "2", tripUpdate: { trip: { tripId: "T2" }, delay: 1200, stopTimeUpdate: [{ stopId: "71801", arrival: { delay: 1200 } }] } },
    ],
  });
  const { live, feedTime } = await parseFeed(rt.FeedMessage.encode(msg).finish());
  assert.equal(feedTime, 1795293739000);
  assert.equal(live.get("T1")?.canceled, true);
  assert.equal(live.get("T2")?.delaySec, 1200);
});

import { plan } from "./journey.ts";

const t0 = madridEpoch("2026-11-21", 8 * 60);
const net = day("2026-11-21", [
  ["d1", "R1", [[1, 480, 490], [3, 520, 520]]],               // direct 1 -> 3 at 08:10, arrives 08:40
  ["a", "R2", [[1, 485, 495], [2, 510, 512]]],                // 1 -> 2
  ["b", "R3", [[2, 520, 525], [3, 550, 550]]],                // 2 -> 3, leaves 08:45 (after a 3-min change at 2 would be too tight: a arrives 08:30)
  ["tight", "R3", [[2, 511, 512], [3, 540, 540]]],            // leaves 08:32, 2 minutes after a arrives
]);

test("direct train is listed first when it exists", () => {
  const j = plan([net], 1, 3, t0, new Set());
  assert.equal(j[0].legs.length, 1);
  assert.equal(j[0].legs[0].tripId, "d1");
});

test("a cancelled direct train is skipped and a change is offered instead", () => {
  const j = plan([net], 1, 3, t0, new Set(["d1"]));
  assert.equal(j.length, 1);
  assert.deepEqual(j[0].legs.map((l) => l.tripId), ["a", "b"]);
});

test("changes need at least 4 minutes", () => {
  const only = day("2026-11-21", [net.trips[1], net.trips[3]]);
  assert.equal(plan([only], 1, 3, t0, new Set()).length, 0);
});

test("never uses a cancelled train, and finds nothing when none is left", () => {
  assert.equal(plan([net], 1, 3, t0, new Set(["d1", "a"])).length, 0);
});

import { dayClock } from "./search.ts";

test("clock changes: the fast path agrees with the exact one on every day of 2026", () => {
  for (let d = Date.UTC(2026, 0, 1); d < Date.UTC(2027, 0, 1); d += 86400e3) {
    const date = new Date(d).toISOString().slice(0, 10);
    const at = dayClock(date);
    for (const m of [0, 150, 180, 600, 1439, 1500]) assert.equal(at(m), madridEpoch(date, m), `${date} ${m}`);
  }
});
