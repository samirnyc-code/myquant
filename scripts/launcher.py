"""Mission Control — one page to start / open / stop every dashboard we've built (S75F).

The dashboards are local servers (stdlib http.server + Streamlit apps), so a plain HTML
file can't spawn them — this is a tiny stdlib launcher (same pattern as the command
center) that:
  * shows every dashboard as a card with a LIVE up/down dot (probes the port),
  * Start  -> spawns the server as a DETACHED subprocess on its port (survives closing
             this launcher); stdout/stderr -> data/_catalog/logs/<key>.log,
  * Open   -> opens http://127.0.0.1:<port>/ in a new tab,
  * Stop   -> taskkill /T /F the process tree (by tracked PID, or found via netstat).

Run:
  .venv/Scripts/python.exe scripts/launcher.py [--port 8590] [--open]
"""
import argparse
import datetime as dt
import json
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---- read-only viewer token (S75L) --------------------------------------
# Remote visitors (Thomas over Tailscale) may ONLY see /view + its JSON, and
# only with ?key=<token>. Control endpoints stay localhost-only regardless.
# The token persists across restarts so the shared link stays stable.
_TOKEN_FILE = ROOT / "data" / "_catalog" / "launcher_viewer_token.txt"


def _viewer_token():
    if _TOKEN_FILE.exists():
        t = _TOKEN_FILE.read_text(encoding="utf-8").strip()
        if t:
            return t
    import secrets
    t = secrets.token_urlsafe(18)
    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_FILE.write_text(t, encoding="utf-8")
    return t


VIEWER_TOKEN = _viewer_token()


def _desk_token():
    """The Options Desk dashboard's own access token (persistent, outside repo) —
    baked into the viewer so its 'Open desk' button works for the remote viewer."""
    try:
        return (Path.home() / ".myquant_dashboard_token.txt").read_text(
            encoding="utf-8").strip()
    except Exception:
        return ""
# pythonw.exe = the GUI-subsystem interpreter: it NEVER allocates a console window,
# so detached dashboards don't spawn stray black console windows on the desktop.
PY = ROOT / ".venv" / "Scripts" / "pythonw.exe"
SD = ROOT / "scripts"
LOGDIR = ROOT / "data" / "_catalog" / "logs"
PIDFILE = ROOT / "data" / "_catalog" / "launcher_pids.json"

# Windows process-creation flags. Note: DETACHED_PROCESS and CREATE_NO_WINDOW are
# mutually exclusive — combining them (the old bug) is why consoles still flashed.
# CREATE_NO_WINDOW alone gives the child no console window; CREATE_NEW_PROCESS_GROUP
# detaches it from this launcher's Ctrl-C group so it survives the launcher closing.
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
_FLAGS = CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW


def _st(script):
    return [str(PY), str(SD / script)]


def _streamlit(entry, port):
    return [str(PY), "-m", "streamlit", "run", str(ROOT / entry),
            "--server.port", str(port), "--server.address", "127.0.0.1",
            "--server.headless", "true", "--browser.gatherUsageStats", "false"]


# key, title, description, port, launch command, group
DASHBOARDS = [
    {"key": "options_desk", "group": "Live desk",
     "title": "Options Desk — Live", "port": 8600,
     "desc": "The daily options desk: live P&L tiles, position cards, gameplan/trigger "
             "state, Desk Report tab. Needs IB Gateway (paper 4002) for live marks.",
     "info": "Live view of the paper-trading day: open positions with live P&L from IB "
             "quotes, the auto-generated gameplan, which triggers are armed or fired, and "
             "the end-of-day report. The keyed :8600 link opens this page.",
     "cmd": _st("options_dashboard_live.py") + ["--host", "0.0.0.0", "--port", "8600"]},

    {"key": "mark_setups", "group": "Live desk",
     "title": "ES Setup Marker", "port": 8630,
     "desc": "Forward-reveal ES volume-bar chart annotator (S75J/K): play/step bars, "
             "mark BOPB / second-entry setups vs MQ levels -> data/annotations/marks.csv.",
     "info": "Chart annotator: ES bars replay one at a time (no peeking ahead) and good "
             "trade setups get hand-marked. The marks become labeled data for finding "
             "which order-flow features the good setups share.",
     "cmd": _st("mark_setups.py") + ["--port", "8630"]},

    {"key": "command_center", "group": "MenthorQ",
     "title": "Gamma Levels — Command Center", "port": 8610,
     "desc": "Hub for the ~5yr MenthorQ levels DB (13 tickers): freshness/status, "
             "per-day price-action chart + levels table, Update-now backfill.",
     "info": "A ~5-year database of daily MenthorQ dealer-gamma levels for 13 tickers, "
             "with per-day charts of price vs the levels and tools to keep the history "
             "filled in. The raw material for all the level studies.",
     "cmd": _st("mq_levels_command_center.py") + ["--port", "8610"]},

    {"key": "discord_intel", "group": "Discord",
     "title": "Discord Intel", "port": 8640,
     "desc": "Scrapes tracked Discord channels (MenthorQ / MZpack / Quant Systems) for "
             "testable setups, nuggets & links. Add a channel or server ID and it "
             "auto-resolves the name and pulls everything; auto-refreshes hourly.",
     "info": "Turns trading-Discord chatter into an intel feed: paste a channel or "
             "server ID, it finds the name and scrapes the history, then extracts "
             "testable setups, insight nuggets and important links. Runs an hourly "
             "incremental pull so it stays current. Data in data/discord/.",
     "cmd": _st("discord_intel.py") + ["--port", "8640"]},

    {"key": "data_catalog", "group": "Reference",
     "title": "Data Catalog", "port": 8620,
     "desc": "Index of every data family (~116 GB): size, freshness, health, "
             "useful-for, access snippet, gotchas. Rescan button.",
     "info": "Index of every dataset on the machine (~116 GB) — futures ticks, options "
             "chains, gamma levels, footprint ladders — with size, freshness and what each "
             "is useful for. Browse it read-only to see what data exists.",
     "cmd": _st("data_catalog.py") + ["serve", "--port", "8620"]},

    {"key": "wfa_app", "group": "Research (Streamlit)",
     "title": "WFA Research App", "port": 8501,
     "desc": "The main Streamlit app — bar analyzer, WFA/PROM, auction & regime tabs. "
             "Heavy: first load imports scipy (~3-4s).",
     "info": "The original research workbench — walk-forward analysis of ES futures "
             "strategies (train on one period, verify on the next), bar analyzers, "
             "auction/regime studies. Where strategies get validated or killed.",
     "cmd": _streamlit("app.py", 8501)},
    # Options Forward-Sim (:8502) removed S75: its live tabs (Trades/Journal/Perf)
    # duplicated the Options Desk, and its unique tabs (Decisions/fill-tapes/calibration)
    # were driven by the retired options_sim_daemon (frozen 7/14). Viewer deleted;
    # data files kept as historical archive.
]
BYKEY = {d["key"]: d for d in DASHBOARDS}

_pids = {}   # key -> pid (loaded from PIDFILE)
_lock = threading.Lock()


def _load_pids():
    global _pids
    if PIDFILE.exists():
        try:
            _pids = json.loads(PIDFILE.read_text())
        except Exception:
            _pids = {}


def _save_pids():
    PIDFILE.parent.mkdir(parents=True, exist_ok=True)
    PIDFILE.write_text(json.dumps(_pids))


def port_up(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        return s.connect_ex((host, port)) == 0


def pid_on_port(port):
    """Fallback: find the PID LISTENING on a port via netstat (Windows)."""
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3] == "LISTENING" and parts[1].endswith(f":{port}"):
            try:
                return int(parts[4])
            except ValueError:
                pass
    return None


def _rec(key):
    """Return the {pid, started} record for a key (tolerates the old int format)."""
    r = _pids.get(key)
    if isinstance(r, int):
        return {"pid": r, "started": None}
    return r if isinstance(r, dict) else None


