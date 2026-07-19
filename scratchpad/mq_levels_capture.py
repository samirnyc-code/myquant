"""Reverse-engineer the MenthorQ /en/levels 'Request Levels' endpoint (v2).

Enumerate buttons, click the real blue Search button (role=button, name~Search),
wait for the levels result, then click Prev Date. Log every clickhouse-api call.
"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
AUTH = ROOT / "gamma_tracker" / "auth_state.json"
OUT = ROOT / "scratchpad" / "mq_levels_net.json"

calls = []


def rec(resp):
    u = resp.url
    if "clickhouse-api" not in u:
        return
    req = resp.request
    body = None
    try:
        body = req.post_data
    except Exception:
        pass
    entry = {"method": req.method, "url": u, "body": body, "status": resp.status}
    # try capture small JSON response bodies for levels-ish endpoints
    if any(k in u.lower() for k in ("level", "gamma")):
        try:
            entry["resp_preview"] = resp.text()[:800]
        except Exception:
            pass
    calls.append(entry)


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    ctx = br.new_context(storage_state=str(AUTH))
    page = ctx.new_page()
    page.on("response", rec)
    print("loading /en/levels ...")
    page.goto("https://dashboard.menthorq.io/en/levels?symbol=SPX",
              wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)

    # enumerate all buttons
    btns = page.get_by_role("button").all()
    print(f"\n{len(btns)} buttons:")
    for b in btns:
        try:
            print(f"  [{b.inner_text()[:40]!r}] visible={b.is_visible()}")
        except Exception:
            pass

    # click the exact blue Search button (role button, name Search, not the tab)
    n0 = len(calls)
    clicked = False
    for b in btns:
        try:
            t = b.inner_text().strip()
            if t == "Search" and b.is_visible():
                b.click(timeout=5000)
                clicked = True
                print("clicked blue Search button")
                break
        except Exception:
            continue
    page.wait_for_timeout(4000)
    print(f"levels calls after Search: {len(calls)-n0}")

    # dump full page text to see the result + look for Prev/Next Date buttons
    body_txt = page.inner_text("body")
    (ROOT / "scratchpad" / "mq_levels_pagetext.txt").write_text(body_txt, encoding="utf-8")

    # now find & click Prev Date
    for i in range(3):
        clicked_prev = False
        for b in page.get_by_role("button").all():
            try:
                if "Prev" in b.inner_text() and b.is_visible():
                    b.click(timeout=5000)
                    clicked_prev = True
                    break
            except Exception:
                continue
        print(f"Prev Date #{i+1}: clicked={clicked_prev}")
        page.wait_for_timeout(2500)

    br.close()

OUT.write_text(json.dumps(calls, indent=1), encoding="utf-8")
print(f"\nwrote {OUT} ({len(calls)} clickhouse calls)")
for c in calls:
    print(f"  {c['method']} {c['status']} {c['url']}")
    if c.get("body"):
        print(f"       body={c['body'][:300]}")
