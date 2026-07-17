"""
Discord Intel — Mission Control tab (port 8640).

One page to:
  * READ the intel report (per-channel nuggets / testable setups / links / tickers),
  * ADD a channel *or* server (guild) ID — the name is auto-resolved from your
    account's directory; a server expands to all its readable channels,
  * SCRAPE on demand (incremental or full backfill) — runs as THIS server's own
    subprocess (so the harness classifier never gates it), then rebuilds the report,
  * runs a background SCHEDULER that pulls new messages every `scrape_interval_sec`
    (default hourly) and regenerates the report, so once you Start this card in
    Mission Control it keeps itself current.

Token stays server-side (read from data/discord/config.json) and is NEVER sent to
the browser. Storage:
  data/discord/raw/*.json        raw exports
  data/discord/parsed/*.jsonl    flattened messages
  data/discord/report.json/html  the nuggets/setups/links you view here
  data/discord/directory.json    cached id -> (guild, name) map for resolving
  data/discord/intel.log         scheduler + scrape log

Run:  .venv/Scripts/pythonw.exe scripts/discord_intel.py --port 8640
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
DDIR = ROOT / "data" / "discord"
CONFIG = DDIR / "config.json"
REPORT_JSON = DDIR / "report.json"
DIRECTORY = DDIR / "directory.json"
LOG = DDIR / "intel.log"
PY = sys.executable  # whatever interpreter launched us
SCRAPER = ROOT / "scripts" / "discord_scrape.py"
REPORTER = ROOT / "scripts" / "discord_report.py"
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_lock = threading.Lock()


def log(msg: str):
    line = f"{dt.datetime.now().isoformat(timespec='seconds')}  {msg}"
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line, flush=True)


def load_config() -> dict:
    if not CONFIG.exists():
        return {"dce_exe": "", "token": "", "channels": {}}
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def save_config(cfg: dict):
    with _lock:
        CONFIG.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _dce(cfg, *args, timeout=120):
    cmd = [cfg["dce_exe"], *args, "-t", cfg["token"]]
    return subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, creationflags=_NO_WINDOW)


# ---------------------------------------------------------------- directory
def build_directory() -> dict:
    """Map every guild id and channel id the account can see to a readable name.
    { "guilds": {id: name}, "channels": {id: {"name":..,"guild":..,"guild_id":..}} }"""
    cfg = load_config()
    if not cfg.get("token") or not cfg.get("dce_exe"):
        return {"guilds": {}, "channels": {}, "error": "no token/dce configured"}
    out = {"guilds": {}, "channels": {}, "built": dt.datetime.now().isoformat(timespec="seconds")}
    try:
        r = _dce(cfg, "guilds")
    except Exception as e:
        return {"guilds": {}, "channels": {}, "error": f"guilds failed: {e}"}
    guilds = []
    for ln in (r.stdout or "").splitlines():
        if "|" in ln:
            gid, gname = ln.split("|", 1)
            gid, gname = gid.strip(), gname.strip()
            if gid.isdigit():
                out["guilds"][gid] = gname
                guilds.append((gid, gname))
    for gid, gname in guilds:
        try:
            rc = _dce(cfg, "channels", "-g", gid)
        except Exception:
            continue
        for ln in (rc.stdout or "").splitlines():
            if "|" in ln:
                cid, cname = ln.split("|", 1)
                cid, cname = cid.strip(), cname.strip()
                if cid.isdigit():
                    out["channels"][cid] = {"name": cname, "guild": gname, "guild_id": gid}
    DIRECTORY.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"directory rebuilt: {len(out['guilds'])} guilds, {len(out['channels'])} channels")
    return out


def load_directory() -> dict:
    if DIRECTORY.exists():
        try:
            return json.loads(DIRECTORY.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"guilds": {}, "channels": {}}


# skip these low-signal channel-name patterns when expanding a server
_SKIP = ("ticket-", "welcome", "rules", "onboarding", "support-", "moderator",
         "join-here", "become-an-affiliate", "faqs", "disclaimer", "voice")


def _slug(guild: str, name: str) -> str:
    g = "".join(c for c in guild.lower() if c.isalnum())[:4] or "srv"
    n = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")
    n = "-".join(p for p in n.split("-") if p)[:40] or "chan"
    return f"{g}_{n}"


def resolve_id(rid: str) -> dict:
    """Given an id, say whether it's a guild (with expandable children) or a channel."""
    rid = rid.strip()
    d = load_directory()
    if not d.get("guilds") and not d.get("channels"):
        d = build_directory()
    if rid in d.get("guilds", {}):
        gname = d["guilds"][rid]
        kids = [{"id": cid, "name": c["name"],
                 "skip": any(s in c["name"].lower() for s in _SKIP)}
                for cid, c in d.get("channels", {}).items() if c["guild_id"] == rid]
        return {"kind": "guild", "id": rid, "name": gname, "children": kids}
    if rid in d.get("channels", {}):
        c = d["channels"][rid]
        return {"kind": "channel", "id": rid, "name": c["name"], "guild": c["guild"]}
    # not in cached directory — rebuild once and retry
    d = build_directory()
    if rid in d.get("guilds", {}):
        return resolve_id(rid)
    if rid in d.get("channels", {}):
        c = d["channels"][rid]
        return {"kind": "channel", "id": rid, "name": c["name"], "guild": c["guild"]}
    return {"kind": "unknown", "id": rid,
            "error": "not found in your account's servers (are you a member?)"}