def start(key):
    d = BYKEY.get(key)
    if not d:
        return {"ok": False, "err": "unknown"}
    if port_up(d["port"]):
        return {"ok": True, "already": True}
    LOGDIR.mkdir(parents=True, exist_ok=True)
    logf = open(LOGDIR / f"{key}.log", "w", encoding="utf-8", errors="replace")
    logf.write(f"# launched {dt.datetime.now().isoformat(timespec='seconds')}\n"
               f"# {' '.join(d['cmd'])}\n\n")
    logf.flush()
    try:
        p = subprocess.Popen(d["cmd"], cwd=str(ROOT), stdout=logf,
                             stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             creationflags=_FLAGS, close_fds=True)
    except Exception as e:
        return {"ok": False, "err": str(e)}
    with _lock:
        _pids[key] = {"pid": p.pid, "started": dt.datetime.now().isoformat(timespec="seconds")}
        _save_pids()
    return {"ok": True, "pid": p.pid}


def stop(key):
    d = BYKEY.get(key)
    if not d:
        return {"ok": False, "err": "unknown"}
    rec = _rec(key)
    pid = (rec or {}).get("pid") or pid_on_port(d["port"])
    if not pid:
        return {"ok": False, "err": "no pid / not running"}
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, text=True, timeout=15)
    except Exception as e:
        return {"ok": False, "err": str(e)}
    with _lock:
        _pids.pop(key, None)
        _save_pids()
    return {"ok": True}


def restart(key):
    stop(key)
    return start(key)


def open_when_up(key, timeout=25.0):
    """Open the dashboard in the user's default browser once its port is LISTENING.
    Runs in a background thread so slow (Streamlit) apps open when actually ready and
    fast (stdlib) apps open near-instantly — no blank/placeholder tabs, no popup blocker
    (the launcher runs locally, so webbrowser.open() gets a real user-desktop context)."""
    d = BYKEY.get(key)
    if not d:
        return
    url = f"http://127.0.0.1:{d['port']}/"

    def _wait():
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if port_up(d["port"]):
                break
            time.sleep(0.4)
        webbrowser.open(url)

    threading.Thread(target=_wait, daemon=True).start()


def _mem_map(pids):
    """One tasklist call -> {pid: mem_bytes} for the given pids (best-effort)."""
    if not pids:
        return {}
    out = {}
    try:
        r = subprocess.run(["tasklist", "/FO", "CSV", "/NH"],
                           capture_output=True, text=True, timeout=8).stdout
        import csv as _csv
        want = set(pids)
        for row in _csv.reader(r.splitlines()):
            if len(row) >= 5:
                try:
                    pid = int(row[1])
                except ValueError:
                    continue
                if pid in want:
                    kb = row[4].replace(",", "").replace("K", "").strip()
                    try:
                        out[pid] = int(kb) * 1024
                    except ValueError:
                        pass
    except Exception:
        pass
    return out




def _artifacts_html():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import artifacts_page
    return artifacts_page.HTML


def _timeline_html():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import timeline_page
    return timeline_page.HTML



def _pause_task(task_name, pause):
    """Enable/disable a Windows scheduled task from Mission Control.

    Pausing is a first-class operation, not an edge case: QUIN's token quota runs out,
    an API goes down for a day, a job is mid-rewrite. Without this the only options are
    to let it fail nightly (training you to ignore red) or to go hunting in Task
    Scheduler. The task keeps its schedule; it simply does not fire.
    """
    verb = "Disable" if pause else "Enable"
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                            "-WindowStyle", "Hidden", "-Command",
                            f"{verb}-ScheduledTask -TaskName '{task_name}' | Out-Null; "
                            f"(Get-ScheduledTask -TaskName '{task_name}').State"],
                           capture_output=True, text=True, timeout=45,
                           creationflags=0x08000000)
        state = (r.stdout or "").strip().splitlines()[-1] if r.stdout.strip() else "?"
        ok = r.returncode == 0
        try:  # the paused/ready state must show up immediately, not in 60s
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import pipeline_health
            pipeline_health._CACHE.pop("taskstatus", None)
        except Exception:
            pass
        return {"ok": ok, "task": task_name, "state": state,
                "error": None if ok else (r.stderr or "")[:200]}
    except Exception as e:
        return {"ok": False, "task": task_name, "state": "?", "error": f"{type(e).__name__}: {e}"}



ARTIFACT_DIR = ROOT / "docs" / "artifacts"


