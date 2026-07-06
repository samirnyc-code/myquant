#!/usr/bin/env python3
"""
Brooks Study Library — Flashcard mode.
Generate a flashcard study page with hidden day-type banners for training context ID.

Usage:
    python scripts/brooks_build_flashcards.py

Generates:
    site/flashcards.html — interactive flashcard study tool
    site/data/flashcards.json — all card data for shuffling/scoring
"""

import json
import csv
import base64
from pathlib import Path

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
    """Load walkthrough and extract day type + lesson."""
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


def load_chart_image_base64(post_id, filename):
    """Load chart image and encode as base64."""
    path = DATA_DIR / filename
    if not path.exists():
        return None
    try:
        with path.open("rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return None


def extract_day_type_short(day_type_full):
    """Extract short day-type tag for answer options."""
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


def main():
    print("Building flashcard study tool…")

    metadata = load_metadata()
    flashcards = []

    for post_id in metadata:
        day_type, lesson = load_walkthrough(post_id)
        if not day_type:
            continue

        meta = metadata[post_id]
        chart_base64 = load_chart_image_base64(post_id, meta["filename"])

        if not chart_base64:
            continue

        flashcards.append({
            "post_id": post_id,
            "date": meta["date"],
            "day_type_full": day_type,
            "day_type_short": extract_day_type_short(day_type),
            "lesson": lesson,
            "chart_base64": chart_base64,
            "title": meta["title"][:60],
        })

    print(f"  Loaded {len(flashcards)} flashcards with embedded images")

    # Save flashcards JSON (split into chunks for reasonable file size)
    # Generate summary JSON without images for index
    flashcards_summary = [
        {k: v for k, v in fc.items() if k != "chart_base64"}
        for fc in flashcards
    ]
    (OUTPUT_DIR / "data" / "flashcards_index.json").write_text(json.dumps(flashcards_summary), encoding="utf-8")

    # Save full flashcards (will be large)
    (OUTPUT_DIR / "data" / "flashcards_full.json").write_text(json.dumps(flashcards), encoding="utf-8")
    print(f"  Generated flashcards JSON ({len(flashcards)} cards)")

    # Get all unique day types for answer shuffle
    day_types = sorted(set(fc["day_type_short"] for fc in flashcards))

    # Generate HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Flashcards — Brooks Study Library</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #1a1a1a; color: #e0e0e0; }}
        .container {{ max-width: 100vw; height: 100vh; display: flex; flex-direction: column; }}
        .header {{ background: #222; padding: 12px 16px; border-bottom: 1px solid #333; display: flex; justify-content: space-between; align-items: center; }}
        .header-left {{ font-size: 14px; }}
        .header-stats {{ font-size: 12px; color: #888; }}
        .main {{ display: flex; flex: 1; overflow: hidden; flex-direction: column; align-items: center; justify-content: center; padding: 20px; }}
        .chart-area {{ flex: 1; display: flex; align-items: center; justify-content: center; margin-bottom: 20px; max-width: 100%; }}
        .chart-img {{ max-width: 90%; max-height: 70vh; object-fit: contain; }}
        .controls {{ display: flex; flex-direction: column; gap: 12px; align-items: center; width: 100%; max-width: 600px; }}
        .button-row {{ display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; }}
        .answer-btn {{
            padding: 10px 16px;
            background: #252525;
            border: 1px solid #333;
            color: #e0e0e0;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
            transition: all 0.2s;
            min-width: 120px;
        }}
        .answer-btn:hover {{ border-color: #1565c0; }}
        .answer-btn.correct {{ background: #2e7d32; border-color: #4caf50; }}
        .answer-btn.incorrect {{ background: #c62828; border-color: #f44336; }}
        .answer-btn.selected:not(.correct):not(.incorrect) {{ background: #1565c0; border-color: #1565c0; }}
        .reveal-btn {{
            padding: 10px 16px;
            background: #1565c0;
            border: 1px solid #1565c0;
            color: white;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
        }}
        .reveal-btn:hover {{ background: #1e88e5; }}
        .reveal-btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        .banner {{ background: #4caf50; color: white; padding: 12px; border-radius: 4px; font-size: 14px; margin: 12px 0; text-align: center; }}
        .banner.hidden {{ display: none; }}
        .lesson {{ background: #252525; border-left: 3px solid #1565c0; padding: 12px; border-radius: 2px; font-size: 12px; line-height: 1.6; margin: 12px 0; max-width: 600px; }}
        .lesson.hidden {{ display: none; }}
        .nav-controls {{ display: flex; gap: 8px; margin-top: 12px; }}
        .nav-btn {{
            padding: 8px 16px;
            background: #252525;
            border: 1px solid #333;
            color: #e0e0e0;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
        }}
        .nav-btn:hover {{ border-color: #1565c0; }}
        a {{ color: #1e88e5; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="header-left">
                📇 Flashcards
                <a href="index.html" style="margin-left: 16px;">← Back to studies</a>
            </div>
            <div class="header-stats">
                <span id="cardCount">Card 1 / {len(flashcards)}</span>
                <span style="margin-left: 16px;" id="scoreDisplay">Correct: 0 / 0</span>
            </div>
        </div>

        <div class="main">
            <div class="chart-area">
                <img id="chartImg" class="chart-img" src="" alt="Study chart">
            </div>

            <div class="controls">
                <div class="banner hidden" id="banner"></div>
                <div class="lesson hidden" id="lesson"></div>

                <div class="button-row" id="answerButtons"></div>

                <button class="reveal-btn" id="revealBtn">Reveal Answer</button>

                <div class="nav-controls">
                    <button class="nav-btn" id="prevBtn">← Previous</button>
                    <button class="nav-btn" id="nextBtn">Next →</button>
                    <button class="nav-btn" id="randomBtn">🔀 Random</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        const DAY_TYPES = {json.dumps(day_types)};
        let flashcards = [];
        let currentIndex = 0;
        let correct = 0;
        let total = 0;
        let revealed = false;
        let userAnswer = null;

        async function loadFlashcards() {{
            const res = await fetch('data/flashcards_full.json');
            flashcards = await res.json();
            render();
        }}

        function shuffleArray(arr) {{
            const copy = [...arr];
            for (let i = copy.length - 1; i > 0; i--) {{
                const j = Math.floor(Math.random() * (i + 1));
                [copy[i], copy[j]] = [copy[j], copy[i]];
            }}
            return copy;
        }}

        function getAnswerOptions(correctAnswer) {{
            const options = [correctAnswer];
            const otherTypes = DAY_TYPES.filter(t => t !== correctAnswer);
            const shuffledOthers = shuffleArray(otherTypes).slice(0, 3);
            return shuffleArray([...options, ...shuffledOthers]);
        }}

        function render() {{
            if (flashcards.length === 0) return;

            const card = flashcards[currentIndex];
            revealed = false;
            userAnswer = null;

            // Chart
            document.getElementById('chartImg').src = `data:image/jpeg;base64,${{card.chart_base64}}`;

            // Banner & lesson
            const banner = document.getElementById('banner');
            const lesson = document.getElementById('lesson');
            banner.textContent = card.day_type_full;
            banner.classList.add('hidden');
            lesson.innerHTML = `<strong>Lesson:</strong> ${{card.lesson}}`;
            lesson.classList.add('hidden');

            // Answer buttons
            const answerOptions = getAnswerOptions(card.day_type_short);
            document.getElementById('answerButtons').innerHTML = answerOptions
                .map(opt => `<button class="answer-btn" data-answer="${{opt}}">${{opt}}</button>`)
                .join('');

            document.querySelectorAll('[data-answer]').forEach(btn => {{
                btn.addEventListener('click', handleAnswer);
            }});

            // Reveal button
            const revealBtn = document.getElementById('revealBtn');
            revealBtn.disabled = false;
            revealBtn.textContent = 'Reveal Answer';

            // Stats
            document.getElementById('cardCount').textContent = `Card ${{currentIndex + 1}} / ${{flashcards.length}}`;
            document.getElementById('scoreDisplay').textContent = `Correct: ${{correct}} / ${{total}}`;
        }}

        function handleAnswer(e) {{
            if (revealed) return;
            const card = flashcards[currentIndex];
            const selected = e.target.dataset.answer;
            userAnswer = selected;
            const correct_ans = card.day_type_short;

            total++;
            if (selected === correct_ans) {{
                correct++;
                e.target.classList.add('correct');
            }} else {{
                e.target.classList.add('incorrect');
                document.querySelectorAll(`[data-answer="${{correct_ans}}"]`).forEach(b => b.classList.add('correct'));
            }}

            document.getElementById('scoreDisplay').textContent = `Correct: ${{correct}} / ${{total}}`;
            document.getElementById('revealBtn').textContent = 'Revealing...';
            setTimeout(() => revealBanner(), 500);
        }}

        function revealBanner() {{
            if (revealed) return;
            revealed = true;
            document.getElementById('banner').classList.remove('hidden');
            document.getElementById('lesson').classList.remove('hidden');
            document.getElementById('revealBtn').textContent = 'Revealed ✓';
            document.getElementById('revealBtn').disabled = true;
            document.querySelectorAll('[data-answer]').forEach(b => b.disabled = true);
        }}

        document.getElementById('revealBtn').addEventListener('click', revealBanner);
        document.getElementById('nextBtn').addEventListener('click', () => {{
            currentIndex = (currentIndex + 1) % flashcards.length;
            render();
        }});
        document.getElementById('prevBtn').addEventListener('click', () => {{
            currentIndex = (currentIndex - 1 + flashcards.length) % flashcards.length;
            render();
        }});
        document.getElementById('randomBtn').addEventListener('click', () => {{
            currentIndex = Math.floor(Math.random() * flashcards.length);
            render();
        }});

        // Keyboard: arrow keys for nav
        document.addEventListener('keydown', (e) => {{
            if (e.key === 'ArrowRight') document.getElementById('nextBtn').click();
            if (e.key === 'ArrowLeft') document.getElementById('prevBtn').click();
            if (e.key === ' ' && e.target === document.body) {{
                e.preventDefault();
                document.getElementById('revealBtn').click();
            }}
        }});

        loadFlashcards();
    </script>
</body>
</html>"""

    (OUTPUT_DIR / "flashcards.html").write_text(html, encoding="utf-8")
    print(f"  Generated flashcards.html")
    print(f"\n✅ Flashcard study tool built: {OUTPUT_DIR}/flashcards.html")


if __name__ == "__main__":
    main()
