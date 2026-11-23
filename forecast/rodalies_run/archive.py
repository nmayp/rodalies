"""Rebuild our poll log and schedule from TrainArchive.eu's Renfe Cercanias files (CC BY 4.0, via Renfe's open feed).

The archive keeps every version of every trip update with the time it was first and last seen, so the state of the
feed at any past moment can be reconstructed. We sample it every `step` seconds, which gives the same table our own
logger writes (polls_*.csv, obs_*.csv). The daily files give the schedule per service date.
Source: https://www.train-archive.eu  (Renfe Cercanias, es-renfe-cercanias). Attribution: Renfe Operadora, CC BY 4.0.
"""
from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .collect import OBS_COLS, POLL_COLS

NUCLEUS = "51"
MADRID = ZoneInfo("Europe/Madrid")


def _secs(ts: pd.Series, service_date: pd.Series) -> pd.Series:
    """Local clock time of a scheduled stop as seconds after midnight of the service date."""
    t = pd.to_datetime(ts)
    mid = pd.to_datetime(service_date)
    return ((t - mid).dt.total_seconds()).astype("Int64")


def schedule_from_daily(daily_files: list[Path]) -> pd.DataFrame:
    out = []
    for f in sorted(daily_files):
        d = pd.read_parquet(f, columns=["service_date", "route", "route_id", "trip_id", "stop_sequence", "stop_id",
                                        "scheduled_arrival", "scheduled_departure", "trip_status"])
        d = d[d.trip_id.str.startswith(NUCLEUS) & (d.trip_status != "added")].sort_values(["trip_id", "stop_sequence"])
        g = d.groupby(["trip_id", "service_date"], sort=False)
        first, last = g.head(1).set_index(["trip_id", "service_date"]), g.tail(1).set_index(["trip_id", "service_date"])
        s = pd.DataFrame({
            "line": first.route.str.split().str[0], "route_id": first.route_id,
            "origin_stop": first.stop_id.astype("int64"), "dest_stop": last.stop_id.astype("int64"),
            "dep_s": _secs(first.scheduled_departure.fillna(first.scheduled_arrival), first.index.get_level_values(1).to_series(index=first.index)),
            "arr_s": _secs(last.scheduled_arrival.fillna(last.scheduled_departure), last.index.get_level_values(1).to_series(index=last.index)),
        }).reset_index()
        out.append(s.dropna(subset=["dep_s", "arr_s"]))
    return pd.concat(out, ignore_index=True)[["trip_id", "service_date", "line", "route_id", "origin_stop", "dest_stop", "dep_s", "arr_s"]]


def _summary(stu) -> tuple:
    delays, skipped = [], 0
    for s in (stu if stu is not None else []):
        if s.get("scheduleRelationship") == "SKIPPED":
            skipped += 1
        ev = s.get("departure") or s.get("arrival")
        if ev and ev.get("delay") is not None:
            delays.append(float(ev["delay"]))
    n = 0 if stu is None else len(stu)
    return (n, delays[0] if delays else np.nan, delays[-1] if delays else np.nan, max(delays) if delays else np.nan, skipped)


def log_from_compacted(files: list[Path], out_dir: Path, step: int = 300, linger: int = 90) -> dict:
    """Write polls_*.csv and obs_*.csv sampled every `step` seconds. A trip stays 'seen' for `linger` s after its last sighting."""
    out_dir.mkdir(parents=True, exist_ok=True)
    versions = []
    for f in sorted(files):
        c = pd.read_parquet(f, columns=["trip_tripId", "trip_scheduleRelationship", "stopTimeUpdate", "firstSeen", "lastSeen"])
        c = c[c.trip_tripId.astype(str).str.startswith(NUCLEUS) & (c.trip_scheduleRelationship != "ADDED")].copy()
        summ = c.stopTimeUpdate.map(_summary)
        c[["n_stu", "delay_first", "delay_last", "delay_max", "n_skipped"]] = pd.DataFrame(summ.tolist(), index=c.index)
        c["canceled"] = (c.trip_scheduleRelationship == "CANCELED").astype(int)
        epoch = pd.Timestamp("1970-01-01", tz="UTC")
        c["t0"] = np.floor((c.firstSeen - epoch).dt.total_seconds()).astype("int64")
        c["t1"] = np.floor((c.lastSeen - epoch).dt.total_seconds()).astype("int64") + linger
        versions.append(c.drop(columns=["stopTimeUpdate", "firstSeen", "lastSeen", "trip_scheduleRelationship"]))
    v = pd.concat(versions, ignore_index=True).rename(columns={"trip_tripId": "trip_id"})
    k0 = np.ceil(v.t0 / step).astype(int)
    k1 = np.floor(v.t1 / step).astype(int)
    keep = k1 >= k0
    v, k0, k1 = v[keep], k0[keep], k1[keep]
    reps = (k1 - k0 + 1).to_numpy()
    idx = np.repeat(np.arange(len(v)), reps)
    k = np.concatenate([np.arange(a, b + 1) for a, b in zip(k0, k1)])
    e = v.iloc[idx].reset_index(drop=True)
    e["fetched_at"] = k * step
    e = e.sort_values(["fetched_at", "trip_id", "t0"]).drop_duplicates(["fetched_at", "trip_id"], keep="last")
    e["has_vehicle"] = 0  # the archive's trip-update files carry no vehicle link; the model does not use it
    obs = e[OBS_COLS]
    polls = obs.groupby("fetched_at").agg(n_trips=("trip_id", "size"), n_canceled=("canceled", "sum")).reset_index()
    polls["feed_ts"], polls["n_vehicles"], polls["n_alerts"] = polls.fetched_at, 0, 0
    polls = polls[POLL_COLS]
    day = lambda s: pd.to_datetime(s, unit="s", utc=True).dt.strftime("%Y-%m-%d")
    for d, g in obs.groupby(day(obs.fetched_at)):
        g.to_csv(out_dir / f"obs_{d}.csv", index=False)
    for d, g in polls.groupby(day(polls.fetched_at)):
        g.to_csv(out_dir / f"polls_{d}.csv", index=False)
    return {"polls": len(polls), "obs_rows": len(obs), "trips": int(obs.trip_id.nunique())}
