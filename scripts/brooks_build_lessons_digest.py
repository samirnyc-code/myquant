#!/usr/bin/env python3
"""
Brooks Study Library — Tells & Lessons digest.
Aggregates all **Lesson:** sections grouped by day type for quick reference.

Usage:
    python scripts/brooks_build_lessons_digest.py

Generates:
    site/lessons.html — searchable digest organized by day type
"""

import json
import csv
from pathlib import Path
from collections import defaultdict

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "brooks_charts"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "site"


def extract_day_type_short(day_type_full):
    """Extract short day-type tag for grouping."""
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


def load_walkthrough(post_id):
    """Load walkthrough and extract lesson section."""
    path = DATA_DIR / "walkthroughs" / f"{post_id}.md"
    if not path.exists():
        return None, None

    text = path.read_text(encoding="utf-8")
    lines = text.strip().split("\n")

    day_type = None
    lesson = None

    for line in lines:
        if line.startswith("## "):
            day_type = line[3:].strip()
        elif line.startswith("**Lesson:**"):
            lesson = line[11:].strip()
            break

    return day_type, lesson


def load_metadata():
    """Load metadata.csv → dict keyed by post_id."""
    meta = {}
    with (DATA_DIR / "metadata.csv").open() as f:
        for row in csv.DictReader(f):
            meta[int(row["post_id"])] = row
    return meta


