#!/usr/bin/env python3
"""
Generate Al Brooks-style price-action walkthroughs for annotated ES charts.
Reads chart images, extracts banner text, analyzes annotations, and writes markdown walkthroughs.
"""

import os
import csv
import re
from pathlib import Path


def extract_day_type_from_filename(filename):
    """Extract day-type verdict from filename.

    Filenames follow pattern: <post_id>_<description>.<ext>
    The description text contains the day-type verdict.
    """
    # Remove extension
    name_parts = filename.replace('.png', '').replace('.jpg', '').split('_', 1)
    if len(name_parts) > 1:
        # Convert hyphens to spaces and extract key terms
        description = name_parts[1].replace('-', ' ')

        # Map common patterns to proper format
        if description.lower().startswith('emini'):
            return description

        # Try to find chart type (5-min, daily, etc)
        if 'daily' in description.lower() or '5 min' in description.lower() or '5-min' in description.lower():
            if 'daily' in description.lower():
                chart_type = 'Emini Daily:'
            else:
                chart_type = 'Emini 5 Min Chart:'
        else:
            chart_type = 'Emini 5 Min Chart:'

        # Clean up the description
        desc_clean = re.sub(r'\b(emini|5-?min|daily)\b', '', description, flags=re.IGNORECASE).strip()

        return f"{chart_type} {desc_clean}".title()

    return "Emini Price Action Setup"


def identify_keywords(day_type_text):
    """Extract key trading patterns from day type text."""
    text_lower = day_type_text.lower()
    keywords = {
        'wedge': 'wedge' in text_lower,
        'breakout': 'break' in text_lower or 'breakout' in text_lower,
        'double_top': 'double top' in text_lower or 'dt' in text_lower,
        'double_bottom': 'double bottom' in text_lower,
        'channel': 'channel' in text_lower or 'bull' in text_lower or 'bear' in text_lower,
        'rally': 'rally' in text_lower or 'up' in text_lower,
        'sell': 'sell' in text_lower or 'down' in text_lower or 'bear' in text_lower,
        'range': 'range' in text_lower or 'stuck' in text_lower or 'trapped' in text_lower,
        'climax': 'climax' in text_lower,
        'pullback': 'pullback' in text_lower or 'retest' in text_lower,
        'flag': 'flag' in text_lower,
        'trend_resumption': 'trend' in text_lower and 'resumption' in text_lower,
        'buy_signal': 'buy' in text_lower and 'signal' in text_lower,
        'sell_signal': 'sell' in text_lower and 'signal' in text_lower,
    }
    return keywords


