import { readFile } from "node:fs/promises";
import path from "node:path";
import { hhmm, madridDate, nextTrains, type Day, type Trip } from "@/lib/trains/search";
import { classify, parseFeed } from "@/lib/trains/status";
import { plan } from "@/lib/trains/journey";

export const runtime = "nodejs";
const FEED = "https://gtfsrt.renfe.com/trip_updates.pb";
const DIR = path.join(process.cwd(), "public", "trains");

let ids: string[] | null = null;
async function stopIndex(id: string): Promise<number> {
  if (!ids) ids = (JSON.parse(await readFile(path.join(DIR, "stops.json"), "utf8")) as { ids: string[] }).ids;
  return ids.indexOf(id);
}

async function loadDay(date: string): Promise<Day | null> {
  try {
    return { date, trips: JSON.parse(await readFile(path.join(DIR, "days", `${date}.json`), "utf8")) as Trip[] };
  } catch {
    return null;
  }
}

export async function GET(req: Request) {
  const u = new URL(req.url);
  const fromId = u.searchParams.get("from") ?? "", toId = u.searchParams.get("to") ?? "";
  const from = await stopIndex(fromId), to = await stopIndex(toId);
  const now = u.searchParams.get("now") ? Date.parse(u.searchParams.get("now") as string) : Date.now();
  if (from < 0 || to < 0 || from === to) return Response.json({ error: "pick two different stations" }, { status: 400 });
  const days = (await Promise.all([-1, 0, 1].map((d) => loadDay(madridDate(now, d))))).filter((d): d is Day => d !== null);
  if (days.length === 0) return Response.json({ error: "the timetable has no file for today", trains: [] }, { status: 503 });
  const found = nextTrains(days, from, to, now);
  let live = new Map(), feedTime = 0, feedOk = true;
  try {
    const r = await fetch(FEED, { next: { revalidate: 20 } });
    if (!r.ok) throw new Error(String(r.status));
    ({ live, feedTime } = await parseFeed(await r.arrayBuffer()));
  } catch {
    feedOk = false;
  }
  const blocked = new Set<string>([...live.entries()].filter(([, v]) => v.canceled).map(([k]) => k));
  const allIds = ids as string[];
  const planB = plan(days, from, to, now, blocked).map((j) => ({
    dep: hhmm(j.depEpoch), arr: hhmm(j.arrEpoch), changes: j.legs.length - 1,
    legs: j.legs.map((l) => ({ trip: l.tripId, line: l.line, from: allIds[l.from], to: allIds[l.to], dep: hhmm(l.depEpoch), arr: hhmm(l.arrEpoch), late: live.get(l.tripId) ? classify(live.get(l.tripId)).kind === "late" : false })),
  }));
  return Response.json({
    now, feedOk, planB, cancelledNow: blocked.size, feedAgeSec: feedTime ? Math.round((now - feedTime) / 1000) : null,
    trains: found.map((f) => ({ trip: f.tripId, line: f.line, dep: hhmm(f.depEpoch), arr: hhmm(f.arrEpoch), ...(feedOk ? classify(live.get(f.tripId)) : { kind: "no-update", delayMin: null, word: "live feed unavailable" }) })),
  }, { headers: { "cache-control": "public, s-maxage=20, stale-while-revalidate=40" } });
}
