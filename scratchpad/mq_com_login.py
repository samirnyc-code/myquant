"""One-time menthorq.com (account area) login capture.
Opens a VISIBLE browser; user logs in; script detects success, saves session to
gamma_tracker/auth_state_mqcom.json, then verifies the CTA + Vol model pages."""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "gamma_tracker" / "auth_state_mqcom.json"

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=False)
    ctx = br.new_context(viewport={"width": 1400, "height": 950})
    page = ctx.new_page()
    page.goto("https://menthorq.com/account/", wait_until="domcontentloaded", timeout=60000)
    print("Waiting for you to log in (up to 5 minutes)...")
    ok = False
    for _ in range(150):  # 5 min, 2s polls
        page.wait_for_timeout(2000)
        try:
            txt = page.inner_text("body")
        except Exception:
            continue
        if "unauthorized" not in txt.lower() and "password" not in txt.lower()[:2000]:
            ok = True
            break
    if not ok:
        print("Timed out — run again when ready.")
    else:
        ctx.storage_state(path=str(STATE))
        print(f"session saved -> {STATE}")
        for cmd in ("cta", "vol"):
            page.goto(f"https://menthorq.com/account/?action=data&type=dashboard&commands={cmd}&date=2026-07-14",
                      wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(4000)
            txt = page.inner_text("body")
            (ROOT / "scratchpad" / f"mq_{cmd}.txt").write_text(txt, encoding="utf-8")
            page.screenshot(path=str(ROOT / "scratchpad" / f"mq_{cmd}.png"), full_page=True)
            print(f"{cmd}: captured {len(txt)} chars")
    br.close()
