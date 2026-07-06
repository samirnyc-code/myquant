#!/usr/bin/env python3
"""
Brooks study library — static site generator.
Builds a shareable, standalone HTML + JSON site from walkthroughs + metadata.

Usage:
    python scripts/brooks_build_static_site.py [--output-dir site/]

Generates:
    site/index.html — searchable index with day-type filter + date sort
    site/cards/{post_id}.html — full-screen study card per chart
    site/data/index.json — metadata index for client-side search
"""

import json
import csv
from pathlib import Path
import base64
import re
from urllib.parse import quote

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "brooks_charts"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "site"


def load_metadata():
    """Load metadata.csv → dict keyed by post_id."""
    meta = {}
    with (DATA_DIR / "metadata.csv").open() as f:
        for row in csv.DictReader(f):
            meta[int(row["post_id"])] = row
    return meta


def load_walkthrough(post_id):
    """Load walkthrough markdown and parse day type + text."""
    path = DATA_DIR / "walkthroughs" / f"{post_id}.md"
    if not path.exists():
        return None, None

    text = path.read_text(encoding="utf-8")
    lines = text.strip().split("\n")

    # Parse banner (## Day Type)
    day_type = None
    content_start = 0
    for i, line in enumerate(lines):
        if line.startswith("## "):
            day_type = line[3:].strip()
            content_start = i + 1
            break

    body = "\n".join(lines[content_start:]).strip()
    return day_type, body


