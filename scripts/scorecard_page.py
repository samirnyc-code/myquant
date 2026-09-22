"""scorecard_page.py — Mission Control /scorecard: the process × day history grid.

Reads every data/_catalog/scorecard/YYYY-MM-DD.json snapshot and renders one column per
day, one row per process, coloured ✓ (ran OK) / ✗ (ran and FAILED) / · (didn't run).
A red cell weeks ago is now answerable: "what failed on the 18th?" — hover it.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SC = ROOT / "data" / "_catalog" / "scorecard"


def data() -> dict:
    days = []
    for f in sorted(SC.glob("20*.json")):
        try:
            days.append(json.loads(f.read_text()))
        except Exception:
            continue
    days = days[-30:]                       # last 30 recorded days
    # union of processes, preserve registry order from the most recent day
    order, seen = [], set()
    for d in reversed(days):
        for it in d.get("items", []):
            if it["id"] not in seen:
                seen.add(it["id"]); order.append({"id": it["id"], "title": it["title"], "phase": it.get("phase", "")})
    order.reverse()
    return {"days": days, "procs": order}


def html() -> str:
    d = data()
    return "<!doctype html><html><head><meta charset=\"utf-8\"><link rel=\"icon\" href=\"data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📅</text></svg>\"><title>Daily Scorecard</title>" + """
<style>
:root{--bg:#0d1117;--card:#161b22;--border:#30363d;--fg:#e6edf3;--muted:#8b949e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:system-ui,'Segoe UI',sans-serif}
header{display:flex;align-items:center;gap:14px;padding:12px 20px;border-bottom:1px solid var(--border);position:sticky;top:0;background:var(--bg);z-index:5}
h1{font-size:17px;margin:0}
a.btn{color:var(--fg);text-decoration:none;border:1px solid var(--border);border-radius:8px;padding:6px 12px;font-size:13px;background:var(--card)}
.hint{color:var(--muted);font-size:12px;margin-left:auto}
.wrap{padding:14px 20px 60px;overflow-x:auto}
table{border-collapse:collapse;font-size:12px}
th,td{border:1px solid #21262d;padding:4px 6px;text-align:center;white-space:nowrap}
th.p{text-align:left;position:sticky;left:0;background:var(--bg);z-index:2;max-width:260px;overflow:hidden;text-overflow:ellipsis}
td.y{background:#12331c;color:#3fb950;font-weight:800}
td.n{background:#3a1417;color:#ef4444;font-weight:800;cursor:help}
td.z{color:#3a3f47}
th.d{color:var(--muted);font-family:ui-monospace,Consolas,monospace}
th.d.bad{color:#ef4444}
.sum{color:var(--muted);font-size:11px}
tr:hover td{outline:1px solid #58a6ff33}
</style></head><body>
<header><h1>📅 Daily Scorecard</h1>
<a class="btn" href="/">← Mission Control</a><a class="btn" href="/timeline">Timeline</a>
<span class="hint">✓ ran OK · ✗ ran and FAILED (hover for why) · · didn't run — one column per day, newest right</span>
</header>
<div class="wrap"><table id="t"></table></div>
<script>
var D=__DATA__;
function esc(s){return (s==null?'':(''+s)).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
(function(){
  var days=D.days, procs=D.procs;
  var byDay=days.map(function(x){var m={};(x.items||[]).forEach(function(i){m[i.id]=i;});return {date:x.date,n_bad:x.n_bad,map:m};});
  var h='<tr><th class="p">process</th>';
  byDay.forEach(function(dd){h+='<th class="d'+(dd.n_bad>0?' bad':'')+'">'+esc(dd.date.slice(5))+'</th>';});
  h+='</tr>';
  procs.forEach(function(pr){
    h+='<tr><th class="p" title="'+esc(pr.title)+'">'+esc(pr.title)+'</th>';
    byDay.forEach(function(dd){
      var it=dd.map[pr.id];
      if(!it||it.ok===null||it.ok===undefined){h+='<td class="z">·</td>';}
      else if(it.ok===true){h+='<td class="y">\\u2713</td>';}
      else{h+='<td class="n" title="'+esc(it.detail||'failed')+'">\\u2717</td>';}
    });
    h+='</tr>';
  });
  h+='<tr><th class="p sum">day totals (ok/fail)</th>';
  byDay.forEach(function(dd){h+='<td class="sum">'+ (days.find(function(x){return x.date===dd.date;}).n_ok||0)+'/'+(dd.n_bad||0)+'</td>';});
  h+='</tr>';
  document.getElementById('t').innerHTML=h;
})();
</script></body></html>""".replace("__DATA__", json.dumps(d))
