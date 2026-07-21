"""Render ALL Brooks figures at high resolution for the Figure Explorer, build the
figure index (with full explanations + PDF page for page-jump links), and copy the
4 book PDFs into the explorer folder so each figure can deep-link to its page.
Output: docs/living/brooks_explorer/figures/*.jpg, /books/*.pdf, figure_index.json
"""
import fitz, re, json, shutil, io
from pathlib import Path
from PIL import Image

DESK = Path(r"C:\Users\Admin\Desktop")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "living" / "brooks_codex"
FIGDIR = OUT / "figures"; BOOKDIR = OUT / "books"
FIGDIR.mkdir(parents=True, exist_ok=True); BOOKDIR.mkdir(parents=True, exist_ok=True)
SCR = ROOT / "scratchpad"

DIGITAL = {"Trends": ("Al-Brooks-Trends.pdf", "TR", "trends.pdf"),
           "Trading Ranges": ("Al-Brooks-Trading-Price-Action-Ranges-(KohanFx.com).pdf", "RG", "ranges.pdf"),
           "Reading Price Charts": ("Al Brooks Reading Price Charts Bar by Bar.pdf", "RP", "rpcbb.pdf")}
REVERSALS = ("Al Brooks Trading Price Action - Reversals.pdf", "reversals.pdf")
expl = json.load(open(SCR / "figures_explanations.json", encoding="utf-8"))
rev_figs = json.load(open(SCR / "reversals_figs.json", encoding="utf-8"))

def save_jpg(im, path, maxw=1200, q=82):
    if im.width > maxw:
        im.thumbnail((maxw, maxw * 3))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=q); path.write_bytes(buf.getvalue())
    return len(buf.getvalue())

index = []
# ---- digital books: caption-cropped hi-res ----
for book, (fn, slug, pdfname) in DIGITAL.items():
    shutil.copy(DESK / fn, BOOKDIR / pdfname)
    d = fitz.open(DESK / fn)
    order = 0
    for pno in range(d.page_count):
        pg = d[pno]; txt = pg.get_text("text")
        if book == "Trading Ranges":
            m = re.search(r'(?m)^Figure\s+(\d+\.\d+)\s+([A-Z][^\n]{2,55})\s*$', txt)
        else:
            m = re.search(r'FIGURE\s+(\d+\.\d+)\s+([A-Z][^\n]{0,60})', txt)
        if not m:
            continue
        num = m.group(1); cap = m.group(2).strip()
        rects = (pg.search_for("FIGURE " + num) or pg.search_for("Figure " + num) or pg.search_for(num))
        pr = pg.rect
        if rects:
            cap_y = max(r.y1 for r in rects)
            clip = fitz.Rect(pr.x0 + 4, pr.y0 + 36, pr.x1 - 4, min(cap_y + 8, pr.y1))
        else:
            clip = fitz.Rect(pr.x0 + 4, pr.y0 + 36, pr.x1 - 4, pr.y0 + pr.height * 0.55)
        if clip.height < 130:
            clip = fitz.Rect(pr.x0 + 4, pr.y0 + 36, pr.x1 - 4, pr.y0 + pr.height * 0.52)
        pix = pg.get_pixmap(clip=clip, dpi=200)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        fid = f"{slug}{num.replace('.', '_')}"
        save_jpg(im, FIGDIR / f"{fid}.jpg")
        e = expl.get(fid, {})
        order += 1
        index.append({"id": fid, "book": book, "book_file": pdfname, "fig_num": num,
                      "caption": cap, "printed_page": e.get("pdf_page", ""), "pdf_page": pno + 1,
                      "file": f"figures/{fid}.jpg", "explanation": e.get("explanation", ""),
                      "order": (0 if book == "Trends" else 1 if book == "Trading Ranges" else 2, order)})
    d.close()
    print(f"{book:22} rendered")

# ---- Reversals: scanned -> render page region hi-res (no text layer) ----
shutil.copy(DESK / REVERSALS[0], BOOKDIR / REVERSALS[1])
dr = fitz.open(DESK / REVERSALS[0])
seen = set()
for i, f in enumerate(sorted(rev_figs, key=lambda x: x["pdf_page"])):
    pno = f["pdf_page"] - 1
    if pno < 0 or pno >= dr.page_count:
        continue
    num = f["fig_num"]; fid = f"RV{num.replace('.', '_').replace(' ', '')}"
    if fid in seen:
        fid = f"{fid}_{i}"
    seen.add(fid)
    pg = dr[pno]; pr = pg.rect
    clip = fitz.Rect(pr.x0, pr.y0 + pr.height * 0.05, pr.x1, pr.y0 + pr.height * 0.66)  # chart+caption
    pix = pg.get_pixmap(clip=clip, dpi=150)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    save_jpg(im, FIGDIR / f"{fid}.jpg", maxw=1200, q=80)
    index.append({"id": fid, "book": "Reversals", "book_file": REVERSALS[1], "fig_num": num,
                  "caption": f["caption"], "printed_page": "", "pdf_page": f["pdf_page"],
                  "file": f"figures/{fid}.jpg", "explanation": "",
                  "order": (3, i)})
dr.close()
print("Reversals rendered")

index.sort(key=lambda x: x["order"])
for x in index:
    x.pop("order", None)
json.dump(index, open(OUT / "figure_index.json", "w", encoding="utf-8"), ensure_ascii=False)
by = {}
for x in index:
    by[x["book"]] = by.get(x["book"], 0) + 1
tot = sum(f.stat().st_size for f in FIGDIR.glob("*.jpg"))
withtext = sum(1 for x in index if x["explanation"])
print(f"TOTAL {len(index)} figures | {by} | images {tot/1e6:.0f} MB | with full text: {withtext}")
