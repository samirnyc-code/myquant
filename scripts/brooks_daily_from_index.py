"""Rebuild Daily Charts data from the REAL metadata in the study-library zip
(site/data/index.json + flashcards_index.json) instead of the generic card text.
Real: title, date, day_type (full + short category), tags, lesson, bar-by-bar
commentary (the 'searchable' field, re-cased for readability). Reuses the already
-extracted daily/<post_id>.jpg images (no re-decode).
Output: docs/living/brooks_codex/daily_index.json
"""
import zipfile, json, re
from pathlib import Path

ZIP = Path(r"G:\My Drive\MC Setup Research Notes\brooks_study_library.zip")
HUB = Path(r"c:\Users\Admin\myquant\docs\living\brooks_codex")
DAILY = HUB / "daily"

with zipfile.ZipFile(ZIP) as z:
    idx = json.loads(z.read("site/data/index.json").decode("utf-8", "replace"))
    try:
        fc = {str(r["post_id"]): r for r in json.loads(z.read("site/data/flashcards_index.json").decode("utf-8", "replace"))}
    except Exception:
        fc = {}

TERMS = {" i ": " I ", "brooks": "Brooks", "emini": "Emini", "e-mini": "E-mini",
         "ema": "EMA", "vwap": "VWAP", "s&p": "S&P", "spy": "SPY"}

def recase(t):
    if not t:
        return ""
    t = t.replace("�", "—").replace("&amp;", "&")
    # ** bold leads -> paragraph breaks
    parts = t.split("**")
    out = []
    for k, seg in enumerate(parts):
        seg = seg.strip()
        if not seg:
            continue
        out.append(("\n\n" if k % 2 == 1 else " ") + seg)
    t = "".join(out).strip()
    # capitalize sentence starts
    t = re.sub(r'(^|[.!?]\s+|\n\s*)([a-z])', lambda m: m.group(1) + m.group(2).upper(), t)
    for a, b in TERMS.items():
        t = re.sub(re.escape(a), b, t, flags=re.I)
    t = re.sub(r'\bh(\d)\b', lambda m: "H" + m.group(1), t)
    t = re.sub(r'\bl(\d)\b', lambda m: "L" + m.group(1), t)
    t = re.sub(r'[ \t]{2,}', ' ', t)
    return t.strip()

def strip_daytype_prefix(text, day_full):
    # 'searchable' starts with the lowercased day_type; drop that duplicate lead
    if day_full:
        low = text.lower().lstrip()
        dl = day_full.lower()
        if low.startswith(dl):
            return text.lstrip()[len(day_full):].lstrip()
    return text

out = []
missing = 0
for r in idx:
    pid = str(r["post_id"])
    if not (DAILY / f"{pid}.jpg").exists():
        missing += 1
        continue
    day_full = r.get("day_type", "")
    commentary = strip_daytype_prefix(r.get("searchable", ""), day_full)
    detailed = len(re.findall(r'\bbar \d', commentary.lower())) >= 2   # real bar-by-bar vs generic filler
    f = fc.get(pid, {})
    out.append({
        "id": pid, "title": r.get("title", "Emini"), "date": r.get("date", ""),
        "day_type": day_full, "day_type_short": r.get("day_type_short", "Other"),
        "tags": [t.replace("&amp;", "&") for t in r.get("tags", [])],
        "detailed": detailed,   # chart-specific AI (real bar refs) vs generic AI filler
        "lesson": f.get("lesson", ""),
        "text": recase(commentary),   # ALL AI-generated (Brooks-style); labeled as such in the UI
        "file": f"daily/{pid}.jpg",
    })
out.sort(key=lambda x: (x.get("date") or "z", x["id"]))
json.dump(out, open(HUB / "daily_index.json", "w", encoding="utf-8"), ensure_ascii=False)
withtext = sum(1 for x in out if len(x["text"]) > 200)
withlesson = sum(1 for x in out if x["lesson"])
print(f"rebuilt daily_index.json: {len(out)} cards ({missing} missing image)")
print(f"  real commentary >200 chars: {withtext} | with lesson: {withlesson}")
print("  sample text:", out[0]["text"][:200])
