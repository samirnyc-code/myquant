#!/usr/bin/env python3
"""MentorQ Backtest tile — automated daily scraper.

Since the panel exposes only *today's* backtest, this logs into the MentorQ
dashboard, reads all six gamma levels off the floating Backtest tile, and feeds
them straight into ingest.py so gamma.db accrues the history MentorQ won't show.

Modes
-----
  python scrape.py discover     # one-time: log in (headed), save session, dump
                                # the page HTML + screenshot so we can find the
                                # level-name and detail-panel selectors.
  python scrape.py run          # daily: load saved session, scrape 6 levels,
                                # build the morning JSON, call ingest.py.
  python scrape.py parse-test   # offline: run parse_detail() on a baked-in
                                # sample to prove the regex without a browser.

Session is persisted to auth_state.json (gitignored) after the first login, so
routine runs skip the login form entirely — fewer bot-detection triggers and no
password re-entry. If MentorQ adds 2FA/captcha, re-run `discover` and complete
it manually once.

Selectors marked TODO are filled in during the `discover` session.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUTH_STATE = HERE / "auth_state.json"
SHOTS = HERE / "screenshots"

# The six levels, in panel order. `label` is the on-screen level name we click.
LEVELS = [
    {"level_name": "1D Max", "label": "1D Max"},
    {"level_name": "Call Res. 0DTE", "label": "Call Res. 0DTE"},
    {"level_name": "Call Res.", "label": "Call Res."},
    {"level_name": "Put Support", "label": "Put Support"},
    {"level_name": "Put Sup. 0DTE", "label": "Put Sup. 0DTE"},
    {"level_name": "1D Min", "label": "1D Min"},
]

# --- selectors: confirmed during `discover`, then pasted here -------------------
SEL_LEVEL_ITEM = "text={label}"   # TODO: refine to the exact clickable row for a level
SEL_DETAIL_PANEL = "TODO"          # TODO: container holding the '... positive outcomes / BROKE ...' block
SEL_LOGIN_EMAIL = "input[type=email]"
SEL_LOGIN_PASSWORD = "input[type=password]"
SEL_LOGIN_SUBMIT = "button[type=submit]"


# --- parsing (browser-independent; unit-testable) ------------------------------
def parse_detail(text: str) -> dict:
    """Extract the numeric fields from one level's detail-panel innerText.

    Robust to whitespace/newlines — matches on the on-screen labels, not layout.
    Signed values (Put-side moves are negative) are preserved.
    """
    def num(pat, s=text, cast=float):
        m = re.search(pat, s, re.I)
        return cast(m.group(1).replace(",", "")) if m else None

    # split into the two sub-blocks so 'worst' / 'avg' don't collide across them
    during = re.search(r"broke during day(.*?)(?:broke at close|$)", text, re.I | re.S)
    at_close = re.search(r"broke at close(.*)", text, re.I | re.S)
    during_s = during.group(1) if during else ""
    close_s = at_close.group(1) if at_close else ""

    return {
        "regime_hold_rate_pct": num(r"([\d.]+)\s*%[^%]*?positive outcomes"),
        "positive_outcomes": num(r"([\d,]+)\s+positive outcomes", cast=int),
        "broke_at_close_pct": num(r"([\d.]+)\s*%", close_s),
        "comeback_rate_pct": num(r"comeback rate\s*([\d.]+)\s*%", during_s),
        "avg_move_intraday": num(r"avg move\s*([+-]?[\d.]+)", during_s),
        "worst_move_intraday": num(r"worst\s*([+-]?[\d.]+)", during_s),
        "median_close_beyond": num(r"median\s*([+-]?[\d.]+)", close_s),
        "avg_close_beyond": num(r"avg close\s*([+-]?[\d.]+)", close_s),
        "worst_close_beyond": num(r"worst\s*([+-]?[\d.]+)", close_s),
    }


_SAMPLE = (
    "CALL RES. 0DTE 72.9% 196 positive outcomes over the past 3 years "
    "BROKE DURING DAY comeback rate 45% avg move +26.51 worst +104.48 "
    "BROKE AT CLOSE 27.1% median +20.98 avg close +26.97 worst +83.48"
)


def cmd_parse_test() -> None:
    got = parse_detail(_SAMPLE)
    print(json.dumps(got, indent=2))
    expect = {"regime_hold_rate_pct": 72.9, "positive_outcomes": 196,
              "broke_at_close_pct": 27.1, "comeback_rate_pct": 45.0,
              "avg_move_intraday": 26.51, "worst_move_intraday": 104.48,
              "median_close_beyond": 20.98, "avg_close_beyond": 26.97,
              "worst_close_beyond": 83.48}
    ok = all(got.get(k) == v for k, v in expect.items())
    print("\nPARSE", "OK" if ok else "MISMATCH")
    if not ok:
        sys.exit(1)


# --- browser flows -------------------------------------------------------------
def _env() -> dict:
    from dotenv import dotenv_values
    cfg = dotenv_values(HERE / ".env")
    for k in ("MENTORQ_EMAIL", "MENTORQ_PASSWORD", "MENTORQ_URL"):
        if not cfg.get(k):
            sys.exit(f"Missing {k} in .env (copy .env.example -> .env and fill in)")
    return cfg


def cmd_discover() -> None:
    """Headed login + page dump so we can identify selectors."""
    from playwright.sync_api import sync_playwright
    cfg = _env()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(cfg["MENTORQ_URL"], wait_until="domcontentloaded")
        # Try automatic login; if the site uses SSO/redirects, just log in by hand
        # in the opened window — the script waits.
        try:
            page.fill(SEL_LOGIN_EMAIL, cfg["MENTORQ_EMAIL"], timeout=8000)
            page.fill(SEL_LOGIN_PASSWORD, cfg["MENTORQ_PASSWORD"])
            page.click(SEL_LOGIN_SUBMIT)
        except Exception:
            print("Auto-login fields not found — log in manually in the window.")
        print("\n>>> In the opened window:")
        print("    1. Log in (if not already).")
        print("    2. Add the indicator: Indicators -> search 'Gamma Levels | Backtesting'")
        print("       -> click it so the floating Backtest tile appears on the chart.")
        print("    3. Leave the tile visible.")
        print("    (Adding it saves to your chart layout, so daily runs won't need to re-add it.)")
        input(">>> When the Backtest tile is visible, press Enter here...")
        ctx.storage_state(path=str(AUTH_STATE))
        SHOTS.mkdir(exist_ok=True)
        (HERE / "discover_page.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(SHOTS / "discover_full.png"), full_page=True)
        print(f"Saved session -> {AUTH_STATE.name}")
        print("Saved discover_page.html + screenshots/discover_full.png")
        print("Send me those and I'll pin the SEL_LEVEL_ITEM / SEL_DETAIL_PANEL selectors.")
        browser.close()


def cmd_run(date: str | None) -> None:
    """Daily scrape -> morning JSON -> ingest."""
    if SEL_DETAIL_PANEL == "TODO":
        sys.exit("Selectors not set yet — run `discover` first and we'll fill them in.")
    from playwright.sync_api import sync_playwright
    cfg = _env()
    if not AUTH_STATE.exists():
        sys.exit("No saved session — run `python scrape.py discover` once first.")

    records = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(storage_state=str(AUTH_STATE))
        page = ctx.new_page()
        page.goto(cfg["MENTORQ_URL"], wait_until="networkidle")
        for lv in LEVELS:
            page.click(SEL_LEVEL_ITEM.format(label=lv["label"]))
            page.wait_for_timeout(600)  # let the detail panel repaint
            text = page.inner_text(SEL_DETAIL_PANEL)
            rec = {"level_name": lv["level_name"], **parse_detail(text)}
            records.append(rec)
            print(f"  {lv['level_name']:<16} hold={rec['regime_hold_rate_pct']} "
                  f"pos={rec['positive_outcomes']}")
        browser.close()

    if date is None:
        sys.exit("Pass --date YYYY-MM-DD (Date.now() is intentionally not used).")
    out = SHOTS / f"{date}_am.json"
    out.write_text(json.dumps({"date": date, "levels": records}, indent=2))
    print(f"\nWrote {out.name}; ingesting...")
    subprocess.run([sys.executable, str(HERE / "ingest.py"), "morning", str(out)], check=True)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    cmd = args[0]
    if cmd == "discover":
        cmd_discover()
    elif cmd == "run":
        date = None
        if "--date" in args:
            date = args[args.index("--date") + 1]
        cmd_run(date)
    elif cmd == "parse-test":
        cmd_parse_test()
    else:
        sys.exit(f"Unknown command: {cmd}\n{__doc__}")


if __name__ == "__main__":
    main()
