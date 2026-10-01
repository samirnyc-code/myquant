# Brooks Study Library — plan & architecture (Session 57, 2026-07-06)

## What it is
A study tool built from Al Brooks' EOD annotated ES 5-min charts + AI-generated
walkthroughs. Each **study card** = the annotated chart + a written play-by-play
("what happened") + a **Lesson** (what to do / what not to do / early tells).
Goal: train real-time **context identification** (the user's actual weak point),
using Brooks' own labeled charts as the answer key.

## Data assets (all under `data/brooks_charts/`)
- `*.jpg` — 1,500 annotated charts (gitignored, ~250MB, local only; metadata is committed)
- `metadata.csv` — post_id, date (POST date = session+1), title (pre-open headline, NOT day-type), tags (partial Brooks labels), filename, urls
- `posts/{id}.md` — full post body text (pre-open analysis). Backfilled via `scripts/brooks_backfill_text.py`
- `walkthroughs/{id}.md` — AI-generated "what happened" + Lesson (generated S57 overnight, 15 agents)
- **Key facts:** day-type verdict is in the image BANNER (not the title); the post's
  "Summary of today's price action" is always empty (EOD analysis is video/paywalled);
  charts are **Pacific Time** (6:30am–1:15pm PT = 8:30–15:00 CT; CT = PT + 2h).

## Scripts built (S57)
- `scripts/brooks_scraper.py` — WP REST API scraper (existing)
- `scripts/brooks_backfill_text.py` — fetch post body text
- `scripts/brooks_make_card.py` — build a self-contained HTML study card (chart + toggle-able explanation panel)

## Where it should live — DECISION FOR TOMORROW
User wants to possibly **share with Thomas**, so lean toward a **separate app**, not a
tab buried in the quant Streamlit app (Thomas shouldn't need the whole backtest stack).

Options (recommend C or B):
- **A. Tab in existing Streamlit app** — fastest, but couples to the quant app; bad for sharing.
- **B. Standalone Streamlit app** (own entry point, same repo subfolder `brooks_study/`) —
  interactive (search/filter/flashcards), but Thomas needs Python/Streamlit to run it.
- **C. Static generated site** (build step → HTML + JSON index + client-side search) —
  most shareable: zero setup for Thomas, host anywhere or open locally. Images are the
  only weight (host on S3/Cloudflare or bundle). Best for a shareable study tool.
- **Recommendation:** Build **C** (static, shareable) with the card format from
  `brooks_make_card.py` as the per-chart page; add an index page with search + day-type filter.
  Keep **B** in mind if we want live flashcard scoring / progress tracking.

## Features to build
1. **Index/browse** — grid or list of all charts by date + day-type tag; full-text search over walkthrough + tags.
2. **Study card** — chart big; explanation in a toggle panel that PUSHES the chart (reflow), does not cover it. (make_card.py toggles via button / E / Space; UI reflow tweak still pending.)
3. **Flashcard mode** — hide the banner, user calls the day type, reveal + read the Lesson. Directly trains context ID.
4. **Tells & Lessons digest** — aggregate every `**Lesson:**` + early-tell across all walkthroughs into one searchable study list (grouped by day type). User explicitly wants this.

## Open items
- UI: make explanation panel reflow the chart (not overlay). (started, not finished)
- Verify walkthrough quality across day types (spot-check a sample tomorrow morning).
- Confirm scraper caught any posts beyond the 1,500 already in metadata.
- Later: this labeled corpus also feeds the "similar-days retrieval" + "earliest-callable" studies (see retrieve.py prototype in scratchpad) — separate from the study tool but same data.
