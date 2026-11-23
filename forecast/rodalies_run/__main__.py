import argparse
import json

from . import collect

p = argparse.ArgumentParser(prog="rodalies_run")
sub = p.add_subparsers(dest="cmd", required=True)
c = sub.add_parser("collect", help="poll the live feeds and log them")
c.add_argument("--db", default="data/log.sqlite")
c.add_argument("--csv-dir", default=None, help="append one poll to daily CSVs here and exit")
c.add_argument("--schedule", default="data/schedule.csv")
c.add_argument("--every", type=int, default=60)
c.add_argument("--minutes", type=float, default=None)
e = sub.add_parser("evaluate", help="score the models on the logged data")
e.add_argument("--log", default="data/log.sqlite", help="SQLite file or CSV directory")
e.add_argument("--schedule", default="data/schedule.csv")
e.add_argument("--strikes", default="data/strike_days.csv")
e.add_argument("--preliminary", action="store_true", help="allow a labelled first reading from under 3 days")
st = sub.add_parser("status", help="what the live feed says about the next hour of trips")
st.add_argument("--schedule", default="data/schedule.csv")
st.add_argument("--minutes", type=int, default=60)
sc = sub.add_parser("schedule", help="rebuild data/schedule.csv from Renfe's Cercanias GTFS zip")
sc.add_argument("--zip", required=True)
sc.add_argument("--out", default="data/schedule.csv")
ar = sub.add_parser("archive", help="rebuild the log and schedule from TrainArchive.eu daily + compacted files")
ar.add_argument("--daily", required=True)
ar.add_argument("--compacted", required=True)
ar.add_argument("--out", required=True, help="directory for polls_*.csv and obs_*.csv")
ar.add_argument("--schedule-out", required=True)
ar.add_argument("--step", type=int, default=300)
a = p.parse_args()

if a.cmd == "status":
    from . import status
    status.main(a.schedule, a.minutes)
elif a.cmd == "schedule":
    from . import static
    print(static.build_schedule(a.zip, a.out).shape)
elif a.cmd == "collect":
    if a.csv_dir:
        import pandas as pd
        ids = set(pd.read_csv(a.schedule, usecols=["trip_id"]).trip_id)
        print(collect.poll_to_csv(a.csv_dir, ids))
    else:
        collect.run(a.db, a.schedule, a.every, a.minutes)
elif a.cmd == "archive":
    from pathlib import Path
    from . import archive
    sch = archive.schedule_from_daily(sorted(Path(a.daily).glob("*.parquet")))
    sch.to_csv(a.schedule_out, index=False)
    print("schedule", sch.shape, sch.service_date.nunique(), "days")
    print(archive.log_from_compacted(sorted(Path(a.compacted).glob("*.parquet")), Path(a.out), a.step))
elif a.cmd == "evaluate":
    from . import dataset, predict
    obs, polls, sch, strikes = dataset.load_log(a.log, a.schedule, a.strikes)
    m = dataset.attach_schedule(obs, sch)
    now = int(polls.fetched_at.max())
    out = dataset.outcomes(m, now)
    ex = dataset.make_examples(m, sch, out, strikes)
    print(f"{len(polls)} polls, {len(out)} resolved trips ({int(out.disrupted.sum())} disrupted), "
          f"{len(ex)} examples over {ex.service_date.nunique() if len(ex) else 0} day(s)")
    print(json.dumps(predict.evaluate(ex, preliminary=a.preliminary), indent=2, default=float))
