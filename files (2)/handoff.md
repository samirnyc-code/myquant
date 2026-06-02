# Handoff — Current State
**Status:** Living — update every session  
**Last Updated:** June 2, 2026  
**Current Versions:** SIM_v3.3 / GS_v4.5 / SHEET_v3.3  
**Rule:** Read this file first every session. It is the only source of truth for current state.

---

## What Is Active Right Now

The NT8 simulator and Sheets analysis pipeline are complete and working. All new development is Python-first. No new Sheets or NT8 features are being built unless explicitly scoped.

The Python WFA engine is the primary focus. It has not started. The prerequisite sequence is:

```
Sierra Charts scid data confirmed
        |
        v
Phase A: scid parser + 5M bar builder
        |
        v
Gate 1: Python bars vs SC export (bar_validation.md)
        |
        v
Gate 2: Sierra bars vs NT8/Rithmic bars (1 year on disk)
        |
        v
Phase B: Signal detector — port from MCSimulatorV5_5.cs
        |
        v
Signal validation gate: match C# output on 4-week test period
        |
        v
Phase C onward: simulator, optimizer, WFA engine
```

Nothing in Phase C or beyond starts until all gates above pass.

---

## Current Versions

| Component | Version | Notes |
|-----------|---------|-------|
| NT8 Simulator | SIM_v3.3 | Multi-leg, OnBarClose, PB66 + EB stop |
| Apps Script | GS_v4.5 | ETH bucket, pre-filters, export fixes |
| Google Sheet | SHEET_v3.3 | |

---

## Data Status

| Source | Status | Notes |
|--------|--------|-------|
| Sierra Charts scid (Delani) | Available | Primary research data. scid parser not yet built. |
| NT8/Rithmic tick data | Available | 1 year on disk. Used for Gate 2 bar validation. |
| Massive.io | Not purchased | Optional crosscheck. Deferred until Phase E complete. |

See `data_sources.md` for full detail.

---

## Known Issues (NT8/Sheets — not blocking Python work)

| Issue | File | Fix |
|-------|------|-----|
| `saveRun` TOD labels wrong | GS_v4.5 | Update `['Early','Mid','Late','End']` → `['Early','Lunch','Late','ETH Full']` |
| ETH signals in dataset | SIM_v3.3 | Add RTH trading hours template to sim |

---

## Pending Items — NT8/Sheets (low priority, post-Python)

| Item | Notes |
|------|-------|
| MCChartMarker vertical legend panel | NT8 OnRender panel showing 5 slots with full metrics |
| Multi-year MASTER selector | See MultiYear_MASTER_Architecture.md |
| TOD 13-bucket expansion | 08:30–15:15, 13 × 30-min buckets |
| Per-leg entry/stop offset ticks | Frontrun offset for PB entries |
| Intra-MC PB fills | Phase 2 — remove MCEnded gate |
| Opposing MC cancels PB position | Bear MC cancels open long PB |
| PBLevelExpiryBars | Cancel unfilled legs after N bars post-MC-end |
| RecalcRiskOnStopMove | New stop → new StopDistPts → recalc targets |

---

## Rules for New Chat

1. Never write code until explicitly instructed
2. Always ask: entire file rewrite or old/new snippets?
3. Never invent NT8 APIs — check NT8 docs in project files first
4. Preserve existing architecture unless instructed otherwise
5. No fluff, no affirmations, be direct and technical
6. Read `NT8_NinjaScript_LessonsLearned.md` before writing any NT8/SharpDX code
7. Always search project knowledge and past chats before answering questions about prior decisions
8. Read `docs/README.md` index before adding any new doc — no duplicates, no orphans
