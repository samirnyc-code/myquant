# New-chat prompt — Data Catalog, MQ-data research, and de-fragmenting the project

> Paste everything below the line into a fresh chat. It assumes you've read
> `docs/living/handoff.md` first (S75E block at the top).

---

Read `docs/living/handoff.md` FIRST (source of truth), then work the plan below. The
theme this session: **stop the fragmentation.** We have a huge amount of data and
several dashboards that don't know about each other. Before building anything new,
we get *visibility* into what we have and a clear architecture. Challenge my
direction, flag overfitting/redundancy, and keep the S73 fill-realism rules (real
fills, chart-audit before reporting, treat PF>3 as a bug).

## The goal (north star — don't lose sight of it)
Systematically **find, validate, and trade real edges** in ES futures (the WFA
engine) and SPX/0DTE options (the live desk), with honest fill realism. Everything
else — ticks, bars, MQ levels, VIX, educational data — is **fuel** for those two
execution arms. Any new tool must serve that, not add surface area.

## Phase 1 (DO FIRST) — build the DATA CATALOG
The #1 ask: **one place to see everything we've collected.** We have ~**108 GB**
across ~13 families and no index. Build a **Data Catalog** = a generated inventory
page + a hand-maintained registry.

**What's on disk today (seed the catalog with this):**
- `data/flatfiles_cache/` 46 G, `flatfiles_cache_cbot/` 15 G, `_nymex/` 14 G,
  `_comex/` 5.6 G — Databento/Massive flat files (raw vendor)
- `data/nt_import/` 15 G — NinjaTrader import data
- `data/optionsdx/` 4.9 G — OptionsDX EOD chains (SPX, NO open-interest — see handoff)
- `data/ticks_continuous/` (ES) 3.4 G, `_NQ/` 3.1 G, `_YM/` 816 M, `_CL/` 744 M,
  `_GC/` 468 M, `_6E/` 189 M, `_6J/` 168 M — continuous tick series
- `data/bars/` 62 M — continuous + per-contract bar parquets (incl. `_continuous_unadj.parquet`)
- `data/wfa_store/` 257 M — walk-forward results
- `data/menthorq/` 152 M — **the MQ mined data** (levels history CSVs, harvest tiles,
  ws.json surfaces, gamma.db backtest stats, `knowledge/` = 392 educational files)
- `data/signals/` — NinjaTrader signal exports (MyReversals, MyMicroChannel txt)
- `data/options_sim/` 2.4 M — the live options desk (trades, gameplans, postmortems, eod_status)
- `data/briefs/`, `data/options_log/`, `data/massive_options/`, `data/cache/`, …
- Educational: `data/menthorq/knowledge/{guides,lessons,wiki}` (392 files) + any `books/`

**Build it as:**
1. `catalog.yaml` (or `data/DATA_CATALOG.md`) — **hand-maintained metadata** per data
   family: description, producing script, update cadence, **what it's useful for**,
   how to access (path + loader snippet), gotchas.
2. A **scanner** (`scripts/data_catalog.py`) that fills the **live metrics**: total
   size, file count, newest-file timestamp (→ "last updated" + staleness), a basic
   **health check** (expected files present? recent? not zero-byte?), row counts for
   key parquets/CSVs.
3. A rendered **page** (reuse the command-center pattern; stdlib http.server, no deps)
   grouped by family, with the metrics above + search/filter. This is "the place."

Design the metrics you'd want on such a tool (freshness, size, health, usefulness,
schema/columns, provenance). Keep it a **scanner + registry**, not a DB.

## Phase 2 — what to actually DO with the MQ data (prove it's useful)
We now have (see handoff): **~5 yr SPX + Mag7 gamma levels**, **~2 yr futures**, the
**signed GEX per level**, **1D expected-move band**, the **backtest-tile stats**
(SPX 6 levels, MQ's own hold-rate claims — accruing daily now), and **5m intraday
candles** on demand (MQ candles endpoint). Run, chart-audited, honest haircuts:
1. **Validate MQ's own backtest claims** — independently recompute real hold/fade
   rates for CR/PS/HVL/0DTE/1D-Max/Min vs the tile's claimed % (98.6% PS, 89% 1D Max…).
   Are they calibrated or marketing? (Confirm intraday source first: MQ 5m candles vs
   our own bars.)
2. **Fade/level-respect edge, conditioned on gamma regime** (pos vs neg γ per day)
   and **wall strength** (signed GEX magnitude). This is the desk's core auto-fire.
3. **Expected-move accuracy** — did the next session stay inside 1D min/max? (the
   87/85/73 claim on 5 yr real data).
4. Does any edge **generalize to Mag7** or is it SPX-only?
Lead with the discounted/live expectation, not the backtest number.

## Phase 3 — architecture (de-fragment; my recommended vision, challenge it)
Don't build five disconnected apps. **Hub-and-spoke:**
- **Spokes (purpose-built, keep):** Options Desk `:8600` (live cockpit) · Levels
  Command Center `:8610` (MQ levels/research) · **Data Catalog** (new, Phase 1) · the
  **ES Streamlit WFA app** (backtest research — decide: keep standalone or link in).
- **Hub (future):** one lightweight home page linking the spokes + a **unified PnL
  rollup** (options desk + any futures sim). Build only when it reduces friction.
- **Future dashboards** the user floated: Mag7, Futures, master-PnL — treat these as
  *views/tabs within the levels command center or the hub*, NOT new servers, unless
  there's a real reason. Consolidate; every new port is maintenance debt.
- Decide the **registry pattern** once and reuse it (catalog, dashboards all read the
  same metadata source of truth).

## Phase 0 — ORATS (only if the user still wants it)
The calculus CHANGED (handoff): we have MQ's ~5 yr labeled levels + backtest stats
**free**. ORATS is now ONLY for (a) pre-2021 depth (→2007) and (b) independent GEX
computation. If the user proceeds: read the ORATS Data-API docs to confirm the
`/datav2/hist/strikes` download mechanics (token, quota, pagination), then use the
ready `scripts/orats_pull.py` — start with **SPX-only overlap-year (~252 req)** to
validate our GEX→levels formula against the MQ answer key BEFORE any big pull. Do NOT
buy it for data we already have.

## Definition of done for this session
- Data Catalog page live, listing all families with size/freshness/health/usefulness
  (educational data included).
- At least one real, chart-audited MQ-data analysis with an honest verdict.
- A written architecture decision (hub-and-spoke or alternative) in the handoff, so
  we stop fragmenting.
