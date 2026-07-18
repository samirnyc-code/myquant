"""QUIN harvest (S73) — ask MenthorQ's in-app AI for structured data nightly.

For each symbol: gamma levels table + top-10 GEX strikes, parsed from QUIN's
answer into data/menthorq/harvest/YYYY-MM-DD/quin_<SYM>.json (raw text kept
alongside). SPX answers also auto-fill scratchpad/mq_levels_today.json (main
block) and ES answers its `es` block — no more morning hand-pasting.

Cross-check rule: QUIN values matched the dashboard tiles exactly on 2026-07-14;
mq_logger's calibration row remains the daily sanity check.

Run (nightly, after mq_harvest.py):  .venv/Scripts/python.exe scripts/mq_quin_harvest.py
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "gamma_tracker" / "auth_state.json"
LVL = ROOT / "scratchpad" / "mq_levels_today.json"

SYMBOLS = ["SPX", "ES"]
if "--symbols" in sys.argv:
    SYMBOLS = sys.argv[sys.argv.index("--symbols") + 1].split(",")

QUESTION = ("Give me today's {s} gamma levels as a plain table: Call Resistance, "
            "Put Support, HVL, the 0DTE levels (Call Resistance 0DTE, Put Support 0DTE, "
            "HVL 0DTE, Gamma Wall 0DTE), 1D Min, 1D Max, and the top 10 GEX strikes "
            "with their values.")

KEYMAP = {  # answer-label regex -> our JSON key
    r"call resistance 0dte|0dte call resistance": "cr0",
    r"put support 0dte|0dte put support": "ps0",
    r"hvl 0dte|0dte hvl": "hvl0",
    r"gamma wall( 0dte)?|0dte gamma wall": "gw0",
    r"call resistance": "cr",
    r"put support": "ps",
    r"hvl": "hvl",
    r"1d min": "d1_min",
    r"1d max": "d1_max",
}


def parse_answer(text):
    """Parse QUIN innerText: 'Label\\n?\\t?Value' rows + strike/GEX pairs."""
    out, gex = {}, []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    joined = []
    i = 0
    while i < len(lines):  # innerText may split label/value across lines
        if "\t" in lines[i]:
            joined.append(lines[i])
            i += 1
        elif i + 1 < len(lines) and re.fullmatch(r"\$?[\d,]+(\.\d+)?", lines[i + 1]):
            joined.append(lines[i] + "\t" + lines[i + 1])
            i += 2
        else:
            joined.append(lines[i])
            i += 1
    in_gex = False
    for ln in joined:
        if re.search(r"top .*gex strikes", ln, re.I):
            in_gex = True
            continue
        parts = ln.split("\t")
        if len(parts) == 2:
            label = parts[0].strip().lower().lstrip("$")
            val = parts[1].replace(",", "").replace("$", "").strip()
            if not re.fullmatch(r"-?[\d.]+", val):
                continue
            if in_gex and re.fullmatch(r"[\d.]+", label.replace(",", "")):
                gex.append({"strike": float(label.replace(",", "")), "gex": float(val)})
                continue
            for pat, key in KEYMAP.items():
                if re.fullmatch(pat, label, re.I) and key not in out:
                    out[key] = float(val)
                    break
    out["gex_strikes"] = gex
    return out


def ask(page, q):
    page.goto("https://dashboard.menthorq.io/en/chats", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(2500)
    box = page.locator("textarea, input[placeholder*='assist' i], [contenteditable='true']").first
    box.click()
    box.fill(q)
    page.keyboard.press("Enter")
    # poll until the answer stabilizes (QUIN streams; "Keep exploring" marks done)
    last = ""
    for _ in range(24):
        page.wait_for_timeout(5000)
        txt = page.inner_text("body")
        if "Keep exploring" in txt or (txt == last and len(txt) > 900):
            return txt
        last = txt
    return last


def main():
    day = dt.date.today().isoformat()
    out_dir = ROOT / "data" / "menthorq" / "harvest" / day
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {}
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(storage_state=str(AUTH), viewport={"width": 1500, "height": 950})
        page = ctx.new_page()
        for s in SYMBOLS:
            txt = ask(page, QUESTION.format(s=s))
            (out_dir / f"quin_{s}.txt").write_text(txt, encoding="utf-8")
            parsed = parse_answer(txt)
            if not parsed["gex_strikes"]:  # QUIN sometimes omits the table — ask directly
                txt2 = ask(page, f"List the top 10 GEX strikes for {s} today with their "
                                 "GEX values, as a two-column plain table.")
                (out_dir / f"quin_{s}_gex.txt").write_text(txt2, encoding="utf-8")
                parsed["gex_strikes"] = parse_answer(txt2)["gex_strikes"]
            parsed["symbol"], parsed["date"] = s, day
            (out_dir / f"quin_{s}.json").write_text(json.dumps(parsed, indent=1), encoding="utf-8")
            results[s] = parsed
            lvl_keys = {k: v for k, v in parsed.items() if k in
                        ("cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0", "d1_min", "d1_max")}
            print(f"{s}: {lvl_keys}  gex_strikes={len(parsed['gex_strikes'])}")
        ctx.storage_state(path=str(AUTH))
        br.close()

    # auto-fill the daily levels file (SPX -> main block, ES -> es block)
    if LVL.exists() and "SPX" in results:
        lv = json.loads(LVL.read_text(encoding="utf-8"))
        for k in ("cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0", "d1_min", "d1_max"):
            if results["SPX"].get(k) is not None:
                lv[k] = results["SPX"][k]
        lv["gex"] = [g["strike"] for g in results["SPX"]["gex_strikes"]][:10] or lv.get("gex", [])
        if "ES" in results:
            lv.setdefault("es", {})
            for k in ("cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0"):
                if results["ES"].get(k) is not None:
                    lv["es"][k] = results["ES"][k]
            lv["es"]["gex"] = [g["strike"] for g in results["ES"]["gex_strikes"]][:10]
        lv["date_note"] = f"AUTO-FILLED by mq_quin_harvest.py on {day} (QUIN); verify vs tiles via mq_logger."
        LVL.write_text(json.dumps(lv, indent=2), encoding="utf-8")
        print(f"mq_levels_today.json auto-filled ({day})")

    # longitudinal SPX-vs-ES wedge tracker (is ES positioning just SPX+basis, or its own animal?)
    if "SPX" in results and "ES" in results:
        import csv
        basis = None
        live_f = ROOT / "data" / "options_sim" / "live.json"
        if live_f.exists():
            try:
                basis = json.loads(live_f.read_text(encoding="utf-8")).get("basis")
            except Exception:
                pass
        wf = ROOT / "data" / "menthorq" / "levels_wedge.csv"
        new = not wf.exists()
        with open(wf, "a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["date", "level", "spx", "es", "basis", "converted", "wedge"])
            for k in ("cr", "ps", "hvl", "cr0", "ps0", "hvl0", "gw0"):
                s, e = results["SPX"].get(k), results["ES"].get(k)
                conv = round(s + basis, 1) if (s is not None and basis is not None) else None
                w.writerow([day, k, s, e, basis,
                            conv, round(e - conv, 1) if (e is not None and conv is not None) else None])
        print(f"wedge rows appended -> {wf.name}")


if __name__ == "__main__":
    main()
