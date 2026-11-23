"""Poll Renfe's public GTFS-Realtime feeds and log the Rodalies trips to SQLite."""
from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from google.transit import gtfs_realtime_pb2 as pb

BASE = "https://gtfsrt.renfe.com"
FEEDS = {"tu": "trip_updates.pb", "vp": "vehicle_positions.pb", "al": "alerts.pb"}
HEADERS = {"User-Agent": "rodalies-will-it-run/0.1 (student research project)"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS polls(
  poll_id INTEGER PRIMARY KEY, fetched_at INTEGER, feed_ts INTEGER, n_trips INTEGER,
  n_canceled INTEGER, n_vehicles INTEGER, n_alerts INTEGER);
CREATE TABLE IF NOT EXISTS obs(
  poll_id INTEGER, trip_id TEXT, canceled INTEGER, n_stu INTEGER,
  delay_first INTEGER, delay_last INTEGER, delay_max INTEGER, n_skipped INTEGER,
  has_vehicle INTEGER, PRIMARY KEY(poll_id, trip_id));
CREATE INDEX IF NOT EXISTS obs_trip ON obs(trip_id);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def fetch(name: str, session: requests.Session | None = None) -> pb.FeedMessage:
    s = session or requests
    r = s.get(f"{BASE}/{FEEDS[name]}", headers=HEADERS, timeout=30)
    r.raise_for_status()
    msg = pb.FeedMessage()
    msg.ParseFromString(r.content)
    return msg


def summarise_trip(tu: pb.TripUpdate) -> dict:
    delays, skipped = [], 0
    for st in tu.stop_time_update:
        if st.schedule_relationship == pb.TripUpdate.StopTimeUpdate.SKIPPED:
            skipped += 1
        ev = st.departure if st.HasField("departure") else st.arrival
        if ev.HasField("delay") or ev.delay:
            delays.append(ev.delay)
    return {
        "canceled": int(tu.trip.schedule_relationship == pb.TripDescriptor.CANCELED),
        "n_stu": len(tu.stop_time_update),
        "delay_first": delays[0] if delays else None,
        "delay_last": delays[-1] if delays else None,
        "delay_max": max(delays) if delays else None,
        "n_skipped": skipped,
    }


def poll_rows(rodalies_ids: set[str]):
    """One poll of the three feeds: (poll summary dict, list of (trip_id, summary, has_vehicle))."""
    now = int(time.time())
    s = requests.Session()
    tu, vp, al = fetch("tu", s), fetch("vp", s), fetch("al", s)
    on_vehicle = {e.vehicle.trip.trip_id for e in vp.entity if e.HasField("vehicle")}
    rows = []
    for e in tu.entity:
        if not e.HasField("trip_update"):
            continue
        tid = e.trip_update.trip.trip_id
        if tid in rodalies_ids:
            rows.append((tid, summarise_trip(e.trip_update), int(tid in on_vehicle)))
    n_alerts = sum(
        1 for e in al.entity
        if any(i.route_id.startswith("51") or i.trip.trip_id in rodalies_ids
               for i in e.alert.informed_entity)
    )
    poll = {"fetched_at": now, "feed_ts": tu.header.timestamp, "n_trips": len(rows),
            "n_canceled": sum(r[1]["canceled"] for r in rows),
            "n_vehicles": sum(1 for r in rows if r[2]), "n_alerts": n_alerts}
    return poll, rows


def poll_once(con: sqlite3.Connection, rodalies_ids: set[str]) -> dict:
    poll, rows = poll_rows(rodalies_ids)
    cur = con.execute(
        "INSERT INTO polls(fetched_at, feed_ts, n_trips, n_canceled, n_vehicles, n_alerts)"
        " VALUES (?,?,?,?,?,?)",
        (poll["fetched_at"], poll["feed_ts"], poll["n_trips"], poll["n_canceled"],
         poll["n_vehicles"], poll["n_alerts"]),
    )
    pid = cur.lastrowid
    con.executemany(
        "INSERT OR REPLACE INTO obs VALUES (?,?,?,?,?,?,?,?,?)",
        [(pid, t, d["canceled"], d["n_stu"], d["delay_first"], d["delay_last"],
          d["delay_max"], d["n_skipped"], hv) for t, d, hv in rows],
    )
    con.commit()
    return {"poll_id": pid, "trips": len(rows), "canceled": poll["n_canceled"]}


OBS_COLS = ["fetched_at", "trip_id", "canceled", "n_stu", "delay_first", "delay_last", "delay_max",
            "n_skipped", "has_vehicle"]
POLL_COLS = ["fetched_at", "feed_ts", "n_trips", "n_canceled", "n_vehicles", "n_alerts"]


def poll_to_csv(out_dir: str | Path, rodalies_ids: set[str]) -> dict:
    """Append one poll to daily CSV files (git-friendly; used by the scheduled workflow)."""
    import csv
    poll, rows = poll_rows(rodalies_ids)
    day = time.strftime("%Y-%m-%d", time.gmtime(poll["fetched_at"]))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, cols, recs in (
        (f"polls_{day}.csv", POLL_COLS, [poll]),
        (f"obs_{day}.csv", OBS_COLS,
         [{"fetched_at": poll["fetched_at"], "trip_id": t, "has_vehicle": hv, **d} for t, d, hv in rows]),
    ):
        path = out / name
        new = not path.exists()
        with open(path, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            if new:
                w.writeheader()
            w.writerows(recs)
    return {"day": day, "trips": len(rows), "canceled": poll["n_canceled"]}


def run(db: str, schedule_csv: str, every: int = 60, minutes: float | None = None) -> None:
    ids = set(pd.read_csv(schedule_csv, usecols=["trip_id"]).trip_id)
    con = connect(db)
    end = time.time() + minutes * 60 if minutes else None
    while end is None or time.time() < end:
        t0 = time.time()
        try:
            print(time.strftime("%H:%M:%S"), poll_once(con, ids), flush=True)
        except Exception as exc:  # keep logging through transient failures
            print("poll failed:", repr(exc)[:120], file=sys.stderr, flush=True)
        time.sleep(max(1, every - (time.time() - t0)))
