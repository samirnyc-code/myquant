from playwright.sync_api import sync_playwright
url="https://databento.com/docs/examples/options/zero-dte-options/definition-schema"
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page()
    pg.goto(url, wait_until="networkidle", timeout=60000); pg.wait_for_timeout(3000)
    text=pg.inner_text("body")
    # pull code blocks specifically
    codes=[c.inner_text() for c in pg.query_selector_all("pre, code")]
    b.close()
open("scratchpad/databento_page.txt","w",encoding="utf-8").write(text)
print("=== MAIN TEXT (first 3500 chars) ===")
print(text[:3500])
print("\n=== CODE BLOCKS ===")
for i,c in enumerate(codes):
    if len(c.strip())>20:
        print(f"--- code {i} ---\n{c[:1200]}")
