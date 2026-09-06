# LegLab

Systematic study of intraday **leg structure** in index futures — reproducing and
extending Tim Fairweather's (zentradingtech.com) "leg counting" research, then
turning it into tradeable edges and, eventually, a single shareable HTML artifact
of all findings (to share back with Tim).

## What a "leg" is
Walk each RTH day bar-by-bar from the open; track the running extreme; when price
reverses off that extreme by **≥ 0.15 × ADR** (ADR = mean of prior 8 RTH daily
ranges) it closes the current leg and starts a new one. Reversal measured on
intrabar **high/low**. Count resets each morning.
`legs_closed` = counted at reversal (Tim's "15"); `legs_total = legs_closed + 1`.

## Status — COMPLETE (S111, 2026-09-06)
Verdict: **legs are a volatility instrument, not a directional one.** Direction was
tested five ways — count, size, day-type persistence, structure persistence,
first-BOS — and is null in all of them. The real, repeatable signal is volatility
(clustering 58.5%, morning→afternoon range +0.40, leg-size mean-reversion 86%,
scalp size ~5× since 2010). Findings report built + sent to Tim.

- **Baseline reproduced** — 16y ES 5M RTH (2010–2026, 4,137 days). Mean ≈ 15.5
  legs/day; matches Tim's published per-year chart within **1.2%**.
- **Asymmetry** — down days > up days; +2.89 leg residual survives volatility
  matching (gamma candidate, GEX test deferred/parked).
- **Big-ES-days** — Tim's 85% continuation REFUTED on 16y; ES mean-reverts.
- **Blog digested** — 104 posts catalogued (`research/zentradingtech_digest.md`).
- **Artifact** — `artifact/leglab_for_tim.html` (standalone, lightbox charts) +
  published claude.ai artifact. First person ("I").
- **Full findings log** — `research/leg_count_research_agenda.md`.
- **If ever resumed** — the only live leads are USING the vol signal (ADR/leg-scaled
  targets, next-day expected range for the options desk), not more direction tests.

## Layout
- `scripts/` — analysis (each saves a DATED output; no inline analysis).
- `research/` — agenda (`leg_count_research_agenda.md`) + blog digest
  (`zentradingtech_digest.md`).
- `outputs/` — dated CSVs, charts, and `tim_charts/` (his published charts for
  side-by-side validation).

## Data
Input: `data/bars/_db_es_5m_rth.parquet` (Databento ES 5M RTH OHLCV).

## Scripts
| script | purpose |
|---|---|
| `leg_count_es.py` | core: per-day leg counts + summary |
| `leg_count_compare_tim.py` | side-by-side vs Tim's per-year chart |
| `leg_count_by_year_16y.py` | 16-year by-year chart |
| `leg_count_daytype_diag.py` | why down days show more legs (range/eff by quintile) |
| `leg_count_vol_control.py` | down−up residual controlling for volatility |

## The 13-idea agenda
See `research/leg_count_research_agenda.md`. Headliners: early-leg day classifier
(#1), leg-count filter for the 0DTE options desk (#2), solve Tim's day-type
taxonomy via RLS + swing-breaks (#3), leg geometry / BOS-vs-inside (#4–6),
combine with our 2E book / scalper / gamma (#7–10), cross with his other setups
(#11–13).
