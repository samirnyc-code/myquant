"""Re-scrape the correct Emini 5-min chart + Brooks' REAL post text for our existing
1,500 daily post-ids (from daily_index.json). Fixes the wrong-image problem AND
gives authentic commentary. Rate-limited. Cookies from scratchpad (gitignored).
  python scripts/brooks_rescrape.py --test 12     # dry test, no full run
  python scripts/brooks_rescrape.py               # full 1,500
"""
import json, re, sys, time, html
from pathlib import Path
import requests
from PIL import Image
import io

ROOT = Path(__file__).resolve().parent.parent
HUB = ROOT / "docs" / "living" / "brooks_codex"
SCR = ROOT / "scratchpad"
CK = json.load(open(SCR / "brooks_cookies.json"))
OUTIMG = HUB / "daily2"; OUTIMG.mkdir(parents=True, exist_ok=True)
API = "https://www.brookstradingcourse.com/wp-json/wp/v2/posts"

s = requests.Session(); s.cookies.update(CK)
s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120",
                  "Referer": "https://www.brookstradingcourse.com/"})

BAD = ['eurusd','gbp','usdjpy','usdcad','audusd','nzd','bitcoin','btc','ethereum','crude','oil',
       'gold','xau','silver','copper','bond','tnote','yield','forex','dax','ftse','nikkei','nifty',
       'nasdaq','ndx','russell','dow','ym-','wolff','video','review','featured','logo','300px','iphone',
       'virus','vaccine','covid','ophthalm','headshot','banner']
TF_BAD = ['daily','weekly','monthly','60-min','60min','15-min','15min','hourly','hour','1-hour']

def score(fn):
    f = fn.lower()
    if any(b in f for b in BAD):
        return -99
    if not any(k in f for k in ['emini','e-mini','sp500','s-p-500','es-5','es5']):
        return -99
    sc = 1
    if re.search(r'5.?min', f):
        sc += 6
    if any(tf in f for tf in TF_BAD):
        sc -= 4
    return sc

def full_size(u):
    return re.sub(r'-\d{2,4}x\d{2,4}(?=\.\w+$)', '', u)

def clean_text(content):
    t = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', content, flags=re.S | re.I)
    t = re.sub(r'(?i)</(p|div|h[1-6]|li|br)>', '\n', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = html.unescape(t)
    t = re.sub(r'[ \t]+', ' ', t)
    t = re.sub(r'\n\s*\n\s*\n+', '\n\n', t)
    return t.strip()

def best_chart(p):
    fm = p.get('_embedded', {}).get('wp:featuredmedia', [{}])[0].get('source_url', '')
    imgs = ([fm] if fm else []) + re.findall(r'<img[^>]+src="([^"]+)"', p['content']['rendered'])
    scored = sorted(((score(u.split('/')[-1]), u) for u in imgs if u), reverse=True)
    return full_size(scored[0][1]) if scored and scored[0][0] > 0 else None

def process(pid):
    r = s.get(f"{API}/{pid}", params={"_embed": 1}, timeout=30)
    if r.status_code != 200:
        return {"id": pid, "error": f"HTTP {r.status_code}"}
    p = r.json()
    title = html.unescape(re.sub(r'<[^>]+>', '', p['title']['rendered'])).strip()
    url = best_chart(p)
    rec = {"id": str(pid), "title": title, "date": p.get("date", "")[:10],
           "chart_url": url, "text": clean_text(p['content']['rendered'])[:6000]}
    if url:
        ir = s.get(url, timeout=30)
        if ir.status_code == 200:
            try:
                im = Image.open(io.BytesIO(ir.content)).convert("RGB")
                if im.width > 1200:
                    im.thumbnail((1200, 1600))
                buf = io.BytesIO(); im.save(buf, "JPEG", quality=85)
                (OUTIMG / f"{pid}.jpg").write_bytes(buf.getvalue())
                rec["got_chart"] = True
            except Exception as e:
                rec["error"] = f"img {e}"
    return rec

if __name__ == "__main__":
    ids = [x["id"] for x in json.load(open(HUB / "daily_index.json", encoding="utf-8"))]
    test_n = None
    if "--test" in sys.argv:
        test_n = int(sys.argv[sys.argv.index("--test") + 1])
        # include the known-broken ones in the test
        known = ["103882", "196855", "272308", "116787"]
        ids = known + [i for i in ids if i not in known]
        ids = ids[:test_n]
    out = []
    t0 = time.time()
    for i, pid in enumerate(ids):
        try:
            out.append(process(pid))
        except Exception as e:
            out.append({"id": pid, "error": str(e)})
        time.sleep(0.6)   # be polite to the server
        if (i + 1) % 100 == 0:
            got = sum(1 for x in out if x.get("got_chart"))
            print(f"[{i+1}/{len(ids)}] charts={got} ({time.time()-t0:.0f}s)", flush=True)
    got = sum(1 for x in out if x.get("got_chart"))
    nochart = [x for x in out if not x.get("got_chart")]
    dest = SCR / ("rescrape_test.json" if test_n else "rescrape_full.json")
    json.dump(out, open(dest, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"\nDONE {len(out)} posts | got chart: {got} | no chart: {len(nochart)}")
    if test_n:
        for x in out:
            c = (x.get("chart_url") or "NONE").split("/")[-1][:55]
            print(f"  {x['id']} {x['title'][:38]:40} -> {c}")
