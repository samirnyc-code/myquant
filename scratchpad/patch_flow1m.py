"""Make docs/gexlab/flow1m.html readable without browser zoom:
  1. stop pinning the card to 1040px on wide monitors
  2. add a persistent zoom control (CSS zoom -> reflows, unlike transform:scale)
"""
import pathlib, re

P = pathlib.Path("docs/gexlab/flow1m.html")
s = P.read_text(encoding="utf-8")
orig = len(s)

# ---- 1. responsive width + zoom hook ----
old = ".wrap{max-width:1040px;margin:0 auto;padding:34px 20px 100px}"
new = (".wrap{max-width:min(1760px,97vw);margin:0 auto;padding:34px 20px 100px;"
       "zoom:var(--z,1)}")
assert s.count(old) == 1, f"anchor count {s.count(old)}"
s = s.replace(old, new)

# ---- 2. zoom toolbar ----
css = """
.zoombar{position:fixed;right:14px;bottom:14px;z-index:9999;display:flex;gap:5px;
 align-items:center;background:var(--card,#fff);border:1px solid var(--line,#0002);
 border-radius:9px;padding:5px 7px;box-shadow:0 2px 12px #0002}
.zoombar button{font:inherit;font-size:13px;line-height:1;color:inherit;background:transparent;
 border:1px solid var(--line,#0002);border-radius:6px;padding:5px 9px;cursor:pointer}
.zoombar button:hover{border-color:currentColor}
.zoombar .pct{font-variant-numeric:tabular-nums;font-size:12px;opacity:.7;min-width:42px;
 text-align:center}
@media print{.zoombar{display:none}}
"""
s = s.replace("</style>", css + "</style>", 1)

html = """
<div class="zoombar" role="group" aria-label="Zoom">
  <button id="zOut" title="Smaller (-)">A&minus;</button>
  <span class="pct" id="zPct">100%</span>
  <button id="zIn" title="Bigger (+)">A+</button>
  <button id="zFit" title="Fit width">fit</button>
  <button id="zRst" title="Reset">100%</button>
</div>
<script>
(function(){
  var KEY='flow1m_zoom', r=document.documentElement;
  function apply(z){z=Math.max(0.6,Math.min(z,2.6));
    r.style.setProperty('--z',z);
    document.getElementById('zPct').textContent=Math.round(z*100)+'%';
    try{localStorage.setItem(KEY,z)}catch(e){}}
  function cur(){return parseFloat(getComputedStyle(r).getPropertyValue('--z'))||1}
  document.getElementById('zIn').onclick=function(){apply(cur()*1.12)};
  document.getElementById('zOut').onclick=function(){apply(cur()/1.12)};
  document.getElementById('zRst').onclick=function(){apply(1)};
  document.getElementById('zFit').onclick=function(){
    // scale so the widest card fills the viewport
    var w=document.querySelector('.bar,.card,.wrap');
    if(!w)return; var natural=w.scrollWidth/cur();
    apply((window.innerWidth-46)/natural);};
  addEventListener('keydown',function(e){
    if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA')return;
    if(e.ctrlKey||e.metaKey)return;           // leave browser zoom alone
    if(e.key==='+'||e.key==='=')apply(cur()*1.12);
    if(e.key==='-'||e.key==='_')apply(cur()/1.12);
    if(e.key==='0')apply(1);});
  var saved=1; try{saved=parseFloat(localStorage.getItem(KEY))||1}catch(e){}
  apply(saved);
})();
</script>
"""
# artifact-style fragment: no </body>, so append at the end
s = s.rstrip() + "\n" + html

P.write_text(s, encoding="utf-8")
print(f"patched {P}  ({orig/1e6:.2f} MB -> {len(s)/1e6:.2f} MB)")
print("  .wrap max-width 1040px -> min(1760px, 97vw)")
print("  zoom control added (A- / A+ / fit / reset, +/-/0 keys, persisted)")
