"""Cancellation history for Rodalies from TrainArchive.eu's daily Renfe Cercanias files (last 7 days, open access).

    python3 scripts/build_history.py [folder with daily/*.parquet]

Without a folder it downloads the days itself; set TRAINARCHIVE_TOKEN (a free token from train-archive.eu) in the environment.
Writes app/public/trains/history.json. Needs pandas and pyarrow.
Source: Renfe Operadora open data, CC BY 4.0, archived by TrainArchive.eu.
"""
import io
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE = "https://data.train-archive.eu"
OUT = Path(__file__).resolve().parent.parent / "app" / "public" / "trains" / "history.json"
COLS = ["service_date", "route", "trip_id", "stop_sequence", "stop_id", "scheduled_departure", "scheduled_arrival", "trip_status"]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def get(url, token=None):
    """Fetch a file. The signed storage address it redirects to is followed without the token."""
    h = {"X-Api-Key": token} if token else {}
    opener = urllib.request.build_opener(NoRedirect)
    try:
        return opener.open(urllib.request.Request(url, headers=h), timeout=120).read()
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            return urllib.request.urlopen(e.headers["Location"], timeout=180).read()
        raise


def load(folder):
    if folder:
        return [pd.read_parquet(f, columns=COLS) for f in sorted(Path(folder).glob("*.parquet"))]
    token = os.environ.get("TRAINARCHIVE_TOKEN")
    idx = pd.read_parquet(io.BytesIO(get(f"{BASE}/index.parquet", token)))
    d = idx[(idx.provider == "es-renfe-cercanias") & (idx.service == "TripUpdate") & (idx.kind == "daily")].sort_values("date").tail(7)
    out = []
    for u in d.url:
        out.append(pd.read_parquet(io.BytesIO(get(u, token)), columns=COLS))
    return out


def main():
    frames = load(sys.argv[1] if len(sys.argv) > 1 else None)
    d = pd.concat(frames)
    d = d[d.trip_id.str.startswith("51") & (d.trip_status != "added")].copy()
    d["line"] = d.route.str.split().str[0]
    d["hm"] = d.scheduled_departure.fillna(d.scheduled_arrival).str[11:16]
    d["c"] = (d.trip_status == "cancelled").astype(int)
    trips = d.sort_values("stop_sequence").groupby(["service_date", "trip_id"]).agg(line=("line", "first"), c=("c", "first"), hm=("hm", "first")).reset_index()
    days = sorted(trips.service_date.unique())
    by_day = [[x, int(len(g)), int(g.c.sum())] for x, g in trips.groupby("service_date")]
    by_line = {k: [int(len(g)), int(g.c.sum())] for k, g in trips.groupby("line")}
    hour = trips.hm.str[:2].astype(int)
    by_hour = [[int((hour == h).sum()), int(trips.c[hour == h].sum())] for h in range(24)]
    keys = {}
    k = d.dropna(subset=["hm"]).groupby(["line", "stop_id", "hm", "service_date"]).c.max().reset_index()
    for (line, stop, hm), g in k.groupby(["line", "stop_id", "hm"]):
        if len(g) >= 3:
            keys[f"{line}|{stop}|{hm}"] = [int(len(g)), int(g.c.sum())]
    OUT.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "days": days, "trips": int(len(trips)),
        "cancelled": int(trips.c.sum()), "byDay": by_day, "byLine": by_line, "byHour": by_hour, "keys": keys,
        "source": "Renfe Operadora open data, CC BY 4.0, archived by TrainArchive.eu",
    }, separators=(",", ":")))
    print(len(days), "days,", len(trips), "trips,", int(trips.c.sum()), "cancelled,", len(keys), "train keys")


if __name__ == "__main__":
    main()
