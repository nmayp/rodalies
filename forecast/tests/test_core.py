import numpy as np
import pandas as pd
from google.transit import gtfs_realtime_pb2 as pb

from rodalies_run import collect, dataset, predict, static


def test_gtfs_times_past_midnight():
    assert static.parse_hms("25:10:00") == 25 * 3600 + 600
    assert static.parse_hms(" 06:05:30 ") == 6 * 3600 + 330


def test_scheduled_epoch_handles_dst_change():
    # Madrid moves to winter time on 2026-10-25: 02:00 on that service day is 3 h after the previous midnight
    a = static.scheduled_epoch("2026-10-25", 0)
    b = static.scheduled_epoch("2026-10-25", 3 * 3600)
    assert b - a == 4 * 3600  # one extra hour in the night


def test_summarise_trip_reads_cancel_and_delay():
    tu = pb.TripUpdate()
    tu.trip.trip_id = "x"
    tu.trip.schedule_relationship = pb.TripDescriptor.CANCELED
    st = tu.stop_time_update.add()
    st.departure.delay = 1200
    out = collect.summarise_trip(tu)
    assert out["canceled"] == 1 and out["delay_max"] == 1200 and out["n_stu"] == 1


def _log():
    # trip A runs late (20 min), trip B is cancelled, trip C is on time; schedule 1 day
    sch = pd.DataFrame({"trip_id": list("ABC"), "service_date": "2026-11-21", "line": "R1",
                        "dep_epoch": [1000, 1200, 1400], "arr_epoch": [2000, 2200, 2400]})
    rows = []
    for t in (500, 1500, 2500):
        for tid, canc, d in (("A", 0, 1200), ("B", 1, None), ("C", 0, 0)):
            rows.append({"poll_id": t, "trip_id": tid, "fetched_at": t, "canceled": canc,
                         "delay_max": d, "n_stu": 1, "delay_first": d, "delay_last": d,
                         "n_skipped": 0, "has_vehicle": 1})
    return pd.DataFrame(rows), sch


def test_outcomes_label_late_and_cancelled():
    obs, sch = _log()
    m = dataset.attach_schedule(obs, sch)
    out = dataset.outcomes(m, now=3000).set_index("trip_id")
    assert out.loc["A", "late"] == 1 and out.loc["B", "canceled"] == 1
    assert out.loc["C", "disrupted"] == 0


def test_unfinished_trips_are_not_labelled():
    obs, sch = _log()
    m = dataset.attach_schedule(obs[obs.fetched_at < 1000], sch)
    out = dataset.outcomes(m, now=1000)
    # A and C have not finished; only the cancelled trip B is already resolved
    assert list(out.trip_id) == ["B"]


def test_evaluate_refuses_to_claim_with_little_data():
    ex = pd.DataFrame({"service_date": ["2026-11-21"] * 50, "y": [0, 1] * 25})
    res = predict.evaluate(ex)
    assert res["ok"] is False and "no performance is claimed" in res["reason"]


def test_models_beat_base_rate_when_feed_flag_is_informative():
    rng = np.random.default_rng(1)
    n = 3000
    flag = rng.integers(0, 2, n)
    y = (rng.uniform(size=n) < np.where(flag == 1, 0.9, 0.2)).astype(int)
    ex = pd.DataFrame({c: np.zeros(n) for c in predict.NUMERIC})
    ex["known_canceled"] = flag
    ex["service_date"] = np.repeat([f"2026-11-{d:02d}" for d in range(1, 11)], n // 10)
    ex["trip_id"] = [f"T{i}" for i in range(n)]
    ex["t"] = np.arange(n) * 60
    ex["lead_min"] = 60.0
    ex["y"] = y
    res = predict.evaluate(ex)
    assert res["ok"] and res["scores"]["feed only"]["brier"] < res["scores"]["base rate"]["brier"]


def test_preliminary_reading_is_labelled_and_has_interval():
    rng = np.random.default_rng(2)
    n = 1200
    flag = rng.integers(0, 2, n)
    ex = pd.DataFrame({c: np.zeros(n) for c in predict.NUMERIC})
    ex["known_canceled"] = flag
    ex["trip_id"] = [f"T{i // 3}" for i in range(n)]
    ex["service_date"] = "2026-11-22"
    ex["t"] = np.arange(n) * 60
    ex["lead_min"] = 60.0
    ex["y"] = (rng.uniform(size=n) < np.where(flag == 1, 0.9, 0.2)).astype(int)
    assert predict.evaluate(ex)["ok"] is False             # refuses without the flag
    res = predict.evaluate(ex, preliminary=True)
    assert res["ok"] and res["preliminary"] and "PRELIMINARY" in res["note"]
    assert len(res["brier_gain_ci95"]) == 2
