"""Turn the poll log into outcomes per trip and training examples at a given lead time."""
from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

from .static import scheduled_epoch

LATE_S = 900          # a trip is "late" once any stop update shows 15+ minutes of delay
LEADS = (30, 120)     # minutes before scheduled departure at which we make predictions


def _read_log(db: str):
    """Read a SQLite log, or a directory of daily CSVs written by the scheduled workflow."""
    from pathlib import Path
    if Path(db).is_dir():
        obs = pd.concat([pd.read_csv(f) for f in sorted(Path(db).glob("obs_*.csv"))], ignore_index=True)
        polls = pd.concat([pd.read_csv(f) for f in sorted(Path(db).glob("polls_*.csv"))], ignore_index=True)
        polls = polls.sort_values("fetched_at").reset_index(drop=True)
        polls["poll_id"] = polls.index + 1
        obs = obs.merge(polls[["fetched_at", "poll_id"]], on="fetched_at")
        return obs, polls
    con = sqlite3.connect(db)
    obs = pd.read_sql("SELECT o.*, p.fetched_at FROM obs o JOIN polls p USING(poll_id)", con)
    return obs, pd.read_sql("SELECT * FROM polls", con)


def load_log(db: str, schedule_csv: str, strikes_csv: str | None = None):
    obs, polls = _read_log(db)
    sch = pd.read_csv(schedule_csv)
    lo, hi = polls.fetched_at.min() - 36 * 3600, polls.fetched_at.max() + 36 * 3600
    sch["dep_epoch"] = [scheduled_epoch(d, s) for d, s in zip(sch.service_date, sch.dep_s)]
    sch["arr_epoch"] = [scheduled_epoch(d, s) for d, s in zip(sch.service_date, sch.arr_s)]
    sch = sch[(sch.dep_epoch >= lo) & (sch.dep_epoch <= hi)].reset_index(drop=True)
    strikes = set(pd.read_csv(strikes_csv).date) if strikes_csv else set()
    return obs, polls, sch, strikes


def attach_schedule(obs: pd.DataFrame, sch: pd.DataFrame) -> pd.DataFrame:
    """Match each observation to the service date whose departure is nearest in time."""
    m = obs.merge(sch[["trip_id", "service_date", "line", "dep_epoch", "arr_epoch"]], on="trip_id")
    m["gap"] = (m.dep_epoch - m.fetched_at).abs()
    m = m.sort_values("gap").drop_duplicates(["poll_id", "trip_id"]).drop(columns="gap")
    return m.sort_values("fetched_at").reset_index(drop=True)


def outcomes(m: pd.DataFrame, now: int, grace_s: int = 600) -> pd.DataFrame:
    """One row per (trip, date) that has finished or been cancelled: did it run as planned?"""
    g = m.groupby(["trip_id", "service_date"])
    o = g.agg(line=("line", "first"), dep_epoch=("dep_epoch", "first"), arr_epoch=("arr_epoch", "first"),
              canceled=("canceled", "max"), max_delay=("delay_max", "max"),
              first_seen=("fetched_at", "min"), last_seen=("fetched_at", "max")).reset_index()
    o["late"] = (o.max_delay.fillna(0) >= LATE_S).astype(int)
    o["disrupted"] = ((o.canceled == 1) | (o.late == 1)).astype(int)
    done = (o.canceled == 1) | (o.last_seen >= o.arr_epoch - grace_s) | (o.arr_epoch + grace_s < now)
    return o[done].reset_index(drop=True)


def make_examples(m: pd.DataFrame, sch: pd.DataFrame, out: pd.DataFrame, strikes: set[str],
                  leads=LEADS) -> pd.DataFrame:
    """For each poll time t and each resolved trip departing 30-120 min later, features known at t."""
    rows = []
    keyed = out.set_index(["trip_id", "service_date"])
    for t, snap in m.groupby("fetched_at"):
        line_state = snap.groupby("line").agg(
            n_seen=("trip_id", "size"), cancel_share=("canceled", "mean"),
            late_share=("delay_max", lambda s: float((s.fillna(0) >= 300).mean())))
        active = sch[(sch.dep_epoch <= t) & (sch.arr_epoch >= t)]
        vis = (active.assign(seen=active.trip_id.isin(snap.trip_id)).groupby("line").seen.mean())
        glob_cancel = float(snap.canceled.mean())
        by_trip = snap.set_index("trip_id")
        cand = sch[(sch.dep_epoch >= t + leads[0] * 60) & (sch.dep_epoch <= t + leads[1] * 60)]
        for r in cand.itertuples():
            k = (r.trip_id, r.service_date)
            if k not in keyed.index:
                continue
            ls = line_state.loc[r.line] if r.line in line_state.index else None
            seen = r.trip_id in by_trip.index
            row = by_trip.loc[r.trip_id] if seen else None
            lt = pd.Timestamp(t, unit="s", tz="UTC").tz_convert("Europe/Madrid")
            rows.append({
                "t": int(t), "trip_id": r.trip_id, "service_date": r.service_date, "line": r.line,
                "lead_min": (r.dep_epoch - t) / 60,
                "known_canceled": int(seen and row.canceled == 1),
                "known_late": int(seen and (row.delay_max or 0) >= LATE_S),
                "visible": int(seen),
                "line_cancel_share": float(ls.cancel_share) if ls is not None else 0.0,
                "line_late_share": float(ls.late_share) if ls is not None else 0.0,
                "line_visibility": float(vis.get(r.line, np.nan)) if r.line in vis.index else np.nan,
                "global_cancel_share": glob_cancel,
                "hour_sin": np.sin(2 * np.pi * lt.hour / 24), "hour_cos": np.cos(2 * np.pi * lt.hour / 24),
                "weekend": int(lt.weekday() >= 5), "strike_day": int(r.service_date in strikes),
                "y": int(keyed.loc[k, "disrupted"]),
            })
    ex = pd.DataFrame(rows)
    if len(ex):
        ex["line_visibility"] = ex.line_visibility.fillna(ex.line_visibility.mean() if ex.line_visibility.notna().any() else 1.0)
    return ex
