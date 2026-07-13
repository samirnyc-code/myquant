"""Prepare the full study-app data bundle: map book figures -> setups & rules,
select a compressed embed subset, build quiz pools. Output: brooks_app_data.json
consumed by brooks_build_full.py.
"""
import json, base64, io, re
from pathlib import Path
from PIL import Image
from collections import defaultdict

SCR = Path(r"C:\Users\Admin\AppData\Local\Temp\claude\c--Users-Admin-myquant\f04593f3-53f8-4ab9-9690-dd0509e339a3\scratchpad")
ROOT = Path(r"c:\Users\Admin\myquant")
figs = json.load(open(SCR / "figures_catalog.json", encoding="utf-8"))
cards = json.load(open(SCR / "brooks_setup_cards.json", encoding="utf-8"))["cards"]
rules = json.load(open(SCR / "brooks_rules_expanded.json", encoding="utf-8"))["rules"]
final = json.load(open(ROOT / "docs" / "living" / "brooks_final.json", encoding="utf-8"))
golden = json.load(open(SCR / "brooks_golden.json", encoding="utf-8"))

# ---- figure -> setup mapping via caption/tag keyword scoring ----------------
SETUP_KW = {
    "High 2 / Low 2 Pullback": ["high 2", "low 2", "two-legged", "two legged", "pullback", "moving average", "m2b", "m2s"],
    "Breakout Pullback": ["breakout pullback", "breakout test", "failed breakout", "breakout"],
    "Trend from the Open": ["trend from the open", "small pullback", "trend from the first", "open"],
    "Opening Reversal": ["opening reversal", "opening range", "opening"],
    "Spike and Channel": ["spike and channel", "spike-and-channel", "channel"],
    "Second Entry Reversal": ["second entry", "reversal", "double bottom", "double top"],
    "Strong Breakout / Spike": ["spike", "strong breakout", "trend bar", "climax"],
    "Always-In Follow-Through": ["always in", "always-in", "trend bar", "follow"],
    "Wedge Reversal": ["wedge reversal", "wedge", "three push", "third push"],
    "Wedge Flag (High 3 / Low 3)": ["wedge flag", "high 3", "low 3", "wedge"],
    "Double Bottom / Double Top Pullback": ["double bottom", "double top", "double"],
    "Final Flag Reversal": ["final flag", "flag"],
    "Moving Average Gap Bar": ["moving average gap", "gap bar", "ma gap", "20 gap"],
    "Major Trend Reversal": ["major trend reversal", "trend line", "trendline", "trend channel", "reversal"],
    "Fade the Trading Range Extremes": ["trading range", "barbwire", "tight range", "range"],
}

CARD_ALIAS = {"always-in": "Always-In Follow-Through", "wedge bull": "Wedge Flag (High 3 / Low 3)",
              "wedge bear": "Wedge Flag (High 3 / Low 3)"}

def card_key(c):  # match the card's canonical name to a SETUP_KW key
    nm = c["setup_name"].lower()
    for frag, k in CARD_ALIAS.items():
        if frag in nm:
            return k
    for k in SETUP_KW:
        if k.split(" (")[0].lower()[:12] in nm or nm[:12] in k.lower():
            return k
    return c["setup_name"]

def score(fig, kws):
    hay = (fig["caption"] + " " + fig.get("discussion", "") + " " + " ".join(fig.get("tags", []))).lower()
    return sum(hay.count(k) for k in kws)

# Prefer the accurate classifier map (figure_map.json) when present; else keyword fallback.
fmap_path = SCR / "figure_map.json"
FMAP = {r["id"]: r for r in json.load(open(fmap_path, encoding="utf-8"))} if fmap_path.exists() else {}
print("using figure_map.json" if FMAP else "figure_map.json ABSENT -> keyword fallback")

setup_figs = {}   # setup_name -> [fig_id,...]
used = set()
for c in cards:
    nm = c["setup_name"]
    if FMAP:
        picks = [f["id"] for f in figs if nm in (FMAP.get(f["id"], {}).get("setups") or [])][:6]
    else:
        key = card_key(c)
        kws = SETUP_KW.get(key, [nm.lower()])
        ranked = sorted(figs, key=lambda f: score(f, kws), reverse=True)
        picks = [f["id"] for f in ranked if score(f, kws) > 0][:5]
    setup_figs[nm] = picks
    used.update(picks)

