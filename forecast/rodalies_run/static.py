"""Build the Rodalies de Catalunya schedule (nucleus 51) from Renfe's public GTFS."""
from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

NUCLEUS = "51"  # Renfe Cercanías nucleus code for Rodalies de Catalunya
MADRID = ZoneInfo("Europe/Madrid")


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Renfe pads its GTFS fields (and some headers) with spaces; strip both."""
    df = df.rename(columns=lambda c: str(c).strip())
    return df.apply(lambda c: c.str.strip() if pd.api.types.is_string_dtype(c) else c)


def parse_hms(value: str) -> int:
    """GTFS time (may exceed 24:00:00) to seconds after midnight."""
    h, m, s = (int(x) for x in value.strip().split(":"))
    return h * 3600 + m * 60 + s


def build_schedule(zip_path: str | Path, out_csv: str | Path) -> pd.DataFrame:
    """One row per (trip, service date) for Rodalies: route, origin, scheduled times."""
    zf = zipfile.ZipFile(zip_path)
    routes = _clean(pd.read_csv(zf.open("routes.txt"), dtype=str))
    routes = routes[routes.route_id.str.startswith(NUCLEUS)]
    trips = _clean(pd.read_csv(zf.open("trips.txt"), dtype=str))
    trips = trips[trips.route_id.isin(routes.route_id)]
    cal = _clean(pd.read_csv(zf.open("calendar.txt"), dtype=str))
    names = routes.set_index("route_id").route_short_name
    keep = set(trips.trip_id)

    first: dict[str, tuple[int, str, int]] = {}
    last: dict[str, tuple[int, str, int]] = {}
    with zf.open("stop_times.txt") as fh:
        for chunk in pd.read_csv(
            io.TextIOWrapper(fh), dtype=str, chunksize=2_000_000, header=0,
            names=["trip_id", "arrival_time", "departure_time", "stop_id", "stop_sequence"],
            usecols=range(5),
        ):
            chunk = _clean(chunk)
            chunk = chunk[chunk.trip_id.isin(keep)]
            for tid, g in chunk.groupby("trip_id"):
                seq = g.stop_sequence.astype(int)
                i0, i1 = seq.idxmin(), seq.idxmax()
                a = (int(seq[i0]), g.stop_id[i0], parse_hms(g.departure_time[i0]))
                b = (int(seq[i1]), g.stop_id[i1], parse_hms(g.arrival_time[i1]))
                if tid not in first or a[0] < first[tid][0]:
                    first[tid] = a
                if tid not in last or b[0] > last[tid][0]:
                    last[tid] = b
    trips = trips[trips.trip_id.isin(first)].copy()
    trips["line"] = trips.route_id.map(names)
    trips["origin_stop"] = trips.trip_id.map(lambda t: first[t][1])
    trips["dep_s"] = trips.trip_id.map(lambda t: first[t][2])
    trips["dest_stop"] = trips.trip_id.map(lambda t: last[t][1])
    trips["arr_s"] = trips.trip_id.map(lambda t: last[t][2])

    cal["start"] = pd.to_datetime(cal.start_date, format="%Y%m%d").dt.date
    cal["end"] = pd.to_datetime(cal.end_date, format="%Y%m%d").dt.date
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    rows = []
    cal = cal[cal.service_id.isin(trips.service_id.unique())]
    svc_dates: dict[str, list[date]] = {}
    for _, c in cal.iterrows():
        d = c.start
        out = []
        while d <= c.end:
            if c[days[d.weekday()]] == "1":
                out.append(d)
            d += timedelta(days=1)
        svc_dates[c.service_id] = out
    for _, t in trips.iterrows():
        for d in svc_dates.get(t.service_id, []):
            rows.append((t.trip_id, d.isoformat(), t.line, t.route_id, t.origin_stop,
                         t.dest_stop, t.dep_s, t.arr_s))
    sched = pd.DataFrame(rows, columns=["trip_id", "service_date", "line", "route_id",
                                        "origin_stop", "dest_stop", "dep_s", "arr_s"])
    sched.to_csv(out_csv, index=False)
    return sched


def scheduled_epoch(service_date: str, seconds: int) -> int:
    """Epoch seconds for a service date plus GTFS seconds-after-midnight, Madrid time."""
    midnight = datetime.fromisoformat(service_date).replace(tzinfo=MADRID)
    # GTFS defines times relative to noon minus 12h, which handles DST days.
    noon = midnight.replace(hour=12)
    return int((noon - timedelta(hours=12) + timedelta(seconds=seconds)).timestamp())
