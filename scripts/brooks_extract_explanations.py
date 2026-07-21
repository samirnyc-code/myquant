"""Extract the FULL per-figure explanation text (the bar-by-bar walkthrough) from
the 3 digital Brooks books, for the sequential 'Figure Explorer' section.
For each figure: text from its caption to the NEXT figure's caption (spans pages).
Output: scratchpad/figures_explanations.json  {fig_id: {book, fig_num, caption, printed_page, explanation}}
Does NOT touch figures_catalog.json (leaves the running classification untouched).
"""
import fitz, re, json
from pathlib import Path

DESK = Path(r"C:\Users\Admin\Desktop")
SCR = Path(__file__).resolve().parent.parent / "scratchpad"
BOOKS = {"Trends": ("Al-Brooks-Trends.pdf", "TR"),
         "Trading Ranges": ("Al-Brooks-Trading-Price-Action-Ranges-(KohanFx.com).pdf", "RG"),
         "Reading Price Charts": ("Al Brooks Reading Price Charts Bar by Bar.pdf", "RP")}

out = {}
for book, (fn, slug) in BOOKS.items():
    d = fitz.open(DESK / fn)
    # build a global text with page-start offsets
    parts = []; page_of = []; g = ""
    for pno in range(d.page_count):
        t = d[pno].get_text("text")
        page_of.append((len(g), pno + 1))
        g += "\n" + t
    pat = (re.compile(r'(?m)^Figure\s+(\d+\.\d+)\s+([A-Z][^\n]{2,55})\s*$')
           if book == "Trading Ranges" else
           re.compile(r'FIGURE\s+(\d+\.\d+)\s+([A-Z][^\n]{0,60})'))
    caps = [(m.start(), m.end(), m.group(1), m.group(2).strip()) for m in pat.finditer(g)]
    def pdfpage(pos):
        pg = 1
        for off, p in page_of:
            if off <= pos: pg = p
            else: break
        return pg
    for i, (cs, ce, num, cap) in enumerate(caps):
        nxt = caps[i + 1][0] if i + 1 < len(caps) else len(g)
        expl = re.sub(r'\s+', ' ', g[ce:nxt]).strip()[:20000]  # effectively full (caption -> next figure)
        fid = f"{slug}{num.replace('.', '_')}"
        out[fid] = {"book": book, "fig_num": num, "caption": cap,
                    "pdf_page": pdfpage(cs), "explanation": expl}
    d.close()
    print(f"{book:22} {sum(1 for k in out if out[k]['book']==book)} explanations")

json.dump(out, open(SCR / "figures_explanations.json", "w", encoding="utf-8"), ensure_ascii=False)
lens = [len(v["explanation"]) for v in out.values()]
print(f"total {len(out)} figure explanations; median len {sorted(lens)[len(lens)//2]} chars")
