"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import RodaliesMap, { useLive } from "./RodaliesMap";

type Stops = { ids: string[]; names: [string, string, string][] };
type Train = { trip: string; line: string; dep: string; arr: string; kind: "cancelled" | "late" | "running" | "no-update"; word: string };
type Leg = { trip: string; line: string; from: string; to: string; dep: string; arr: string; late: boolean };
type Plan = { dep: string; arr: string; changes: number; legs: Leg[] };
type Reply = { feedOk: boolean; feedAgeSec: number | null; trains: Train[]; planB?: Plan[]; error?: string };
type Index = { generated: string; dates: string[]; trips: number };

const norm = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

function Pick({ label, value, onPick, stops }: { label: string; value: string; onPick: (id: string) => void; stops: Stops }) {
  const [q, setQ] = useState<string | null>(null);
  const name = stops.names[stops.ids.indexOf(value)]?.[0] ?? "";
  const hits = useMemo(() => {
    if (!q || q.length < 2) return [];
    const n = norm(q);
    return stops.names.map((x, i) => [x[0], stops.ids[i]] as const).filter(([nm]) => norm(nm).includes(n)).slice(0, 4);
  }, [q, stops]);
  return (
    <div className="sky-ctl">
      <label htmlFor={`tr-${label}`}>{label}</label>
      <input id={`tr-${label}`} value={q ?? name} onFocus={(e) => e.currentTarget.select()} onChange={(e) => setQ(e.target.value)} placeholder="Type a station" />
      {hits.length > 0 && (
        <ul className="sky-pick">
          {hits.map(([nm, id]) => <li key={id}><button type="button" className="see-more" onClick={() => { onPick(id); setQ(null); }}>{nm}</button></li>)}
        </ul>
      )}
    </div>
  );
}

const say = (t: Train) => (t.kind === "cancelled" ? "cancelled" : t.word);

