"""Build a self-contained HTML study card: full-screen chart + toggle-able
explanation overlay (button or keyboard E / Space). Reusable for any post_id.

Usage: python scripts/brooks_make_card.py <post_id> [out.html]
"""
import sys, re, csv, html, base64
from pathlib import Path
OUT = Path(__file__).resolve().parent.parent / "data" / "brooks_charts"

def md2html(md):
    out=[]
    for ln in md.strip().split("\n"):
        ln=ln.rstrip()
        if not ln: continue
        if ln.startswith("## "):
            out.append(f"<h2>{esc(ln[3:])}</h2>"); continue
        t=esc(ln)
        t=re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t=re.sub(r"\*(.+?)\*", r"<em>\1</em>", t)
        out.append(f"<p>{t}</p>")
    return "\n".join(out)

def esc(s): return html.escape(s, quote=False)

def meta_for(pid):
    with (OUT/"metadata.csv").open() as f:
        for r in csv.DictReader(f):
            if r["post_id"]==str(pid): return r
    return {}

def build(pid, outpath=None):
    m=meta_for(pid)
    img=OUT/m["filename"]
    wk=(OUT/"walkthroughs"/f"{pid}.md")
    walk = wk.read_text() if wk.exists() else "## (no walkthrough yet)"
    title=html.unescape(m.get("title","")); date=m.get("date","")[:10]
    tags=" · ".join(x for x in html.unescape(m.get("tags","")).split("|")
                    if x and "Forex" not in x and x!="S&P Emini")
    b64=base64.b64encode(img.read_bytes()).decode()
    body=md2html(walk)
    doc=f"""<!doctype html><meta charset=utf-8><title>{esc(title)}</title>
<style>
*{{box-sizing:border-box}}html,body{{margin:0;height:100%;background:#111;font:16px/1.65 -apple-system,Helvetica,sans-serif;color:#eee}}
#chart{{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;background:#fff}}
#chart img{{max-width:100%;max-height:100%;object-fit:contain}}
#meta{{position:fixed;top:0;left:0;padding:8px 14px;background:rgba(68,114,196,.92);color:#fff;font-size:14px;border-bottom-right-radius:10px;z-index:5}}
#meta b{{font-size:16px}}#meta .t{{opacity:.85;font-size:12px}}
#btn{{position:fixed;top:12px;right:14px;z-index:6;background:#4472c4;color:#fff;border:0;border-radius:8px;padding:10px 16px;font-size:15px;font-weight:600;cursor:pointer;box-shadow:0 2px 10px rgba(0,0,0,.4)}}
#panel{{position:fixed;top:0;right:0;height:100%;width:min(560px,44vw);background:rgba(17,18,22,.94);backdrop-filter:blur(6px);
  overflow:auto;padding:64px 30px 40px;transform:translateX(102%);transition:transform .28s ease;z-index:5;border-left:1px solid #333}}
#panel.show{{transform:translateX(0)}}
#panel h2{{color:#7aa7ff;font-size:19px;margin:0 0 14px}}#panel p{{margin:0 0 13px}}#panel strong{{color:#fff}}
.hint{{position:fixed;bottom:10px;right:16px;font-size:12px;color:#999;z-index:6}}
</style>
<div id=chart><img src="data:image/jpeg;base64,{b64}"></div>
<div id=meta><b>{esc(title)}</b><div class=t>{date} &nbsp;·&nbsp; {esc(tags)}</div></div>
<button id=btn onclick="tog()">📖 Explanation</button>
<div id=panel>{body}</div>
<div class=hint>press <b>E</b> or <b>Space</b> to toggle</div>
<script>
function tog(){{document.getElementById('panel').classList.toggle('show')}}
addEventListener('keydown',e=>{{if(e.key==='e'||e.key==='E'||e.code==='Space'){{e.preventDefault();tog()}}if(e.key==='Escape')document.getElementById('panel').classList.remove('show')}});
</script>"""
    op=Path(outpath) if outpath else (OUT/"walkthroughs"/f"card_{pid}.html")
    op.write_text(doc); return op

if __name__=="__main__":
    pid=sys.argv[1]; out=sys.argv[2] if len(sys.argv)>2 else None
    print(build(pid,out))