def _artifact_files():
    """Locally-backed-up Claude artifacts, newest first.

    The claude_artifacts.json snapshot only ever held titles and URLs - the pages
    themselves lived on claude.ai and nothing was in the repo. These are the real
    backups: readable with no account, no network, and versioned in git.
    """
    if not ARTIFACT_DIR.exists():
        return []
    meta = {}
    try:
        raw = json.loads((ROOT / "data" / "_catalog" / "claude_artifacts.json").read_text(encoding="utf-8"))
        items = raw if isinstance(raw, list) else raw.get("artifacts", raw.get("items", []))
        import re as _re
        for a in items:
            slug = _re.sub(r"[^a-zA-Z0-9]+", "_", a.get("title", "")).strip("_").lower()[:48]
            meta[slug] = a
    except Exception:
        pass
    out = []
    for f in sorted(ARTIFACT_DIR.glob("*.html")):
        st = f.stat()
        m = meta.get(f.stem, {})
        out.append({"slug": f.stem, "title": m.get("title") or f.stem.replace("_", " "),
                    "kb": round(st.st_size / 1024, 1), "url": m.get("url", ""),
                    "group": m.get("group", ""), "info": (m.get("info") or "")[:400],
                    "saved": dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")})
    return sorted(out, key=lambda x: x["title"].lower())


def _timeline():
    """Registry + live status per process, for Mission Control /timeline."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import process_registry as reg
        import pipeline_health as ph
        h = ph.health()
        sess = ph.session_info()
        hs = {c["name"]: c for c in h["checks"]}
        ts = ph.task_status()
        ok_codes = (0, 267009, 267011, 267014)
        out = []
        for key, label, items in reg.by_phase():
            rows = []
            for pr in sorted(items, key=lambda x: x["ct"]):
                st, detail = "idle", ""
                # 1) a health check is the strongest evidence (it reads the artefact)
                chk = hs.get(pr.get("health") or "")
                if chk:
                    st, detail = chk["state"], chk["detail"]
                # 2) otherwise fall back to the scheduled-task result
                t = ts.get(pr.get("task") or "")
                if t:
                    detail = detail or f"last {t['last'] or 'never'} - next {t['next'] or '-'}"
                    if not chk:
                        if t["result"] in ok_codes:
                            st = "ok"
                        elif t["day"] in (0, 6):
                            st = "idle"          # stale weekend result, not a failure
                        elif h["market"] == "closed":
                            # A weekday failure is real, but while the market is SHUT nothing
                            # is wrong right now and the job is not due - so do not light the
                            # board amber all weekend. The detail still carries the failure and
                            # it goes amber again the moment the market reopens.
                            st = "ok"
                            detail += "  (last weekday run failed - recheck at the open)"
                        else:
                            st = "warn"
                # Continuous recorders have no clock time, but they are not "never next":
                # while the market is shut the very next thing that happens is that they
                # START at the open. Excluding them made the board point at a 07:30 archive
                # job while the real next event was ES depth recording beginning at 17:00 CT.
                if pr["ct"] != "cont":
                    nxt = ph.next_process_epoch(pr["ct"])
                elif sess["session"] in ("closed", "halt"):
                    nxt = sess["next_eth_epoch"]
                else:
                    nxt = None          # already running
                paused = bool(t and str(t.get("tstate", "")).lower() == "disabled")
                if paused:
                    st, nxt = "paused", None
                    detail = "PAUSED - will not run until resumed"
                rows.append(dict(pr, state=st, detail=detail, next_epoch=nxt, paused=paused,
                                 last=(t or {}).get("last", ""), next=(t or {}).get("next", "")))
            out.append({"key": key, "label": label, "items": rows})
        # the process the clock is about to hit — the board should point at what is NEXT,
        # not just report what already happened
        upcoming = [i for phz in out for i in phz["items"] if i.get("next_epoch")]
        up_id = min(upcoming, key=lambda i: i["next_epoch"])["id"] if upcoming else None
        return {"phases": out, "market": h["market"], "chicago": h["chicago"],
                "overall": h["overall"], "upcoming": up_id, **sess}
    except Exception as e:
        return {"phases": [], "market": "?", "chicago": "",
                "overall": "warn", "error": f"{type(e).__name__}: {e}"}


def _health():
    """Evidence-based pipeline health (see scripts/pipeline_health.py).

    Never let a broken check take Mission Control down - degrade to an error card.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import pipeline_health
        # NO importlib.reload here. It reset pipeline_health's module-level cache on every
        # request, so the expensive probes (Get-ScheduledTask, tasklist) re-ran on every
        # poll from every open tab - a strobe of console windows. Restart MC to pick up
        # edits instead.
        return pipeline_health.health()
    except Exception as e:
        return {"overall": "warn", "market": "?", "chicago": "",
                "checks": [{"name": "pipeline_health", "state": "warn",
                            "detail": f"{type(e).__name__}: {e}"}]}


_HEALTH_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Pipeline Health — Mission Control</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--chip:#30363d;--fg:#e6edf3;--muted:#8b949e}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--fg);font:13.5px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;
  display:flex;flex-direction:column;overflow:hidden}
header{display:flex;align-items:center;gap:10px;padding:10px 16px;border-bottom:1px solid var(--chip);flex:0 0 auto}
h1{font-size:15px;margin:0}
a{color:#58a6ff;text-decoration:none}
.pill{padding:2px 10px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid var(--chip)}
.ok{color:#22c55e;border-color:#22c55e}.warn{color:#f59e0b;border-color:#f59e0b}
.bad{color:#ef4444;border-color:#ef4444}.idle{color:#8b949e}
.hint{color:var(--muted);font-size:11.5px;padding:6px 16px 0}
/* grid: everything visible at once, no page scroll */
#rows{flex:1 1 auto;display:grid;gap:9px;padding:10px 16px 14px;overflow:hidden;
  grid-template-columns:repeat(auto-fit,minmax(255px,1fr));
  grid-auto-rows:minmax(74px,1fr)}
.row{background:var(--card);border:1px solid var(--chip);border-radius:10px;padding:10px 12px;
  display:flex;gap:9px;align-items:flex-start;cursor:grab;transition:transform .12s,box-shadow .12s,opacity .12s;
  overflow:hidden}
.row:active{cursor:grabbing}
.row.bad{border-color:#ef4444}.row.warn{border-color:#f59e0b66}
.row.drag{opacity:.35}
.row.over{transform:scale(1.03);box-shadow:0 0 0 2px #58a6ff inset}
.dot{width:10px;height:10px;border-radius:50%;margin-top:4px;flex:0 0 auto}
.bd{min-width:0}
.nm{font-weight:600;font-size:13px}
.dt{color:var(--muted);font-family:ui-monospace,Consolas,monospace;font-size:11.5px;
  overflow-wrap:anywhere}
.fix{margin-top:4px;font-size:11px;color:#7d8590;border-left:2px solid var(--chip);padding-left:7px}
footer{flex:0 0 auto;padding:5px 16px 9px;color:var(--muted);font-size:11px;display:flex;gap:12px}
button{background:var(--chip);color:var(--fg);border:1px solid #444c56;border-radius:7px;
  padding:3px 9px;font-size:11px;cursor:pointer}
</style></head><body>
<header><h1>Pipeline Health</h1>
  <span class="pill" id="overall">…</span>
  <span class="pill" id="mkt">…</span>
  <span style="margin-left:auto"></span>
  <a href="/">← Mission Control</a>
</header>
<p class="hint">Each check reads the <b>artefact</b> a process produces and how fresh it is — never
whether the process is alive. Drag tiles to reorder; the layout is remembered.</p>
<div id="rows"></div>
<footer><span id="gen"></span><span id="note"></span></footer>
<script>
const FIX={
 "L2 depth":"Control Center → Strategies → MarketDepthRecorder must be ENABLED (a recompile disables it).",
 "Contract":"Roll the chart/strategy to the front-month contract, then re-enable the recorder.",
 "Footprint":"FootprintExporter needs Tick Replay ON for its data series.",
 "NinjaTrader":"scripts/nt8_login.ps1 starts NT8 and signs in.",
 "NT8 tick DB":"Tools → Options → Market data → 'Record live data as historical' must be ON.",
 "IB gateway":"Login is not the same as the API port — run scripts/gateway_ensure.py.",
 "Options sim":"Check the sim daemon scheduled task and data/options_sim/live.json.",
 "Disk":"data/depth grows fast — convert finished days to parquet.",
 "Scheduled tasks":"Task Scheduler → look at Last Run Result for the named tasks."};
const C={ok:"#22c55e",warn:"#f59e0b",bad:"#ef4444",idle:"#6b7280"};
const LSKEY='healthOrder';
let order=JSON.parse(localStorage.getItem(LSKEY)||'[]');
let dragName=null;

function saveOrder(){
  order=[...document.querySelectorAll('.row')].map(r=>r.dataset.name);
  localStorage.setItem(LSKEY,JSON.stringify(order));
}
function sortChecks(cs){
  if(!order.length) return cs;
  const ix=n=>{const i=order.indexOf(n);return i<0?999:i;};
  return [...cs].sort((a,b)=>ix(a.name)-ix(b.name));
}
function wire(el){
  el.draggable=true;
  el.addEventListener('dragstart',e=>{dragName=el.dataset.name;el.classList.add('drag');
    e.dataTransfer.effectAllowed='move';});
  el.addEventListener('dragend',()=>{el.classList.remove('drag');
    document.querySelectorAll('.row').forEach(r=>r.classList.remove('over'));saveOrder();});
  el.addEventListener('dragover',e=>{e.preventDefault();el.classList.add('over');});
  el.addEventListener('dragleave',()=>el.classList.remove('over'));
  el.addEventListener('drop',e=>{e.preventDefault();el.classList.remove('over');
    const src=[...document.querySelectorAll('.row')].find(r=>r.dataset.name===dragName);
    if(!src||src===el)return;
    const rows=[...document.querySelectorAll('.row')];
    (rows.indexOf(src)<rows.indexOf(el)?el.after(src):el.before(src));
    saveOrder();});
}
async function load(){
  const h=await(await fetch('/health.json')).json();
  const o=document.getElementById('overall');
  o.textContent=h.overall.toUpperCase(); o.className='pill '+h.overall;
  document.getElementById('mkt').textContent='market '+h.market;
  document.getElementById('gen').textContent='checked '+h.chicago+' CT';
  const n=h.checks.filter(c=>c.state==='bad'||c.state==='warn').length;
  document.getElementById('note').textContent=n?(n+' need attention'):'all clear';
  const box=document.getElementById('rows');
  box.innerHTML=sortChecks(h.checks).map(c=>{
    const fix=(c.state==='bad'||c.state==='warn')&&FIX[c.name]
      ?'<div class="fix">'+FIX[c.name]+'</div>':'';
    return '<div class="row '+c.state+'" data-name="'+c.name+'">'
      +'<span class="dot" style="background:'+C[c.state]+'"></span>'
      +'<div class="bd"><div class="nm">'+c.name+'</div>'
      +'<div class="dt">'+c.detail+'</div>'+fix+'</div></div>';}).join('');
  document.querySelectorAll('.row').forEach(wire);
}
load(); setInterval(load,30000);
</script></body></html>"""

def _health_html():
    return _HEALTH_HTML


def status():
    rows = []
    probe = {}
    live_pids = []
    for d in DASHBOARDS:
        t0 = dt.datetime.now()
        up = port_up(d["port"])
        ms = round((dt.datetime.now() - t0).total_seconds() * 1000)
        rec = _rec(d["key"]) if up else None
        pid = (rec or {}).get("pid")
        if pid:
            live_pids.append(pid)
        probe[d["key"]] = (up, ms, rec)
    mem = _mem_map(live_pids)
    for d in DASHBOARDS:
        up, ms, rec = probe[d["key"]]
        pid = (rec or {}).get("pid")
        started = (rec or {}).get("started")
        up_secs = None
        if started:
            try:  # computed here so clients never parse timezone-less timestamps
                up_secs = max(0, int((dt.datetime.now()
                                      - dt.datetime.fromisoformat(started)).total_seconds()))
            except ValueError:
                pass
        rows.append({"key": d["key"], "title": d["title"], "desc": d["desc"],
                     "info": d.get("info", ""), "up_secs": up_secs,
                     "port": d["port"], "group": d["group"], "up": up,
                     "pid": pid, "started": started,
                     "mem": mem.get(pid) if pid else None, "ms": ms,
                     "url": f"http://127.0.0.1:{d['port']}/"})
    running = sum(1 for r in rows if r["up"])
    return {"dashboards": rows, "running": running, "total": len(rows),
            "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


def tail_log(key, n=60):
    f = LOGDIR / f"{key}.log"
    if not f.exists():
        return "(no log yet)"
    try:
        lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except Exception as e:
        return f"(log read failed: {e})"


# ---------------------------------------------------------------- artifacts
# Published Claude Artifacts (claude.ai-hosted pages we've built over the project).
# The launcher (plain Python) can't call the Artifact tool, so the list is kept as a
# snapshot in data/_catalog/claude_artifacts.json — ask Claude to "refresh the
# artifacts list" to regenerate it (Artifact action:list -> this file).
ARTIFACTS_FILE = ROOT / "data" / "_catalog" / "claude_artifacts.json"


def load_artifacts():
    if ARTIFACTS_FILE.exists():
        try:
            return json.loads(ARTIFACTS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"artifacts": [], "generated": None}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json", code=200):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, loc):
        self.send_response(301)
        self.send_header("Location", loc)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _is_local(self):
        return self.client_address[0] in ("127.0.0.1", "::1")

    def _has_key(self):
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)
        return q.get("key", [""])[0] == VIEWER_TOKEN

    def do_GET(self):
        p = self.path.split("?")[0]
        # ---- remote (Tailscale) visitors: read-only surface, token required ----
        if not self._is_local():
            if p in ("/favicon.svg", "/favicon.ico"):
                return self._send(FAVICON, "image/svg+xml")
            if not self._has_key():
                return self._send("<h1>403</h1><p>viewer key required (?key=...)</p>",
                                  "text/html; charset=utf-8", 403)
            if p in ("/", "/view"):
                return self._send(VIEW_HTML.replace("__DESKKEY__", _desk_token()),
                                  "text/html; charset=utf-8")
            if p == "/status.json":
                return self._send(json.dumps(status()))
            if p == "/artifacts.json":
                return self._send(json.dumps(load_artifacts()))
            if p == "/tour":
                return self._send_tour()
            if p == "/library":
                return self._send_library()
            if p == "/levels":
                return self._send_levels()
            if p == "/mqmethod":
                return self._send_mqmethod()
            if p == "/gexlab":
                return self._send_gexlab()
            if p == "/flowlab":
                return self._send_flowlab()
            if p == "/slides" or p.startswith("/slides/"):
                return self._send_slides(p)
            if p == "/catalog" or p.startswith("/catalog/"):
                return self._proxy_catalog(p[len("/catalog"):])
            return self._send("<h1>403</h1><p>read-only viewer: not available</p>",
                              "text/html; charset=utf-8", 403)
        # ---- localhost: full Mission Control ----
        if p == "/":
            return self._send(HTML, "text/html; charset=utf-8")
        if p == "/view":
            return self._send(VIEW_HTML.replace("__DESKKEY__", _desk_token()),
                              "text/html; charset=utf-8")
        if p == "/tour":
            return self._send_tour()
        if p == "/library":
            return self._send_library()
        if p == "/levels":
            return self._send_levels()
        if p == "/mqmethod":
            return self._send_mqmethod()
        if p == "/gexlab":
            return self._send_gexlab()
        if p == "/flowlab":
            return self._send_flowlab()
        if p == "/slides" or p.startswith("/slides/"):
            return self._send_slides(p)
        if p in ("/favicon.svg", "/favicon.ico"):
            return self._send(FAVICON, "image/svg+xml")
        if p == "/status.json":
            return self._send(json.dumps(status()))
        if p == "/health.json":
            return self._send(json.dumps(_health()))
        if p == "/health":
            return self._send(_health_html(), "text/html; charset=utf-8")
        if p.startswith("/pause/") or p.startswith("/resume/"):
            import urllib.parse
            name = urllib.parse.unquote(p.split("/", 2)[2])
            return self._send(json.dumps(_pause_task(name, p.startswith("/pause/"))))
        if p == "/artifacts":
            return self._send(_artifacts_html(), "text/html; charset=utf-8")
        if p == "/artifacts_local.json":
            return self._send(json.dumps(_artifact_files()))
        if p.startswith("/artifact/"):
            slug = p[len("/artifact/"):]
            f = ARTIFACT_DIR / (slug + ".html")
            # never let a crafted slug walk out of the artifacts directory
            if ".." in slug or "/" in slug or "\\" in slug or not f.exists():
                return self._send("<h1>404</h1>", "text/html; charset=utf-8", 404)
            return self._send(f.read_text(encoding="utf-8", errors="replace"),
                              "text/html; charset=utf-8")
        if p == "/timeline.json":
            return self._send(json.dumps(_timeline()))
        if p == "/timeline":
            return self._send(_timeline_html(), "text/html; charset=utf-8")
        if p == "/artifacts.json":
            return self._send(json.dumps(load_artifacts()))
        if p.startswith("/log/"):
            return self._send(json.dumps({"log": tail_log(p[len("/log/"):])}))
        if p == "/catalog" or p.startswith("/catalog/"):
            return self._proxy_catalog(p[len("/catalog"):])
        self.send_response(404)
        self.end_headers()

    def _proxy_catalog(self, sub):
        """GET-only proxy to the Data Catalog (:8620) so remote viewers can browse
        what data exists without reaching the catalog server (which stays on
        127.0.0.1 and keeps its Rescan POST). The catalog page's absolute-path
        fetches are rewritten to come back through this proxy with the key."""
        import urllib.request
        url = f"http://127.0.0.1:8620{sub or '/'}"
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                body = r.read()
                ctype = r.headers.get("Content-Type", "text/html; charset=utf-8")
        except Exception:
            return self._send("<h1>Data Catalog offline</h1><p>the :8620 server isn't "
                              "running right now.</p>", "text/html; charset=utf-8")
        if "html" in ctype:
            txt = body.decode("utf-8", "replace")
            txt = txt.replace("fetch('/view.json')",
                              f"fetch('/catalog/view.json?key={VIEWER_TOKEN}')")
            txt = txt.replace("fetch('/scan_log')",
                              f"fetch('/catalog/scan_log?key={VIEWER_TOKEN}')")
            # read-only: the Rescan button becomes a no-op
            txt = txt.replace("fetch('/rescan',{method:'POST'})", "Promise.resolve()")
            body = txt.encode("utf-8")
        return self._send(body, ctype)

    def _send_tour(self):
        f = ROOT / "docs" / "options_desk_tour.html"
        if f.exists():
            return self._send(f.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        return self._send("<h1>tour not found</h1><p>docs/options_desk_tour.html missing.</p>",
                          "text/html; charset=utf-8")

    def _send_slides(self, p):
        # Slide Library (S75N): /slides -> gallery (docs/slides/index.html, built by
        # scripts/slides_build.py); /slides/<topic>/<file> -> static file. Read-only,
        # path-traversal-safe, so the keyed remote viewer may browse it too.
        base = (ROOT / "docs" / "slides").resolve()
        # The gallery's links are RELATIVE ("footprint-reading/01_x.png"). Served at
        # "/slides" with no trailing slash a browser resolves them against "/", so it
        # asks for "/footprint-reading/01_x.png" and every slide 404s. Redirecting to
        # "/slides/" makes relative resolution land inside the gallery. Query string is
        # preserved so the keyed remote viewer keeps its ?key= across the hop.
        if p == "/slides":
            from urllib.parse import urlsplit
            q = urlsplit(self.path).query
            return self._redirect("/slides/" + (("?" + q) if q else ""))
        if p == "/slides/":
            f = base / "index.html"
            if f.exists():
                return self._send(f.read_text(encoding="utf-8"), "text/html; charset=utf-8")
            return self._send("<h1>no gallery yet</h1><p>run scripts/slides_build.py.</p>",
                              "text/html; charset=utf-8")
        from urllib.parse import unquote
        target = (base / unquote(p[len("/slides/"):])).resolve()
        if base not in target.parents or not target.is_file():
            return self._send("not found", "text/plain", 404)
        ctype = {"png": "image/png", "md": "text/plain; charset=utf-8",
                 "html": "text/html; charset=utf-8", "py": "text/plain; charset=utf-8",
                 "jpg": "image/jpeg", "svg": "image/svg+xml"}.get(
            target.suffix.lstrip(".").lower(), "application/octet-stream")
        return self._send(target.read_bytes(), ctype)

    def _send_library(self):
        # MZpack Insights knowledge base (S75N) — built from docs/mzpack_insights/notes/
        # by scripts/mzpack_library_build.py; self-contained HTML, safe for the remote
        # viewer too (static educational content, no controls).
        f = ROOT / "docs" / "mzpack_insights" / "library.html"
        if f.exists():
            return self._send(f.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        return self._send("<h1>library not built</h1><p>run scripts/mzpack_library_build.py "
                          "to generate docs/mzpack_insights/library.html.</p>",
                          "text/html; charset=utf-8")

    def _send_mqmethod(self):
        # MenthorQ Method research dossier (S75P) - the trading method extracted from
        # 7 Academy video transcripts, with every mechanical claim tested against
        # 1,159 sessions of ES. Static self-contained HTML, safe for the remote viewer.
        f = ROOT / "docs" / "mq_method" / "index.html"
        if f.exists():
            return self._send(f.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        return self._send("<h1>dossier missing</h1><p>docs/mq_method/index.html not found.</p>",
                          "text/html; charset=utf-8")

    def _send_levels(self):
        # Gamma Levels slide deck (S75P) — 10 sessions/slide across every session we
        # have ORATS chains + ES bars for, with MenthorQ and our own CR/PS/HVL overlaid,
        # plus the SPX daily navigator. Built by scripts/orats_levels_slides.py.
        # Self-contained HTML (data embedded), static — safe for the remote viewer.
        f = ROOT / "docs" / "levels_slides" / "levels.html"
        if f.exists():
            return self._send(f.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        return self._send("<h1>slides not built</h1><p>run scripts/orats_levels_slides.py "
                          "to generate docs/levels_slides/levels.html.</p>",
                          "text/html; charset=utf-8")

    def _send_flowlab(self):
        # S75R — ES 1M order-flow reading, two complete swings of 2026-07-17
        # (08:45-09:21, 37 bars). Ladder + delta arithmetic + commentary per bar.
        # Rebuild: scripts/flowlab_1m.py -> render_1m_bars.py -> flowlab_report.py.
        # ~3.7MB, images embedded base64 so it works from any route.
        f = ROOT / "docs" / "gexlab" / "flow1m.html"
        if f.exists():
            return self._send(f.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        return self._send("<h1>report not built</h1><p>run scripts/flowlab_1m.py, "
                          "scripts/render_1m_bars.py, then scripts/flowlab_report.py.</p>",
                          "text/html; charset=utf-8")

    def _send_gexlab(self):
        # S75Q research report — does MenthorQ gamma positioning help the Brooks
        # method? Regime axis: dead. Level axis: one weak CR result (n=66) plus
        # three nulls. Pre-reg in docs/living/s75q_prereg.md; rebuild with
        # scripts/gex_levels_brooks.py then scripts/s75q_report.py.
        # Self-contained HTML, static — safe for the remote viewer.
        f = ROOT / "docs" / "gexlab" / "s75q.html"
        if f.exists():
            return self._send(f.read_text(encoding="utf-8"), "text/html; charset=utf-8")
        return self._send("<h1>report not built</h1><p>run scripts/gex_levels_brooks.py "
                          "then scripts/s75q_report.py to generate docs/gexlab/s75q.html.</p>",
                          "text/html; charset=utf-8")

    def do_POST(self):
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)
        key = q.get("key", [""])[0]
        if not self._is_local():
            # Remote exceptions: a keyed viewer may START or RESTART the Options
            # Desk (so Thomas can bring the dashboard up / reload it himself).
            # No stop, nothing else. Auth via `token` (`key` carries the
            # dashboard key).
            act = self.path.split("?")[0]
            if (act in ("/start", "/restart") and key == "options_desk"
                    and q.get("token", [""])[0] == VIEWER_TOKEN):
                fn = start if act == "/start" else restart
                return self._send(json.dumps(fn("options_desk")))
            return self._send(json.dumps({"ok": False, "err": "read-only viewer"}), code=403)
        if self.path.startswith("/startall"):
            res = {d["key"]: start(d["key"]) for d in DASHBOARDS}
            for d in DASHBOARDS:
                open_when_up(d["key"])
            return self._send(json.dumps(res))
        if self.path.startswith("/openall"):
            for d in DASHBOARDS:
                if port_up(d["port"]):
                    open_when_up(d["key"])
            return self._send(json.dumps({"ok": True}))
        if self.path.startswith("/stopall"):
            return self._send(json.dumps({d["key"]: stop(d["key"]) for d in DASHBOARDS}))
        if self.path.startswith("/restart"):
            r = restart(key)
            open_when_up(key)
            return self._send(json.dumps(r))
        if self.path.startswith("/open"):
            open_when_up(key)
            return self._send(json.dumps({"ok": True}))
        if self.path.startswith("/start"):
            r = start(key)
            open_when_up(key)
            return self._send(json.dumps(r))
        if self.path.startswith("/stop"):
            return self._send(json.dumps(stop(key)))
        self.send_response(404)
        self.end_headers()


FAVICON = r"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#bef264"/><stop offset="1" stop-color="#65a30d"/>
    </linearGradient>
    <linearGradient id="fl" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#fbbf24"/><stop offset="1" stop-color="#f97316"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="15" fill="url(#bg)"/>
  <path d="M40 54 L32 58 L24 54 Q23 46 24 42 L40 42 Q41 46 40 54 Z" fill="url(#fl)"/>
  <path d="M32 8 Q43 20 42 38 Q42 44 40 47 L24 47 Q22 44 22 38 Q21 20 32 8 Z" fill="#ffffff"/>
  <path d="M24 40 L15 49 Q14 50 15 50 L24 47 Z" fill="#c7d2fe"/>
  <path d="M40 40 L49 49 Q50 50 49 50 L40 47 Z" fill="#c7d2fe"/>
  <circle cx="32" cy="26" r="5.5" fill="#1e3a8a"/>
  <circle cx="32" cy="26" r="3" fill="#60a5fa"/>
</svg>"""

HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mission Control</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="apple-touch-icon" href="/favicon.svg">
<style>
:root{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
  --border:rgba(11,11,11,.10);--pos:#2a78d6;--card:#fff;--good:#0ca30c;--bad:#e34948;--chip:#f0efea}
@media(prefers-color-scheme:dark){:root{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;
  --muted:#898781;--border:rgba(255,255,255,.10);--pos:#3987e5;--card:#1f1f1e;--good:#0ca30c;--bad:#e66767;--chip:#26261f}}
:root[data-theme=dark]{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
  --border:rgba(255,255,255,.10);--pos:#3987e5;--card:#1f1f1e;--chip:#26261f}
:root[data-theme=light]{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
  --border:rgba(11,11,11,.10);--pos:#2a78d6;--card:#fff;--chip:#f0efea}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px}
header{padding:13px 20px;border-bottom:1px solid var(--border);background:var(--surface);display:flex;gap:16px;align-items:baseline;flex-wrap:wrap;position:sticky;top:0;z-index:5}
h1{font-size:16px;margin:0;font-weight:650}
.wrap{max-width:none;margin:0;padding:18px 20px 80px;overflow-x:auto}
button{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--border);border-radius:8px;padding:6px 13px;cursor:pointer}
button:hover{border-color:var(--muted)}
button.primary{background:var(--pos);color:#fff;border-color:var(--pos)}
button.danger{color:var(--bad);border-color:var(--bad)}
button:disabled{opacity:.4;cursor:default}
button.ic{padding:6px 9px}
.auto{font-size:12px;color:var(--ink2);display:flex;align-items:center;gap:4px;cursor:pointer}
.pill{font-size:12px;font-weight:600;padding:3px 10px;border-radius:20px;background:var(--chip);color:var(--muted)}
.pill.on{background:rgba(12,163,12,.14);color:var(--good)}
.arthead{display:flex;gap:12px;align-items:center;margin:34px 0 12px;border-bottom:1px solid var(--border);padding-bottom:8px}
.arthead .grp{font-size:13px}
#art-filter{padding:5px 10px;border:1px solid var(--border);border-radius:8px;background:var(--card);color:var(--ink);font:inherit;width:150px}
.artgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}
.agrp{margin:6px 0 4px;font-size:11px;font-weight:600;letter-spacing:.03em;text-transform:uppercase;color:var(--muted)}
.acard{display:block;text-decoration:none;color:inherit;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:11px 13px;transition:border-color .12s,transform .12s}
.acard:hover{border-color:var(--pos);transform:translateY(-1px)}
.acard .at{font-weight:600;font-size:13.5px;display:flex;align-items:center;gap:6px}
.acard .am{font-size:11.5px;color:var(--muted);margin-top:3px;font-variant-numeric:tabular-nums}
.acard .ext{font-size:14px;opacity:.85}
#groups{display:flex;gap:16px;align-items:flex-start}
.col{flex:1 1 0;min-width:250px;display:flex;flex-direction:column;gap:12px}
.grp{margin:0 0 2px;font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--ink2);border-bottom:1px solid var(--border);padding-bottom:6px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;gap:9px}
.top{display:flex;align-items:center;gap:9px}
.dot{width:10px;height:10px;border-radius:50%;flex:0 0 auto;background:var(--muted)}
.dot.up{background:var(--good);box-shadow:0 0 0 3px rgba(12,163,12,.18)}
.title{font-weight:650;font-size:14.5px}
.port{margin-left:auto;font-family:ui-monospace,monospace;font-size:12px;color:var(--muted)}
.desc{font-size:12.5px;color:var(--ink2);line-height:1.45;min-height:34px}
.actions{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.actions button{padding:5px 9px;font-size:12.5px}
.state{width:100%}
.state{font-size:12px;color:var(--muted);margin-left:auto}
.state.up{color:var(--good)}
a.open{text-decoration:none}
.spin{display:inline-block;width:12px;height:12px;border:2px solid var(--border);border-top-color:var(--pos);border-radius:50%;animation:s .7s linear infinite;vertical-align:-1px}
@keyframes s{to{transform:rotate(360deg)}}
details{margin-top:2px}details summary{cursor:pointer;font-size:11.5px;color:var(--muted)}
pre{background:var(--chip);border-radius:7px;padding:8px 10px;font-size:11px;overflow:auto;max-height:180px;margin:6px 0 0}
.muted{color:var(--muted)}
.menu{position:relative;display:inline-block}
.menu-pop{display:none;position:absolute;right:0;top:calc(100% + 6px);z-index:50;min-width:210px;
  background:var(--card,#161b22);border:1px solid var(--chip,#30363d);border-radius:9px;padding:5px;
  box-shadow:0 10px 30px rgba(0,0,0,.45)}
.menu-pop a{display:block;padding:7px 10px;border-radius:6px;font-size:12.5px;text-decoration:none;color:inherit}
.menu-pop a:hover{background:var(--chip,#30363d)}
.menu.open .menu-pop{display:block}
#healthbtn.ok{border-color:#22c55e;color:#22c55e}
#healthbtn.warn{border-color:#f59e0b;color:#f59e0b}
#healthbtn.bad{border-color:#ef4444;color:#ef4444;font-weight:700}
</style></head><body>
<header>
  <h1>🚀 Mission Control</h1>
  <span class="pill" id="summary">…</span>
  <span style="margin-left:auto"></span>
  <a href="/timeline" target="_blank" rel="noopener"><button title="the trading day as a chronological set of automated processes">🕐 Timeline</button></a>
  <a href="/health" target="_blank" rel="noopener"><button id="healthbtn" title="is everything actually recording? evidence-based pipeline health">● Health</button></a>
  <div class="menu">
    <button id="libbtn" title="explanations, study material and research write-ups">📚 Library ▾</button>
    <div class="menu-pop" id="libpop">
      <a href="/tour" target="_blank" rel="noopener" title="how the options desk automation works — shareable explainer">📖 Desk Tour</a>
      <a href="/library" target="_blank" rel="noopener" title="MZpack Insights knowledge base — order-flow education organized by topic">📚 MZpack Library</a>
      <a href="/slides" target="_blank" rel="noopener" title="study-material slides by topic (docs/slides/)">🎞 Slides</a>
      <a href="/levels" target="_blank" rel="noopener" title="Gamma Levels slide deck — MenthorQ + our CR/PS/HVL over intraday price">📈 Gamma Levels</a>
      <a href="/mqmethod" target="_blank" rel="noopener" title="MenthorQ Method — framework from 7 Academy videos, every claim tested">🔬 MQ Method</a>
      <a href="/gexlab" target="_blank" rel="noopener" title="S75Q — do MenthorQ gamma levels help the Brooks method?">🧪 GEX Lab</a>
      <a href="/flowlab" target="_blank" rel="noopener" title="S75R — ES 1M order-flow reading, bar by bar">🕯 Flow Lab</a>
      <a href="/artifacts" target="_blank" rel="noopener" title="Local backups of every Claude artifact - readable offline">🗂 Artifact Library</a>
      <a href="/catalog" target="_blank" rel="noopener" title="Data Catalog — every dataset, where it lives, how fresh it is">🗄 Data Catalog</a>
    </div>
  </div>
  <button id="reload" title="refresh status now">↻ Reload</button>
  <button class="primary" id="startall">▶ Start all</button>
  <button id="openall" title="open every running dashboard">↗ Open running</button>
  <button class="danger" id="stopall">■ Stop all</button>
  <label class="auto"><input type="checkbox" id="autochk" checked> auto</label>
  <button id="theme" title="toggle light/dark">◐</button>
  <span class="muted" id="gen"></span>
</header>
<div class="wrap">
  <div id="groups"></div>
  <div class="arthead">
    <span class="grp" style="border:0;margin:0;padding:0">Claude Artifacts</span>
    <span class="pill" id="art-count">…</span>
    <input id="art-filter" placeholder="filter…" autocomplete="off">
    <span style="margin-left:auto"></span>
    <span class="muted" id="art-gen"></span>
  </div>
  <div id="artifacts"></div>
</div>
<script>
// Library dropdown + health pill in the header
(function(){
  const m=document.getElementById('libbtn'); if(m){
    const box=m.parentElement;
    m.onclick=e=>{e.stopPropagation();box.classList.toggle('open');};
    document.addEventListener('click',()=>box.classList.remove('open'));
  }
  async function hp(){try{
    const h=await(await fetch('/health.json')).json();
    const b=document.getElementById('healthbtn');
    if(b){b.className=h.overall;
      const n=h.checks.filter(c=>c.state==='bad'||c.state==='warn').length;
      b.textContent=(h.overall==='ok'?'● Health':'● Health ('+n+')');}
  }catch(e){}}
  hp(); setInterval(hp,20000);
})();

const css=k=>getComputedStyle(document.documentElement).getPropertyValue(k).trim();
let ST=null, timer=null;
const mem=b=>b==null?'':(b>=1e9?(b/1e9).toFixed(2)+' GB':(b/1e6).toFixed(0)+' MB');
function uptime(s){if(s==null)return '';const h=Math.floor(s/3600),m=Math.floor(s%3600/60);
  if(h)return h+'h '+m+'m';if(m)return m+'m';return s+'s';}

async function load(){
  ST=await(await fetch('/status.json')).json();
  document.getElementById('gen').textContent='checked '+ST.generated;
  const s=document.getElementById('summary');
  s.textContent=ST.running+' / '+ST.total+' running';
  s.className='pill '+(ST.running?'on':'');
  const groups={};ST.dashboards.forEach(d=>{(groups[d.group]=groups[d.group]||[]).push(d);});
  const openDetails=new Set([...document.querySelectorAll('details[open]')].map(e=>e.dataset.k));
  let h='';
  for(const g of Object.keys(groups)){
    h+=`<div class="col"><div class="grp">${g}</div>`;
    for(const d of groups[g]){
      const meta=d.up?[d.pid?('pid '+d.pid):'', d.up_secs!=null?('up '+uptime(d.up_secs)):'', mem(d.mem), d.ms+'ms'].filter(Boolean).join(' · '):'stopped';
      h+=`<div class="card" id="card-${d.key}">
        <div class="top"><span class="dot ${d.up?'up':''}"></span>
          <span class="title">${d.title}</span><span class="port">:${d.port}</span></div>
        <div class="desc">${d.desc}</div>
        <div class="actions">
          <button class="primary btn-start" data-k="${d.key}" ${d.up?'disabled':''}>▶ Start</button>
          <a class="open" href="${d.url}" target="_blank" rel="noopener"><button ${d.up?'':'disabled'}>↗ Open</button></a>
          <button class="btn-restart" data-k="${d.key}" ${d.up?'':'disabled'} title="stop then start">⟳ Restart</button>
          <button class="danger btn-stop" data-k="${d.key}" ${d.up?'':'disabled'}>■ Stop</button>
          <button class="ic btn-copy" data-u="${d.url}" title="copy URL">⧉</button>
          <span class="state ${d.up?'up':''}">${meta}</span>
        </div>
        <details data-k="${d.key}" ${openDetails.has(d.key)?'open':''}><summary>log</summary><pre id="log-${d.key}">…</pre></details>
      </div>`;
    }
    h+='</div>';
  }
  document.getElementById('groups').innerHTML=h;
  document.querySelectorAll('.btn-start').forEach(b=>b.onclick=()=>act('start',b.dataset.k));
  document.querySelectorAll('.btn-stop').forEach(b=>b.onclick=()=>act('stop',b.dataset.k));
  document.querySelectorAll('.btn-restart').forEach(b=>b.onclick=()=>act('restart',b.dataset.k));
  document.querySelectorAll('.btn-copy').forEach(b=>b.onclick=()=>{navigator.clipboard?.writeText(b.dataset.u);b.textContent='✓';setTimeout(()=>b.textContent='⧉',900);});
  document.querySelectorAll('details').forEach(el=>{el.ontoggle=()=>{if(el.open)loadLog(el.dataset.k);};if(el.open)loadLog(el.dataset.k);});
}
async function loadLog(k){const j=await(await fetch('/log/'+k)).json();
  const el=document.getElementById('log-'+k);if(el)el.textContent=j.log;}
async function act(kind,key){
  const card=document.getElementById('card-'+key);
  card.querySelectorAll('button').forEach(b=>b.disabled=true);
  const st=card.querySelector('.state');
  st.innerHTML='<span class="spin"></span> '+({start:'starting…',stop:'stopping…',restart:'restarting…'}[kind]);
  await fetch('/'+kind+'?key='+encodeURIComponent(key),{method:'POST'});
  for(let i=0;i<9;i++){await new Promise(r=>setTimeout(r,700));await load();
    const d=ST.dashboards.find(x=>x.key===key);
    if((kind!=='stop'&&d.up)||(kind==='stop'&&!d.up))break;}
  loadLog(key);
}
async function bulk(kind,label){const map={startall:'starting all…',stopall:'stopping all…'};
  const b=document.getElementById(kind);const t=b.textContent;b.disabled=true;b.innerHTML='<span class="spin"></span>';
  await fetch('/'+kind,{method:'POST'});
  for(let i=0;i<11;i++){await new Promise(r=>setTimeout(r,800));await load();}
  b.disabled=false;b.textContent=t;}
// Start all: POST /startall — the launcher spawns each server AND opens its tab
// (server-side webbrowser.open once the port is up), so there are no blank tabs and
// no popup blocker. We just poll to refresh the dots.
document.getElementById('startall').onclick=()=>bulk('startall');
document.getElementById('stopall').onclick=()=>bulk('stopall');
// Open running: let the launcher open the tabs server-side (reliable; no popup block).
document.getElementById('openall').onclick=()=>fetch('/openall',{method:'POST'});
document.getElementById('reload').onclick=load;
const auto=document.getElementById('autochk');
function setAuto(){if(timer)clearInterval(timer);timer=null;if(auto.checked)timer=setInterval(load,5000);}
auto.onchange=setAuto;
// theme toggle (pages read data-theme; default follows OS)
const root=document.documentElement;
document.getElementById('theme').onclick=()=>{
  const cur=root.getAttribute('data-theme')||(matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
  root.setAttribute('data-theme',cur==='dark'?'light':'dark');};
// ---- Claude Artifacts section ----
const GEMOJI={Brooks:'📘',Options:'🎯',Signals:'📈',MenthorQ:'⬡','Expected Move':'📐',Footprint:'👣',Other:'🧩'};
let ARTS=null;
async function loadArtifacts(){
  const j=await(await fetch('/artifacts.json')).json();
  ARTS=j.artifacts||[];
  document.getElementById('art-count').textContent=ARTS.length+' artifacts';
  document.getElementById('art-gen').textContent=j.generated?('snapshot '+j.generated+' · ask Claude to refresh'):'no snapshot — ask Claude to refresh';
  renderArtifacts();
}
function renderArtifacts(){
  const q=(document.getElementById('art-filter').value||'').toLowerCase();
  const items=ARTS.filter(a=>!q||a.title.toLowerCase().includes(q)||(a.group||'').toLowerCase().includes(q));
  const groups={};items.forEach(a=>{(groups[a.group||'Other']=groups[a.group||'Other']||[]).push(a);});
  // order groups by most-recent update inside
  const order=Object.keys(groups).sort((a,b)=>Math.max(...groups[b].map(x=>+new Date(x.updated)))-Math.max(...groups[a].map(x=>+new Date(x.updated))));
  let h='';
  for(const g of order){
    h+=`<div class="agrp">${GEMOJI[g]||'🧩'} ${g} · ${groups[g].length}</div><div class="artgrid">`;
    for(const a of groups[g].sort((x,y)=>+new Date(y.updated)-+new Date(x.updated))){
      h+=`<a class="acard" href="${a.url}" target="_blank" rel="noopener">
        <div class="at"><span class="ext">${GEMOJI[a.group]||'🧩'}</span>${a.title} <span style="margin-left:auto;opacity:.5">↗</span></div>
        <div class="am">updated ${a.updated||'—'}</div></a>`;
    }
    h+='</div>';
  }
  document.getElementById('artifacts').innerHTML=h||'<div class="muted" style="padding:10px">no artifacts match.</div>';
}
document.getElementById('art-filter').oninput=renderArtifacts;

load();setAuto();loadArtifacts();
</script></body></html>"""


VIEW_HTML = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mission Control — Viewer</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>
:root{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
  --border:rgba(11,11,11,.10);--pos:#2a78d6;--card:#fff;--good:#0ca30c;--bad:#e34948;--chip:#f0efea}
@media(prefers-color-scheme:dark){:root{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;
  --muted:#898781;--border:rgba(255,255,255,.10);--pos:#3987e5;--card:#1f1f1e;--bad:#e66767;--chip:#26261f}}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px}
header{padding:13px 20px;border-bottom:1px solid var(--border);background:var(--surface);display:flex;gap:14px;align-items:baseline;flex-wrap:wrap;position:sticky;top:0;z-index:5}
h1{font-size:16px;margin:0;font-weight:650}
.ro{font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--bad);border:1px solid var(--bad);border-radius:20px;padding:2px 9px}
.pill{font-size:12px;font-weight:600;padding:3px 10px;border-radius:20px;background:var(--chip);color:var(--muted)}
.pill.on{background:rgba(12,163,12,.14);color:var(--good)}
.wrap{max-width:1100px;margin:0 auto;padding:18px 20px 80px}
.hint{font-size:12.5px;color:var(--ink2);margin:0 0 16px}
a{color:var(--pos)}
#groups{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap}
.col{flex:1 1 250px;min-width:250px;display:flex;flex-direction:column;gap:12px}
.grp{margin:0 0 2px;font-size:12px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--ink2);border-bottom:1px solid var(--border);padding-bottom:6px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px;display:flex;flex-direction:column;gap:8px}
.top{display:flex;align-items:center;gap:9px}
.dot{width:10px;height:10px;border-radius:50%;flex:0 0 auto;background:var(--muted)}
.dot.up{background:var(--good);box-shadow:0 0 0 3px rgba(12,163,12,.18)}
.title{font-weight:650;font-size:14.5px}
.port{margin-left:auto;font-family:ui-monospace,monospace;font-size:12px;color:var(--muted)}
.desc{font-size:12.5px;color:var(--ink2);line-height:1.45}
.state{font-size:12px;color:var(--muted)}
.state.up{color:var(--good)}
.arthead{display:flex;gap:12px;align-items:center;margin:34px 0 12px;border-bottom:1px solid var(--border);padding-bottom:8px}
.artgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:10px}
.agrp{margin:6px 0 4px;font-size:11px;font-weight:600;letter-spacing:.03em;text-transform:uppercase;color:var(--muted)}
.acard{display:block;background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:11px 13px}
.acard .at{font-weight:600;font-size:13.5px}
.acard .am{font-size:11.5px;color:var(--muted);margin-top:3px}
button{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--border);border-radius:8px;padding:5px 11px;cursor:pointer;font-size:12.5px}
button.primary{background:var(--pos);color:#fff;border-color:var(--pos)}
button:disabled{opacity:.4;cursor:default}
.muted{color:var(--muted)}
.tour{font-size:12.5px;margin:0 0 6px}
.info{display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:50%;
  border:1px solid var(--muted);color:var(--muted);font-size:10.5px;font-weight:600;cursor:help;flex:0 0 auto;
  font-family:Georgia,serif;font-style:italic;user-select:none}
.info:hover{border-color:var(--pos);color:var(--pos)}
</style></head><body>
<header>
  <h1>🚀 Mission Control</h1><span class="ro">viewer</span>
  <span class="pill" id="summary">…</span>
  <span style="margin-left:auto"></span>
  <button id="reload" onclick="load()" title="refresh status now">↻ Reload</button>
  <span class="muted" id="gen"></span>
</header>
<div class="wrap">
  <p class="hint">Live view of Samir's research &amp; trading stack. You can <b>start the Options
  Desk</b> and <b>browse the Data Catalog</b>; everything else is status-only. The desk itself
  opens with the keyed :8600 link Samir gave you.</p>
  <p class="tour" style="margin:0 0 10px;font-size:13px">📖 <a id="tourlink" href="/tour" target="_blank" rel="noopener">How the Options Desk works</a>
  &nbsp;·&nbsp; 📚 <a id="liblink" href="/library" target="_blank" rel="noopener">MZpack order-flow library</a></p>
  <div id="groups"></div>
  <div class="arthead"><span style="font-size:13px;font-weight:600">Claude Artifacts — research &amp; learning pages built along the way</span>
    <span class="info" title="Interactive pages generated with Claude during the research: courses, data dictionaries, cheat sheets, trade-audit reports. They live in Samir's Claude account, so the cards aren't clickable here — ask him to share any you want to read.">i</span>
    <span class="pill" id="art-count">…</span></div>
  <div id="artifacts"></div>
</div>
<script>
const KEY=new URLSearchParams(location.search).get('key')||'';
const k=u=>u+(u.includes('?')?'&':'?')+'key='+encodeURIComponent(KEY);
document.getElementById('tourlink').href=k('/tour');
document.getElementById('liblink').href=k('/library');
function fmtup(s){if(s==null)return '';const h=Math.floor(s/3600),m=Math.floor(s%3600/60);
  if(h)return h+'h '+m+'m';if(m)return m+'m';return s+'s';}
async function load(){
  const ST=await(await fetch(k('/status.json'))).json();
  document.getElementById('gen').textContent='checked '+ST.generated;
  const s=document.getElementById('summary');
  s.textContent=ST.running+' / '+ST.total+' running';
  s.className='pill '+(ST.running?'on':'');
  const groups={};ST.dashboards.forEach(d=>{(groups[d.group]=groups[d.group]||[]).push(d);});
  let h='';
  for(const g of Object.keys(groups)){
    h+=`<div class="col"><div class="grp">${g}</div>`;
    for(const d of groups[g]){
      let extra='';
      if(d.key==='options_desk')
        extra=d.up?`<a href="http://${location.hostname}:8600/?key=__DESKKEY__" target="_blank" rel="noopener"><button class="primary">↗ Open desk</button></a>
                    <button onclick="deskAct(this,'restart','reloading…')" title="restart the desk server if it looks stuck">⟳ Reload desk</button>`
                  :`<button class="primary" onclick="deskAct(this,'start','starting…')">▶ Start desk</button>`;
      if(d.key==='data_catalog'&&d.up)
        extra=`<a href="${k('/catalog')}" target="_blank" rel="noopener"><button>↗ Browse (read-only)</button></a>`;
      const inf=d.info?`<span class="info" title="${d.info.replace(/"/g,'&quot;')}">i</span>`:'';
      h+=`<div class="card">
        <div class="top"><span class="dot ${d.up?'up':''}"></span>
          <span class="title">${d.title}</span>${inf}<span class="port">:${d.port}</span></div>
        <div class="desc">${d.desc}</div>
        <div style="display:flex;gap:8px;align-items:center">${extra}
          <span class="state ${d.up?'up':''}">${d.up?('running'+(d.up_secs!=null?' · up '+fmtup(d.up_secs):'')):'stopped'}</span></div>
      </div>`;
    }
    h+='</div>';
  }
  document.getElementById('groups').innerHTML=h;
}
async function deskAct(btn,act,label){
  btn.disabled=true;btn.textContent=label;
  await fetch('/'+act+'?key=options_desk&token='+encodeURIComponent(KEY),{method:'POST'});
  for(let i=0;i<10;i++){await new Promise(r=>setTimeout(r,800));await load();}
}
async function loadArtifacts(){
  const j=await(await fetch(k('/artifacts.json'))).json();
  const arts=j.artifacts||[];
  document.getElementById('art-count').textContent=arts.length+' pages';
  const groups={};arts.forEach(a=>{(groups[a.group||'Other']=groups[a.group||'Other']||[]).push(a);});
  let h='';
  for(const g of Object.keys(groups)){
    h+=`<div class="agrp">${g} · ${groups[g].length}</div><div class="artgrid">`;
    for(const a of groups[g]){
      const inf=a.info?`<span class="info" title="${a.info.replace(/"/g,'&quot;')}">i</span>`:'';
      h+=`<div class="acard"><div class="at" style="display:flex;gap:6px;align-items:center">${a.title}${inf}</div>
        <div class="am">updated ${a.updated||'—'}</div></div>`;
    }
    h+='</div>';
  }
  document.getElementById('artifacts').innerHTML=h||'<div class="muted">none listed.</div>';
}
load();loadArtifacts();setInterval(load,5000);
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Mission Control — dashboard launcher")
    ap.add_argument("--port", type=int, default=8590)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    _load_pids()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Mission Control at {url}  (Ctrl-C to stop)")
    # Read-only share link for remote viewers (Thomas) — needs --host 0.0.0.0
    try:
        tsip = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True,
                              timeout=5).stdout.strip().splitlines()
        if tsip:
            print(f"  VIEWER (Tailscale, read-only): "
                  f"http://{tsip[0]}:{args.port}/view?key={VIEWER_TOKEN}")
            if args.host == "127.0.0.1":
                print("  (viewer unreachable remotely — relaunch with --host 0.0.0.0)")
    except Exception:
        pass
    if args.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
