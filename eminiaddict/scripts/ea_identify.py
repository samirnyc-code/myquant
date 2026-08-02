"""ea_identify.py — read the TICKER HEADER on each grabbed frame (OCR) to label it by the
TRUE instrument + timeframe, instead of guessing from transcript keywords. Fixes mislabels
(Crude->regime chart, RTY->'ES 4h', etc.). Rewrites frames.json with instrument/tf/header.

Usage: python ea_identify.py <MMDDYY> [MMDDYY ...]   |   --all
"""
import json
import os
import re
import sys

import pytesseract
from PIL import Image, ImageOps

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DAILY = os.path.join(ROOT, "eminiaddict", "data", "daily")

# instrument tokens (checked against the OCR'd header, first ~18 chars for the ticker)
INSTR = [("ES", ["/ES", "JES", "ES 180", "ES 360", " ES "]),
         ("NQ", ["/NQ", "NQ 1", "NASDAQ"]),
         ("YM", ["/YM", "YM 1"]),
         ("RTY", ["/RTY", "RTY 1", "RUSSELL"]),
         ("6E", ["/6E", "6E ", "EUR", "EURO"]),
         ("6J", ["/6J", "6J ", "YEN", "JPY"]),
         ("CL", ["/CL", "CL 1", "CRUDE", "WTI"]),
         ("GC", ["/GC", "GC 1", "GOLD"]),
         ("SI", ["/SI", "SI 1", "SILVER"]),
         ("DXY", ["DXY", "DOLLAR IND"]),
         ("VIX", ["VIX"]),
         ("BANK", ["BANK", "BKX", "/BKX"]),
         ("BTC", ["BTC", "BITCOIN"]),
         ("ETH", ["ETH", "ETHEREUM", "AETHER"]),
         ("ZB", ["/ZB", "ZB 1", "BOND"])]
TF_RE = re.compile(r"\bD\s*(\d{1,2}\s*[hm])\b", re.I)   # 'D 12h' / 'D 4h' / 'D 15m'


def header_text(path):
    im = Image.open(path).convert("L").crop((0, 55, 460, 110))
    im = im.resize((im.width * 4, im.height * 4), Image.LANCZOS)
    im = ImageOps.autocontrast(im)
    return pytesseract.image_to_string(im, config="--psm 7").strip()


def identify(txt):
    head = txt.upper()[:22]
    instr = None
    for name, toks in INSTR:
        if any(t.upper() in head for t in toks):
            instr = name; break
    m = TF_RE.search(txt)
    tf = m.group(1).replace(" ", "").lower() if m else ""
    return instr, tf


def process(mmddyy):
    fdir = os.path.join(DAILY, mmddyy, "frames")
    fj = os.path.join(fdir, "frames.json")
    if not os.path.exists(fj):
        print(f"! {mmddyy}: no frames.json"); return
    frames = json.load(open(fj, encoding="utf-8"))
    for f in frames:
        p = os.path.join(fdir, f["file"])
        if not os.path.exists(p):
            f["instrument"], f["tf"], f["header"] = None, "", ""
            continue
        h = header_text(p)
        instr, tf = identify(h)
        f["instrument"], f["tf"], f["header"] = instr, tf, h[:60]
    json.dump(frames, open(fj, "w", encoding="utf-8"), indent=1)
    ided = [f for f in frames if f.get("instrument")]
    print(f"{mmddyy}: identified {len(ided)}/{len(frames)} frames")
    for f in frames:
        print(f"   {f['file']:20s} cue={f['topic']:8s} -> "
              f"OCR={f.get('instrument') or '?'} {f.get('tf','')}   [{f.get('header','')}]")


def main():
    args = sys.argv[1:]
    if args == ["--all"]:
        args = sorted(d for d in os.listdir(DAILY) if os.path.isdir(os.path.join(DAILY, d)))
    for m in args:
        process(m)


if __name__ == "__main__":
    main()
