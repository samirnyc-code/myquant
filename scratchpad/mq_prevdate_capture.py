"""Drive /en/levels: select SPX in the picker, Search, then Prev Date. Log all xhr."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "gamma_tracker" / "auth_state.json"
calls = []
PHASE = "load"

def rec(resp):
    if resp.request.resource_type not in ("xhr", "fetch"):
        return
    u = resp.url
    if "menthorq.io" not in u or "_rsc=" in u or "/auth/" in u:
        return
    calls.append({"phase": PHASE, "url": u, "status": resp.status})

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    ctx = br.new_context(storage_state=str(AUTH), viewport={"width": 1400, "height": 900})
    page = ctx.new_page()
    page.on("response", rec)
    page.goto("https://dashboard.menthorq.io/en/levels", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)

    # 1) open the ticker picker and type SPX
    picker = page.get_by_text("Select Tickers", exact=False).first
    picker.click(timeout=5000)
    page.wait_for_timeout(800)
    # type into whatever input appeared
    try:
        page.keyboard.type("SPX", delay=60)
    except Exception:
        pass
    page.wait_for_timeout(1500)
    page.screenshot(path=str(ROOT / "scratchpad" / "mq_picker.png"))
    # SPX is highlighted at top of the dropdown — select it
    picked = False
    try:
        page.get_by_role("option", name="SPX", exact=True).first.click(timeout=3000)
        picked = True
    except Exception:
        try:
            page.keyboard.press("Enter")
            picked = True
        except Exception:
            pass
    print("picked SPX:", picked)
    page.keyboard.press("Escape")
    page.wait_for_timeout(800)

    # 2) Search
    PHASE = "search"
    page.get_by_role("button", name="Search", exact=True).click(timeout=8000)
    page.wait_for_timeout(4000)
    page.screenshot(path=str(ROOT / "scratchpad" / "mq_after_search.png"))

    # 3) Prev Date x3
    PHASE = "prevdate"
    for i in range(3):
        done = False
        for sel in ["button:has-text('Prev Date')", "button:has-text('Prev')"]:
            try:
                page.locator(sel).first.click(timeout=3000)
                done = True
                break
            except Exception:
                continue
        page.wait_for_timeout(2500)
        print(f"prevdate #{i+1}: clicked={done}")
    page.screenshot(path=str(ROOT / "scratchpad" / "mq_after_prev.png"))
    (ROOT / "scratchpad" / "mq_prev_pagetext.txt").write_text(page.inner_text("body"), encoding="utf-8")
    br.close()

(ROOT / "scratchpad" / "mq_prevdate_net.json").write_text(json.dumps(calls, indent=1), encoding="utf-8")
print(f"\n{len(calls)} data calls:")
for c in calls:
    print(f"  [{c['phase']:8}] {c['status']} {c['url']}")
