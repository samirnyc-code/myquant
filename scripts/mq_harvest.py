"""MenthorQ full-dashboard harvester (S73) — nightly EOD data capture.

Reuses gamma_tracker's saved Playwright session (auth_state.json — from the
S66 Backtest-tile scraper, still valid). For each SYMBOL x PAGE it saves, under
data/menthorq/harvest/YYYY-MM-DD/:

  <sym>_<page>.txt    full rendered innerText (parse offline, reparse anytime)
  <sym>_<page>.png    full-page screenshot (ground truth)
  <sym>_<page>_ws.json  any JSON WebSocket frames / XHR bodies seen (data feed)

Pages: options matrix (GEX/DEX per expiry), exposure (per-strike NetGEX + OI),
heatmap, price chart with levels indicator, and the levels page (Backtest tile
home). MenthorQ shows only TODAY — running this nightly accrues the history
they don't sell. Private use only; do not redistribute captures.

Run (nightly, after 16:30 ET):  .venv/Scripts/python.exe scripts/mq_harvest.py
Optional: --symbols SPX,ES,NQ
"""
import datetime as dt
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "gamma_tracker" / "auth_state.json"

SYMBOLS = ["SPX", "ES1!"]  # ES1! = front ES future; bare "ES" resolves to Eversource stock!
if "--symbols" in sys.argv:
    SYMBOLS = sys.argv[sys.argv.index("--symbols") + 1].split(",")

PAGES = {
    "matrix": "https://dashboard.menthorq.io/en/options/matrix?symbol={s}",
    "exposure": "https://dashboard.menthorq.io/en/options/exposure?symbol={s}",
    "heatmap": "https://dashboard.menthorq.io/en/options/heatmap?symbol={s}",
    # interval=15 + historicalLevels shows the INTRADAY side panel: regime + flip time,
    # expected move, NetGEX/NetDEX 1H deltas, GEX-by-DTE, P/C volume, 0DTE/1M skew
    "chart_levels": "https://dashboard.menthorq.io/en/charts/price?symbol={s}&interval=15&indicators=historicalLevels",
    "levels": "https://dashboard.menthorq.io/en/levels?symbol={s}",
}


def main():
    day = dt.date.today().isoformat()
    out = ROOT / "data" / "menthorq" / "harvest" / day
    out.mkdir(parents=True, exist_ok=True)
    feed = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(headless=True)
        ctx = br.new_context(storage_state=str(AUTH), viewport={"width": 1600, "height": 1000})
        page = ctx.new_page()

        def on_response(resp):
            if "json" in resp.headers.get("content-type", "") and "menthorq" in resp.url \
                    and not any(x in resp.url for x in ("auth/session", "users/me", "profile",
                                                        "watchlists", "screeners", "chats")):
                try:
                    feed.append({"url": resp.url, "body": resp.json()})
                except Exception:
                    pass

        def on_ws(ws):
            ws.on("framereceived", lambda f: feed.append({"ws": ws.url, "frame": f[:20000]})
                  if isinstance(f, str) and f[:1] in "[{" else None)

        page.on("response", on_response)
        page.on("websocket", on_ws)

        ok = fail = 0
        for s in SYMBOLS:
            for name, tpl in PAGES.items():
                feed.clear()
                tag = f"{s.replace('!', '').replace('/', '')}_{name}"
                try:
                    page.goto(tpl.format(s=s), wait_until="networkidle", timeout=60000)
                    page.wait_for_timeout(6000)  # WS-fed tables render after idle
                    if "login" in page.url.lower():
                        raise RuntimeError("SESSION EXPIRED — rerun gamma_tracker discover login")
                    (out / f"{tag}.txt").write_text(page.inner_text("body"), encoding="utf-8")
                    page.screenshot(path=str(out / f"{tag}.png"), full_page=True)
                    if feed:
                        (out / f"{tag}_ws.json").write_text(
                            json.dumps(feed, indent=1)[:2_000_000], encoding="utf-8")
                    print(f"  ok  {tag}  (text {len((out / (tag + '.txt')).read_text(encoding='utf-8')):,}ch, "
                          f"{len(feed)} feed msgs)")
                    ok += 1
                except Exception as e:
                    print(f"  FAIL {tag}: {e}")
                    fail += 1
        # refresh the stored session (keeps it alive indefinitely)
        ctx.storage_state(path=str(AUTH))

        # --- menthorq.com account area (separate login/session): CTA + Vol models ---
        AUTH2 = AUTH.parent / "auth_state_mqcom.json"
        if AUTH2.exists():
            ctx2 = br.new_context(storage_state=str(AUTH2), viewport={"width": 1600, "height": 1000})
            p2 = ctx2.new_page()
            for cmd in ("cta", "vol"):
                try:
                    p2.goto(f"https://menthorq.com/account/?action=data&type=dashboard"
                            f"&commands={cmd}&date={day}", wait_until="networkidle", timeout=60000)
                    p2.wait_for_timeout(6000)
                    txt = p2.inner_text("body")
                    if "unauthorized" in txt.lower():
                        raise RuntimeError("mqcom session expired — rerun scratchpad/mq_com_login.py")
                    (out / f"models_{cmd}.txt").write_text(txt, encoding="utf-8")
                    p2.screenshot(path=str(out / f"models_{cmd}.png"), full_page=True)
                    print(f"  ok  models_{cmd}")
                    ok += 1
                except Exception as e:
                    print(f"  FAIL models_{cmd}: {e}")
                    fail += 1
            ctx2.storage_state(path=str(AUTH2))
        br.close()
    print(f"\nharvest {day}: {ok} ok, {fail} failed -> {out}")


if __name__ == "__main__":
    main()