function TripCheck() {
  const [stops, setStops] = useState<Stops | null>(null);
  const [from, setFrom] = useState("71801"); // Barcelona-Sants
  const [to, setTo] = useState("79500"); // Mataro
  const [reply, setReply] = useState<Reply | null>(null);

  useEffect(() => { fetch("/trains/stops.json").then((r) => r.json()).then(setStops).catch(() => {}); }, []);
  const load = useCallback(async () => {
    try { setReply(await (await fetch(`/api/trains?from=${from}&to=${to}`)).json()); } catch { setReply({ feedOk: false, feedAgeSec: null, trains: [], error: "could not reach the server" }); }
  }, [from, to]);
  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, [load]);

  if (!stops) return <p className="note">Loading…</p>;
  const nm = (id: string) => stops.names[stops.ids.indexOf(id)]?.[0] ?? id;
  const trains = reply?.trains ?? [];
  const first = trains[0];
  const trouble = trains.some((t) => t.kind === "cancelled" || t.kind === "late");
  const b = (reply?.planB ?? [])[0];
  const lead = !reply ? "Checking…" : reply.error ? reply.error : first ? `Next: ${first.line} at ${first.dep}, ${say(first)}. Arrives ${first.arr}.` : "No direct train in the next 4 hours.";
  return (
    <>
      <div className="pair">
        <Pick label="From" value={from} onPick={setFrom} stops={stops} />
        <Pick label="To" value={to} onPick={setTo} stops={stops} />
      </div>
      <p className="lead small">{lead}</p>
      {trains.length > 1 && (
        <table>
          <tbody>
            {trains.slice(1, 4).map((t) => (
              <tr key={t.trip}><th scope="row">{t.dep} → {t.arr}</th><td>{t.line}</td><td>{t.kind === "cancelled" ? <b>cancelled</b> : t.word}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      {trouble && b && <p><b>Plan B:</b> {b.legs.map((l, k) => <span key={l.trip}>{k > 0 ? ", then " : ""}{l.line} {l.dep} from {nm(l.from)}</span>)}, arrives {b.arr}.</p>}
      <p className="note">
        <button type="button" className="see-more sky-inline" onClick={() => { setFrom(to); setTo(from); }}>swap</button>{" "}
        {reply?.feedOk === false ? "The live feed is not answering." : reply?.feedAgeSec != null ? `Live feed, ${reply.feedAgeSec} s old.` : ""}
      </p>
    </>
  );
}

const STATE = ["about to reach", "stopped at", "heading to"];

function TripMap() {
  const live = useLive();
  const [stops, setStops] = useState<Stops | null>(null);
  const [line, setLine] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  useEffect(() => { fetch("/trains/stops.json").then((r) => r.json()).then(setStops).catch(() => {}); }, []);
  const v = live?.vehicles ?? [];
  const late = v.filter((x) => x.kind === "late" || x.kind === "cancelled").length;
  const lines = [...new Set(v.map((x) => x.line))].sort((a, b) => a.localeCompare(b, "en", { numeric: true }));
  const t = v.find((x) => x.trip === sel);
  const stopName = t && stops ? stops.names[stops.ids.indexOf(t.stop)]?.[0] : undefined;
  return (
    <>
      <p className="lead small">
        {t ? `${t.line}: ${t.kind === "cancelled" ? "cancelled" : t.word ?? t.kind}${stopName ? `, ${STATE[t.status] ?? "near"} ${stopName}` : ""}.` : live ? `${v.length} trains running, ${late} cancelled or 15+ min late. Click one.` : "Reading live positions…"}
      </p>
      <div className="bench-chart map">
        <RodaliesMap live={live} big line={line} selected={sel} onSelect={setSel} />
      </div>
      <div className="sky-chips">
        {lines.map((l) => <button key={l} type="button" className="see-more" aria-pressed={line === l} onClick={() => { setLine(line === l ? null : l); setSel(null); }}>{l}</button>)}
      </div>
    </>
  );
}

function TripData() {
  const [idx, setIdx] = useState<Index | null>(null);
  const [hist, setHist] = useState<History | null>(null);
  useEffect(() => { fetch("/trains/index.json").then((r) => r.json()).then(setIdx).catch(() => {}); }, []);
  useEffect(() => { fetch("/trains/history.json").then((r) => r.json()).then(setHist).catch(() => {}); }, []);
  const cancelRate = hist ? ((hist.cancelled / hist.trips) * 100).toFixed(1) : null;
  return (
    <>
      <ul className="tiles">
        <li><span className="n">{idx ? idx.trips.toLocaleString("en-GB") : "–"}</span><span className="l">trips in the timetable</span></li>
        <li><span className="n">11</span><span className="l">tests: midnight, clock changes, plan B</span></li>
        {cancelRate && <li><span className="n">{cancelRate}%</span><span className="l">cancelled last {hist!.days.length} days (Renfe feed)</span></li>}
      </ul>
      <table>
        <thead><tr><th>Source</th><th>Used for</th><th>Refresh</th></tr></thead>
        <tbody>
          <tr><th scope="row">Renfe timetable (GTFS)</th><td>trains between two stations</td><td>{idx ? `daily, ${idx.dates.length} days ahead` : "daily"}</td></tr>
          <tr><th scope="row">Renfe real-time feed</th><td>cancelled, late, positions</td><td>every 15 s</td></tr>
        </tbody>
      </table>
      <p className="note">{idx ? `Timetable rebuilt ${idx.generated.slice(0, 10)}. ` : ""}Renfe open data, CC BY 4.0. Tests cover midnight trips, clock changes, and plan B journeys that skip cancelled trains.</p>
    </>
  );
}

function FeedValidation() {
  const [hist, setHist] = useState<History | null>(null);
  useEffect(() => { fetch("/trains/history.json").then((r) => r.json()).then(setHist).catch(() => {}); }, []);
  if (!hist) return null;
  const rate = ((hist.cancelled / hist.trips) * 100).toFixed(1);
  return (
    <>
      <table>
        <thead><tr><th>Period</th><th>Trips</th><th>Cancelled</th><th>Rate</th></tr></thead>
        <tbody>
          {hist.byDay.slice(-7).map(([d, trips, cancelled]) => (
            <tr key={d}><th scope="row">{d}</th><td>{trips}</td><td>{cancelled}</td><td>{((cancelled / trips) * 100).toFixed(1)}%</td></tr>
          ))}
        </tbody>
      </table>
      <p className="note">
        {hist.days.length}-day cancellation rate: <b>{rate}%</b> of {hist.trips.toLocaleString("en-GB")} scheduled Rodalies trips (Renfe feed, resolved trips only).
        Feed rebuilt {hist.generated.slice(0, 10)} from TrainArchive.eu. The feed&apos;s delay numbers are often stale; only cancellations are counted here.
      </p>
    </>
  );
}

export default function TrainsPanel() {
  return (
    <>
      <section>
        <h2>Your trip</h2>
        <TripCheck />
      </section>
      <section>
        <h2>Live map</h2>
        <TripMap />
      </section>
      <section>
        <h2>How to read it</h2>
        <ul className="plain">
          <li><b>Cancelled</b> is the feed&apos;s own flag: the clearest signal.</li>
          <li><b>Late</b> only from 15 minutes: smaller delays in the feed are often stale.</li>
          <li><b>No update yet</b> is normal for trains further ahead.</li>
          <li><b>Plan B</b> appears only when a train is cancelled or late, with one change at most.</li>
          <li><b>Times</b> are Madrid time; midnight and clock changes are tested.</li>
        </ul>
      </section>
      <section>
        <h2>Data</h2>
        <TripData />
      </section>
      <section>
        <h2>Validation</h2>
        <FeedValidation />
      </section>
    </>
  );
}
