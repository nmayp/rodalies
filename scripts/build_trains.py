"""Turn Renfe's open Cercanias timetable into small per-day files for Rodalies (nucleus 51).

    python3 scripts/build_trains.py [path/to/fomento_transit.zip]

Writes app/public/trains/stops.json, app/public/trains/network.json, app/public/trains/index.json and app/public/trains/days/YYYY-MM-DD.json.
Only the standard library is used so it can run on a bare CI runner.
Source: Renfe Operadora open data, CC BY 4.0 (https://data.renfe.com).
"""
import csv
import io
import json
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

URL = "https://ssl.renfe.com/ftransit/Fichero_CER_FOMENTO/fomento_transit.zip"
OUT = Path(__file__).resolve().parent.parent / "app" / "public" / "trains"


def rows(zf, name):
    with zf.open(name) as fh:
        for r in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig")):
            yield {k.strip(): (v or "").strip() for k, v in r.items()}


def secs(t):
    h, m, s = (int(x) for x in t.split(":"))
    return h * 3600 + m * 60 + s


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    if src:
        zf = zipfile.ZipFile(src)
    else:
        zf = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(URL, timeout=120).read()))
    routes = {r["route_id"]: r["route_short_name"] for r in rows(zf, "routes.txt") if r["route_id"].startswith("51")}
    trips = {r["trip_id"]: (routes[r["route_id"]], r["service_id"]) for r in rows(zf, "trips.txt") if r["route_id"] in routes}
    days = {}
    for c in rows(zf, "calendar.txt"):
        if c["start_date"] == c["end_date"]:
            days[c["service_id"]] = f"{c['start_date'][:4]}-{c['start_date'][4:6]}-{c['start_date'][6:]}"
    stop_names = {s["stop_id"]: (s["stop_name"], s.get("stop_lat", ""), s.get("stop_lon", "")) for s in rows(zf, "stops.txt")}
    by_trip = {}
    for st in rows(zf, "stop_times.txt"):
        tid = st["trip_id"]
        if tid in trips:
            by_trip.setdefault(tid, []).append((int(st["stop_sequence"]), st["stop_id"], secs(st["arrival_time"]), secs(st["departure_time"])))
    used = sorted({s[1] for v in by_trip.values() for s in v})
    stops = {sid: [stop_names[sid][0], stop_names[sid][1], stop_names[sid][2]] for sid in used if sid in stop_names}
    sidx = {sid: i for i, sid in enumerate(used)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "days").mkdir(exist_ok=True)
    for old in (OUT / "days").glob("*.json"):
        old.unlink()
    # network drawing: every pair of neighbouring stops that some train runs between, per line
    lines = sorted({trips[t][0] for t in by_trip})
    edges = set()
    for tid, seq in by_trip.items():
        seq.sort()
        li = lines.index(trips[tid][0])
        for a, b in zip(seq, seq[1:]):
            x, y = sidx[a[1]], sidx[b[1]]
            edges.add((li, min(x, y), max(x, y)))
    (OUT / "network.json").write_text(json.dumps({"lines": lines, "edges": sorted(edges)}, separators=(",", ":")))
    per_day = {}
    for tid, seq in by_trip.items():
        line, svc = trips[tid]
        d = days.get(svc)
        if not d:
            continue
        seq.sort()
        per_day.setdefault(d, []).append([tid, line, [[sidx[s[1]], s[2] // 60, s[3] // 60] for s in seq]])
    for d, tr in per_day.items():
        tr.sort(key=lambda t: t[2][0][2])
        (OUT / "days" / f"{d}.json").write_text(json.dumps(tr, separators=(",", ":")))
    (OUT / "stops.json").write_text(json.dumps({"ids": used, "names": [stops.get(s, [s, "", ""]) for s in used]}, ensure_ascii=False, separators=(",", ":")))
    (OUT / "index.json").write_text(json.dumps({"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "dates": sorted(per_day),
                                                "source": "Renfe Operadora open data, CC BY 4.0", "trips": sum(len(v) for v in per_day.values())}))
    print(len(per_day), "days,", sum(len(v) for v in per_day.values()), "trips,", len(used), "stops")


if __name__ == "__main__":
    main()