# ---- quiz pool: figures with a confident single concept (name-that-setup) ----
CONCEPT_LABEL = {  # primary tag -> a clean quiz answer label
    "H2/L2 pullback": "High 2 / Low 2 pullback", "Wedge": "Wedge",
    "Double top/bottom": "Double top / bottom", "Final flag": "Final flag",
    "Spike and channel": "Spike and channel", "Breakout pullback": "Breakout pullback",
    "Trend from the open": "Trend from the open", "Opening reversal": "Opening reversal",
    "Trading range": "Trading range", "Reversal": "Major reversal",
    "Trend line / channel": "Trendline break", "Climax": "Climax", "Gap": "Gap",
}
quiz_pool = []
by_concept = defaultdict(list)
for f in figs:
    if FMAP:
        r = FMAP.get(f["id"], {})
        if r.get("quiz_ok") and r.get("concept") and r["concept"] != "General":
            by_concept[r["concept"]].append(f)
    elif f.get("tags") and f["tags"][0] in CONCEPT_LABEL:
        by_concept[CONCEPT_LABEL[f["tags"][0]]].append(f)
for label, fl in by_concept.items():
    for f in fl[:9]:            # cap per concept -> balanced quiz
        quiz_pool.append({"id": f["id"], "answer": label, "caption": f["caption"],
                          "cite": f"Brooks {f['book']}, Fig {f['fig_num']}"})
        used.add(f["id"])

# ---- encode the embed subset (compressed) ------------------------------------
def b64_of(fid):
    p = SCR / "figures" / f"{fid}.jpg"
    if not p.exists():
        return None
    im = Image.open(p).convert("RGB")
    if im.width > 600:
        im.thumbnail((600, 900))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=62)
    return base64.b64encode(buf.getvalue()).decode()

fig_meta = {f["id"]: f for f in figs}
images = {}
for fid in used:
    b = b64_of(fid)
    if b:
        images[fid] = b

# figure display record
def fig_rec(fid):
    m = fig_meta[fid]
    return {"id": fid, "caption": m["caption"], "fig_num": m["fig_num"], "book": m["book"],
            "page": m.get("printed_page", "")}

bundle = {
    "setups": [{
        "name": c["setup_name"], "aliases": c.get("aliases", []), "grade": c.get("grade", ""),
        "category": c.get("category", ""), "direction": c.get("direction", ""),
        "one_liner": c.get("one_liner", ""), "context": c.get("context", ""),
        "entry": c.get("entry", ""), "stop": c.get("stop", ""), "management": c.get("management", ""),
        "must_know_rules": c.get("must_know_rules", []), "dont_trade_tells": c.get("dont_trade_tells", []),
        "figures": [fig_rec(fid) for fid in setup_figs.get(c["setup_name"], [])],
    } for c in cards],
    "rules": rules,
    "notrade": golden.get("when_not_to_trade", []),
    "memorize": golden.get("memorize_10", []),
    "teachings": final["teachings"],
    "quiz_pool": quiz_pool,
    "quiz_answers": sorted(set(q["answer"] for q in quiz_pool)),
    "images": images,
    "counts": {"setups": len(cards), "rules": len(rules),
               "core": sum(1 for r in rules if r.get("tier") == "core"),
               "figures_embedded": len(images), "figures_total": len(figs),
               "quiz": len(quiz_pool),
               "teachings": sum(len(v) for v in final["teachings"].values())},
}
json.dump(bundle, open(SCR / "brooks_app_data.json", "w", encoding="utf-8"), ensure_ascii=False)
emb = sum(len(v) for v in images.values())
print("counts:", bundle["counts"])
print(f"embedded {len(images)} figures, ~{emb*3/4/1e6:.1f} MB of image bytes")
print("figures per setup:", {c['setup_name'][:22]: len(setup_figs.get(c['setup_name'], [])) for c in cards})
print("quiz answers:", bundle["quiz_answers"])
