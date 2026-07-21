"""One-card demo: an H2 setup card in the app style with a real Brooks book figure
embedded + click-to-enlarge (fly-to-center). For the user to approve the look."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
SCR = ROOT / "scratchpad"
d = json.load(open(SCR / "demo_data.json", encoding="utf-8"))
b64 = d["b64"]; c = d["card"]

def esc(s): return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def rules_html(items, cls):
    out = []
    for it in items:
        rule = esc(it.get("rule") or it.get("tell") or "")
        q = esc(it.get("quote") or "")
        cite = " · ".join(x for x in [it.get("book"), ("p." + str(it.get("pages"))) if it.get("pages") else ""] if x)
        out.append(f'<li class="{cls}"><div class="rl">{rule}</div>'
                   f'<div class="ql">&ldquo;{q}&rdquo; <span class="pg">{esc(cite)}</span></div></li>')
    return "".join(out)

FRAG = f"""<style>
:root{{--bg:#0c1016;--panel:#141b24;--panel2:#1b2430;--ink:#e8eef6;--dim:#93a2b4;--faint:#6b7a8c;--line:#25303d;
 --gold:#e6b23a;--red:#ec5b5b;--green:#45c26a;--blue:#5aa0ff;--mono:ui-monospace,Menlo,Consolas,monospace;
 --sans:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;}}
