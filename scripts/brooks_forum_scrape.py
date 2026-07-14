"""Scrape Al Brooks' forum daily bar-by-bar (brookspriceaction.com forum f=1,
~600 threads 2020-2023). Per thread: the chart (album_picm) + the WITH-definitions
bar-by-bar text (from files/barbybar/brooksbars.php, abbreviations expanded inline).
Rate-limited. Login creds from scratchpad (gitignored).
  python scripts/brooks_forum_scrape.py --test 5
  python scripts/brooks_forum_scrape.py
"""
import requests, re, json, sys, time, html as H, io
from pathlib import Path
from PIL import Image

ROOT = Path(r"c:\Users\Admin\myquant")
HUB = ROOT / "docs" / "living" / "brooks_codex"
SCR = Path(r"C:\Users\Admin\AppData\Local\Temp\claude\c--Users-Admin-myquant\f04593f3-53f8-4ab9-9690-dd0509e339a3\scratchpad")
OUTIMG = HUB / "forum_charts"; OUTIMG.mkdir(parents=True, exist_ok=True)
BASE = "https://www.brookspriceaction.com"
cr = json.load(open(SCR / "bpa_login.json"))

def login():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120", "Referer": BASE + "/"})
    s.get(BASE + "/login.php", timeout=25)
    s.post(BASE + "/login.php", data={"username": cr["username"], "password": cr["password"],
                                       "autologin": "on", "login": "Log in", "redirect": ""}, timeout=25)
    return s

def collect_threads(s):
    out = []; start = 0
    while True:
        h = s.get(f"{BASE}/viewforum.php?f=1&start={start}", timeout=25).text
        rows = re.findall(r'viewtopic\.php\?[^"]*t=(\d+)[^"]*"[^>]*>\s*(\d{2}-\d{2}-\d{4})([^<]{0,30})', h)
        rows = [(t, d, ttl) for (t, d, ttl) in rows]
        seen = set(t for t, _, _ in out)
        new = [(t, d, ttl) for (t, d, ttl) in rows if t not in seen]
        if not new:
            break
        out.extend(new)
        start += 50
        if start > 2000:
            break
        time.sleep(0.3)
    # dedup keep first
    dd = {}
    for t, d, ttl in out:
        dd.setdefault(t, (d, ttl))
    return [(t, v[0], v[1].strip(" -")) for t, v in dd.items()]

def expand_and_clean(h):
    h2 = re.sub(r'<(?:abbr|acronym)[^>]*title="([^"]*)"[^>]*>(.*?)</(?:abbr|acronym)>', r'\2(\1)', h, flags=re.I | re.S)
    h2 = re.sub(r'<style.*?</style>', ' ', h2, flags=re.S | re.I)
    h2 = re.sub(r'<script.*?</script>', ' ', h2, flags=re.S | re.I)
    t = re.sub(r'<[^>]+>', ' ', h2); t = H.unescape(t)
    t = re.sub(r'[ \t]+', ' ', t); t = re.sub(r'\n\s*\n+', '\n', t)
    # skip the template header. Two known shapes: an instruction block ending
    # in "White Out!", and/or analysis starting at "1 - <Cap>" or "1 <ABBR>(".
    w = re.search(r'White Out!\s*', t)
    if w:
        t = t[w.end():].lstrip()
    m = re.search(r'(?:^|\n|\s)1\s*[-–]\s+[A-Z]', t) or re.search(r'(?:^|\n)\s*1\s+[A-Z]{2,}', t)
    if m:
        t = t[m.start():].lstrip()
    t = re.split(r'(Powered by|phpBB|Select a forum|Display posts from previous)', t)[0]
    return t.strip()

def logged_in(html):
    return 'mode=logout' in html or 'Log out' in html

class SessionBox:
    """Holds the live session; re-logins transparently when it dies."""
    def __init__(self):
        self.s = login()
        self.relogins = 0

    def get_page(self, url, check=None, **kw):
        ok = check or logged_in
        h = self.s.get(url, timeout=25, **kw).text
        if not ok(h):
            self.s = login(); self.relogins += 1
            h = self.s.get(url, timeout=25, **kw).text
            if not ok(h):
                raise RuntimeError("relogin failed")
        return h

