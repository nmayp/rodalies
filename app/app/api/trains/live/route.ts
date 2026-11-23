import { classify, parseFeed, parseVehicles } from "@/lib/trains/status";

export const runtime = "nodejs";
const BASE = "https://gtfsrt.renfe.com";

export async function GET() {
  const get = (f: string) => fetch(`${BASE}/${f}`, { next: { revalidate: 15 } }).then((r) => { if (!r.ok) throw new Error(String(r.status)); return r.arrayBuffer(); });
  try {
    const [vb, tb] = await Promise.all([get("vehicle_positions.pb"), get("trip_updates.pb")]);
    const [{ vehicles, feedTime }, { live }] = await Promise.all([parseVehicles(vb), parseFeed(tb)]);
    const out = vehicles.map((v) => ({ ...v, ...classify(live.get(v.trip)) }));
    const cancelled = [...live.entries()].filter(([k, x]) => k.startsWith("51") && x.canceled).length;
    return Response.json({ now: Date.now(), feedAgeSec: feedTime ? Math.round((Date.now() - feedTime) / 1000) : null, vehicles: out, cancelledInFeed: cancelled },
      { headers: { "cache-control": "public, s-maxage=15, stale-while-revalidate=30" } });
  } catch {
    return Response.json({ error: "the live feed is not answering", vehicles: [], cancelledInFeed: 0 }, { status: 502 });
  }
}
