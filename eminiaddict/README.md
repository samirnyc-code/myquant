# EminiAddict — reverse-engineering David Halsey's Measured-Move method

New project (started S91, 2026-07-29). Goal: learn, codify, and test the
**Measured Move (MM)** methodology from David Halsey's *Trading the Measured
Move* (Wiley, 2014) and the eminiaddict.com member content.

## Source material
- **Book** (`data/halsey_measured_move.pdf`, gitignored — copyrighted): 226 pp.
  Full text extracted to `data/book_text.txt` (gitignored). Key chapters: 2 (Fibs),
  6 (three setups), 8 (entries), 12 (gap fills), 13 (mgmt), 16 (trading plan).
- **Site** (eminiaddict.com): $29.99/mo, WishList paywall. Daily analysis + videos
  are member-only (verified not scrapable logged-out). Pending subscription →
  cookie/Playwright scrape + Whisper transcript nugget-mining.

## The method (verified from the book)
Draw a Fib on a swing leg. For an UP leg from swing low L to high H (range R):
- **100% = L** (start) · **61.8% = L+0.382R = FAILURE** (breach kills the MM)
- **50% = L+0.500R = HWB** (half-way-back = entry/continuation zone)
- **0% = H** (end) · **123.6% = H+0.236R = TARGET** (also seeds the next swing)

Down leg is the mirror. Swing points after the seed are mechanical (prior MM's
retracement high = new peak; prior MM's 123.6% target = new trough); confirmation
= the 61.8% break of the opposing MM. **Only discretionary step = the seed swing.**

## Scripts
- `scripts/render_pages.py N ...` — render book pages to `figures/page_NNN.png`.
- `scripts/draw_mm_fib.py [last|dominant]` — ZigZag seed-swing detector on ES daily
  (`data/bars/_db_es_daily_24h.parquet`) → draws the MM Fib with all Halsey levels.
  Anchors snap to true extreme wicks. Output: `figures/es_daily_mm_fib_{mode}.png`.

## Next
- Codify Ch 6 setups (Traditional 50% MM, Extension 50% MM, 61.8% Failure) into a
  machine-readable `{trigger, entry, stop, target, filters, session}` rulebook.
- Wire the seed-swing detector param into WFA for validation.