def process(sb, t, date, title):
    s = sb.s
    th = sb.get_page(f"{BASE}/viewtopic.php?t={t}")
    s = sb.s  # may have been replaced by a relogin
    pic = re.search(r'album_picm\.php\?pic_id=(\d+)', th)
    rec = {"id": t, "date": date, "title": title, "has_text": False, "has_chart": False}
    # bar-by-bar link: threads can also contain Al's TUTORIAL link (pic_id 7214,
    # a 2010 example) — only trust a brooksbars link whose pic_id matches the
    # thread's own chart. If the thread has no chart of its own, take the link
    # only if it's not the known tutorial, and flag it for review.
    bbs = re.findall(r'(files/barbybar/brooksbars\.php\?[^"\'\s]*pic_id=\d+[^"\'\s]*)', th)
    bb = None
    for cand in bbs:
        m = re.search(r'pic_id=(\d+)', cand)
        if pic and m and m.group(1) == pic.group(1):
            bb = cand; break
    if bb is None and bbs:
        m = re.search(r'pic_id=(\d+)', bbs[0])
        if pic is None and m and m.group(1) != "7214":
            bb = bbs[0]; rec["bb_unverified"] = True
        else:
            rec["bb_mismatch"] = [re.search(r'pic_id=(\d+)', x).group(1) for x in bbs]
    # bar-by-bar text
    if bb:
        url = BASE + "/" + H.unescape(bb).replace("&amp;", "&")
        rec["tool_url"] = url                       # live interactive tool link (needs login)
        q = dict(re.findall(r'(\w+)=(\d+)', url))    # bars/left/width/top/height geometry
        rec["geom"] = {k: int(v) for k, v in q.items() if k in ("pic_id", "bars", "left", "width", "top", "height")}
        # tool pages have no Log-out link; valid ones contain the bar viewer JS
        bh = sb.get_page(url, check=lambda h: 'MyDiv' in h or 'BarNum' in h)
        txt = expand_and_clean(bh)
        if len(txt) > 200:
            rec["text"] = txt[:60000]; rec["has_text"] = True
        pm = re.search(r'album_picm\.php\?pic_id=(\d+)', bh)
        if pm and not pic:
            pic = pm
    # chart
    if pic:
        ir = sb.s.get(f"{BASE}/album_picm.php?pic_id={pic.group(1)}", timeout=30)
        if "image" in (ir.headers.get("content-type") or ""):
            try:
                im = Image.open(io.BytesIO(ir.content)).convert("RGB")
                if im.width > 1200:
                    im.thumbnail((1200, 1600))
                buf = io.BytesIO(); im.save(buf, "JPEG", quality=85)
                (OUTIMG / f"{t}.jpg").write_bytes(buf.getvalue())
                rec["has_chart"] = True; rec["file"] = f"forum_charts/{t}.jpg"
            except Exception as e:
                rec["err"] = f"img {e}"
    return rec

if __name__ == "__main__":
    sb = SessionBox()
    threads = collect_threads(sb.s)
    print(f"collected {len(threads)} daily threads")
    if "--test" in sys.argv:
        n = int(sys.argv[sys.argv.index("--test") + 1]); threads = threads[:n]
    dest = SCR / ("forum_test.json" if "--test" in sys.argv else "forum_index.json")
    # resume: keep previously-complete records, redo the rest
    done = {}
    if "--resume" in sys.argv and dest.exists():
        for x in json.load(open(dest, encoding="utf-8")):
            if x.get("has_chart") and (x.get("has_text") or x.get("bb_mismatch") is not None
                                       or "err" not in x and not x.get("tool_url")):
                done[x["id"]] = x
        print(f"resume: keeping {len(done)} complete records")
    out = list(done.values()); t0 = time.time()
    todo = [(t, d, ttl) for (t, d, ttl) in threads if t not in done]
    for i, (t, date, title) in enumerate(todo):
        try:
            out.append(process(sb, t, date, title))
        except Exception as e:
            out.append({"id": t, "date": date, "title": title, "err": str(e)})
        time.sleep(0.5)
        if (i + 1) % 50 == 0:
            txt = sum(1 for x in out if x.get("has_text")); ch = sum(1 for x in out if x.get("has_chart"))
            print(f"[{i+1}/{len(todo)}] text={txt} chart={ch} relogins={sb.relogins} ({time.time()-t0:.0f}s)", flush=True)
            json.dump(out, open(dest, "w", encoding="utf-8"), ensure_ascii=False)  # checkpoint
    json.dump(out, open(dest, "w", encoding="utf-8"), ensure_ascii=False)
    txt = sum(1 for x in out if x.get("has_text")); ch = sum(1 for x in out if x.get("has_chart"))
    print(f"\nDONE {len(out)} threads | with text: {txt} | with chart: {ch} -> {dest}")
    if "--test" in sys.argv:
        for x in out:
            print(f"  {x['date']} t={x['id']} text={x.get('has_text')} chart={x.get('has_chart')} | {x.get('text','')[:90]}")
