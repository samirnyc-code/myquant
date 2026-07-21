"""Inject the Codex control bar (gold ⌂ Home + A-/A+ font size) into the built
pages, placed in each page's top header (fixed top-right if no header).
Idempotent — replaces any older injected version. Run after any rebuild
(brooks_sync_drive.ps1 calls it automatically before syncing).

Per-page rules:
  - index.html gets font buttons only (it IS home)
  - daily.html gets Home only (its own S/M/L selector; page zoom would break
    its vh-locked snap layout)
  - Home hides itself inside iframes (the portable file's embedded tabs)
  - existing "<- Codex hub" links are hidden where Home is added

  python scripts/brooks_font_ctl.py
"""
from pathlib import Path

HUB = Path(__file__).resolve().parent.parent / "docs" / "living" / "brooks_codex"
# name -> (home button, zoom buttons)
FILES = {
    'app.html': (True, True),
    'explorer.html': (True, True),
    'forum.html': (True, True),
    'slides.html': (True, True),
    'cheatsheet.html': (True, True),
    'index.html': (False, True),
    'daily.html': (True, False),
}
OPEN = '<script id=cxfont>'
CLOSE = '</script>'

BASE = """(function(){
var w=document.createElement("div");
var host=document.querySelector("header .top")||document.querySelector("#cs .hd")||document.querySelector("header");
if(host){w.style.cssText="display:flex;gap:6px;align-items:center;margin-left:auto;padding-left:10px";host.appendChild(w);}
else{w.style.cssText="position:fixed;top:14px;right:70px;z-index:9999;display:flex;gap:6px;opacity:.95";document.body.appendChild(w);}
function mk(t,tip,fn,gold){var x=document.createElement("button");x.textContent=t;x.title=tip;
x.style.cssText="font:700 13px/1 ui-monospace,Consolas,monospace;border-radius:8px;padding:9px 11px;cursor:pointer;"+
(gold?"background:#e6b23a;color:#0c1016;border:1px solid #e6b23a":"background:#141b24;color:#e8eef6;border:1px solid #3a4757");
x.onclick=fn;w.appendChild(x);}
__HOME__
__ZOOM__
})();"""

HOME_JS = """if(window.self===window.top){
document.querySelectorAll("a").forEach(function(a){if(/Codex hub/.test(a.textContent))a.style.display="none";});
mk("\\u2302 Home","Back to the Codex home",function(){location.href="index.html";},true);}"""

ZOOM_JS = """var z=parseFloat(localStorage.cxZoom||"1.2");function ap(){document.body.style.zoom=z;}ap();
mk("A\\u2212","Smaller (all Codex pages)",function(){z=Math.round(Math.max(.8,z-.1)*100)/100;localStorage.cxZoom=z;ap();});
mk("A+","Larger (all Codex pages)",function(){z=Math.round(Math.min(1.6,z+.1)*100)/100;localStorage.cxZoom=z;ap();});"""

for name, (home, zoom) in FILES.items():
    p = HUB / name
    if not p.exists():
        print(f'{name}: MISSING, skipped')
        continue
    snippet = (OPEN + BASE.replace('__HOME__', HOME_JS if home else '')
                          .replace('__ZOOM__', ZOOM_JS if zoom else '') + CLOSE)
    t = p.read_text(encoding='utf-8')
    action = 'injected'
    i = t.find(OPEN)
    if i >= 0:
        j = t.find(CLOSE, i)
        old = t[i:j + len(CLOSE)]
        if old == snippet:
            print(f'{name}: up to date')
            continue
        t = t.replace(old, snippet, 1)
        action = 'updated'
    elif '</body>' in t:
        t = t.replace('</body>', snippet + '</body>', 1)
    else:
        t += snippet
    p.write_text(t, encoding='utf-8')
    print(f'{name}: {action}')
