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
     "cmd": _st("options_dashboard_live.py") + ["--host", "127.0.0.1", "--port", "8600"]},

    {"key": "command_center", "group": "MenthorQ",
     "title": "Gamma Levels — Command Center", "port": 8610,
     "desc": "Hub for the ~5yr MenthorQ levels DB (13 tickers): freshness/status, "
             "per-day price-action chart + levels table, Update-now backfill.",
     "cmd": _st("mq_levels_command_center.py") + ["--port", "8610"]},

    {"key": "data_catalog", "group": "Reference",
     "title": "Data Catalog", "port": 8620,
     "desc": "Index of every data family (~116 GB): size, freshness, health, "
             "useful-for, access snippet, gotchas. Rescan button.",
     "cmd": _st("data_catalog.py") + ["serve", "--port", "8620"]},

    {"key": "wfa_app", "group": "Research (Streamlit)",
     "title": "WFA Research App", "port": 8501,
     "desc": "The main Streamlit app — bar analyzer, WFA/PROM, auction & regime tabs. "
             "Heavy: first load imports scipy (~3-4s).",
     "cmd": _streamlit("app.py", 8501)},

    {"key": "options_sim_app", "group": "Research (Streamlit)",
     "title": "Options Forward-Sim", "port": 8502,
     "desc": "Read-only Streamlit over the options pipeline files (trades, grades, POP). "
             "No IB connection.",
     "cmd": _streamlit("scripts/options_app.py", 8502)},
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
        rows.append({"key": d["key"], "title": d["title"], "desc": d["desc"],
                     "port": d["port"], "group": d["group"], "up": up,
                     "pid": pid, "started": (rec or {}).get("started"),
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

    def _send(self, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/":
            return self._send(HTML, "text/html; charset=utf-8")
        if p in ("/favicon.svg", "/favicon.ico"):
            return self._send(FAVICON, "image/svg+xml")
        if p == "/status.json":
            return self._send(json.dumps(status()))
        if p == "/artifacts.json":
            return self._send(json.dumps(load_artifacts()))
        if p.startswith("/log/"):
            return self._send(json.dumps({"log": tail_log(p[len("/log/"):])}))
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(self.path).query)
        key = q.get("key", [""])[0]
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
</style></head><body>
<header>
  <h1>🚀 Mission Control</h1>
  <span class="pill" id="summary">…</span>
  <span style="margin-left:auto"></span>
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
const css=k=>getComputedStyle(document.documentElement).getPropertyValue(k).trim();
let ST=null, timer=null;
const mem=b=>b==null?'':(b>=1e9?(b/1e9).toFixed(2)+' GB':(b/1e6).toFixed(0)+' MB');
function uptime(iso){if(!iso)return '';let s=(Date.now()-new Date(iso))/1000;if(s<0)s=0;
  const h=Math.floor(s/3600),m=Math.floor(s%3600/60);
  if(h)return h+'h '+m+'m';if(m)return m+'m';return Math.floor(s)+'s';}

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
      const meta=d.up?[d.pid?('pid '+d.pid):'', d.started?('up '+uptime(d.started)):'', mem(d.mem), d.ms+'ms'].filter(Boolean).join(' · '):'stopped';
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
    if args.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
