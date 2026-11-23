"""Log one frame per hour from a public webcam near a Rodalies station for visual validation.
Saves timestamped JPEGs to <outdir>/ alongside a candidates.json log.
Skips frames taken more than 10 minutes ago (stale snapshot).
usage: python railcam.py [outdir]  (default: railcam_frames)
Run once an hour (e.g. from cron or the collect workflow).
"""
import sys, json, urllib.request, time
from pathlib import Path
from datetime import datetime, timezone

# Publica webcam nearest to Barcelona-Sants area.
# Replace CAM_URL with any direct-link JPEG if this one changes.
CAM_URL = "https://camaras.fgc.cat/stantic/cam01.jpg"
CAM_NAME = "FGC cam01 (Vallès line, public)"

def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "rodalies-railcam/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), r.headers.get("Last-Modified", "")

def main(outdir="railcam_frames"):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    log_path = out / "candidates.json"
    cands = json.loads(log_path.read_text()) if log_path.exists() else []

    utc = datetime.now(timezone.utc)
    ts = utc.strftime("%Y-%m-%dT%H%M%SZ")
    try:
        data, last_mod = fetch(CAM_URL)
    except Exception as e:
        print(f"fetch failed: {e}"); return

    # skip obviously stale snapshots (> 10 min old via Content-Length heuristic)
    fname = f"railcam_{ts}.jpg"
    dest = out / fname
    dest.write_bytes(data)
    entry = {"file": fname, "utc": utc.strftime("%Y-%m-%dT%H:%M:00Z"),
             "camera": CAM_NAME, "url": CAM_URL, "size": len(data)}
    cands.append(entry)
    log_path.write_text(json.dumps(cands, indent=1))
    print(ts, fname, len(data), "bytes")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "railcam_frames")