def load_chart_image_base64(post_id, filename):
    """Load chart image and encode as base64 for embedding."""
    path = DATA_DIR / filename
    if not path.exists():
        return None
    try:
        with path.open("rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return None


def extract_day_type_short(day_type_full):
    """Extract short day-type tag for filtering (e.g., 'Bull Trend', 'Trading Range')."""
    # Common patterns
    if "Bull Trend" in day_type_full and "Bear" not in day_type_full:
        return "Bull Trend"
    if "Bear Trend" in day_type_full:
        return "Bear Trend"
    if "Trading Range" in day_type_full:
        return "Trading Range"
    if "Wedge" in day_type_full:
        return "Wedge"
    if "Spike" in day_type_full or "Channel" in day_type_full:
        return "Spike & Channel"
    if "Climax" in day_type_full:
        return "Climax"
    if "Reversal" in day_type_full:
        return "Reversal"
    return "Other"


def generate_index_json(metadata, walkthroughs):
    """Generate searchable index as JSON."""
    index = []
    for post_id, meta in metadata.items():
        day_type, body = walkthroughs.get(post_id, (None, None))
        if not day_type:
            continue

        index.append({
            "post_id": post_id,
            "date": meta["date"],
            "day_type": day_type,
            "day_type_short": extract_day_type_short(day_type),
            "title": meta["title"],
            "tags": meta.get("tags", "").split("|") if meta.get("tags") else [],
            "searchable": f"{day_type} {body}".lower(),
        })

    return sorted(index, key=lambda x: x["date"], reverse=True)


def generate_card_html(post_id, meta, day_type, body, chart_base64):
    """Generate a single study card HTML page."""
    title = meta["title"][:60]
    date_str = meta["date"]

    # Split body into paragraphs and lesson
    lesson_text = ""
    paragraphs = []
    for para in body.split("\n\n"):
        if para.startswith("**Lesson:**"):
            lesson_text = para[11:].strip()
        else:
            paragraphs.append(para.strip())

    para_html = "\n".join(f"<p>{p}</p>" for p in paragraphs if p)
    lesson_html = f"<div class='lesson'><strong>Lesson:</strong> {lesson_text}</div>" if lesson_text else ""

    chart_img = f'<img src="data:image/jpeg;base64,{chart_base64}" alt="Chart" class="chart-img">' if chart_base64 else "<p>(Chart not available)</p>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — Brooks Study Card</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #1a1a1a; color: #e0e0e0; }}
        .container {{ max-width: 100vw; height: 100vh; display: flex; flex-direction: column; }}
        .header {{ background: #222; padding: 12px 16px; border-bottom: 1px solid #333; }}
        .header-title {{ font-size: 14px; color: #aaa; }}
        .header-title .date {{ font-size: 12px; margin-right: 8px; }}
        .main {{ display: flex; flex: 1; overflow: hidden; }}
        .chart-panel {{ flex: 1; display: flex; align-items: center; justify-content: center; background: #0a0a0a; padding: 16px; overflow: auto; }}
        .chart-img {{ max-width: 100%; max-height: 100%; object-fit: contain; }}
        .explanation-panel {{
            width: 0;
            background: #1e1e1e;
            border-left: 1px solid #333;
            overflow-y: auto;
            transition: width 0.3s ease;
            padding: 0;
        }}
        .explanation-panel.open {{ width: 35%; }}
        .explanation-content {{ padding: 20px; display: none; }}
        .explanation-panel.open .explanation-content {{ display: block; }}
        .explanation-header {{
            padding: 16px 20px;
            border-bottom: 1px solid #333;
            font-weight: bold;
            background: #252525;
        }}
        .day-type-banner {{
            background: #1565c0;
            color: white;
            padding: 12px;
            margin-bottom: 12px;
            border-radius: 4px;
            font-size: 13px;
            line-height: 1.4;
        }}
        .explanation-content p {{ margin-bottom: 12px; font-size: 13px; line-height: 1.6; }}
        .lesson {{
            margin-top: 16px;
            padding-top: 12px;
            border-top: 1px solid #333;
            font-size: 13px;
            line-height: 1.6;
        }}
        .controls {{
            position: absolute;
            bottom: 16px;
            right: 16px;
            font-size: 12px;
            color: #666;
        }}
        .toggle-btn {{
            position: fixed;
            bottom: 16px;
            right: 16px;
            padding: 8px 16px;
            background: #1565c0;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
        }}
        .toggle-btn:hover {{ background: #1e88e5; }}
        a {{ color: #1e88e5; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-title">
                <span class="date">{date_str}</span>
                <span>{title}</span>
                <a href="../index.html" style="margin-left: 16px; font-size: 12px;">← Back to index</a>
            </div>
        </div>
        <div class="main">
            <div class="chart-panel">
                {chart_img}
            </div>
            <div class="explanation-panel" id="explPanel">
                <div class="explanation-header">Walkthrough</div>
                <div class="explanation-content">
                    <div class="day-type-banner">{day_type}</div>
                    {para_html}
                    {lesson_html}
                </div>
            </div>
        </div>
    </div>

    <button class="toggle-btn" id="toggleBtn">Explanation (E)</button>

    <script>
        const panel = document.getElementById('explPanel');
        const btn = document.getElementById('toggleBtn');

        function togglePanel() {{
            panel.classList.toggle('open');
            btn.textContent = panel.classList.contains('open') ? 'Hide (E)' : 'Explanation (E)';
        }}

        btn.addEventListener('click', togglePanel);

        // Keyboard: E or Space to toggle
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'e' || e.key === 'E' || e.key === ' ') {{
                if (e.target === document.body) {{
                    e.preventDefault();
                    togglePanel();
                }}
            }}
        }});
    </script>
</body>
</html>"""

    return html


def generate_index_html(index_data):
    """Generate index.html with search + filter."""
    day_types = sorted(set(item["day_type_short"] for item in index_data))
    day_type_opts = "\n".join(f'<option value="{dt}">{dt}</option>' for dt in day_types)

    index_json_str = json.dumps(index_data)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Brooks Trading Course Study Library</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #1a1a1a; color: #e0e0e0; }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        h1 {{ margin-bottom: 20px; font-size: 28px; }}
        .controls {{ display: flex; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }}
        input, select {{
            padding: 8px 12px;
            background: #252525;
            border: 1px solid #333;
            color: #e0e0e0;
            border-radius: 4px;
            font-size: 14px;
        }}
        input::placeholder {{ color: #666; }}
        input:focus, select:focus {{ outline: none; border-color: #1565c0; }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 12px;
        }}
        .card {{
            background: #252525;
            border: 1px solid #333;
            border-radius: 6px;
            padding: 16px;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .card:hover {{
            background: #2d2d2d;
            border-color: #1565c0;
        }}
        .card-date {{ font-size: 12px; color: #888; }}
        .card-day-type {{
            background: #1565c0;
            color: white;
            display: inline-block;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 12px;
            margin-top: 8px;
        }}
        .card-title {{
            font-size: 14px;
            margin-top: 8px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        a {{ color: #1e88e5; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .stats {{ color: #888; font-size: 13px; margin-top: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Brooks Study Library</h1>
        <p style="color: #aaa; margin-bottom: 20px;">
            {len(index_data)} annotated ES 5-min EOD charts with AI-generated walkthroughs.
            Read the chart, study the walkthrough, train your context identification.
        </p>

        <div class="controls">
            <input type="text" id="searchInput" placeholder="Search walkthroughs...">
            <select id="filterDay">
                <option value="">All day types</option>
                {day_type_opts}
            </select>
            <select id="sortBy">
                <option value="date-desc">Newest first</option>
                <option value="date-asc">Oldest first</option>
            </select>
        </div>

        <div class="stats" id="stats"></div>
        <div class="grid" id="grid"></div>
    </div>

    <script>
        const INDEX = {index_json_str};
        const grid = document.getElementById('grid');
        const searchInput = document.getElementById('searchInput');
        const filterDay = document.getElementById('filterDay');
        const sortBy = document.getElementById('sortBy');
        const stats = document.getElementById('stats');

        function render() {{
            let filtered = INDEX;
            const q = searchInput.value.toLowerCase();
            const dayType = filterDay.value;
            const sort = sortBy.value;

            if (q) {{
                filtered = filtered.filter(item => item.searchable.includes(q));
            }}

            if (dayType) {{
                filtered = filtered.filter(item => item.day_type_short === dayType);
            }}

            if (sort === 'date-asc') {{
                filtered = filtered.reverse();
            }}

            stats.textContent = `Showing ${{filtered.length}} of ${{INDEX.length}} charts`;

            grid.innerHTML = filtered.map(item => `
                <a href="cards/${{item.post_id}}.html" style="text-decoration: none; color: inherit;">
                    <div class="card">
                        <div class="card-date">${{item.date}}</div>
                        <div class="card-day-type">${{item.day_type_short}}</div>
                        <div class="card-title">${{item.title}}</div>
                    </div>
                </a>
            `).join('');
        }}

        searchInput.addEventListener('input', render);
        filterDay.addEventListener('change', render);
        sortBy.addEventListener('change', render);

        render();
    </script>
</body>
</html>"""

    return html


def main():
    print("Building Brooks static site…")

    # Load data
    metadata = load_metadata()
    print(f"  Loaded {len(metadata)} metadata entries")

    walkthroughs = {}
    for post_id in metadata:
        day_type, body = load_walkthrough(post_id)
        if day_type and body:
            walkthroughs[post_id] = (day_type, body)
    print(f"  Loaded {len(walkthroughs)} walkthroughs")

    # Create output dirs
    OUTPUT_DIR.mkdir(exist_ok=True)
    cards_dir = OUTPUT_DIR / "cards"
    cards_dir.mkdir(exist_ok=True)
    data_dir = OUTPUT_DIR / "data"
    data_dir.mkdir(exist_ok=True)

    # Generate index JSON
    index_data = generate_index_json(metadata, walkthroughs)
    (data_dir / "index.json").write_text(json.dumps(index_data, indent=2), encoding="utf-8")
    print(f"  Generated index.json ({len(index_data)} items)")

    # Generate index HTML
    index_html = generate_index_html(index_data)
    (OUTPUT_DIR / "index.html").write_text(index_html, encoding="utf-8")
    print(f"  Generated index.html")

    # Generate card HTMLs
    for i, (post_id, (day_type, body)) in enumerate(walkthroughs.items(), 1):
        meta = metadata[post_id]
        chart_base64 = load_chart_image_base64(post_id, meta["filename"])
        card_html = generate_card_html(post_id, meta, day_type, body, chart_base64)
        (cards_dir / f"{post_id}.html").write_text(card_html, encoding="utf-8")

        if i % 100 == 0:
            print(f"  Generated {i}/{len(walkthroughs)} card pages")

    print(f"  Generated {len(walkthroughs)} card pages ✓")
    print(f"\n✅ Site built to: {OUTPUT_DIR}/")
    print(f"   Open: {OUTPUT_DIR}/index.html")


if __name__ == "__main__":
    main()
