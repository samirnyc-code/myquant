"""Parse the ~1,500 Brooks EOD study cards out of brooks_study_library.zip (on Drive),
extract each chart image + title/day-type/date/commentary, and build the Daily
Charts data for the Codex. Reads the zip directly (no full extraction).
Output: docs/living/brooks_codex/daily/*.jpg + daily_index.json
"""
import zipfile, re, io, json, base64
from pathlib import Path
from PIL import Image

ZIP = Path(r"G:\My Drive\MC Setup Research Notes\brooks_study_library.zip")
OUT = Path(r"c:\Users\Admin\myquant\docs\living\brooks_codex")
DAILY = OUT / "daily"; DAILY.mkdir(parents=True, exist_ok=True)

def _strip(inner):
    # preserve paragraph / line breaks, then strip remaining tags
    t = re.sub(r'(?i)</(p|div|h[1-6]|li)>', '\n', inner)
    t = re.sub(r'(?i)<br\s*/?>', '\n', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n\s*\n\s*\n+', '\n\n', t)
    return t.strip()

def div_inner(html, cls):
    """Full inner HTML of the FIRST <div class="...cls...">, matching nested divs."""
    m = re.search(r'<div[^>]*class="[^"]*\b' + cls + r'\b[^"]*"[^>]*>', html)
    if not m:
        return ""
    i = m.end(); depth = 1
    for mm in re.finditer(r'<(/?)div\b', html[i:]):
        depth += -1 if mm.group(1) else 1
        if depth == 0:
            return html[i:i + mm.start()]
    return html[i:]

def tag_text(html, cls):
    # single-element fields (date, banner): grab inner up to its close
    m = re.search(r'<[^>]*class="[^"]*\b' + cls + r'\b[^"]*"[^>]*>(.*?)</', html, re.S)
    return _strip(m.group(1)) if m else ""

def clean_title(t):
    t = re.sub(r'\s*[–—|\-]\s*Brooks Study Card\s*$', '', t).strip()
    return t

index = []
skipped = 0
with zipfile.ZipFile(ZIP) as z:
    cards = [n for n in z.namelist() if re.search(r'site/cards/\d+\.html$', n)]
    print(f"cards in zip: {len(cards)}")
    for i, name in enumerate(cards):
        pid = re.search(r'(\d+)\.html$', name).group(1)
        html = z.read(name).decode("utf-8", "replace")
        m = re.search(r'data:image/(?:png|jpeg|jpg|gif);base64,([A-Za-z0-9+/=]+)', html)
        if not m:
            skipped += 1
            continue
        try:
            raw = base64.b64decode(m.group(1))
            im = Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception:
            skipped += 1
            continue
        if im.width > 900:
            im.thumbnail((900, 1400))
        buf = io.BytesIO(); im.save(buf, "JPEG", quality=72)
        (DAILY / f"{pid}.jpg").write_bytes(buf.getvalue())
        title = clean_title((re.search(r'<title>(.*?)</title>', html, re.S) or ["", ""])[1])
        index.append({
            "id": pid,
            "title": title or "Emini",
            "date": tag_text(html, "date"),
            "day_type": tag_text(html, "day-type-banner"),
            "text": _strip(div_inner(html, "explanation-content")) or _strip(div_inner(html, "explanation-panel")),
            "file": f"daily/{pid}.jpg",
        })
        if (i + 1) % 300 == 0:
            print(f"[{i+1}/{len(cards)}] parsed, {len(index)} ok ({skipped} skipped)", flush=True)

# order by date if parseable, else by id
def datekey(x):
    m = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', x.get("date", "")) or \
        re.search(r'(\w+)\s+(\d{1,2}),?\s+(\d{4})', x.get("date", ""))
    return x.get("date", "") or x["id"]
index.sort(key=lambda x: (x.get("date", "") or "z", x["id"]))

json.dump(index, open(OUT / "daily_index.json", "w", encoding="utf-8"), ensure_ascii=False)
sz = sum(f.stat().st_size for f in DAILY.glob("*.jpg"))
withtext = sum(1 for x in index if x["text"])
withtype = sum(1 for x in index if x["day_type"])
print(f"\nDONE {len(index)} daily cards | images {sz/1e6:.0f} MB | with text {withtext} | with day-type {withtype} | skipped {skipped}")
