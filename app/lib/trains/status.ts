// What Renfe's live feed says about a trip. The feed's delay numbers are often stale or carried forward, so a delay
// is only called "late" when it is large; the cancelled flag is the clearest signal.

export type Live = { canceled: boolean; delaySec: number | null };
export type Status = { kind: "cancelled" | "late" | "running" | "no-update"; delayMin: number | null; word: string };

export const LATE_MIN = 15;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Rt = any;

export function classify(live: Live | undefined): Status {
  if (!live) return { kind: "no-update", delayMin: null, word: "no update in the feed yet" };
  if (live.canceled) return { kind: "cancelled", delayMin: null, word: "cancelled" };
  const m = live.delaySec == null ? null : Math.round(live.delaySec / 60);
  if (m != null && m >= LATE_MIN) return { kind: "late", delayMin: m, word: `late: the feed says ${m} min` };
  return { kind: "running", delayMin: m, word: m != null && m > 0 ? `running, feed shows ${m} min late` : "running as planned" };
}

/** Decode the protobuf feed into trip id -> live state. */
export async function parseFeed(buf: ArrayBuffer | Uint8Array): Promise<{ live: Map<string, Live>; feedTime: number }> {
  const mod = (await import("gtfs-realtime-bindings")) as unknown as { transit_realtime?: Rt; default?: { transit_realtime: Rt } };
  const rt = (mod.transit_realtime ?? mod.default!.transit_realtime) as Rt;
  const msg = rt.FeedMessage.decode(buf instanceof Uint8Array ? buf : new Uint8Array(buf));
  const live = new Map<string, Live>();
  for (const e of msg.entity) {
    const tu = e.tripUpdate;
    const id = tu?.trip?.tripId;
    if (!tu || !id) continue;
    const upd = tu.stopTimeUpdate?.[0];
    const d = tu.delay ?? upd?.departure?.delay ?? upd?.arrival?.delay ?? null;
    live.set(id, { canceled: tu.trip?.scheduleRelationship === rt.TripDescriptor.ScheduleRelationship.CANCELED, delaySec: d == null ? null : Number(d) });
  }
  return { live, feedTime: Number(msg.header?.timestamp ?? 0) * 1000 };
}

export type Vehicle = { trip: string; line: string; lat: number; lon: number; stop: string; status: number; ts: number };

/** Positions of Rodalies trains (trip ids starting with 51) from the vehicle feed. */
export async function parseVehicles(buf: ArrayBuffer | Uint8Array): Promise<{ vehicles: Vehicle[]; feedTime: number }> {
  const mod = (await import("gtfs-realtime-bindings")) as unknown as { transit_realtime?: Rt; default?: { transit_realtime: Rt } };
  const rt = (mod.transit_realtime ?? mod.default!.transit_realtime) as Rt;
  const msg = rt.FeedMessage.decode(buf instanceof Uint8Array ? buf : new Uint8Array(buf));
  const vehicles: Vehicle[] = [];
  for (const e of msg.entity) {
    const v = e.vehicle;
    const id = v?.trip?.tripId as string | undefined;
    if (!v || !id || !id.startsWith("51") || v.position?.latitude == null) continue;
    vehicles.push({ trip: id, line: String(v.vehicle?.label ?? "").split("-")[0], lat: v.position.latitude, lon: v.position.longitude, stop: String(v.stopId ?? ""), status: Number(v.currentStatus ?? 2), ts: Number(v.timestamp ?? 0) * 1000 });
  }
  return { vehicles, feedTime: Number(msg.header?.timestamp ?? 0) * 1000 };
}
