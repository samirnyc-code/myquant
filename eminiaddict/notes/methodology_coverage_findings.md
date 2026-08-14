# Methodology Coverage — findings (verified)

**Question (user).** He seems to teach things in the live room that aren't in the
book or webinars, and the webinars are scattered. Verify what the components of
his method actually are, and which are covered poorly.

**Method.** A curated lexicon of **58 method components** (9 categories) counted
across 4 corpora, normalized per 10,000 words so different-sized corpora compare
fairly. Script: `scripts/methodology_coverage.py` → dated CSV in `data/analysis/`.
- BOOK = `book_text.txt` (64k words)
- WEBINARS = 11 method webinars + 8 getting-started lessons (131k words)
- ROOM = 5 daily-analysis video transcripts (21k words) — **proxy for the trade room**
- DIAGRAMS = the 16 teaching-diagram filenames

**Caveats (honest).** (1) The ROOM corpus is only **5 days** — room signals are
suggestive, not conclusive; transcribe more daily videos (`ea_transcribe.py
--daily MMDDYY`; S3 keys verified live) to harden it. (2) Keyword counting has
false positives; the headline findings below were **spot-checked by eye** and
confirmed.

---

## Headline findings (each verified against the raw text)

### 1. The seed-selection PROCEDURE is absent EVERYWHERE — the #1 gap
`how to pick/choose/draw the anchor/swing` → **0 hits in book, 0 in webinars, 0 in
the room.** Yet "anchor / starting point / seed" is *mentioned* constantly
(well-covered). He tells you the seed exists and matters ("crucial," Ch 2) and
then **never teaches how to choose it, in any channel.** This is the single
biggest hole and it's not a sampling artifact — it's a true void, matching Ch 2's
explicit deferral. (This is exactly the gap our `seed_swing_methodology.md` fills.)

### 2. VIX is a ROOM/daily concept, not in the book
VIX per-10k: **BOOK 0.0 · WEB 0.0 · ROOM 31.7.** Verified: in the daily videos he
runs a full VIX measured-move read ("the VIX is long inside its lows-to-highs,"
"VIX bullish above line in the sand," "VIX uptrend in an indices downtrend"). The
2014 book never mentions VIX. His live internals read is richer than either
published channel.

### 3. The live "leading-indicators" routine is ROOM-heavy
Dollar/DXY per-10k: **BOOK 3.6 · WEB 3.0 · ROOM 84.0** (verified real DXY/
correlation analysis, not the word "dollar"). Each morning in the room he walks
**dollar + financials/BANK + VIX + indices** as interlocking measured moves — a
multi-instrument confluence routine. The book has the *pieces* (Ch 10 Bank/breadth/
tick) but not this daily cross-market walk-through; the frames we captured (DXY,
BANK, NQ, BTC, GC, CL, 6E, SI, 6J per day) corroborate it.

### 4. Psychology + the trading PLAN are BOOK-ONLY (missing from the videos)
Per-10k, BOOK vs WEB vs ROOM:
- Casino vs gambler 3.6 / 0.0 / 0.0
- Proactive vs reactive 2.8 / 0.1 / 0.0
- Emotional capital 8.2 / 0.5 / 0.0
- Trading journal 4.0 / 0.1 / 0.0
- Four legs / trading plan 6.7 / 0.3 / 0.0
- Four phases (Ch 15 model) 1.7 / 0.3 / 0.0
→ A learner who only watches **videos never gets the mindset or the plan
framework.** It lives solely in the book. (Inverse of the usual complaint.)

### 5. Post-book additions (in webinars/room, thin/absent in the 2014 book)
- History/replay "Groundhog Day" (webinars 16/25) — BOOK 0.2
- Nested/fractal-timeframe framing — BOOK 0.5
- The extension trigger "blows past target" — BOOK 0.3 (and never given a
  numeric threshold anywhere — see #6)
- The packaged VIX/Indices/TICK/BANK/USD **signal-alignment checklist** — a
  site-diagram construct; the phrase barely appears in prose.

### 6. Named-but-never-defined (thin/undefined in ALL channels)
Referenced as if known, never given a crisp rule or threshold:
- **"Blows past target"** — the traditional→extension trigger; no magnitude given.
- **Tick hook** — named (Ch 10) but barely explained (0.5–1.9/10k).
- **Failure significance by context** — "6th-MM failure = trend over" is asserted,
  never operationalized.
- **Which touch counts** (1st/2nd/3rd) — treated case-by-case, no rule.
- **Zone tolerance** — "zones not lines," but how wide is never quantified.

---

## Coverage summary (58 components)

| Class | n | Meaning |
|-------|---|---------|
| WELL COVERED | 36 | the mechanical core (geometry, setups, entries, gaps, tick, sessions) — taught in book AND video |
| BOOK-ONLY | 6 | psychology + plan + four-phases + failure-significance — **missing from videos** |
| PARTIAL | 6 | confirmation-of-trend, half-size days, tick hook, emotional capital, 90/10, expanded extension |
| POST-BOOK | 4 | VIX, Groundhog/replay, nested/fractal, blows-past — **not in the 2014 book** |
| ROOM-LEANING | 1 | USD/DXY leading-indicator routine |
| ABSENT everywhere | 4 | **seed-selection rule**, signal-checklist phrase, which-touch, 10k-hours |

## Direct answer

- **Yes, the room covers things the book/webinars don't** — chiefly the live VIX
  read and the daily multi-instrument leading-indicator walk (dollar/BANK/VIX/
  indices as measured moves). Verified in the 5 daily transcripts.
- **Yes, several concepts are covered poorly** — in three distinct ways:
  1. **Absent everywhere:** how to pick the seed (the one discretionary step).
  2. **Named but undefined:** blows-past threshold, tick hook, failure
     significance, which-touch, zone width.
  3. **Siloed by channel:** psychology + trading-plan are book-only; VIX + the
     leading-indicator routine are room-only; history/replay + nested framing are
     webinar-only. Nobody meets all of it in one place — which is exactly why the
     material feels scattered.

## To strengthen this

The ROOM sample is 5 days. Transcribe a larger batch of daily videos (the S3 keys
are live) and re-run `methodology_coverage.py` — the room-only signals (VIX,
dollar, and anything else that surfaces) will sharpen, and new room-only concepts
may appear that 5 days can't reveal. This is the cheapest high-value next step if
we want to map the room fully.
