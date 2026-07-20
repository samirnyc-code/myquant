"""playbook_page.py — Mission Control /playbook: the day's reasoning, archived by day.

Every morning the gameplan run renders one chart per price path and per trade idea
(gameplan_charts/YYYYMMDD/), and the trigger daemon snapshots every trade at entry and
exit (options_log/cards/auto_YYYYMMDD_*). This page is where they live: pick a day,
review the full visual playbook — today or any past session. Nothing to file manually.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GP_DIR = ROOT / "data" / "options_sim" / "gameplan_charts"
CARDS = ROOT / "data" / "options_log" / "cards"

_SAFE = re.compile(r"^[A-Za-z0-9._-]+$")


def dates():
    """Every day that has any playbook material, newest first."""
    out = set()
    if GP_DIR.exists():
        out |= {d.name for d in GP_DIR.iterdir() if d.is_dir() and d.name.isdigit()}
    if CARDS.exists():
        for f in CARDS.glob("auto_*_*.png"):
            m = re.match(r"auto_(\d{8})_", f.name)
            if m:
                out.add(m.group(1))
    return sorted(out, reverse=True)


def day_data(date: str) -> dict:
    """File lists for one day, split into the page's three sections."""
    if not re.fullmatch(r"\d{8}", date or ""):
        return {"date": date, "paths": [], "trades": [], "cards": []}
    gp = sorted((GP_DIR / date).glob("*.png")) if (GP_DIR / date).exists() else []
    cards = sorted(CARDS.glob(f"auto_{date}_*.png"))
    return {
        "date": date,
        "paths": [f.name for f in gp if f.name.startswith("path_")],
        "trades": [f.name for f in gp if f.name.startswith("trade_")],
        "cards": [f.name for f in cards],
    }


def resolve_img(kind: str, date: str, name: str) -> Path | None:
    """Strictly-validated image path (no traversal: whitelisted chars only)."""
    if not (_SAFE.fullmatch(name or "") and name.endswith(".png")):
        return None
    if kind == "gp" and re.fullmatch(r"\d{8}", date or ""):
        f = GP_DIR / date / name
    elif kind == "card" and name.startswith("auto_"):
        f = CARDS / name
    else:
        return None
    return f if f.exists() else None


def _title(name: str) -> str:
    n = name.rsplit(".", 1)[0]
    n = re.sub(r"^trade_\d+_", "", n)
    n = re.sub(r"^auto_\d{8}_\d{6}_", "", n)
    return n.replace("_", " ")


def html() -> str:
    ds = dates()
    opts = "".join(f'<option value="{d}">{d[:4]}-{d[4:6]}-{d[6:]}</option>' for d in ds)
    return """<!doctype html><html><head><meta charset="utf-8">
<title>Daily Playbook</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--fg:#e6edf3;--muted:#8b949e;--acc:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:system-ui,'Segoe UI',sans-serif}
header{display:flex;align-items:center;gap:14px;padding:12px 20px;border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--bg);z-index:5}
h1{font-size:17px;margin:0}
select{background:var(--card);color:var(--fg);border:1px solid var(--border);border-radius:8px;padding:6px 10px;font-size:14px}
a.btn{color:var(--fg);text-decoration:none;border:1px solid var(--border);border-radius:8px;padding:6px 12px;font-size:13px;background:var(--card)}
.hint{color:var(--muted);font-size:12px;margin-left:auto}
h2{font-size:14px;color:var(--muted);margin:22px 20px 8px;text-transform:uppercase;letter-spacing:.06em}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(430px,1fr));gap:14px;padding:0 20px}
.tile{background:var(--card);border:1px solid var(--border);border-radius:10px;overflow:hidden}
.tile img{width:100%;display:block;cursor:zoom-in}
.tile .cap{padding:7px 10px;font-size:12.5px;color:var(--muted)}
#empty{color:var(--muted);padding:40px 20px}
#big{position:fixed;inset:0;background:rgba(0,0,0,.88);display:none;align-items:center;justify-content:center;z-index:20;cursor:zoom-out}
#big img{max-width:96vw;max-height:96vh}
</style></head><body>
<header>
  <h1>📋 Daily Playbook</h1>
  <select id="day">__OPTS__</select>
  <a class="btn" href="/">← Mission Control</a>
  <a class="btn" href="/timeline">Timeline</a>
  <span class="hint">price paths + trade ideas rendered at 08:28 · trade cards at each entry/exit — archived every day automatically</span>
</header>
<div id="content"></div>
<div id="big" onclick="this.style.display='none'"><img id="bigimg"></div>
<script>
const SECTIONS=[["paths","Price paths — the day's scenarios and why"],
                ["trades","Trade ideas — structure, zones, grade reasoning"],
                ["cards","Executed trades — entry / exit snapshots"]];
async function load(){
  const d=document.getElementById('day').value;
  if(!d){document.getElementById('content').innerHTML='<div id="empty">no playbook days yet</div>';return}
  const j=await (await fetch('/playbook.json?date='+d)).json();
  let h='';
  for(const [key,title] of SECTIONS){
    const files=j[key]||[];
    if(!files.length) continue;
    h+='<h2>'+title+'</h2><div class="grid">';
    for(const f of files){
      const src=key==='cards'?('/playbook_img/card/'+d+'/'+f):('/playbook_img/gp/'+d+'/'+f);
      h+='<div class="tile"><img loading="lazy" src="'+src+'" onclick="zoom(this.src)">'+
         '<div class="cap">'+f.replace(/\\.png$/,'').replace(/_/g,' ')+'</div></div>';
    }
    h+='</div>';
  }
  document.getElementById('content').innerHTML=h||'<div id="empty">nothing rendered for this day</div>';
}
function zoom(s){document.getElementById('bigimg').src=s;document.getElementById('big').style.display='flex'}
document.getElementById('day').addEventListener('change',load);
load();
</script></body></html>""".replace("__OPTS__", opts)
