# Is my train running?

Pick two Rodalies de Catalunya stations and see the next trains, whether Renfe's live feed says they are
cancelled or late, a plan B (one change at most) and a live map of the trains. Plain black and white.

- `app/` the Next.js site and API. `cd app && npm install && npm run dev`, then open localhost:3000.
- `forecast/` Python experiment that logs the live feed and tests delay predictions (`pip install -r requirements.txt`).
- `scripts/` rebuild the timetable files in `app/public/trains/`.

Tests: `cd app && npm test` (11 tests, Node 22.18+) and `npx tsc --noEmit`; `cd forecast && python -m pytest`.

Validation: `node scripts/collect_feed.cjs [outdir]` saves raw GTFS-RT protobufs every 60 s;
`python scripts/validate_feed.py [outdir]` reports per-poll coverage and cancellation counts.
`python scripts/railcam.py [outdir]` logs one JPEG per hour from a public webcam near the network.

Data: Renfe Operadora open data (GTFS timetable and GTFS-Realtime feed), CC BY 4.0, https://data.renfe.com.
- `python scripts/build_trains.py [fomento_transit.zip]` reads Renfe's Cercanias GTFS zip (downloads it if no path
  is given), stdlib only, writes the per-day files, stops and network.
- `python scripts/build_history.py [folder of daily *.parquet]` builds the cancellation history from TrainArchive.eu
  (needs pandas, pyarrow). Without a folder it downloads, using a free key in the `TRAINARCHIVE_TOKEN` env variable.
- The Renfe real-time feed needs no key. Nothing secret is stored in this repo.

Limitation: the timetable files cover about a month and must be rebuilt regularly, and the feed's delay numbers are often stale.
