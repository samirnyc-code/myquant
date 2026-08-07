# 0DTE SPXW — v1 Bull Put Spread + one-shot data pull spec

**Status:** spec locked, download NOT yet submitted (needs GO — ~$8 spend)
**Owner:** Samir · **Written:** 2026-08-06 (S75T cont.)

## The one-shot download (structure-agnostic)

Download **individual strikes**, not spreads — a spread is two strikes subtracted in
the backtest. This is why one pull serves every future variant.

| Field | Value |
|---|---|
| Dataset | `OPRA.PILLAR` |
| Schema | `cbbo-1m` (1-min consolidated BBO, full RTH session) |
| Root | `SPXW` only (0DTE weeklies/dailies) |
| Symbols | **deterministic OSI**, constructed — NO definitions pull needed |
| Grid | prior_close ± **200 pts**, **5-pt** step, **calls + puts** |
| 0DTE | expiration == session date |
| Window | **2023-03-28 → today** (cbbo-1m availability start) |
| Symbology | `stype_in="raw_symbol"` |
| Cost | **~$8** (get_cost verified, `data/databento/_band_price.json`) |

Symbol format (proven to resolve): `SPXW  {YYMMDD}{C|P}{strike*1000:08d}`
e.g. `SPXW  260805P07780000`. Unlisted grid strikes return 0 bytes → **$0**, so a
too-wide grid is free insurance. The one thing a one-shot pull can't fix is a strike
we didn't buy → go wide (±200).

## v1 strategy — Bull Put credit spread (easiest end-to-end test)

| Leg | Rule |
|---|---|
| Entry time | fixed morning time (backtest param; default open+5min) |
| Short put | at the **lower EM edge** = `prior_close − EM` |
| Long put | wing below short (default 25-wide; **swept** later) |
| Exit | **hold to cash close** (v1); management layered as v2 |
| Score | credit kept, or capped loss if breached |

EM formula (gexlog production, validated 9,201 sessions — handoff:1876):
```
EM = prior_close × (VIX_prior / 100) / 15.874507866387544     # /√252, trading days
```

**EM edge is the anchor of a sweep, not a truth.** Prior: price closes above the lower
EM edge 87.6% of sessions. BUT high hold-rate ≠ profit (ATR-band study: levels held
often, negative expectancy after costs — handoff:1898). v1 tests the edge; the same
download then sweeps short distance {0.75, 1.0, 1.25 EM}, wing width {10,25,50}, and
open- vs close-anchored band.

## Backtest prerequisites (free, not download blockers)
1. **SPX cash OPEN series** — no file on disk has Open (all are H/L/C). Re-pull Yahoo
   `^GSPC` with Open, extend to today. Needed for the open-anchored band comparison.
2. **Extend SPX close + VIX to today** — `spx_daily_full.csv` / `vix_daily_full.csv`
   end 2026-07-17.

## Open decisions (do NOT block the download — grid covers all)
- Entry clock time (backtest param)
- Exit rule beyond hold-to-close (profit target / stop / buy-back-when-breached — the
  8/05 move: closed the tested short intraday, re-sold lower)

## Cost ledger (this account, $125 credit)
| Item | $ |
|---|---|
| definitions full-range (SPXW.OPT) | AVOIDED (was ~$23) |
| one-shot cbbo-1m grid | ~$8 (pending GO) |
| `trades` schema | REJECTED (~$12k on OPRA) |