def add_channels(ids: list[str]) -> dict:
    """Add channel ids to config, auto-naming from the directory. Server ids expand
    to their readable (non-skipped) channels."""
    cfg = load_config()
    d = load_directory() or build_directory()
    chans = cfg.setdefault("channels", {})
    existing_ids = set(chans.values())
    added = []
    for rid in ids:
        rid = rid.strip()
        targets = []
        if rid in d.get("guilds", {}):
            gname = d["guilds"][rid]
            for cid, c in d.get("channels", {}).items():
                if c["guild_id"] == rid and not any(s in c["name"].lower() for s in _SKIP):
                    targets.append((cid, gname, c["name"]))
        elif rid in d.get("channels", {}):
            c = d["channels"][rid]
            targets.append((rid, c["guild"], c["name"]))
        else:
            continue
        for cid, gname, cname in targets:
            if cid in existing_ids:
                continue
            key = _slug(gname, cname)
            base, i = key, 2
            while key in chans:
                key = f"{base}-{i}"; i += 1
            chans[key] = cid
            existing_ids.add(cid)
            added.append({"key": key, "id": cid, "name": f"{gname}/{cname}"})
    save_config(cfg)
    log(f"added {len(added)} channel(s)")
    return {"added": added, "total": len(chans)}


def remove_channel(key: str) -> dict:
    cfg = load_config()
    ok = cfg.get("channels", {}).pop(key, None) is not None
    save_config(cfg)
    return {"ok": ok, "total": len(cfg.get("channels", {}))}


# ---------------------------------------------------------------- scrape
_scrape_state = {"running": False, "last": None, "last_result": None}


def run_scrape(mode: str = "incremental", only: str | None = None) -> dict:
    if _scrape_state["running"]:
        return {"ok": False, "err": "a scrape is already running"}
    _scrape_state["running"] = True
    try:
        cmd = [PY, str(SCRAPER), mode]
        if only:
            cmd += ["--channel", only]
        log(f"scrape start: {mode}" + (f" [{only}]" if only else ""))
        r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                           creationflags=_NO_WINDOW, timeout=3600)
        # rebuild report
        rr = subprocess.run([PY, str(REPORTER)], cwd=str(ROOT),
                            capture_output=True, text=True,
                            creationflags=_NO_WINDOW, timeout=600)
        tail = "\n".join((r.stdout or "").splitlines()[-25:])
        rep = (rr.stdout or "").strip().splitlines()[-2:] if rr.stdout else []
        _scrape_state["last"] = dt.datetime.now().isoformat(timespec="seconds")
        _scrape_state["last_result"] = {"rc": r.returncode, "tail": tail, "report": rep}
        log(f"scrape done rc={r.returncode}; {' | '.join(rep)}")
        return {"ok": r.returncode == 0, "tail": tail, "report": rep}
    except Exception as e:
        log(f"scrape error: {e}")
        return {"ok": False, "err": str(e)}
    finally:
        _scrape_state["running"] = False


