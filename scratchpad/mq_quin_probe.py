"""Talk to QUIN (MenthorQ's in-app AI) programmatically — can it serve data?"""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(r"c:\Users\Admin\myquant")
AUTH = ROOT / "gamma_tracker" / "auth_state.json"
OUT = ROOT / "scratchpad" / "mq_quin"
OUT.mkdir(exist_ok=True)

QUESTION = ("Give me today's SPX gamma levels as a plain table: Call Resistance, "
            "Put Support, HVL, the 0DTE levels (CR, PS, HVL, Gamma Wall), and the "
            "top 10 GEX strikes with their values.")

with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    ctx = br.new_context(storage_state=str(AUTH), viewport={"width": 1500, "height": 950})
    page = ctx.new_page()
    page.goto("https://dashboard.menthorq.io/en/chats", wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)
    # the landing input: placeholder "How can I assist you today?"
    box = page.locator("textarea, input[placeholder*='assist' i], [contenteditable='true']").first
    box.click()
    box.fill(QUESTION)
    page.keyboard.press("Enter")
    print("question sent, waiting for QUIN...")
    page.wait_for_timeout(45000)
    page.screenshot(path=str(OUT / "quin_answer.png"), full_page=True)
    txt = page.inner_text("body")
    (OUT / "quin_answer.txt").write_text(txt, encoding="utf-8")
    print(f"captured {len(txt)} chars -> scratchpad/mq_quin/")
    tail = txt[-2500:]
    print("---- tail of page text ----")
    print(tail)
    br.close()
