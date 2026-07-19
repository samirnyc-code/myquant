"""timeline_page.py — the HTML for Mission Control's /timeline.

Kept out of launcher.py so the page markup can be edited without touching the server.
"""

HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Day Timeline — Mission Control</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--chip:#30363d;--fg:#e6edf3;--muted:#8b949e}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:13.5px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}
header{display:flex;align-items:center;gap:10px;padding:11px 18px;border-bottom:1px solid var(--chip);
  position:sticky;top:0;background:var(--bg);z-index:20}
h1{font-size:15px;margin:0}
a{color:#58a6ff;text-decoration:none;margin-left:12px}
.pill{padding:2px 10px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid var(--chip)}
.ok{color:#22c55e;border-color:#22c55e}.warn{color:#f59e0b;border-color:#f59e0b}
.bad{color:#ef4444;border-color:#ef4444}.idle{color:#8b949e}
.wrap{padding:14px 18px 40px}
.cd{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;color:var(--muted);
  border:1px solid var(--chip);border-radius:7px;padding:2px 8px}
.cd b{color:#e6edf3;font-weight:600}
.sess-RTH{color:#22c55e;border-color:#22c55e}
.sess-ETH{color:#58a6ff;border-color:#58a6ff}
.sess-halt{color:#f59e0b;border-color:#f59e0b}
.sess-closed{color:#8b949e}
.tile.up{border-color:#58a6ff;box-shadow:0 0 0 1px #58a6ff55, 0 0 18px #58a6ff22}
.up-badge{position:absolute;top:-8px;right:9px;background:#58a6ff;color:#04121f;
  font-size:9.5px;font-weight:800;letter-spacing:.05em;padding:1px 6px;border-radius:6px}
.t-eta{margin-top:4px;font-size:11px;color:#58a6ff;font-family:ui-monospace,Consolas,monospace}
.phase{margin-bottom:20px}
.ph-h{display:flex;align-items:baseline;gap:9px;margin:0 0 9px}
.ph-t{font-size:12px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
.ph-s{font-size:11.5px;color:#6b7280}
.grid{display:grid;gap:9px;grid-template-columns:repeat(auto-fill,minmax(228px,1fr))}
.tile{background:var(--card);border:1px solid var(--chip);border-radius:10px;padding:10px 11px;
  cursor:grab;position:relative;transition:transform .12s,box-shadow .12s,opacity .12s}
.tile:hover{border-color:#58a6ff88;transform:translateY(-1px)}
.tile:active{cursor:grabbing}
.tile.bad{border-color:#ef4444}.tile.warn{border-color:#f59e0b66}
.tile.drag{opacity:.35}.tile.over{box-shadow:0 0 0 2px #58a6ff inset}
.t-top{display:flex;align-items:center;gap:7px;margin-bottom:3px}
.dot{width:9px;height:9px;border-radius:50%;flex:0 0 auto}
.ct{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:var(--muted);
  background:#0d1117;border:1px solid var(--chip);border-radius:5px;padding:0 5px}
.t-name{font-weight:600;font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.t-what{color:var(--muted);font-size:11.5px;display:-webkit-box;-webkit-line-clamp:2;
  -webkit-box-orient:vertical;overflow:hidden}
.t-foot{margin-top:5px;font-size:10.5px;color:#6b7280;font-family:ui-monospace,Consolas,monospace;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#ov{display:none;position:fixed;inset:0;background:#000a;z-index:50;align-items:center;
  justify-content:center;padding:24px}
#ov.on{display:flex}
#modal{background:var(--card);border:1px solid var(--chip);border-radius:14px;max-width:660px;
  width:100%;max-height:86vh;overflow:auto;padding:20px 22px;box-shadow:0 24px 70px #000c}
#modal h2{margin:0 0 3px;font-size:17px}
.m-sub{color:var(--muted);font-size:12px;margin-bottom:14px;font-family:ui-monospace,Consolas,monospace}
.m-sec{margin:13px 0 0}
.m-lbl{font-size:10.5px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:#6b7280;
  margin-bottom:3px}
.m-txt{font-size:13px}
.m-why{border-left:3px solid #58a6ff;padding-left:10px}
.m-mono{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:#8b949e}
#mclose{float:right;background:var(--chip);color:var(--fg);border:0;border-radius:7px;
  padding:3px 9px;cursor:pointer}
</style></head><body>
<header><h1>Day Timeline</h1>
  <span class="pill" id="overall">…</span>
  <span class="pill" id="sess">…</span>
  <span class="cd" id="cd-rth"></span>
  <span class="cd" id="cd-eth"></span>
  <span style="margin-left:auto"></span>
  <span class="pill idle" id="gen"></span>
  <a href="/health">Health</a><a href="/">← Mission Control</a>
</header>
<div class="wrap" id="wrap"></div>
<div id="ov"><div id="modal"></div></div>
<script>
var C={ok:"#22c55e",warn:"#f59e0b",bad:"#ef4444",idle:"#6b7280"};
var LS='timelineOrder';
var ORD=JSON.parse(localStorage.getItem(LS)||'{}');
var DATA=null, dragId=null;

function save(){
  var o={};
  document.querySelectorAll('.grid').forEach(function(g){
    o[g.dataset.phase]=Array.prototype.map.call(g.querySelectorAll('.tile'),function(t){return t.dataset.id;});
  });
  ORD=o; localStorage.setItem(LS,JSON.stringify(o));
}
function sortItems(ph,items){
  var ord=ORD[ph]; if(!ord) return items;
  function ix(i){var k=ord.indexOf(i); return k<0?999:k;}
  return items.slice().sort(function(a,b){return ix(a.id)-ix(b.id);});
}
function fmtEta(sec){
  if(sec===null||sec===undefined) return '';
  if(sec<=0) return 'now';
  var d=Math.floor(sec/86400), h=Math.floor(sec%86400/3600),
      m=Math.floor(sec%3600/60), s2=Math.floor(sec%60);
  if(d) return d+'d '+h+'h';
  if(h) return h+'h '+String(m).padStart(2,'0')+'m';
  if(m) return m+'m '+String(s2).padStart(2,'0')+'s';
  return s2+'s';
}
/* server sends exchange-anchored epochs; drift is corrected against the browser clock
   so the countdown stays honest between the 30s data polls */
var SKEW=0;
function nowEpoch(){return Math.floor(Date.now()/1000)+SKEW;}
function tickClocks(){
  if(!DATA) return;
  var n=nowEpoch();
  var r=document.getElementById('cd-rth'), e=document.getElementById('cd-eth');
  if(DATA.session==='RTH'){
    r.innerHTML='RTH closes in <b>'+fmtEta(DATA.rth_close_epoch-n)+'</b>';
  }else{
    r.innerHTML='RTH in <b>'+fmtEta(DATA.next_rth_epoch-n)+'</b>';
  }
  if(DATA.session==='closed'||DATA.session==='halt'){
    e.innerHTML='market opens in <b>'+fmtEta(DATA.next_eth_epoch-n)+'</b>';
  }else{
    e.innerHTML='ETH · next RTH <b>'+fmtEta(DATA.next_rth_epoch-n)+'</b>';
  }
  document.querySelectorAll('.t-eta[data-ep]').forEach(function(el){
    el.textContent='starts in '+fmtEta(parseInt(el.dataset.ep,10)-n);
  });
}
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');}

function openModal(p){
  var taskBlock = p.task
    ? '<div class="m-sec"><div class="m-lbl">Scheduled task</div><div class="m-txt m-mono">'
      + esc(p.task) + '<br>last ' + (esc(p.last)||'never') + ' \\u00b7 next ' + (esc(p.next)||'-')
      + '</div></div>'
    : '';
  document.getElementById('modal').innerHTML =
    '<button id="mclose">close</button>'
    + '<h2>' + esc(p.title) + '</h2>'
    + '<div class="m-sub">' + (p.ct==='cont'?'continuous':esc(p.ct)+' CT') + ' \\u00b7 ' + esc(p.script) + '</div>'
    + '<div class="m-sec"><div class="m-lbl">Status</div><div class="m-txt" style="color:'
      + C[p.state] + '">' + p.state.toUpperCase() + ' \\u2014 ' + (esc(p.detail)||'no detail') + '</div></div>'
    + '<div class="m-sec"><div class="m-lbl">What it does</div><div class="m-txt">' + esc(p.what) + '</div></div>'
    + '<div class="m-sec"><div class="m-lbl">Why we do it</div><div class="m-txt m-why">' + esc(p.why) + '</div></div>'
    + '<div class="m-sec"><div class="m-lbl">Writes</div><div class="m-txt m-mono">' + esc(p.writes) + '</div></div>'
    + '<div class="m-sec"><div class="m-lbl">What we do with that data</div><div class="m-txt">'
      + esc(p.downstream) + '</div></div>'
    + taskBlock;
  document.getElementById('ov').classList.add('on');
  document.getElementById('mclose').onclick=closeModal;
}
function closeModal(){document.getElementById('ov').classList.remove('on');}
document.getElementById('ov').onclick=function(e){if(e.target.id==='ov')closeModal();};
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeModal();});

function wire(el,p){
  el.onclick=function(){openModal(p);};
  el.draggable=true;
  el.addEventListener('dragstart',function(e){dragId=p.id;el.classList.add('drag');});
  el.addEventListener('dragend',function(){el.classList.remove('drag');
    document.querySelectorAll('.tile').forEach(function(t){t.classList.remove('over');}); save();});
  el.addEventListener('dragover',function(e){e.preventDefault();el.classList.add('over');});
  el.addEventListener('dragleave',function(){el.classList.remove('over');});
  el.addEventListener('drop',function(e){
    e.preventDefault(); el.classList.remove('over');
    var g=el.parentElement, src=g.querySelector('[data-id="'+dragId+'"]');
    if(!src||src===el) return;
    var rows=Array.prototype.slice.call(g.querySelectorAll('.tile'));
    if(rows.indexOf(src)<rows.indexOf(el)){el.after(src);}else{el.before(src);}
    save();});
}
function render(){
  var d=DATA; if(!d) return;
  var o=document.getElementById('overall');
  o.textContent=(d.overall||'').toUpperCase(); o.className='pill '+(d.overall||'idle');
  var sp=document.getElementById('sess');
  sp.textContent = d.session==='RTH' ? 'RTH · regular hours'
                 : d.session==='ETH' ? 'ETH · overnight session'
                 : d.session==='halt' ? 'daily halt 16:00-17:00 CT' : 'market closed';
  sp.className='pill sess-'+d.session;
  SKEW = d.chicago_epoch ? (d.chicago_epoch - Math.floor(Date.now()/1000)) : 0;
  document.getElementById('gen').textContent=d.chicago+' CT';
  document.getElementById('wrap').innerHTML = d.phases.map(function(ph){
    var n=ph.items.filter(function(i){return i.state==='bad'||i.state==='warn';}).length;
    return '<div class="phase"><div class="ph-h"><span class="ph-t">' + esc(ph.label) + '</span>'
      + '<span class="ph-s">' + ph.items.length + ' steps' + (n?' \\u00b7 '+n+' need attention':'') + '</span></div>'
      + '<div class="grid" data-phase="' + ph.key + '">'
      + sortItems(ph.key,ph.items).map(function(p){
          var isUp = (p.id===d.upcoming);
          return '<div class="tile ' + p.state + (isUp?' up':'') + '" data-id="' + p.id
            + '" title="' + esc(p.what) + '">'
            + (isUp?'<span class="up-badge">NEXT UP</span>':'')
            + '<div class="t-top"><span class="dot" style="background:' + C[p.state] + '"></span>'
            + '<span class="ct">' + (p.ct==='cont'?'live':esc(p.ct)) + '</span>'
            + '<span class="t-name">' + esc(p.title) + '</span></div>'
            + '<div class="t-what">' + esc(p.what) + '</div>'
            + '<div class="t-foot">' + (esc(p.detail)||esc(p.writes)) + '</div>'
            + (isUp&&p.next_epoch?'<div class="t-eta" data-ep="'+p.next_epoch+'"></div>':'')
            + '</div>';
        }).join('')
      + '</div></div>';
  }).join('');
  d.phases.forEach(function(ph){ph.items.forEach(function(p){
    var el=document.querySelector('.tile[data-id="'+p.id+'"]'); if(el) wire(el,p);});});
  tickClocks();
}
function load(){fetch('/timeline.json').then(function(r){return r.json();})
  .then(function(j){DATA=j;render();});}
load(); setInterval(load,30000); setInterval(tickClocks,1000);
</script></body></html>"""
