# REGIME-2E · Trade-Review & Annotation Gallery — TOOL SPEC (the final big sweep)

Goal (Samir, 2026-07-25): every 2E trade of the past 5yr, latest params, in the fade-gallery format
(context + tick zoom), auto-verified (green ✓), with a bar-selection + textbox annotation tool whose
notes persist forever and feed the order-flow/feature research. Weeks of work; must be perfect; lossless.

## Why interactive, not static PNGs
Bar-selection + textbox + persistence REQUIRE interactive charts. Static PNGs can't do it. → a **local
web app** (Python server + JS charts), annotations saved to **committed JSON in the repo** (git-versioned,
never lost). Not localStorage (fragile), not a cloud DB (offline, private).

## Architecture
- **Backend:** tiny local server (FastAPI/Flask). Serves per-trade data (bars, ticks, levels, verify flag),
  receives annotation POSTs → writes `docs/living/trade_review/annotations/<trade_id>.json`.
- **Data build (offline, reproducible):** one pass generates `trades_<mode>.json` — for every trade: 5M
  context bars, tick path, entry/stop/exit levels & ticks, EMA20 series, prior-session last bar, gap stats,
  regime shading spans, and the VERIFY result. Modes: engine {old / new-immediate-flip} × book {2EL,2ES,f2EL}.
- **Frontend:** JS charting (candles + overlays). Recommend **lightweight-charts** (TradingView, fast, free,
  candle-native) or a small custom canvas if we need footprint cells later. Plotly = fallback (heavier).
- **Everything self-contained & offline** (data embedded/served locally; no external calls).

## Per-trade VERIFICATION (the green ✓)
Batch audit pass, independent of the sim: replay the tick path and confirm (a) entry limit actually traded
through at the recorded tick, (b) stop/exit actually hit at the recorded tick, (c) EOD flat if no stop, (d)
timing window respected. Output per trade: `verified: true/false (+reason)`. Render **big green ✓** on the
tick-zoom when true; **red ✗ + reason** when not. This IS the per-trade fill-realism audit, visualized.

## Rendering fixes (from Samir's screenshot — no overlap, ever)
- **KILL the entry arrows** — they cover the signal bar. Dotted horizontal level line ONLY.
- **All price labels → a clean side "level gutter"** (fixed right/left margin panel): color-coded rows
  (entry / stop / target / SB-low / prior-close), each with a thin **leader tick** pointing to its price on
  the axis. Numbers live in the gutter, never on the candles → zero overlap.
- If a label must sit inline, **whitespace-aware placement**: detect empty vertical bands (no candles) and
  drop the label there with a gentle leader line — never at the crowded edge.
- **EMA20** overlaid (thin line). **Prior-session last bar** drawn as a ghost candle at the left + a dotted
  prior-close line. **Gap stats** in a small header chip (gap %, ADR10, vs 0.54 threshold, skip/trade).
- Consistent color legend; nothing rendered on top of a candle body except its own wick.

## Annotation tool (the point of the whole thing)
- **Select:** click a bar or drag-select a bar range on either chart.
- **Annotate:** textbox opens → free text + **optional structured TAGS** (dropdown: absorption / EMA-reject /
  big-wick / prior-POC / imbalance / trapped / other). Tags are the bridge to the order-flow research —
  a tag becomes a candidate feature to backtest under the anti-overfit protocol.
- **Persist:** save → `annotations/<trade_id>.json` = list of {chart, bar_range, tags[], text, ts}. Committed.
- **Review/edit/delete** existing annotations; annotations re-render as small markers + hover text.
- **Export view:** "annotated" (with notes) vs "clean" toggle, so a trade can be studied then presented.

## Multi-view per trade (tabs/layers — "label different things")
1. **Context (5M):** regime shading, EMA20, prior bar, gap chip, level gutter, the trade.
2. **Tick zoom:** the actual fill/exit path + green ✓.
3. **(later) Footprint/order-flow layer:** delta/absorption/VP — the order-flow research lives here; annotations
   made here directly seed hypotheses.
4. **(optional) Clean vs annotated** toggle on any view.

## Navigation & scale (hundreds of trades over weeks)
- Index grid (like the current gallery) with filters: book, year, win/loss, verified ✓/✗, has-annotation,
  tag. Keyboard cycling (←/→). Progress tracker ("annotated 84/678"). Resume where you left off.
- **Lossless:** annotations are committed JSON; git history = every note ever. Nothing overwritten silently.

## From annotations → code (the dream, made tractable)
Structured tags make it real: "show all trades tagged `absorption`" → aggregate → test tag-vs-outcome as a
conditioner (train/test, orthogonal, mechanism) → if it survives, code the tag into a computable feature.
Free text stays as context I read when converting a cluster of tags into a testable rule.

## Phased build
- **P0 — one-trade prototype:** ONE trade, both charts, the NEW label/gutter rendering + EMA20 + prior bar +
  gap chip + green ✓. Validate the look BEFORE the big build. (cheap, do first)
- **P1 — static full gallery:** all 678 (three-book) on latest params, verified, new rendering, index+filters.
  No annotation yet — get the corpus + verification right.
- **P2 — annotation layer:** local server + select/tag/textbox + committed JSON + review/edit.
- **P3 — footprint layer:** ties to the order-flow research design.

## Open decisions (need Samir's call before P1)
- Charting lib: lightweight-charts (recommended) vs custom-canvas (needed if footprint cells matter early) vs Plotly.
- Trade set: three-book 678 only, or include dead FADE-L (121) for study? Mode selector scope (engines/books).
- Annotation granularity: single-bar + range enough, or also freehand/price-level notes?
