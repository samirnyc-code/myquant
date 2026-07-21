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
import datetime as dt
import json
import secrets
import socket
import sys
import threading
import urllib.parse
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
TOKEN_FILE = Path.home() / ".myquant_dashboard_token.txt"  # OUTSIDE the repo — never committed


def load_token():
    """Access token for remote viewers (localhost is exempt). Persisted in a
    gitignored file so it stays stable across restarts; generated on first run."""
    if TOKEN_FILE.exists() and TOKEN_FILE.read_text(encoding="utf-8").strip():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    tok = secrets.token_urlsafe(16)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(tok, encoding="utf-8")
    return tok


TOKEN = load_token()

# Files that, when they change, mean the page needs a rebuild (cards / journal /
# results / game-plan status). Today's gameplan is resolved lazily in gen_stamp.
WATCH = [LOG / "trades.parquet", LOG / "journal.json", SIM / "sim_ledger.csv", SIM / "marks.csv"]


def _watch_files():
    import datetime as _dt
    from zoneinfo import ZoneInfo
    date = _dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d")
    return WATCH + [SIM / f"gameplan_{date}.json", SIM / f"postmortem_{date}.json",
                    SIM / f"eod_status_{date}.json"]  # Desk Report grows through the day → soft-reload

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
    def _send(self, body, ctype, set_cookie=False):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        if set_cookie:
            self.send_header("Set-Cookie",
                             f"dash={TOKEN}; Path=/; Max-Age=86400; SameSite=Lax")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _authed(self, query):
        # the owner on this machine is always allowed
        if self.client_address[0] in ("127.0.0.1", "::1"):
            return True, False
        # a valid session cookie
        for part in self.headers.get("Cookie", "").split(";"):
            if part.strip().startswith("dash=") and part.strip()[5:] == TOKEN:
                return True, False
        # a valid ?key= (first entry) — set the cookie so poll/refresh keep working
        if urllib.parse.parse_qs(query).get("key", [None])[0] == TOKEN:
            return True, True
        return False, False

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        ok, set_cookie = self._authed(u.query)
        if not ok:
            self.send_response(401)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<body style='font:15px system-ui;background:#0b0d12;color:#e8ebf0;"
                             b"padding:40px'><h3>401 &mdash; access key required</h3>"
                             b"<p>Append <code>?key=YOUR_KEY</code> to the URL.</p></body>")
            return
        if u.path in ("/", "/index.html", "/dashboard.html"):
            ensure_html()
            self._send(DASH.read_bytes(), "text/html; charset=utf-8", set_cookie)
        elif u.path == "/state.json":
            self._send(json.dumps(state()), "application/json", set_cookie)
        elif u.path == "/live.json":
            self._send(json.dumps(live_json()), "application/json", set_cookie)
        else:
            self.send_error(404)

    def do_POST(self):
        """POST /close {"trade_id": ...} — queue a manual close.

        This server does NOT place orders. It appends a request to
        close_requests.json; options_trigger_daemon.py (the single process that
        owns the IB connection) picks it up on its next poll and executes it.
        Two processes placing orders on one account is how you get double fills.
        """
        u = urllib.parse.urlparse(self.path)
        ok, _ = self._authed(u.query)
        if not ok or u.path != "/close":
            self.send_error(401 if not ok else 404)
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            tid = str(req.get("trade_id", "")).strip()
            if not tid:
                raise ValueError("trade_id required")
        except Exception as e:
            self._send(json.dumps({"error": str(e)}), "application/json")
            return
        f = SIM / "close_requests.json"
        try:
            d = json.loads(f.read_text()) if f.exists() else {"requests": []}
        except Exception:
            d = {"requests": []}
        if not any(r["trade_id"] == tid and not r.get("done") for r in d["requests"]):
            d["requests"].append({"trade_id": tid, "requested_at": dt.datetime.now().isoformat(),
                                  "source": "dashboard", "done": False})
            f.write_text(json.dumps(d, indent=2))
        self._send(json.dumps({"ok": True, "trade_id": tid, "queued": True}), "application/json")

    def log_message(self, *args):  # keep the console quiet
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8600)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true", help="open a browser tab")
    args = ap.parse_args()

    # Windows lets 0.0.0.0:PORT bind alongside an existing 127.0.0.1:PORT, so a
    # bind-error check is NOT reliable — probe the port explicitly. Another
    # instance (e.g. Mission Control's) already serving is a healthy state for
    # the scheduled backstop task, not a failure.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.settimeout(2)
    already = probe.connect_ex(("127.0.0.1", args.port)) == 0
    probe.close()
    if already:
        print(f"port {args.port} already serving — dashboard already running, exiting clean.")
        return 0

    ensure_html(force=True)  # build once up front so the first GET is instant
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"live options dashboard -> {url}  (Ctrl-C to stop)")
    print("  polling /state.json every 5s; regenerates on trade/journal change.")
    print(f"  ACCESS TOKEN: {TOKEN}   (localhost exempt; remote needs ?key=)")
    # Tailscale share URL for remote viewers (e.g. Thomas), if tailscale is up
    try:
        import subprocess
        tsip = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True,
                              timeout=5, creationflags=0x08000000).stdout.strip().splitlines()
        if tsip:
            print(f"  SHARE (Tailscale): http://{tsip[0]}:{args.port}/?key={TOKEN}")
    except Exception:
        print("  (Tailscale not detected — install it, then share http://<your-tailscale-ip>:"
              f"{args.port}/?key={TOKEN})")
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
