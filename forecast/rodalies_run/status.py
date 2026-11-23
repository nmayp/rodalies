"""Right now, per line: scheduled trips in the next hour vs what the live feed says about them."""
from __future__ import annotations

import time

import pandas as pd

from . import collect
from .static import scheduled_epoch


def snapshot(schedule_csv: str, horizon_min: int = 60) -> pd.DataFrame:
    sch = pd.read_csv(schedule_csv)
    now = int(time.time())
    sch["dep_epoch"] = [scheduled_epoch(d, s) for d, s in zip(sch.service_date, sch.dep_s)]
    sch["arr_epoch"] = [scheduled_epoch(d, s) for d, s in zip(sch.service_date, sch.arr_s)]
    soon = sch[(sch.dep_epoch >= now) & (sch.dep_epoch <= now + horizon_min * 60)]
    poll, rows = collect.poll_rows(set(sch.trip_id))
    live = {t: d for t, d, _ in rows}
    soon = soon.assign(
        in_feed=soon.trip_id.isin(live),
        canceled=[live.get(t, {}).get("canceled", 0) for t in soon.trip_id],
        late15=[int((live.get(t, {}).get("delay_max") or 0) >= 900) for t in soon.trip_id],
    )
    g = soon.groupby("line").agg(scheduled=("trip_id", "size"), in_feed=("in_feed", "sum"),
                                 flagged_cancelled=("canceled", "sum"), late_15min=("late15", "sum"))
    g["not_in_feed"] = g.scheduled - g.in_feed
    return g.sort_values("scheduled", ascending=False)


def main(schedule_csv: str, horizon_min: int = 60) -> None:
    g = snapshot(schedule_csv, horizon_min)
    print(f"Rodalies trips scheduled to leave in the next {horizon_min} min vs the live Renfe feed")
    print(g.to_string())
    print(f"\ntotal scheduled {int(g.scheduled.sum())}; flagged cancelled {int(g.flagged_cancelled.sum())}; "
          f"not in the feed at all {int(g.not_in_feed.sum())} "
          f"(a trip missing from the feed is not necessarily cancelled: the feed may not cover it yet)")