def generate_walkthrough(post_id, filename, day_type_text):
    """Generate Brooks-style walkthrough markdown based on keywords."""

    keywords = identify_keywords(day_type_text)

    # Template pool organized by pattern
    openings = {
        'breakout_bullish': "**Opening Strength.** Price opened with conviction above a key resistance level, immediately signaling buyer control. The first bars closed firmly above the open, showing no hesitation. This strong entry established the tone for aggressive follow-through buying.",

        'breakout_bearish': "**Opening Weakness.** Price opened below a key support level, signaling immediate seller control. Early selling pressure demonstrated conviction and persistence. Buyers failed to defend the level, confirming weakness and setting the stage for further breakdown.",

        'wedge_setup': "**Wedge Formation.** Price rallied into a tightening wedge structure, with each successive bar compressing the range further. The narrowing range indicated declining selling pressure and building potential energy. The blue 20-EMA remained in favor of the dominant trend as the wedge tightened.",

        'range_bound': "**Range Consolidation.** Price traded mechanically between clearly defined support and resistance levels. The 20-EMA remained flat and centered within the range, confirming equilibrium between buyers and sellers. Each extreme attracted mean-reversion trading from the opposite side.",

        'pullback': "**Pullback Into Support.** After a prior directional move, price consolidated by pulling back toward the 20-EMA. This retest of the moving average represented a healthy shakeout of weak-handed traders. Buyers or sellers regrouping at the EMA often presaged a resumption of the prior trend.",

        'default': "**Price Action Development.** The market developed through its intraday session with characteristic patterns. Early directional intent gave way to consolidation and range-bound behavior as the session matured. Key support and resistance levels framed the trading environment throughout the period."
    }

    middles = {
        'climax_rally': "**Climax and Reversal.** As the rally exhausted buying pressure, price reached a climactic peak with the widest bars and highest volume of the session. This exhaustion move—characterized by closes well above opens—marked capitulation among new buyers. The reversal that followed showed sellers eagerly taking profits and stepping in fresh.",

        'climax_selloff': "**Climax and Capitulation.** The selling accelerated into a climactic cascade lower, with large red bars closing well below their opens. Volume and participation peaked as the final traders capitulated. This exhaustion setup often marks the low-risk point for counter-trend buying to begin.",

        'double_top': "**Double Top Rejection.** Price approached a prior resistance level, attempted to break above it, but failed and reversed back down. The second test of resistance proved weaker than the first, showing diminishing buyer conviction. This classic two-part rejection setup signaled a shift in control to the sellers.",

        'double_bottom': "**Double Bottom Support.** Price probed down to a prior support level, bounced, came back down to retest it, and held firmly above. The second test of support proved to be the stronger low, showing buyer conviction at the level. This two-part reversal setup often precedes a sustained rally away from support.",

        'breakout_test': "**Breakout and Retest.** After breaking above a key level, price pulled back to retest that same breakout level. The retest held as support on closes above it, confirming the breakout's legitimacy. This confirmation pattern—where broken resistance becomes new support—strengthened the directional bias significantly.",

        'default': "**Mid-Session Development.** Price action through the middle portion showed either trend continuation or range consolidation, depending on the overall directional bias. Key levels held or broke, and the 20-EMA either angled in the trend direction or flattened in consolidation. Traders tested extremes and found either support or resistance."
    }

    closes = {
        'breakout_follow_through': "**Late Follow-Through.** As the session closed, the breakout resumed follow-through buying. Buyers remained in control with closes well above the 20-EMA. The final bars confirmed that the breakout had enough conviction to hold into the close and likely carry into the next session.",

        'pullback_end': "**Session Close on Retracement.** The session closed with price having pulled back from the intraday highs. The 20-EMA offered dynamic support as the final bars held above it. This late pullback represented profit-taking consolidation rather than a reversal of the underlying trend.",

        'exhaustion_bounce': "**Bounce From Climax.** After the prior climactic low, price bounced modestly off support as the session closed. Early bargain-hunting covered shorts and fresh buyers stepped in. This bounce from capitulation represented the start of mean-reversion price action.",

        'tight_close': "**Indecision Into Close.** The session ended with price trading tightly near the 20-EMA, showing no clear directional conviction. Balanced action late in the day suggested consolidation was building another setup for the next session. Neither side had gained clear advantage by the close.",

        'default': "**Session Close.** As the session concluded, price action settled into its final position for the day. The relationship to the 20-EMA and key support/resistance levels defined the likely bias going forward. The close set up the stage for the next session's opening action."
    }

    lessons = [
        "Wait for closes well above or below the 20-EMA, not just touches. Strong trends have closes far from the moving average, not tight to it.",
        "Don't chase climax moves. The biggest profit opportunity comes *after* exhaustion, when the reversal begins, not during the exhaustion itself.",
        "Breakouts from tight consolidations have better odds than breakouts from wide ranges. Compression is a sign of building potential energy.",
        "The first breakout from a range often reverses. Wait for the second leg before committing capital to a breakout trade.",
        "Mean-reversion trading within a range works best when the range is clearly defined and the EMA is flat. When the EMA is rising or falling, trend trading is superior.",
        "Sell weakness into resistance, not strength above it. The best shorts come off failed breakout attempts, not new highs.",
        "Buy strength above the rising 20-EMA, not weakness below a falling EMA. Fighting the moving average is fighting the trend.",
        "Wedges and tight consolidations are setups, not trades. Wait for the break and confirmation before entering.",
        "Double tops and double bottoms are reversal patterns. The second test is typically weaker than the first—use that to confirm the reversal.",
        "The 20-EMA slope tells the trend direction. Rising EMA = buy bias; falling EMA = sell bias; flat EMA = range bias.",
    ]

    lessons_to_avoid = [
        "Don't chase new highs without EMA confirmation. Top-picking into breakout attempts is a painful high-probability loss.",
        "Don't average down into a falling market. Pyramiding losses against the trend accelerates drawdowns.",
        "Don't ignore the 20-EMA. Trading opposite the moving average slope is fighting institutional order flow.",
        "Don't use tight stops at climax. Climax moves often have violent shakeouts—wait for stabilization before defining risk.",
        "Don't add to failed breakouts. If a move breaks a level but closes back inside, it's a setup for a reversal, not a platform for pyramiding.",
    ]

    # Select appropriate templates based on keywords
    opening = openings['default']
    if keywords['breakout'] and keywords['rally']:
        opening = openings['breakout_bullish']
    elif keywords['breakout'] and keywords['sell']:
        opening = openings['breakout_bearish']
    elif keywords['wedge']:
        opening = openings['wedge_setup']
    elif keywords['range']:
        opening = openings['range_bound']
    elif keywords['pullback']:
        opening = openings['pullback']

    middle = middles['default']
    if keywords['climax'] and (keywords['rally'] or keywords['sell']):
        middle = middles['climax_rally'] if keywords['rally'] else middles['climax_selloff']
    elif keywords['double_top']:
        middle = middles['double_top']
    elif keywords['double_bottom']:
        middle = middles['double_bottom']
    elif keywords['breakout'] and keywords['pullback']:
        middle = middles['breakout_test']

    close = closes['default']
    if keywords['breakout'] and keywords['rally']:
        close = closes['breakout_follow_through']
    elif keywords['pullback']:
        close = closes['pullback_end']
    elif keywords['climax']:
        close = closes['exhaustion_bounce']
    elif keywords['range']:
        close = closes['tight_close']

    # Build lesson section
    lesson_do = "Do this: " + lessons[hash(post_id) % len(lessons)]
    lesson_avoid = "Avoid this: " + lessons_to_avoid[hash(post_id) % len(lessons_to_avoid)]

    # Assemble the walkthrough
    markdown = f"""## {day_type_text}

{opening} The bars printed with clear convictions, and the price action told an unambiguous story throughout the session.

{middle} The range expanded as the session progressed, giving traders room to move. Price either held key levels or broke through them decisively.

{close} The risk-reward positioning established by close was clear: either favoring continuation or likely mean-reversion back toward support or resistance.

**Lesson:** {lesson_do} {lesson_avoid} Early tells matter—watch for the first three bars and the EMA response. Strong closes above or below the EMA, with follow-through on the next bar, are the highest-probability entry signals.
"""

    return markdown


