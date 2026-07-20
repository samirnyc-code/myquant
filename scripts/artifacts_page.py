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
.grid{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(275px,1fr))}
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
  <div class="grid" id="grid"></div>
</div>
<script>
var ALL=[];
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');}
function render(){
  var q=(document.getElementById('q').value||'').toLowerCase();
  var rows=ALL.filter(function(a){
    return !q || (a.title+' '+a.info+' '+a.slug).toLowerCase().indexOf(q)>=0; });
  document.getElementById('count').textContent=rows.length+' / '+ALL.length+' saved';
  document.getElementById('grid').innerHTML=rows.map(function(a){
    return '<div class="card"><div class="t">'+esc(a.title)+'</div>'
      + (a.info?'<div class="i">'+esc(a.info)+'</div>':'<div class="i"></div>')
      + '<div class="meta">'+a.kb+' KB · saved '+esc(a.saved)+'</div>'
      + '<div class="acts"><a href="/artifact/'+encodeURIComponent(a.slug)+'" target="_blank">Open local</a>'
      + (a.url?'<a class="cloud" href="'+esc(a.url)+'" target="_blank" rel="noopener">original ↗</a>':'')
      + '</div></div>';
  }).join('') || '<p class="hint">no local backups yet — run the artifact backup</p>';
}
document.getElementById('q').addEventListener('input',render);
fetch('/artifacts_local.json').then(function(r){return r.json();})
  .then(function(j){ALL=j;render();});
</script>
<style>
#mcThemeBtn{position:fixed;right:14px;bottom:14px;z-index:9999;display:flex;align-items:center;
  gap:7px;background:var(--card,#161b22);color:var(--fg,#e6edf3);border:1px solid var(--chip,#30363d);
  border-radius:999px;padding:6px 13px 6px 10px;font:600 12px/1 -apple-system,Segoe UI,Roboto,sans-serif;
  cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.35);opacity:.85;transition:opacity .15s,transform .1s}
#mcThemeBtn:hover{opacity:1;transform:translateY(-1px)}
#mcThemeBtn .sw{width:13px;height:13px;border-radius:50%;border:1px solid rgba(128,128,128,.5)}
</style>
<button id="mcThemeBtn" title="cycle theme (dark/light/blue/green/red/yellow/grey)">
  <span class="sw" id="mcThemeSw"></span><span id="mcThemeLbl">dark</span>
</button>
<script>
(function(){
  var THEMES = {
    dark:  {bg:'#0d1117',card:'#161b22',surface:'#161b22',chip:'#30363d',border:'#30363d',
            line:'#30363d',fg:'#e6edf3',ink:'#e6edf3',muted:'#8b949e',ink2:'#8b949e',sw:'#0d1117'},
    light: {bg:'#f6f7f9',card:'#ffffff',surface:'#ffffff',chip:'#e2e6ee',border:'#e2e6ee',
            line:'#e2e6ee',fg:'#161b24',ink:'#161b24',muted:'#5b6472',ink2:'#5b6472',sw:'#ffffff'},
    blue:  {bg:'#0a1628',card:'#10233d',surface:'#10233d',chip:'#1e3f66',border:'#1e3f66',
            line:'#1e3f66',fg:'#dbe9fb',ink:'#dbe9fb',muted:'#7fa2ca',ink2:'#7fa2ca',sw:'#1e6fe0'},
    green: {bg:'#08150e',card:'#0e2418',surface:'#0e2418',chip:'#1c4630',border:'#1c4630',
            line:'#1c4630',fg:'#d6f5e4',ink:'#d6f5e4',muted:'#6fb089',ink2:'#6fb089',sw:'#1f9d57'},
    red:   {bg:'#180b0b',card:'#2a1414',surface:'#2a1414',chip:'#4a2020',border:'#4a2020',
            line:'#4a2020',fg:'#f6dede',ink:'#f6dede',muted:'#c78a8a',ink2:'#c78a8a',sw:'#d24a3f'},
    yellow:{bg:'#171307',card:'#28220f',surface:'#28220f',chip:'#49401c',border:'#49401c',
            line:'#49401c',fg:'#f5ecd0',ink:'#f5ecd0',muted:'#b8a566',ink2:'#b8a566',sw:'#e6a94a'},
    grey:  {bg:'#181818',card:'#232323',surface:'#232323',chip:'#393939',border:'#393939',
            line:'#393939',fg:'#e9e9e9',ink:'#e9e9e9',muted:'#8f8f8f',ink2:'#8f8f8f',sw:'#7a7a7a'}
  };
  var ORDER = ['dark','light','blue','green','red','yellow','grey'];
  function apply(name){
    var t = THEMES[name] || THEMES.dark, r = document.documentElement.style;
    for (var k in t){ if(k!=='sw') r.setProperty('--'+k, t[k]); }
    document.documentElement.setAttribute('data-theme', (name==='light')?'light':'dark');
    var sw=document.getElementById('mcThemeSw'), lbl=document.getElementById('mcThemeLbl');
    if(sw) sw.style.background=t.sw;
    if(lbl) lbl.textContent=name;
  }
  window.__mcTheme = localStorage.getItem('mcTheme') || 'dark';
  // apply immediately (button labels get set once DOM is ready)
  apply(window.__mcTheme);
  document.addEventListener('DOMContentLoaded', function(){
    apply(window.__mcTheme);
    var b=document.getElementById('mcThemeBtn');
    if(b) b.onclick=function(){
      var i=(ORDER.indexOf(window.__mcTheme)+1)%ORDER.length;
      window.__mcTheme=ORDER[i]; localStorage.setItem('mcTheme',window.__mcTheme); apply(window.__mcTheme);
    };
  });
})();
</script>
</body></html>"""
