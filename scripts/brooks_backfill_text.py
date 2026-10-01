"""Backfill Brooks post body text (play-by-play analysis) for the study library.
Reads metadata.csv, fetches each post's content via WP REST API, saves cleaned
text to data/brooks_charts/posts/{post_id}.md. Resumable (skips existing)."""
import csv, re, time, html, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from brooks_scraper import get_session, API_BASE, OUT_DIR

POSTS_DIR = OUT_DIR / "posts"; POSTS_DIR.mkdir(parents=True, exist_ok=True)

def clean(h):
    h = re.sub(r'(?i)<(br|/p|/div|/h[1-6])\s*>', '\n', h)
    h = re.sub(r'(?i)<h[1-6][^>]*>', '\n## ', h)
    h = re.sub(r'<[^>]+>', '', h)
    h = html.unescape(h)
    h = re.sub(r'[ \t]+', ' ', h)
    h = re.sub(r'\n\s*\n\s*\n+', '\n\n', h)
    return h.strip()

def main():
    with (OUT_DIR/"metadata.csv").open() as f:
        rows = list(csv.DictReader(f))
    s = get_session()
    done = skipped = err = 0
    for i, r in enumerate(rows):
        pid = r["post_id"]
        dest = POSTS_DIR / f"{pid}.md"
        if dest.exists(): skipped += 1; continue
        try:
            resp = s.get(f"{API_BASE}/posts/{pid}", timeout=30)
            if resp.status_code != 200: err += 1; continue
            p = resp.json()
            body = clean(p.get("content", {}).get("rendered", ""))
            fm = (f"---\npost_id: {pid}\ndate: {r['date']}\n"
                  f"title: {html.unescape(r['title'])}\ntags: {r['tags']}\n"
                  f"url: {r['post_url']}\nimage: {r['filename']}\n---\n\n")
            dest.write_text(fm + body, encoding="utf-8")
            done += 1
            if done % 50 == 0: print(f"  {done} fetched ({i+1}/{len(rows)})", flush=True)
            time.sleep(0.3)
        except Exception as e:
            err += 1; print(f"  ERR {pid}: {e}", flush=True)
    print(f"DONE. fetched={done} skipped={skipped} errors={err} -> {POSTS_DIR}")

if __name__ == "__main__":
    main()