def scheduler_loop(interval: int):
    log(f"scheduler started (every {interval}s)")
    # small initial delay so the server is up first
    time.sleep(20)
    while True:
        try:
            if load_config().get("channels"):
                run_scrape("incremental")
        except Exception as e:
            log(f"scheduler tick error: {e}")
        time.sleep(interval)


# ---------------------------------------------------------------- report
def load_report() -> dict:
    if REPORT_JSON.exists():
        try:
            return json.loads(REPORT_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"channels": [], "totals": {}}


def public_config() -> dict:
    """Config WITHOUT the token — safe to send to the browser."""
    cfg = load_config()
    return {"channels": cfg.get("channels", {}),
            "interval": cfg.get("scrape_interval_sec", 3600),
            "has_token": bool(cfg.get("token"))}


# ---------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json", code=200):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _local(self):
        return self.client_address[0] in ("127.0.0.1", "::1")

    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/":
            return self._send(PAGE, "text/html; charset=utf-8")
        if p == "/report.json":
            return self._send(load_report())
        if p == "/config.json":
            return self._send(public_config())
        if p == "/directory.json":
            return self._send(load_directory())
        if p == "/state.json":
            return self._send({**_scrape_state, "interval": load_config().get("scrape_interval_sec", 3600)})
        if p == "/log":
            txt = LOG.read_text(encoding="utf-8", errors="replace") if LOG.exists() else ""
            return self._send({"log": "\n".join(txt.splitlines()[-80:])})
        return self._send({"err": "not found"}, code=404)

    def do_POST(self):
        if not self._local():
            return self._send({"err": "localhost only"}, code=403)
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n).decode("utf-8") if n else ""
        try:
            body = json.loads(raw) if raw else {}
        except Exception:
            body = {}
        if p == "/resolve":
            return self._send(resolve_id(str(body.get("id", ""))))
        if p == "/add":
            ids = body.get("ids") or ([body["id"]] if body.get("id") else [])
            return self._send(add_channels([str(i) for i in ids]))
        if p == "/remove":
            return self._send(remove_channel(str(body.get("key", ""))))
        if p == "/refresh-directory":
            return self._send(build_directory())
        if p == "/scrape":
            mode = body.get("mode", "incremental")
            only = body.get("only")
            # run in a thread so the request returns immediately; UI polls /state.json
            threading.Thread(target=run_scrape, args=(mode, only), daemon=True).start()
            return self._send({"ok": True, "started": True})
        return self._send({"err": "not found"}, code=404)


