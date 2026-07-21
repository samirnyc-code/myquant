"""Map MenthorQ's real data endpoints — capture ALL network traffic (URLs,
methods, request bodies, response bodies, auth headers) while loading the
data pages and while QUIN answers. Goal: replay the endpoints directly,
bypassing both scraping and QUIN. Output -> scratchpad/mq_endpoints/"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
AUTH = ROOT / "gamma_tracker" / "auth_state.json"
OUT = ROOT / "scratchpad" / "mq_endpoints"
OUT.mkdir(exist_ok=True)

SKIP = ("auth/session", "users/me", "/profile", "watchlists", "screeners", "/chats",
        ".js", ".css", ".woff", ".png", ".svg", ".ico", "sentry", "analytics",
        "clarity", "posthog", "speculation")

calls = []


def interesting(url):
    return ("menthorq" in url) and not any(s in url for s in SKIP)


with sync_playwright() as pw:
    br = pw.chromium.launch(headless=True)
    ctx = br.new_context(storage_state=str(AUTH), viewport={"width": 1500, "height": 950})

    def on_request(req):
        if interesting(req.url):
            calls.append({"phase": PHASE, "method": req.method, "url": req.url,
                          "post": (req.post_data or "")[:600],
                          "auth": req.headers.get("authorization", "")[:40]})

    page = ctx.new_page()
    page.on("request", on_request)

    def dump_responses(tag):
        # attach a response sink that saves bodies for data endpoints
        def on_resp(r):
            if interesting(r.url) and "json" in r.headers.get("content-type", ""):
                try:
                    body = r.text()
                    if len(body) > 60:
                        fn = OUT / f"{tag}_{abs(hash(r.url)) % 99999}.json"
                        fn.write_text(json.dumps({"url": r.url, "body": body[:8000]}, indent=1),
                                      encoding="utf-8")
                except Exception:
                    pass
        page.on("response", on_resp)

    dump_responses("resp")
    for PHASE, url in [
        ("exposure", "https://dashboard.menthorq.io/en/options/exposure?symbol=SPX"),
        ("matrix", "https://dashboard.menthorq.io/en/options/matrix?symbol=SPX"),
        ("heatmap", "https://dashboard.menthorq.io/en/options/heatmap?symbol=SPX"),
        ("summary", "https://dashboard.menthorq.io/en/tickers/SPX"),
    ]:
        try:
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(6000)
        except Exception as e:
            print(f"{PHASE}: {e}")

    (OUT / "all_calls.json").write_text(json.dumps(calls, indent=1), encoding="utf-8")
    # dedup unique endpoint patterns
    seen = {}
    for c in calls:
        key = c["url"].split("?")[0] + " " + c["method"]
        seen.setdefault(key, c)
    print(f"{len(calls)} data calls, {len(seen)} unique endpoints:\n")
    for k, c in sorted(seen.items()):
        print(f"  [{c['phase']:9s}] {c['method']:4s} {k.split(' ')[0][:95]}")
        if c["post"]:
            print(f"             body: {c['post'][:120]}")
    br.close()
print(f"\nresponse bodies + all_calls.json -> {OUT}")