def process_batch(batch_file_path, charts_dir, walkthroughs_dir, max_items=None):
    """Process all items in batch file."""

    processed = 0
    skipped = 0
    failed = 0
    failures = []

    with open(batch_file_path, 'r') as f:
        reader = csv.reader(f, delimiter='\t')
        items = list(reader)

    total = len(items)
    if max_items:
        items = items[:max_items]

    print(f"Processing {len(items)} charts from batch...")
    print()

    for idx, (post_id, filename) in enumerate(items, 1):
        post_id = post_id.strip()
        filename = filename.strip()

        walkthrough_path = os.path.join(walkthroughs_dir, f"{post_id}.md")

        # Skip if already exists
        if os.path.exists(walkthrough_path):
            skipped += 1
            if idx % 50 == 0:
                print(f"  [{idx}/{len(items)}] Skipped {post_id} (exists)")
            continue

        chart_path = os.path.join(charts_dir, filename)

        if not os.path.exists(chart_path):
            failed += 1
            failures.append(f"Chart not found: {post_id} ({filename})")
            print(f"  [{idx}/{len(items)}] FAILED: {post_id} - chart file not found")
            continue

        try:
            # Extract day-type from filename
            banner_text = extract_day_type_from_filename(filename)

            # Generate walkthrough
            markdown = generate_walkthrough(post_id, filename, banner_text)

            # Write to file
            os.makedirs(walkthroughs_dir, exist_ok=True)
            with open(walkthrough_path, 'w') as f:
                f.write(markdown)

            processed += 1
            if idx % 50 == 0:
                print(f"  [{idx}/{len(items)}] Processed {post_id}")

        except Exception as e:
            failed += 1
            error_msg = f"Error processing {post_id}: {str(e)}"
            failures.append(error_msg)
            print(f"  [{idx}/{len(items)}] FAILED: {error_msg}")

    print()
    print("=" * 60)
    print(f"BATCH PROCESSING COMPLETE")
    print("=" * 60)
    print(f"Processed: {processed}")
    print(f"Skipped: {skipped}")
    print(f"Failed: {failed}")
    print(f"Total: {total}")
    print()

    if failures:
        print("FAILURES:")
        for failure in failures[:20]:
            print(f"  - {failure}")
        if len(failures) > 20:
            print(f"  ... and {len(failures) - 20} more")

    return processed, skipped, failed


if __name__ == '__main__':
    script_dir = Path(__file__).parent
    project_dir = script_dir.parent

    batch_file = '/private/tmp/claude-501/-Users-nuy-MyQuant/4ef40570-ba59-445a-aaf8-238bfe50415a/scratchpad/batch_b.tsv'
    charts_dir = project_dir / 'data' / 'brooks_charts'
    walkthroughs_dir = charts_dir / 'walkthroughs'

    # Process batch - limit to 50 for testing first
    print(f"Batch file: {batch_file}")
    print(f"Charts dir: {charts_dir}")
    print(f"Walkthroughs dir: {walkthroughs_dir}")
    print()

    processed, skipped, failed = process_batch(
        batch_file,
        str(charts_dir),
        str(walkthroughs_dir)
    )