@media(prefers-color-scheme:light){{:root{{--bg:#eef1f5;--panel:#fff;--panel2:#f4f6f9;--ink:#141b24;--dim:#54636f;--faint:#8593a1;--line:#dbe2ea;--gold:#b1810c;--red:#c8352f;--green:#1f9a4d;--blue:#2f6fd6;}}}}
:root[data-theme="light"]{{--bg:#eef1f5;--panel:#fff;--panel2:#f4f6f9;--ink:#141b24;--dim:#54636f;--faint:#8593a1;--line:#dbe2ea;--gold:#b1810c;--red:#c8352f;--green:#1f9a4d;--blue:#2f6fd6;}}
:root[data-theme="dark"]{{--bg:#0c1016;--panel:#141b24;--panel2:#1b2430;--ink:#e8eef6;--dim:#93a2b4;--faint:#6b7a8c;--line:#25303d;--gold:#e6b23a;--red:#ec5b5b;--green:#45c26a;--blue:#5aa0ff;}}
*{{box-sizing:border-box}}
#dx{{font-family:var(--sans);background:var(--bg);color:var(--ink);min-height:100vh;padding:30px 18px 80px;line-height:1.5}}
#dx .wrap{{max-width:820px;margin:0 auto}}
#dx .eyebrow{{font-family:var(--mono);font-size:11.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint);margin-bottom:10px}}
#dx .card{{border:1px solid var(--line);border-radius:16px;background:var(--panel);overflow:hidden}}
#dx .head{{padding:20px 24px;border-bottom:1px solid var(--line);background:linear-gradient(180deg,var(--panel2),var(--panel))}}
#dx .grade{{font-family:var(--mono);font-weight:800;font-size:12px;letter-spacing:.05em;color:var(--bg);background:var(--gold);
 padding:3px 9px;border-radius:6px;vertical-align:middle}}
#dx h1{{font-size:24px;margin:8px 0 6px;letter-spacing:-.01em}}
#dx .one{{color:var(--dim);font-size:15px;max-width:62ch}}
#dx .body{{padding:22px 24px;display:flex;flex-direction:column;gap:22px}}
#dx .cxt{{display:grid;grid-template-columns:88px 1fr;gap:6px 14px;font-size:14px}}
#dx .cxt .k{{font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--faint);padding-top:2px}}
#dx .cxt .v b{{color:var(--green)}}
#dx h2{{font-size:12.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--gold);margin:0 0 10px;font-weight:800}}
#dx h2.red{{color:var(--red)}}
#dx ul{{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:12px}}
#dx li{{border-left:3px solid var(--gold);padding-left:13px}}
#dx li.tell{{border-color:var(--red)}}
#dx .rl{{font-size:14.5px;font-weight:600}}
#dx .ql{{font-size:12.5px;color:var(--dim);font-style:italic;margin-top:3px}}
#dx .pg{{font-family:var(--mono);font-style:normal;color:var(--faint);font-size:11px}}
#dx .figwrap{{border-top:1px solid var(--line);padding-top:18px}}
#dx figure{{margin:0;cursor:zoom-in}}
#dx figure img{{width:100%;border-radius:10px;border:1px solid var(--line);display:block;box-shadow:0 10px 30px rgba(0,0,0,.25)}}
#dx figcaption{{font-family:var(--mono);font-size:11.5px;color:var(--faint);margin-top:9px;letter-spacing:.02em}}
#dx figcaption b{{color:var(--blue)}}
#dx .hint{{font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:14px;text-align:center}}
/* zoom */
#dx .zov{{position:fixed;inset:0;z-index:50;display:flex;align-items:center;justify-content:center;padding:24px;
 background:rgba(4,7,11,.8);backdrop-filter:blur(3px);opacity:0;transition:opacity .3s;cursor:zoom-out}}
#dx .zov.show{{opacity:1}}
#dx .zov img{{max-width:96vw;max-height:88vh;border-radius:12px;border:1px solid var(--line);
 box-shadow:0 30px 80px rgba(0,0,0,.6);transition:transform .42s cubic-bezier(.22,1,.36,1);will-change:transform}}
</style>
<div id="dx"><div class="wrap">
 <div class="eyebrow">The Brooks Codex · demo — one setup card with a book figure</div>
 <div class="card">
  <div class="head">
   <div><span class="grade">{esc(c.get('grade','A+'))}</span></div>
   <h1>{esc(c['setup_name'])}</h1>
   <div class="one">{esc(c.get('one_liner',''))}</div>
  </div>
  <div class="body">
   <div class="cxt">
    <div class="k">Context</div><div class="v">{esc(c.get('context',''))}</div>
    <div class="k">Entry</div><div class="v">{esc(c.get('entry',''))}</div>
    <div class="k">Stop</div><div class="v">{esc(c.get('stop',''))}</div>
    <div class="k">Manage</div><div class="v">{esc(c.get('management',''))}</div>
   </div>
   <div><h2>Must-know rules</h2><ul>{rules_html(c.get('must_know_rules',[]),'rule')}</ul></div>
   <div><h2 class="red">Don't trade it when…</h2><ul>{rules_html(c.get('dont_trade_tells',[]),'tell')}</ul></div>
   <div class="figwrap">
    <h2>Brooks' own chart</h2>
    <figure id="fig"><img id="figimg" src="data:image/jpeg;base64,{b64}" alt="Brooks figure">
     <figcaption><b>Figure 23.2 — Small Pullback Bull Trend Day</b> · Trading Price Action: Trends, p392 — the two-legged pullback tests the 20-EMA (bars 9 &amp; 11), then resumes. Click to enlarge.</figcaption>
    </figure>
   </div>
  </div>
 </div>
 <div class="hint">This is a mock of ONE card. If you like it, I'll wire figures into all setup + rule cards in the main app.</div>
</div></div>
<script>
const fig=document.getElementById("fig"),img=document.getElementById("figimg");
fig.onclick=()=>{{const r=img.getBoundingClientRect();const ov=document.createElement("div");ov.className="zov";
 const big=new Image();big.src=img.src;ov.appendChild(big);document.getElementById("dx").appendChild(ov);
 const br=big.getBoundingClientRect();
 const dx=r.left+r.width/2-(br.left+br.width/2),dy=r.top+r.height/2-(br.top+br.height/2);
 big.style.transform=`translate(${{dx}}px,${{dy}}px) scale(${{r.width/br.width}})`;
 requestAnimationFrame(()=>{{ov.classList.add("show");big.style.transform="none";}});
 const close=()=>{{const r2=img.getBoundingClientRect(),b2=big.getBoundingClientRect();
  big.style.transform=`translate(${{r2.left+r2.width/2-(b2.left+b2.width/2)}}px,${{r2.top+r2.height/2-(b2.top+b2.height/2)}}px) scale(${{r2.width/b2.width}})`;
  ov.classList.remove("show");setTimeout(()=>ov.remove(),440);document.removeEventListener("keydown",k);}};
 ov.onclick=close;function k(e){{if(e.key==="Escape"||e.key===" ")close();}}document.addEventListener("keydown",k);}};
</script>"""
(ROOT / "docs" / "living" / "brooks_figure_demo.html").write_text(FRAG, encoding="utf-8")
print("wrote brooks_figure_demo.html", len(FRAG), "bytes")