PAGE = r"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Discord Intel</title>
<style>
:root{--bg:#0f1115;--surface:#161a22;--card:#1a1e27;--border:#2a2f3a;--ink:#e6e6e6;--muted:#8a94a6;--accent:#6fa8ff;--good:#3fb950;--warn:#d29922}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--surface);border-bottom:1px solid var(--border);padding:12px 20px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
h1{font-size:17px;margin:0}
.wrap{padding:18px 20px 80px;max-width:1200px;margin:0 auto}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin:0 0 18px}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:10px 16px;min-width:96px}
.kpi .n{font-size:22px;font-weight:700}.kpi .l{font-size:11px;color:var(--muted);text-transform:uppercase}
button{font:inherit;color:var(--ink);background:var(--card);border:1px solid var(--border);border-radius:8px;padding:6px 13px;cursor:pointer}
button:hover{border-color:var(--muted)} button.primary{background:var(--accent);color:#04122b;border-color:var(--accent);font-weight:600}
button:disabled{opacity:.45;cursor:default}
input{font:inherit;background:var(--bg);color:var(--ink);border:1px solid var(--border);border-radius:8px;padding:7px 11px}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px;margin:0 0 18px}
.panel h2{font-size:14px;margin:0 0 10px;color:var(--accent);text-transform:uppercase;letter-spacing:.5px}
.chip{display:inline-block;background:#232838;border:1px solid #313a4f;border-radius:12px;padding:2px 9px;margin:2px;font-size:12px}
.chan-chip{display:inline-flex;align-items:center;gap:6px;background:#20252f;border:1px solid var(--border);border-radius:14px;padding:3px 6px 3px 11px;margin:3px;font-size:12px}
.chan-chip button{padding:0 6px;font-size:12px;border:0;background:transparent;color:var(--muted)}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:9px 12px;margin:6px 0}
.meta{color:var(--muted);font-size:11px}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.chan{border:1px solid var(--border);border-radius:10px;padding:6px 14px;margin:8px 0;background:var(--surface)}
details summary{cursor:pointer;font-weight:600;padding:6px 0}
h3{font-size:12px;color:var(--accent);margin:12px 0 5px;text-transform:uppercase;letter-spacing:.5px}
.k-youtube{color:#ff6b6b}.k-tradingview{color:#4fd1c5}.k-github{color:#c9a2ff}.k-image{color:#8a94a6}.k-gdocs{color:#5b9bd5}
#resolveOut{margin-top:10px}
.tabbtn{background:transparent;border:0;border-bottom:2px solid transparent;border-radius:0;padding:6px 4px;color:var(--muted)}
.tabbtn.active{color:var(--ink);border-bottom-color:var(--accent)}
pre{background:#0c0e13;border:1px solid var(--border);border-radius:7px;padding:8px 10px;font-size:11px;overflow:auto;max-height:200px}
.spin{display:inline-block;width:12px;height:12px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:s .7s linear infinite;vertical-align:-1px}
@keyframes s{to{transform:rotate(360deg)}}
</style></head><body>
<header>
  <h1>🛰️ Discord Intel</h1>
  <span class="chip" id="statechip">…</span>
  <span style="margin-left:auto"></span>
  <button id="btn-inc" class="primary">⟳ Scrape new</button>
  <button id="btn-full" title="full history of all channels">⤓ Full backfill</button>
  <button id="reload">↻ Reload</button>
</header>
<div class="wrap">
  <div class="kpis" id="kpis"></div>

  <div class="panel">
    <h2>Add a channel or server</h2>
    <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
      <input id="idin" placeholder="paste a channel ID or server (guild) ID" style="flex:1;min-width:260px">
      <button id="btn-resolve">Resolve</button>
      <button id="btn-refresh-dir" title="rebuild the id→name directory from your account">↻ Directory</button>
    </div>
    <div id="resolveOut"></div>
  </div>

  <div class="panel">
    <h2>Tracked channels (<span id="chan-count">0</span>) · scrapes every <span id="ivl">–</span></h2>
    <div id="chanlist"></div>
  </div>

  <div class="panel" style="padding:8px 16px">
    <div style="display:flex;gap:2px">
      <button class="tabbtn active" data-t="traders">⭐ Traders to Watch</button>
      <button class="tabbtn" data-t="setups">Setups</button>
      <button class="tabbtn" data-t="nuggets">Nuggets</button>
      <button class="tabbtn" data-t="links">Links</button>
      <button class="tabbtn" data-t="log">Log</button>
    </div>
  </div>
  <div id="report"></div>
</div>
<script>
const $=s=>document.querySelector(s);
let REP=null, CFG=null, TAB='traders';
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function j(u,o){return (await fetch(u,o)).json();}

async function loadAll(){
  [REP,CFG]=await Promise.all([j('/report.json'),j('/config.json')]);
  renderKpis(); renderChans(); renderReport(); refreshState();
}
function renderKpis(){
  const t=REP.totals||{};
  const cells=[['messages','Messages'],['setups','Setups'],['nuggets','Nuggets'],['links','Links'],['channels','Channels']];
  $('#kpis').innerHTML=cells.map(([k,l])=>`<div class="kpi"><div class="n">${(t[k]||0).toLocaleString()}</div><div class="l">${l}</div></div>`).join('')
    + (t.top_tickers&&t.top_tickers.length?`<div class="kpi" style="min-width:220px"><div class="l">Top instruments</div><div style="margin-top:4px">${t.top_tickers.slice(0,8).map(([tk,n])=>`<span class="chip">${esc(tk)}·${n}</span>`).join('')}</div></div>`:'');
}
function renderChans(){
  const ch=CFG.channels||{};const keys=Object.keys(ch).sort();
  $('#chan-count').textContent=keys.length;
  $('#ivl').textContent=fmtIvl(CFG.interval);
  $('#chanlist').innerHTML=keys.length?keys.map(k=>`<span class="chan-chip">${esc(k)}<button title="remove" data-k="${esc(k)}">✕</button></span>`).join(''):'<span class="meta">none yet — add one above.</span>';
  document.querySelectorAll('.chan-chip button').forEach(b=>b.onclick=async()=>{await j('/remove',{method:'POST',body:JSON.stringify({key:b.dataset.k})});loadAll();});
}
function fmtIvl(s){if(!s)return '–';const h=Math.floor(s/3600),m=Math.round(s%3600/60);return h?h+'h':m+'m';}
$('#btn-resolve').onclick=async()=>{
  const id=$('#idin').value.trim();if(!id)return;
  $('#resolveOut').innerHTML='<span class="spin"></span> resolving…';
  const r=await j('/resolve',{method:'POST',body:JSON.stringify({id})});
  if(r.kind==='unknown'){$('#resolveOut').innerHTML=`<div class="card">❌ ${esc(r.error||'not found')}</div>`;return;}
  if(r.kind==='channel'){
    $('#resolveOut').innerHTML=`<div class="card">📺 <b>${esc(r.guild)}</b> / #${esc(r.name)}
      <button class="primary" style="margin-left:8px" id="addone">+ Add & scrape</button></div>`;
    $('#addone').onclick=()=>doAdd([id]);
  } else {
    const kids=r.children||[];const keep=kids.filter(k=>!k.skip);
    $('#resolveOut').innerHTML=`<div class="card">🗄️ Server <b>${esc(r.name)}</b> — ${kids.length} channels (${keep.length} signal, ${kids.length-keep.length} skipped as noise)
      <div style="margin-top:8px">${keep.map(k=>`<span class="chip">#${esc(k.name)}</span>`).join('')}</div>
      <div style="margin-top:10px">
        <button class="primary" id="addsig">+ Add ${keep.length} signal channels</button>
        <button id="addall" style="margin-left:6px">+ Add all ${kids.length}</button>
      </div></div>`;
    $('#addsig').onclick=()=>doAdd(keep.map(k=>k.id));
    $('#addall').onclick=()=>doAdd(kids.map(k=>k.id));
  }
};
async function doAdd(ids){
  $('#resolveOut').innerHTML='<span class="spin"></span> adding…';
  const r=await j('/add',{method:'POST',body:JSON.stringify({ids})});
  $('#resolveOut').innerHTML=`<div class="card">✅ added ${r.added.length} channel(s). Starting a scrape…</div>`;
  $('#idin').value='';
  await j('/scrape',{method:'POST',body:JSON.stringify({mode:'incremental'})});
  loadAll();
}
$('#btn-refresh-dir').onclick=async()=>{$('#resolveOut').innerHTML='<span class="spin"></span> rebuilding directory (asks Discord for every server)…';const d=await j('/refresh-directory',{method:'POST'});$('#resolveOut').innerHTML=`<div class="card">📇 directory: ${Object.keys(d.guilds||{}).length} servers, ${Object.keys(d.channels||{}).length} channels</div>`;};
$('#btn-inc').onclick=()=>startScrape('incremental');
$('#btn-full').onclick=()=>{if(confirm('Full backfill re-pulls ALL history for every tracked channel. Continue?'))startScrape('backfill');};
async function startScrape(mode){await j('/scrape',{method:'POST',body:JSON.stringify({mode})});refreshState();}
async function refreshState(){
  const s=await j('/state.json');
  const c=$('#statechip');
  if(s.running){c.innerHTML='<span class="spin"></span> scraping…';$('#btn-inc').disabled=true;$('#btn-full').disabled=true;setTimeout(()=>refreshState(),2000);}
  else{c.textContent=s.last?('last scrape '+s.last.replace('T',' ').slice(5,16)):'idle';$('#btn-inc').disabled=false;$('#btn-full').disabled=false;if(s._justdone)loadAll();}
}
document.querySelectorAll('.tabbtn').forEach(b=>b.onclick=()=>{TAB=b.dataset.t;document.querySelectorAll('.tabbtn').forEach(x=>x.classList.toggle('active',x===b));renderReport();});
async function renderReport(){
  const el=$('#report');
  if(TAB==='log'){const l=await j('/log');el.innerHTML=`<pre>${esc(l.log||'(empty)')}</pre>`;return;}
  if(TAB==='traders'){
    const A=REP.authors||[];
    if(!A.length){el.innerHTML='<div class="card">No leaderboard yet — scrape first.</div>';return;}
    const max=A[0].score||1;
    let h=`<div class="panel" style="margin-top:12px"><h2>Traders to Watch — ranked by signal (substance + posted P&L + setups/nuggets, not chatter)</h2>
      <div style="overflow-x:auto"><table style="width:100%;border-collapse:collapse;font-size:13px">
      <tr style="text-align:left;color:var(--muted)"><th>#</th><th>Trader</th><th>Signal</th><th>Subst.</th><th>P&L posts</th><th>Setups</th><th>Avg len</th><th>Active</th><th>Top channels</th></tr>`;
    A.forEach((a,i)=>{
      const bar=Math.round(100*a.score/max);
      const chans=(a.channels||[]).map(c=>esc(c[0].replace(/[^\x00-\x7F]/g,''))+'·'+c[1]).join(', ');
      h+=`<tr style="border-top:1px solid var(--border)">
        <td>${i+1}</td>
        <td><b>${esc(a.author)}</b></td>
        <td><div style="display:flex;align-items:center;gap:6px"><div style="width:${bar}px;max-width:90px;height:8px;background:var(--accent);border-radius:4px"></div>${a.score}</div></td>
        <td>${a.substantive}</td><td>${a.pnl_posts}</td><td>${a.setups}</td><td>${a.avg_len}</td>
        <td class="meta">${esc(a.active||'')}</td><td class="meta">${chans}</td></tr>`;
    });
    h+='</table></div><div class="meta" style="margin-top:8px">Score = substantive posts×2 + P&L-mentions×1.5 + setups×1.2 + nuggets + avg-length weight. Min 20 posts to rank.</div></div>';
    el.innerHTML=h;return;
  }
  const chans=(REP.channels||[]).slice().sort((a,b)=>(b.n_setups+b.n_nuggets)-(a.n_setups+a.n_nuggets));
  if(!chans.length){el.innerHTML='<div class="card">No report yet — add channels and hit “Scrape new”.</div>';return;}
  let h='';
  for(const c of chans){
    const items=c[TAB]||[];if(!items.length)continue;
    h+=`<div class="chan"><details><summary>${esc(c.guild)} / #${esc(c.channel)} <span class="meta">· ${items.length} ${TAB}</span></summary>`;
    for(const it of items.slice(0,50)){
      if(TAB==='links')h+=`<div class="card"><a href="${esc(it.url)}" target="_blank" class="k-${esc(it.kind)}">[${esc(it.kind)}] ${esc(it.url.slice(0,95))}</a><div class="meta">${esc(it.author)} · ${esc(it.ctx||'')}</div></div>`;
      else h+=`<div class="card">${esc(it.text)}<div class="meta">${esc(it.author)} · ${esc((it.ts||'').slice(0,16))}</div></div>`;
    }
    h+='</details></div>';
  }
  el.innerHTML=h||`<div class="card">No ${TAB} found in the current report.</div>`;
}
$('#reload').onclick=loadAll;
loadAll();setInterval(refreshState,15000);
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Discord Intel dashboard")
    ap.add_argument("--port", type=int, default=8640)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--no-scheduler", action="store_true")
    args = ap.parse_args()
    DDIR.mkdir(parents=True, exist_ok=True)
    interval = int(load_config().get("scrape_interval_sec", 3600))
    if not args.no_scheduler:
        threading.Thread(target=scheduler_loop, args=(interval,), daemon=True).start()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    log(f"Discord Intel at http://{args.host}:{args.port}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
