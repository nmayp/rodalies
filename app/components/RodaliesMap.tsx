"use client";

import { useEffect, useMemo, useState } from "react";

type Stops = { ids: string[]; names: [string, string, string][] };
type Net = { lines: string[]; edges: [number, number, number][] };
export type V = { trip: string; line: string; lat: number; lon: number; stop: string; status: number; kind: string; word?: string; delayMin?: number };
export type Live = { vehicles: V[]; cancelledInFeed: number; feedAgeSec: number | null; error?: string };

const BLUE = "#1840ff";

export function useLive(every = 15000) {
  const [d, setD] = useState<Live | null>(null);
  useEffect(() => {
    let on = true;
    const go = () => fetch("/api/trains/live").then((r) => r.json()).then((j) => on && setD(j)).catch(() => on && setD({ vehicles: [], cancelledInFeed: 0, feedAgeSec: null, error: "no answer" }));
    go();
    const t = setInterval(go, every);
    return () => { on = false; clearInterval(t); };
  }, [every]);
  return d;
}

export default function RodaliesMap({ from, to, live, big, line, selected, onSelect }: { from?: string; to?: string; live?: Live | null; big?: boolean; line?: string | null; selected?: string | null; onSelect?: (trip: string | null) => void }) {
  const [stops, setStops] = useState<Stops | null>(null);
  const [net, setNet] = useState<Net | null>(null);
  useEffect(() => {
    fetch("/trains/stops.json").then((r) => r.json()).then(setStops).catch(() => {});
    fetch("/trains/network.json").then((r) => r.json()).then(setNet).catch(() => {});
  }, []);
  const geo = useMemo(() => {
    if (!stops) return null;
    const pts = stops.names.map((n) => [parseFloat(n[2]), parseFloat(n[1])]);
    const ok = pts.filter((p) => isFinite(p[0]) && isFinite(p[1]));
    const k = Math.cos((41.5 * Math.PI) / 180);
    const x0 = Math.min(...ok.map((p) => p[0])), x1 = Math.max(...ok.map((p) => p[0]));
    const y0 = Math.min(...ok.map((p) => p[1])), y1 = Math.max(...ok.map((p) => p[1]));
    const W = 1000, H = Math.max(300, Math.round(((y1 - y0) / ((x1 - x0) * k)) * W));
    const px = (lon: number) => 20 + ((lon - x0) / (x1 - x0)) * (W - 40);
    const py = (lat: number) => 20 + ((y1 - lat) / (y1 - y0)) * (H - 40);
    return { pts, W, H, px, py };
  }, [stops]);
  if (!geo || !stops || !net) return <p className="note">Loading map…</p>;
  const { pts, W, H, px, py } = geo;
  const fi = from ? stops.ids.indexOf(from) : -1, ti = to ? stops.ids.indexOf(to) : -1;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Rodalies network and live trains" style={{ width: "100%", maxWidth: "none", height: big ? "72vh" : "auto", maxHeight: big ? "none" : "16em" }} preserveAspectRatio="xMidYMid meet" onClick={onSelect ? () => onSelect(null) : undefined}>
      <g stroke="currentColor" fill="none">
        {net.edges.map(([l, a, b], i) => {
          if (!(isFinite(pts[a]?.[0]) && isFinite(pts[b]?.[0]))) return null;
          const on = line ? net.lines[l] === line : false;
          return <line key={i} x1={px(pts[a][0])} y1={py(pts[a][1])} x2={px(pts[b][0])} y2={py(pts[b][1])} strokeOpacity={line ? (on ? 0.9 : 0.1) : 0.25} strokeWidth={on ? 3 : 1.5} />;
        })}
      </g>
      <g fill="currentColor" fillOpacity={0.35}>
        {pts.map((p, i) => (isFinite(p[0]) ? <circle key={i} cx={px(p[0])} cy={py(p[1])} r={2} /> : null))}
      </g>
      {live?.vehicles.map((v) => {
        const bad = v.kind === "late" || v.kind === "cancelled";
        const dim = line ? v.line !== line : false;
        const sel = selected === v.trip;
        const x = px(v.lon), y = py(v.lat);
        return (
          <g key={v.trip} style={{ cursor: onSelect && !dim ? "pointer" : undefined, pointerEvents: dim ? "none" : undefined }} opacity={dim ? 0.15 : 1} onClick={onSelect ? (e) => { e.stopPropagation(); onSelect(sel ? null : v.trip); } : undefined}>
            <title>{`${v.line}: ${v.word ?? v.kind}`}</title>
            <circle cx={x} cy={y} r={16} fill="transparent" />
            <circle cx={x} cy={y} r={bad ? 7 : 5} fill={bad ? BLUE : "currentColor"} />
            {sel && <circle cx={x} cy={y} r={14} fill="none" stroke={BLUE} strokeWidth={3} />}
            {sel && <text x={x + 20} y={y - 14} fontSize={24} fontWeight={700} fill="currentColor">{v.line}</text>}
          </g>
        );
      })}
      {[fi, ti].map((i, n) => (i >= 0 && isFinite(pts[i][0]) ? (
        <g key={n}>
          <circle cx={px(pts[i][0])} cy={py(pts[i][1])} r={11} fill="none" stroke={BLUE} strokeWidth={3} />
          <text x={px(pts[i][0]) + 16} y={py(pts[i][1]) + 5} fontSize={22} fill="currentColor">{stops.names[i][0]}</text>
        </g>
      ) : null))}
    </svg>
  );
}
