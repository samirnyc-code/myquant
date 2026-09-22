"""backtest_page.py — Mission Control section for MenthorQ's "Gamma Levels | Backtesting"
tile. Six level panels per session (captured daily into gamma_tracker/gamma.db by the
'MyQuant Backtest Levels' task), one expander per day, all fields shown.
"""

HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Gamma-Level Backtest — Mission Control</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--card2:#1b222b;--chip:#30363d;--fg:#e6edf3;--muted:#8b949e;
  --pos:#3fb950;--warn:#d29922;--neg:#f85149;--accent:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:13.5px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
header{display:flex;align-items:center;gap:10px;padding:11px 18px;border-bottom:1px solid var(--chip);
  position:sticky;top:0;background:var(--bg);z-index:20}
h1{font-size:15px;margin:0}
a{color:var(--accent);text-decoration:none}
.pill{padding:2px 10px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid var(--chip);color:var(--muted)}
.btn{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;border-radius:8px;
  padding:5px 12px;border:1px solid;margin-left:7px;color:var(--accent);border-color:#58a6ff55;background:#58a6ff12}
.btn:hover{background:#58a6ff26;border-color:var(--accent)}
.wrap{padding:14px 18px 60px;max-width:1400px}
.hint{color:var(--muted);font-size:12px;margin:0 0 16px;max-width:90ch}
details{background:var(--card);border:1px solid var(--chip);border-radius:11px;margin:0 0 10px;overflow:hidden}
details[open]{border-color:#58a6ff55}
summary{cursor:pointer;list-style:none;padding:11px 16px;display:flex;align-items:center;gap:14px;
  flex-wrap:wrap;user-select:none}
summary::-webkit-details-marker{display:none}
summary::before{content:"▸";color:var(--muted);font-size:12px;transition:transform .15s}
details[open] summary::before{transform:rotate(90deg)}
.d-date{font-family:ui-monospace,Consolas,monospace;font-weight:700;font-size:14px}
.d-glance{display:flex;gap:7px;flex-wrap:wrap;margin-left:auto}
.g{font-family:ui-monospace,Consolas,monospace;font-size:11px;padding:2px 8px;border-radius:6px;
  border:1px solid var(--chip);color:var(--muted)}
.g b{color:var(--fg)}
.panels{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;
  padding:6px 16px 16px}
.panel{background:var(--card2);border:1px solid var(--chip);border-radius:10px;padding:13px 15px}
.p-head{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin-bottom:10px}
.p-name{font-weight:650;font-size:13.5px}
.p-hold{font-family:ui-monospace,Consolas,monospace;font-weight:700;font-size:20px;font-variant-numeric:tabular-nums}
.p-holdlab{font-size:9.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;text-align:right}
.rows{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-family:ui-monospace,Consolas,monospace;font-size:12px}
.rows .k{color:var(--muted)}
.rows .v{text-align:right;font-variant-numeric:tabular-nums}
.sub{grid-column:1/-1;border-top:1px solid var(--chip);margin:7px 0 3px;padding-top:6px;
  font-size:9.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.pos{color:var(--pos)} .warn{color:var(--warn)} .neg{color:var(--neg)}
.empty{color:var(--muted);padding:30px;text-align:center}
</style></head><body>
<header><h1>Gamma-Level Backtest</h1>
  <span class="pill" id="count">…</span>
  <span style="margin-left:auto"></span>
  <a class="btn" href="/artifacts">Artifacts</a>
  <a class="btn" href="/timeline">Timeline</a>
  <a class="btn" href="/">Mission Control</a>
</header>
<div class="wrap">
  <p class="hint">MenthorQ's <b>Gamma Levels | Backtesting</b> tile, scraped daily into
  <code>gamma.db</code> (task: <i>MyQuant Backtest Levels</i>, 08:15 CT). Six level panels per
  session — how each gamma level has historically behaved: hold-rate, break-at-close, comeback,
  and the size of moves when tested. Newest day open; click any day to expand.</p>
  <div id="days"></div>
</div>
<script>
function esc(s){return (s==null?'':String(s)).replace(/&/g,'&amp;').replace(/</g,'&lt;');}
function num(x,d){return (x==null||x!=x)?'—':(d!=null?Number(x).toFixed(d):x);}
function holdClass(v){return v==null?'':(v>=85?'pos':(v>=70?'warn':'neg'));}
function moveCls(v){return v==null?'':(v>=0?'pos':'neg');}
// which db columns are the "today actuals" (often null until EOD backfill)
var ACTUALS=[['session_high','sess H'],['session_low','sess L'],['session_close','sess close'],
  ['touched','touched'],['held','held'],['broke_intraday','broke intraday'],
  ['max_excursion_beyond','max excursion'],['closed_beyond','closed beyond'],
  ['dist_beyond_at_close','dist@close']];
function panel(p){
  var hc=holdClass(p.regime_hold_rate_pct);
  var h='<div class="panel"><div class="p-head"><div class="p-name">'+esc(p.level_name)
    + (p.level_price!=null?' <span style="color:var(--muted);font-weight:400">@'+num(p.level_price)+'</span>':'')
    + '</div><div><div class="p-hold '+hc+'">'+num(p.regime_hold_rate_pct,1)+'%</div>'
    + '<div class="p-holdlab">hold rate</div></div></div><div class="rows">';
  function row(k,v,cls){h+='<div class="k">'+k+'</div><div class="v '+(cls||'')+'">'+v+'</div>';}
  row('sample (n)', num(p.positive_outcomes));
  row('broke at close', num(p.broke_at_close_pct,1)+'%');
  row('comeback rate', num(p.comeback_rate_pct,1)+'%');
  row('avg move', num(p.avg_move_intraday,1), moveCls(p.avg_move_intraday));
  row('worst move', num(p.worst_move_intraday,1), moveCls(p.worst_move_intraday));
  row('median close-beyond', num(p.median_close_beyond,1), moveCls(p.median_close_beyond));
  row('avg close-beyond', num(p.avg_close_beyond,1), moveCls(p.avg_close_beyond));
  row('worst close-beyond', num(p.worst_close_beyond,1), moveCls(p.worst_close_beyond));
  var acts=ACTUALS.filter(function(a){return p[a[0]]!=null;});
  if(acts.length){ h+='<div class="sub">that session — actual outcome</div>';
    acts.forEach(function(a){row(a[1], num(p[a[0]], typeof p[a[0]]==='number'?1:null));}); }
  if(p.regime_label){ h+='<div class="sub">regime</div>'; row('regime', esc(p.regime_label)); }
  if(p.notes){ h+='<div class="sub">notes</div><div class="k" style="grid-column:1/-1;color:var(--fg)">'+esc(p.notes)+'</div>'; }
  h+='</div></div>';
  return h;
}
function render(days){
  document.getElementById('count').textContent=days.length+' sessions';
  if(!days.length){document.getElementById('days').innerHTML='<div class="empty">no backtest data in gamma.db yet</div>';return;}
  var html=days.map(function(d,i){
    var glance=d.levels.map(function(p){return '<span class="g">'+esc(p.level_name.replace(' 0DTE','·0DTE'))
      +' <b class="'+holdClass(p.regime_hold_rate_pct)+'">'+num(p.regime_hold_rate_pct,0)+'%</b></span>';}).join('');
    return '<details'+(i===0?' open':'')+'><summary>'
      + '<span class="d-date">'+esc(d.date)+'</span>'
      + '<span class="g">'+d.levels.length+' panels</span>'
      + '<span class="d-glance">'+glance+'</span></summary>'
      + '<div class="panels">'+d.levels.map(panel).join('')+'</div></details>';
  }).join('');
  document.getElementById('days').innerHTML=html;
}
fetch('/backtest.json').then(function(r){return r.json();}).then(render)
  .catch(function(e){document.getElementById('days').innerHTML='<div class="empty">failed to load: '+esc(e)+'</div>';});
</script></body></html>"""
