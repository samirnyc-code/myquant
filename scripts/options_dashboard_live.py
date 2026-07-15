"""Live options dashboard server (S75) — makes options_dashboard.py genuinely live.

Serves the standalone dashboard over HTTP and keeps it ticking without manual
regeneration:
  GET /             -> dashboard.html (regenerated only when trades/journal/ledger change)
  GET /state.json   -> fresh KPI tiles + live.json spot/vix/basis + a `gen` counter
  GET /live.json    -> raw feed passthrough (handy for debugging)

The page (see the poll() script in options_dashboard.py) fetches /state.json
every 5s to update the KPI tiles and the live SPX/ES/VIX ticker, and does a
soft reload when `gen` changes so the flip-card wall and journal pick up
new/closed trades. Fetches fail silently over file://, so the same HTML also
works as a static file.

Live spot requires the feed running alongside it (after Gateway login):
  .venv/Scripts/python.exe scripts/spot_feed.py

Run the dashboard server:
  .venv/Scripts/python.exe scripts/options_dashboard_live.py [--port 8600] [--open]
"""
import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import options_dashboard as dash

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
LOG = ROOT / "data" / "options_log"
DASH = SIM / "dashboard.html"
LIVE = SIM / "live.json"

# Files that, when they change, mean the page needs a rebuild (cards / journal /
# results / game-plan status). Today's gameplan is resolved lazily in gen_stamp.
WATCH = [LOG / "trades.parquet", LOG / "journal.json", SIM / "sim_ledger.csv"]


def _watch_files():
    import datetime as _dt
    from zoneinfo import ZoneInfo
    date = _dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d")
    return WATCH + [SIM / f"gameplan_{date}.json", SIM / f"postmortem_{date}.json"]

_lock = threading.Lock()
_last_gen = [None]


def gen_stamp():
    """Integer that changes whenever any watched file is written."""
    return int(sum(f.stat().st_mtime_ns for f in _watch_files() if f.exists()) % 2_000_000_000)


def live_json():
    if LIVE.exists():
        try:
            return json.loads(LIVE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"state": "offline"}


def ensure_html(force=False):
    """Regenerate dashboard.html only if the underlying data changed."""
    g = gen_stamp()
    with _lock:
        if force or g != _last_gen[0] or not DASH.exists():
            dash.main()
            _last_gen[0] = g
    return g


def state():
    s = dash.load_stats()
    tiles = {k: {"value": v, "cls": c} for k, _label, v, c in dash.tile_specs(s)}
    return {"gen": gen_stamp(), "live": live_json(),
            "tiles": tiles, "lr": dash.levels_regime()}


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html", "/dashboard.html"):
            ensure_html()
            self._send(DASH.read_bytes(), "text/html; charset=utf-8")
        elif path == "/state.json":
            self._send(json.dumps(state()), "application/json")
        elif path == "/live.json":
            self._send(json.dumps(live_json()), "application/json")
        else:
            self.send_error(404)

    def log_message(self, *args):  # keep the console quiet
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8600)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true", help="open a browser tab")
    args = ap.parse_args()

    ensure_html(force=True)  # build once up front so the first GET is instant
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"live options dashboard -> {url}  (Ctrl-C to stop)")
    print("  polling /state.json every 5s; regenerates on trade/journal change.")
    if not LIVE.exists() or live_json().get("state") != "live":
        print("  NOTE: live feed offline — run scripts/spot_feed.py for real-time SPX/ES/VIX.")
    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        srv.shutdown()


if __name__ == "__main__":
    main()
