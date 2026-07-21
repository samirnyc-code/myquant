import glob
import json
import re
import sys
from pathlib import Path

# 1) what arrays live inside a per-expiration block of net-gex-by-expiration?
for f in glob.glob(str(Path(__file__).resolve().parent / "mq_endpoints" / "resp_*.json")):
    d = json.load(open(f, encoding="utf-8"))
    if "net-gex-by-expiration" in d["url"]:
        raw = d["body"]
        i = raw.find('"expirations":[')
        blk = raw[i:i + 1200]
        print("per-expiration block keys:", sorted(set(re.findall(r'"(\w+)":', blk))))
        print(blk[:900])
        break

# 2) ASK QUIN for historical OI
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from mq_quin_harvest import ask
from playwright.sync_api import sync_playwright

AUTH = str(Path(__file__).resolve().parent.parent / "gamma_tracker" / "auth_state.json")
with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    ctx = br.new_context(storage_state=AUTH, viewport={"width": 1500, "height": 950})
    page = ctx.new_page()
    q = ("For SPX, can you give historical open interest? Show total call OI and total "
         "put OI at end of day for each trading day from 2026-06-15 through 2026-07-14, "
         "one row per day: Date, Call OI, Put OI.")
    txt = ask(page, q)
    (Path(__file__).resolve().parent / "mq_quin" / "quin_oi_hist.txt").write_text(txt, encoding="utf-8")
    k = txt.find("one row per day")
    print("\n\n=== QUIN historical-OI answer ===")
    print(txt[k:k + 1400] if k > 0 else txt[-1400:])
    br.close()
