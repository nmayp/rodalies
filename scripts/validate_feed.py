"""Read a directory of collected feed dumps and report coverage and consistency stats.
usage: python validate_feed.py [feed_dumps/]
Needs: protobuf, gtfs-realtime-bindings (pip install gtfs-realtime-bindings)
"""
import sys, os, json, re
from pathlib import Path
from collections import defaultdict

def load_feed(path):
    from google.transit import gtfs_realtime_pb2
    msg = gtfs_realtime_pb2.FeedMessage()
    msg.ParseFromString(path.read_bytes())
    return msg

def summarise(folder):
    folder = Path(folder)
    files = sorted(folder.glob("*_trip_updates.pb"))
    if not files:
        print("no trip_updates.pb files in", folder); return

    rows = []
    for f in files:
        ts = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z)", f.name)
        ts = ts.group(1).replace("-", ":").replace("T", "T").replace(":pb", "") if ts else f.stem
        try:
            msg = load_feed(f)
        except Exception as e:
            print("skip", f.name, e); continue
        trips = {e.trip_update.trip.trip_id for e in msg.entity if e.HasField("trip_update")}
        cancelled = {e.trip_update.trip.trip_id for e in msg.entity
                     if e.HasField("trip_update") and
                     e.trip_update.trip.schedule_relationship == 3}  # CANCELED
        rodalies = {t for t in trips if t.startswith("51")}
        rodalies_c = {t for t in cancelled if t.startswith("51")}
        rows.append({"ts": ts, "total": len(trips), "rodalies": len(rodalies), "cancelled": len(rodalies_c)})

    if not rows: return
    print(f"{'time':20s}  {'total':>6}  {'rodalies':>8}  {'cancelled':>9}")
    for r in rows:
        print(f"{r['ts']:20s}  {r['total']:6d}  {r['rodalies']:8d}  {r['cancelled']:9d}")
    avg_rod = sum(r["rodalies"] for r in rows) / len(rows)
    avg_can = sum(r["cancelled"] for r in rows) / len(rows)
    print(f"\n{len(rows)} polls  avg rodalies trips: {avg_rod:.1f}  avg cancelled: {avg_can:.1f}")

if __name__ == "__main__":
    summarise(sys.argv[1] if len(sys.argv) > 1 else "feed_dumps")
