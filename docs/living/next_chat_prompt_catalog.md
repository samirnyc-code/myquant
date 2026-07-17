# New-chat prompt — Phase 1: DATA CATALOG (build this only)

> Paste everything below the line into a fresh chat.

---

Read `docs/living/handoff.md` FIRST (source of truth). This session builds **one thing:
the Data Catalog** — a single place to see everything we've collected for this project.
Don't scope-creep into research or other dashboards. Challenge my design if a simpler
one is better.

## Why
We have ~**108 GB** of data across ~13 families (ticks, continuous contracts, bars,
vendor flat files, OptionsDX, MQ mined levels + backtest db + educational text, signals,
options-desk state, WFA results, VIX/IB) and **no index**. We keep losing track of what
exists, where it is, how fresh it is, and what it's for.

## Hard design constraint (get this right first)
`data/` is 108 GB / 12k+ parquet files — **a blind recursive walk on page load will
hang** (a full `find` already timed out at 2 min). So build it as **three parts**:
1. **Registry** — `catalog.yaml` (hand-maintained), one entry per data family:
   `key, title, paths/globs, category, description, produced_by (script), update_cadence,
   expected_freshness_days, useful_for, access (python loader snippet), gotchas`.
2. **Scanner** — `scripts/data_catalog.py scan`: for **each registered path only** (never
   a blind walk of all of data/), compute size, file_count, newest-file mtime, and a
   health verdict; write `data/_catalog/manifest.json` (cached). Row/schema counts ONLY
   for small flagged key datasets. Run on demand + make it schedulable (nightly task).
3. **Page/server** — `scripts/data_catalog.py serve` (stdlib http.server, reuse the
   `mq_levels_command_center.py` pattern, no deps): reads registry + cached manifest and
   renders fast. A "Rescan" button triggers the scanner in the background (like the
   command center's Update-now). Never scan inside the request handler synchronously.

## The page
Group families by **category** (Raw vendor · Ticks · Bars/continuous · MQ · Options desk
· Research/WFA · Educational · Misc). Each family = a card showing:
- **size** + file count + % of total footprint
- **last updated** + a **freshness dot** (green/amber/red vs `expected_freshness_days`)
- **health** (path exists? newest file within cadence? no zero-byte? optional schema check)
- **what it's useful for** (from registry) · **how to access** (loader snippet) ·
  **produced by** (script) · gotchas
Header: total footprint, family count, worst-staleness, last scan time.

## Seed the registry with what's on disk now
- `data/flatfiles_cache/` 46G, `_cbot/` 15G, `_nymex/` 14G, `_comex/` 5.6G — Databento/
  Massive vendor flat files (raw)
- `data/nt_import/` 15G — NinjaTrader import data
- `data/optionsdx/` 4.9G — OptionsDX SPX EOD chains (⚠️ NO open-interest — see handoff)
- `data/ticks_continuous/` (ES) 3.4G, `_NQ/` 3.1G, `_YM/` 816M, `_CL/` 744M, `_GC/` 468M,
  `_6E/` 189M, `_6J/` 168M — continuous tick series
- `data/bars/` 62M — continuous + per-contract bar parquets (incl `_continuous_unadj.parquet`)
- `data/wfa_store/` 257M — walk-forward results
- `data/menthorq/` 152M — MQ levels history CSVs, harvest tiles/ws.json, `gamma.db`
  (backtest stats), `knowledge/` (392 educational files: guides/lessons/wiki)
- `data/signals/` — NinjaTrader signal exports (MyReversals, MyMicroChannel)
- `data/options_sim/` 2.4M — live options desk (trades, gameplans, postmortems, eod_status)
- `data/briefs/`, `data/options_log/`, `data/massive_options/`, `data/cache/`
- Also register: **educational** = `data/menthorq/knowledge/**` + any `books/`; and VIX/IB
  sources (find where they land — grep the feed/scanner scripts).
Fill `produced_by` / `update_cadence` by grepping which scripts write each path (many map
to the scheduled MyQuant tasks). Where unknown, mark TODO — don't guess.

**Design the registry WITH the user (don't autofill silently).** The scanner fills the
mechanical fields (size/freshness/health). But two fields need the user's knowledge, so
**ask** rather than guess: `useful_for` and `access`/gotchas — the user knows things the
filesystem doesn't (e.g. OptionsDX has no OI; which continuous series are backadjusted;
which signals are stale/superseded; which ticks are canonical). Draft your best guess per
family, then confirm the useful-for + gotchas with the user in one pass.

## Build order (prove the risky part FIRST)
Do NOT build the pretty page first. Sequence:
1. Write `catalog.yaml` for a few families + the `scan` mode, and **prove the scan
   completes in reasonable time and writes `manifest.json`** across the big dirs (46G
   flatfiles, 12k+ parquet) — per-family `os.scandir`, cached, no blind walk. This is the
   only real risk; verify it before anything visual.
2. Then flesh out the full registry (with the user, per above).
3. Then build the `serve` page + Rescan button on top of the cached manifest.

## Definition of done
- `scripts/data_catalog.py` (scan + serve), `catalog.yaml`, cached manifest.
- Catalog page live on its own port, every family listed with size/freshness/health/
  useful-for/access, educational data included, Rescan button working.
- A one-line entry in the handoff + (optional) a nightly scan task.
- Commit + push (ask first per the standing rule).

## Explicitly OUT of scope this session
No research/analysis, no new asset dashboards, no ORATS. Catalog only.
