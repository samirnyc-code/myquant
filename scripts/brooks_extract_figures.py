"""Extract annotated chart figures from the Brooks book PDFs, caption-cropped,
tagged by concept. Output: scratchpad/figures/*.jpg  + figures_catalog.json
(each: id, book, fig_num, printed_page, pdf_page, caption, concept tags, discussion snippet).
Digital books (Trends/Ranges/RPCBB) have a text layer with 'FIGURE x.y Title' captions.
Reversals is scanned (no text) -> handled separately later.
"""
import fitz, re, json, io
from pathlib import Path
from PIL import Image

DESK = Path(r"C:\Users\Admin\Desktop")
OUT = Path(__file__).resolve().parent.parent / "scratchpad" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
BOOKS = {"Trends": "Al-Brooks-Trends.pdf",
         "Trading Ranges": "Al-Brooks-Trading-Price-Action-Ranges-(KohanFx.com).pdf",
         "Reading Price Charts": "Al Brooks Reading Price Charts Bar by Bar.pdf"}

# concept tags from caption keywords (order matters; first match wins for primary)
TAGS = [
    ("H2/L2 pullback", ["high 2", "low 2", "two-legged", "two legged", "moving average pullback", "m2b", "m2s", "second entry"]),
    ("H1/L1 pullback", ["high 1", "low 1", "first pullback"]),
    ("Wedge", ["wedge"]),
    ("Double top/bottom", ["double top", "double bottom", "double-top", "double-bottom"]),
    ("Final flag", ["final flag"]),
    ("Spike and channel", ["spike and channel", "spike-and-channel"]),
    ("Breakout pullback", ["breakout pullback", "breakout test"]),
    ("Trend from the open", ["trend from the open", "trend from the first", "small pullback"]),
    ("Opening reversal", ["opening reversal", "opening range"]),
    ("Trading range", ["trading range", "barbwire", "tight range", "trading-range"]),
    ("Reversal", ["reversal", "major trend reversal", "reverses"]),
    ("Trend line / channel", ["trend line", "trendline", "channel line", "trend channel"]),
    ("Climax", ["climax", "parabolic", "exhaustion"]),
    ("Gap", ["gap"]),
    ("Flag", ["flag"]),
    ("Trend bar / doji", ["doji", "trend bar", "bar", "tail"]),
    ("Always-in", ["always in", "always-in"]),
]

def concept_tags(caption, discussion):
    t = (caption + " " + discussion).lower()
    tags = [name for name, kws in TAGS if any(k in t for k in kws)]
    return tags[:4]

def printed_page(txt):
    # bold page number appears alone near top/bottom of running head
    nums = re.findall(r'(?<!\d)(\d{2,3})(?!\d)', txt[:120] + txt[-120:])
    return nums[0] if nums else ""

catalog = []
for book, fn in BOOKS.items():
    d = fitz.open(DESK / fn)
    slug = {"Trends": "TR", "Trading Ranges": "RG", "Reading Price Charts": "RP"}[book]
    n = 0
    for pno in range(d.page_count):
        pg = d[pno]
        txt = pg.get_text("text")
        if book == "Trading Ranges":   # title-case caption, line-anchored to avoid inline refs
            m = re.search(r'(?m)^Figure\s+(\d+\.\d+)\s+([A-Z][^\n]{2,55})\s*$', txt)
        else:                          # Trends / RPCBB: bold UPPERCASE caption
            m = re.search(r'FIGURE\s+(\d+\.\d+)\s+([A-Z][^\n]{0,60})', txt)
        if not m:
            continue
        fig_num = m.group(1); caption = m.group(2).strip()
        # locate caption on page to crop the chart ABOVE it
        rects = (pg.search_for("FIGURE " + fig_num) or pg.search_for("Figure " + fig_num)
                 or pg.search_for(fig_num))
        pr = pg.rect
        if rects:
            cap_y = max(r.y1 for r in rects)
            clip = fitz.Rect(pr.x0 + 6, pr.y0 + 40, pr.x1 - 6, min(cap_y + 8, pr.y1))
        else:
            clip = fitz.Rect(pr.x0 + 6, pr.y0 + 40, pr.x1 - 6, pr.y0 + pr.height * 0.55)
        if clip.height < 120:   # caption near top -> chart likely below; take upper half
            clip = fitz.Rect(pr.x0 + 6, pr.y0 + 40, pr.x1 - 6, pr.y0 + pr.height * 0.52)
        pix = pg.get_pixmap(clip=clip, dpi=150)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        im.thumbnail((760, 1100))
        # discussion = text after the caption line
        disc = txt[m.end():m.end() + 600].replace("\n", " ").strip()
        tags = concept_tags(caption, disc)
        fid = f"{slug}{fig_num.replace('.', '_')}"
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=74)
        (OUT / f"{fid}.jpg").write_bytes(buf.getvalue())
        catalog.append({"id": fid, "book": book, "fig_num": fig_num,
                        "printed_page": printed_page(txt), "pdf_page": pno + 1,
                        "caption": caption, "tags": tags, "discussion": disc[:280],
                        "bytes": len(buf.getvalue())})
        n += 1
    d.close()
    print(f"{book:22} {n} figures")

json.dump(catalog, open(OUT.parent / "figures_catalog.json", "w", encoding="utf-8"), ensure_ascii=False)
tot = sum(c["bytes"] for c in catalog)
print(f"TOTAL {len(catalog)} figures, {tot/1e6:.1f} MB raw jpeg")
from collections import Counter
print("by primary tag:", dict(Counter((c['tags'][0] if c['tags'] else '—') for c in catalog).most_common()))
