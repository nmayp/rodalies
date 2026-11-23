# Delay forecast

Logs Renfe's GTFS-Realtime feed for Rodalies de Catalunya (nucleus 51) and scores predictions of cancellation
or 15+ minute delay against what then happens. Data: Renfe open feeds, CC BY 4.0 (data.renfe.com).

    pip install -r requirements.txt
    python -m rodalies_run collect --every 60     # poll the feed; leave it running
    python -m rodalies_run evaluate               # score on the log (needs ≥ 3 service days)
    python -m rodalies_run status                 # next-hour feed summary per line

Copy `collect.workflow.yml` to `.github/workflows/collect.yml` to poll every ~10 min on a public repo.

**Results**: no scores yet — the log covers only minutes. `evaluate` refuses to report until there are at least
3 service days. The first number worth quoting is feed + line-state vs. feed alone on held-out days.