def main():
    print("Building Tells & Lessons digest…")

    metadata = load_metadata()
    lessons_by_type = defaultdict(list)

    # Extract all lessons
    for post_id in metadata:
        day_type, lesson = load_walkthrough(post_id)
        if day_type and lesson:
            day_type_short = extract_day_type_short(day_type)
            lessons_by_type[day_type_short].append({
                "post_id": post_id,
                "day_type_full": day_type,
                "lesson": lesson,
                "date": metadata[post_id].get("date", ""),
            })

    total_lessons = sum(len(v) for v in lessons_by_type.values())
    print(f"  Extracted {total_lessons} lessons across {len(lessons_by_type)} day types")

    # Sort each day type by date (newest first)
    for key in lessons_by_type:
        lessons_by_type[key].sort(key=lambda x: x["date"], reverse=True)

    # Generate JSON index
    lessons_json = {k: v for k, v in lessons_by_type.items()}
    (OUTPUT_DIR / "data" / "lessons.json").write_text(json.dumps(lessons_json, indent=2), encoding="utf-8")
    print(f"  Generated lessons.json")

    # Generate HTML digest
    day_types_sorted = sorted(lessons_by_type.keys())
    day_type_buttons = "\n".join(f'<button class="day-filter-btn" data-type="{dt}">{dt} ({len(lessons_by_type[dt])})</button>' for dt in day_types_sorted)

    lessons_data_json = json.dumps(lessons_json)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tells & Lessons — Brooks Study Library</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #1a1a1a; color: #e0e0e0; }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}
        .header {{ margin-bottom: 30px; }}
        h1 {{ font-size: 28px; margin-bottom: 8px; }}
        .subtitle {{ color: #888; font-size: 14px; margin-bottom: 20px; }}
        .controls {{ display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }}
        .day-filter-btn {{
            padding: 8px 12px;
            background: #252525;
            border: 1px solid #333;
            color: #e0e0e0;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
        }}
        .day-filter-btn.active {{
            background: #1565c0;
            border-color: #1565c0;
        }}
        .day-filter-btn:hover {{
            border-color: #1565c0;
        }}
        .search-box {{
            padding: 8px 12px;
            background: #252525;
            border: 1px solid #333;
            color: #e0e0e0;
            border-radius: 4px;
            font-size: 13px;
            flex: 1;
            min-width: 200px;
        }}
        .search-box::placeholder {{ color: #666; }}
        .search-box:focus {{ outline: none; border-color: #1565c0; }}
        .stats {{ color: #888; font-size: 13px; margin-bottom: 16px; }}
        .lessons-container {{ display: flex; flex-direction: column; gap: 16px; }}
        .day-type-section {{ border-top: 2px solid #333; padding-top: 16px; margin-top: 16px; }}
        .day-type-section:first-child {{ border-top: none; margin-top: 0; }}
        .day-type-header {{
            font-size: 18px;
            font-weight: bold;
            color: #1e88e5;
            margin-bottom: 12px;
        }}
        .lesson-item {{
            background: #252525;
            border-left: 3px solid #1565c0;
            padding: 12px;
            margin-bottom: 8px;
            border-radius: 2px;
            font-size: 13px;
            line-height: 1.6;
        }}
        .lesson-meta {{
            font-size: 11px;
            color: #888;
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px solid #333;
        }}
        .lesson-link {{
            color: #1e88e5;
            text-decoration: none;
            margin-left: 8px;
        }}
        .lesson-link:hover {{ text-decoration: underline; }}
        a.back-link {{ color: #1e88e5; text-decoration: none; font-size: 13px; }}
        a.back-link:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📚 Tells & Lessons</h1>
            <p class="subtitle">Trading lessons aggregated from {total_lessons} Brooks studies</p>
            <a href="index.html" class="back-link">← Back to studies</a>
        </div>

        <div class="controls">
            <input type="text" id="searchBox" class="search-box" placeholder="Search lessons...">
            <div>
                {day_type_buttons}
            </div>
        </div>

        <div class="stats" id="stats"></div>
        <div class="lessons-container" id="lessonsContainer"></div>
    </div>

    <script>
        const LESSONS_DATA = {lessons_data_json};
        const searchBox = document.getElementById('searchBox');
        const lessonsContainer = document.getElementById('lessonsContainer');
        const stats = document.getElementById('stats');
        let activeFilter = null;

        // Set up filter buttons
        document.querySelectorAll('.day-filter-btn').forEach(btn => {{
            btn.addEventListener('click', (e) => {{
                document.querySelectorAll('.day-filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                activeFilter = activeFilter === btn.dataset.type ? null : btn.dataset.type;
                if (activeFilter) {{
                    btn.classList.add('active');
                }}
                render();
            }});
        }});

        function render() {{
            const q = searchBox.value.toLowerCase();
            let filtered = {{}};

            for (const [dayType, lessons] of Object.entries(LESSONS_DATA)) {{
                if (activeFilter && dayType !== activeFilter) continue;

                const matchingLessons = lessons.filter(l =>
                    l.lesson.toLowerCase().includes(q) ||
                    l.day_type_full.toLowerCase().includes(q)
                );

                if (matchingLessons.length > 0) {{
                    filtered[dayType] = matchingLessons;
                }}
            }}

            // Count total
            let totalCount = 0;
            for (const lessons of Object.values(filtered)) {{
                totalCount += lessons.length;
            }}
            stats.textContent = `Showing ${{totalCount}} lessons`;

            // Render
            lessonsContainer.innerHTML = Object.entries(filtered).map(([dayType, lessons]) => `
                <div class="day-type-section">
                    <div class="day-type-header">${{dayType}} (${{lessons.length}})</div>
                    ${{lessons.map(l => `
                        <div class="lesson-item">
                            ${{l.lesson}}
                            <div class="lesson-meta">
                                ${{l.date}}
                                <a href="cards/${{l.post_id}}.html" class="lesson-link">→ View study</a>
                            </div>
                        </div>
                    `).join('')}}
                </div>
            `).join('');
        }}

        searchBox.addEventListener('input', render);
        render();
    </script>
</body>
</html>"""

    (OUTPUT_DIR / "lessons.html").write_text(html, encoding="utf-8")
    print(f"  Generated lessons.html")
    print(f"\n✅ Digest built: {OUTPUT_DIR}/lessons.html")


if __name__ == "__main__":
    main()
