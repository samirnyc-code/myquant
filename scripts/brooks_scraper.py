"""
Brooks Trading Course — EOD chart scraper.
Downloads annotated 5M ES chart images from brookstradingcourse.com.

Usage:
    python scripts/brooks_scraper.py

Images saved to: data/brooks_charts/
Metadata CSV:   data/brooks_charts/metadata.csv

Resumable — skips images already on disk.
"""

import csv
import json
import re
import time
from pathlib import Path
import requests
from urllib.parse import urlparse, unquote

# ── Auth cookies (session — re-export from browser if scraper gets 403) ────
COOKIES = {
    "wordpress_logged_in_c9a4459aae541f551fc28cf6257acde2": (
        "samirnyc%40gmail.com%7C1783473136%7CCpwhippY84Y2RygfKSXaTzd2Rhvjk3cGGi1QAN5KLda"
        "%7C13d6e17aa2834115ad119d07bba42848f0e32e7d709df3319f00dc01c5a873cf"
    ),
    "wordpress_sec_c9a4459aae541f551fc28cf6257acde2": (
        "samirnyc%40gmail.com%7C1783473136%7CCpwhippY84Y2RygfKSXaTzd2Rhvjk3cGGi1QAN5KLda"
        "%7C22f9df77ad834335fbe3e452c7d79f4bd6ffcaa07e8e65e5523b052ae672f9a7"
    ),
    "cf_clearance": (
        "xZ.VZ.HX3sGF09xMdY0dcQiBA52tnwg2Dyu1LTNcQSI-1767904686-1.2.1.1-2Nz.8gRCR0BciNRqjr1Xum"
        "tZShJmBVygrwxFK_GQpbXXQ9dedUJ_O_wepAFiExgoVVeJy2v7Fo7VsDqF_hg5s_m8tCMnnf7s0dm5XOQj2qHR2kc"
        "PWaYDs2m8fCPPVoyfwDh8OgFgeiX79j_MEj5tIOGUotffAiJcpzdG6hKj.KsxetBnluvzVvLnw0VjKS2.nm8zHglbq"
        "xI4utm8Ht36BXwil3GfJXtxX2Eq2gqEdaM"
    ),
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.brookstradingcourse.com/",
}

BASE_URL  = "https://www.brookstradingcourse.com"
API_BASE  = f"{BASE_URL}/wp-json/wp/v2"
OUT_DIR   = Path(__file__).resolve().parent.parent / "data" / "brooks_charts"
META_FILE = OUT_DIR / "metadata.csv"

# Only keep ES/S&P 5-min EOD charts — skip Forex, Gold, weekly, monthly
EMINI_KEYWORDS = ["e-mini", "emini", "sp500", "s&p", "es ", "5-min", "5 min"]
SKIP_KEYWORDS  = ["forex", "weekly", "monthly", "gold", "crude", "bitcoin", "nasdaq",
                  "dow", "russell", "euro", "gbp", "aud", "jpy", "cad", "chf"]


def is_emini_5m(title: str) -> bool:
    t = title.lower()
    if any(s in t for s in SKIP_KEYWORDS):
        return False
    return any(k in t for k in EMINI_KEYWORDS)


def get_session() -> requests.Session:
    s = requests.Session()
    s.cookies.update(COOKIES)
    s.headers.update(HEADERS)
    return s


def fetch_posts(session: requests.Session) -> list[dict]:
    """Pull all posts via WP REST API (embedded featured images)."""
    posts, page = [], 1
    while True:
        r = session.get(
            f"{API_BASE}/posts",
            params={"_embed": 1, "per_page": 100, "page": page,
                    "orderby": "date", "order": "desc"},
            timeout=30,
        )
        if r.status_code == 400:
            break  # past last page
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        posts.extend(batch)
        total_pages = int(r.headers.get("X-WP-TotalPages", 1))
        print(f"  page {page}/{total_pages}  ({len(posts)} posts so far)")
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.5)
    return posts


def extract_chart_url(post: dict) -> str | None:
    """Return the full-size chart image URL from an embedded post."""
    try:
        media = post["_embedded"]["wp:featuredmedia"][0]
        # Prefer the full-size URL
        sizes = media.get("media_details", {}).get("sizes", {})
        for key in ("full", "large", "medium_large"):
            if key in sizes:
                return sizes[key]["source_url"]
        return media.get("source_url")
    except (KeyError, IndexError, TypeError):
        return None


def safe_filename(title: str, post_id: int, ext: str = ".jpg") -> str:
    slug = re.sub(r"[^\w\s-]", "", title).strip()
    slug = re.sub(r"[\s]+", "-", slug)[:120]
    return f"{post_id}_{slug}{ext}"


def download_image(session: requests.Session, url: str, dest: Path) -> bool:
    try:
        r = session.get(url, timeout=30, stream=True)
        r.raise_for_status()
        dest.write_bytes(r.content)
        return True
    except Exception as e:
        print(f"    ERROR downloading {url}: {e}")
        return False


def load_existing_ids(meta_file: Path) -> set[int]:
    if not meta_file.exists():
        return set()
    with meta_file.open() as f:
        reader = csv.DictReader(f)
        return {int(row["post_id"]) for row in reader if row.get("post_id")}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = get_session()

    existing = load_existing_ids(META_FILE)
    print(f"Already downloaded: {len(existing)} posts\n")

    print("Fetching post list from WP REST API…")
    posts = fetch_posts(session)
    print(f"\nTotal posts found: {len(posts)}")

    # Filter to ES 5-min EOD charts
    emini_posts = [p for p in posts if is_emini_5m(p.get("title", {}).get("rendered", ""))]
    print(f"ES 5-min posts:   {len(emini_posts)}")

    write_header = not META_FILE.exists()
    new_count = 0

    with META_FILE.open("a", newline="", encoding="utf-8") as csvf:
        writer = csv.DictWriter(csvf, fieldnames=[
            "post_id", "date", "title", "tags", "filename", "image_url", "post_url"
        ])
        if write_header:
            writer.writeheader()

        for i, post in enumerate(emini_posts):
            post_id = post["id"]
            if post_id in existing:
                continue

            title    = post.get("title", {}).get("rendered", "")
            date     = post.get("date", "")[:10]
            post_url = post.get("link", "")
            tags     = [t.get("name", "") for t in post.get("_embedded", {})
                        .get("wp:term", [[]])[1] if isinstance(t, dict)]

            img_url = extract_chart_url(post)
            if not img_url:
                print(f"  [{i+1}] No image: {title[:60]}")
                continue

            ext      = Path(urlparse(img_url).path).suffix or ".jpg"
            filename = safe_filename(title, post_id, ext)
            dest     = OUT_DIR / filename

            if dest.exists():
                print(f"  [{i+1}] Skip (file exists): {filename}")
            else:
                print(f"  [{i+1}] Downloading: {title[:60]}")
                ok = download_image(session, img_url, dest)
                if not ok:
                    continue
                time.sleep(0.3)

            writer.writerow({
                "post_id":   post_id,
                "date":      date,
                "title":     title,
                "tags":      "|".join(tags),
                "filename":  filename,
                "image_url": img_url,
                "post_url":  post_url,
            })
            new_count += 1

    print(f"\nDone. {new_count} new charts downloaded to {OUT_DIR}")
    print(f"Metadata: {META_FILE}")


if __name__ == "__main__":
    main()
