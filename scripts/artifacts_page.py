"""artifacts_page.py — Mission Control's local artifact library.

Before this, data/_catalog/claude_artifacts.json held only titles and URLs; the pages
themselves lived on claude.ai and nothing was in the repo. These are the real backups —
readable with no account, no network, versioned in git — served straight from
docs/artifacts/.
"""

HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Artifact Library — Mission Control</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--chip:#30363d;--fg:#e6edf3;--muted:#8b949e}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:13.5px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
header{display:flex;align-items:center;gap:10px;padding:11px 18px;border-bottom:1px solid var(--chip);
  position:sticky;top:0;background:var(--bg);z-index:20}
h1{font-size:15px;margin:0}
a{color:#58a6ff;text-decoration:none}
.pill{padding:2px 10px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid var(--chip);
  color:var(--muted)}
.btn{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;border-radius:8px;
  padding:5px 12px;border:1px solid;margin-left:7px;color:#58a6ff;border-color:#58a6ff55;background:#58a6ff12}
.btn:hover{background:#58a6ff26;border-color:#58a6ff}
.wrap{padding:14px 18px 40px;max-width:1500px}
.hint{color:var(--muted);font-size:12px;margin:0 0 14px}
.grid{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(275px,1fr));margin:0 0 20px}
.daterow{display:flex;align-items:center;gap:10px;margin:18px 0 11px;font-family:ui-monospace,Consolas,monospace;
  font-size:12px;font-weight:600;color:var(--muted);letter-spacing:.02em}
.daterow::after{content:"";flex:1;height:1px;background:var(--chip)}
.daterow .n{color:#6b7280;font-weight:500}
.card{background:var(--card);border:1px solid var(--chip);border-radius:11px;padding:12px 14px;
  display:flex;flex-direction:column;gap:6px;transition:transform .12s,border-color .12s}
.card:hover{border-color:#58a6ff88;transform:translateY(-1px)}
.t{font-weight:650;font-size:13.5px}
.i{color:var(--muted);font-size:11.5px;display:-webkit-box;-webkit-line-clamp:3;
  -webkit-box-orient:vertical;overflow:hidden;flex:1}
.meta{display:flex;align-items:center;gap:8px;font-family:ui-monospace,Consolas,monospace;
  font-size:10.5px;color:#6b7280;margin-top:2px}
.acts{display:flex;gap:7px;margin-top:4px}
.acts a{font-size:11.5px;border:1px solid var(--chip);border-radius:6px;padding:3px 9px}
.acts a:hover{border-color:#58a6ff}
.cloud{color:var(--muted)}
input#q{background:var(--card);border:1px solid var(--chip);color:var(--fg);border-radius:8px;
  padding:5px 11px;font-size:12.5px;min-width:230px}
</style></head><body>
<header><h1>Artifact Library</h1>
  <span class="pill" id="count">…</span>
  <input id="q" placeholder="filter…" autocomplete="off">
  <span style="margin-left:auto"></span>
  <a class="btn" href="/timeline">Timeline</a>
  <a class="btn" href="/">Mission Control</a>
</header>
<div class="wrap">
  <p class="hint">Local backups of every Claude artifact built during this project — served from
  <code>docs/artifacts/</code>, so they open with no account and no network. <b>Open local</b> reads
  the saved copy; <b>original</b> goes to claude.ai.</p>
  <div id="grid"></div>
</div>
<script>
var ALL=[];
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');}
function render(){
  var q=(document.getElementById('q').value||'').toLowerCase();
  var rows=ALL.filter(function(a){
    return !q || (a.title+' '+a.info+' '+a.slug).toLowerCase().indexOf(q)>=0; });
  document.getElementById('count').textContent=rows.length+' / '+ALL.length+' saved';
  function card(a){
    return '<div class="card"><div class="t">'+esc(a.title)+'</div>'
      + (a.info?'<div class="i">'+esc(a.info)+'</div>':'<div class="i"></div>')
      + '<div class="meta">'+a.kb+' KB · saved '+esc(a.saved)+'</div>'
      + '<div class="acts"><a href="/artifact/'+encodeURIComponent(a.slug)+'" target="_blank">Open local</a>'
      + '<a href="/artifact/'+encodeURIComponent(a.slug)+'" download="'+esc(a.slug)+'.html" title="download the standalone .html to share">share .html ⬇</a>'
      + (a.url?'<a class="cloud" href="'+esc(a.url)+'" target="_blank" rel="noopener">original ↗</a>':'')
      + '</div></div>';
  }
  // rows arrive newest-first; group them under a date header per day.
  var MO=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  function fmt(d){var p=(d||'').slice(0,10).split('-');
    return p.length<3?'Undated':(MO[+p[1]-1]||p[1])+' '+(+p[2])+', '+p[0];}
  var html='',cur=null,n=0;
  rows.forEach(function(a){
    var d=(a.date||a.saved||'').slice(0,10);
    if(d!==cur){ if(cur!==null) html+='</div>';
      cur=d; n=rows.filter(function(r){return (r.date||r.saved||'').slice(0,10)===d;}).length;
      html+='<div class="daterow">'+esc(fmt(d))+' <span class="n">· '+n+'</span></div><div class="grid">'; }
    html+=card(a);
  });
  if(cur!==null) html+='</div>';
  document.getElementById('grid').innerHTML=html || '<p class="hint">no local backups yet — run the artifact backup</p>';
}
document.getElementById('q').addEventListener('input',render);
fetch('/artifacts_local.json').then(function(r){return r.json();})
  .then(function(j){ALL=j;render();});
</script></body></html>"""
