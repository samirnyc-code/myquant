# 0DTE SPXW premium-selling — autonomous research log

## ★ CONSOLIDATED STATE (after Cycles 1-4)

**Candidate book:** open-anchored IC (or BPS), skip up-gaps > +0.2%, **hold to expiry**,
1-EM short / 25-wide. No intraday stop.

**What's real:**
- VRP harvest — market moves ~0.5× implied EM every year (stable, the durable edge).
- Execution-robust: positive even at worst-case cross fills (break-even fill fraction > 1).
- Passed true OOS (threshold locked on 2023-24 → 2025-26 held).
- Defined-risk: single-day loss capped ~−$2,300/contract (no naked blowup).

**What's fragile / unproven:**
- Recent $ is VIX-tailwind-inflated (credit $133→$180 as VIX 15→19); base strategy is flat.
- Gap filter is in-sample (mitigated by OOS + monotonic sweep + economic logic, not eliminated).
- **Un-hedged crash tail** — crashes are down-gaps the filter does NOT skip; BPS's big losses
  are 100% down days. A crash streak ≈ −$2.3k/contract/day.
- IC & BPS are 0.81 correlated — no diversification from running both.
- **Zero crisis data** — 0DTE has no pre-2023 history; never stress-tested in a real bear.
- Intraday STOPS do NOT help (mid-fill mirage; fill worst exactly when they fire).

**Realistic expectation:** ~20% (worst-case fills) to ~33% (mid, recent regime) per year on
~$20k/contract, LUMPY (29% red months, −$3k worst month), with a fat un-hedged left tail.
NOT a $500/mo annuity. Best next step to change the risk profile: a cheap far-OTM tail hedge.

**Cycle 5 result — static tail hedge FAILS.** A continuous long put at 2-3× EM below open
drags ~$75/day (~$40k over 522 days), pays only 2-4× in a no-crisis sample: Sharpe 1.47→0.2,
worst day WORSE. Crash tail is real but not cheaply hedgeable with a static long put; a real
defense must be regime-conditional (hedge only on stress signals) or via sizing-down.

**Queued (Cycle 6+):** regime-conditional hedge/sizing (VIX or term-structure trigger);
entry-time sweep; day-of-week (M/W/F vs Tu/Th 0DTE); put-spread hedge (cheaper than long put).

---

Running log of hypotheses tested, results, and next ideas. Newest cycle at top.
Data: OPRA.PILLAR cbbo-1m, 841 sessions 2023-03-28 → 2026-08-04, ±200pt 0DTE grid.
Engine: `options_0dte_backtest.py` (hold-to-expiry) + `options_0dte_exits.py` (intraday).
All P&L per 1 contract, mid + cross fills, $1.30/leg commission.

---

## Established before cycles (Cycle 0)

- **Anchor:** open-anchored EM band beats close-anchored on every directional structure
  (+$6–31/trade). The gap carries information. Open anchor used everywhere below.
- **Structures:** open IC and BPS are the survivors; BCS is a 2024 artifact; iron fly loses.
- **Gap filter (skip up>+0.2%):** lifts IC $13→$43/trade, Sharpe 0.41→1.47, positive every
  year AND at cross fills. Passes true OOS (IC OOS Sharpe 2.83). **BUT** the acceleration is
  a *filter* property, not the base strategy (unfiltered IC/yr: 6.9/16.7/9.7/21.1 — flat).
- **Driver diagnosis:** recent P&L bump is mostly a VIX regime tailwind (VIX 15→19 → credit
  $133→$180) + filter overfit to recent up-gap tails. Durable piece = VRP (realized ≈ 0.5×
  implied EM, stable every year, modest). **No pre-2023 history; never crisis-tested.**
- **Sizing:** ~$20k/contract (maxDD $8.7k + margin $2.3k). Mid ~33%/yr, cross ~20%/yr,
  ~29% of months red, worst month −$3.2k. Minis (XSP) DON'T work — fixed fee eats 1/10 premium.
- **Baseline exits:** hold-to-expiry only, NO intraday management modeled.

### Standing skepticism (keep_in_check)
1. Filter is in-sample; base strategy is modest. 2. VIX tailwind inflates recent $.
3. Zero crisis data. 4. Treat any Sharpe > ~1.5 as regime-flattered until proven otherwise.

---

## Cycle 1 (intraday exits) — `options_0dte_exits.py`

Swept profit targets {25,33,50,66,75,90%} × stops {1.5,2,3× credit} × time-stop {none,15:45}
on IC & BPS (open anchor, mid fills). Baseline = hold-to-expiry.

**Findings:**
- **STOPS >> profit targets.** BPS + stop@2× credit (no PT): Sharpe **0.25→1.25**, maxDD
  **$13,237→$1,713 (−87%)**, mean $6.9→$10.1. The hard stop caps the fat left tail.
- **Profit targets alone don't help.** Tight PTs (25/33%) go NEGATIVE (commission churn +
  capped winners). Loose PTs (75/90%) ≈ baseline. Premium already mostly decays by expiry.
- **IC benefits less** — best Sharpe 0.51 (PT90+stop3+15:45). Two-sided = already balanced;
  the stop helps DD ($12.9k→$9.9k) but not mean.
- Win rate falls with stops (BPS 95.6%→61.8%) — you stop out more, but avoid the disasters.

**Caveats to verify (Cycle 1 analysis):**
- Mid fills OVERSTATE stops — a stop fires on a fast adverse move, exactly when the spread
  is widest; real fill is worse than mid. Need cross-fill check.
- Path-dependency / whipsaw: stop out then market reverts. Year-by-year needed.
- Per-trade P&L for all configs saved to `exit_trades.parquet` for fast slicing.

---

## Cycle 2 (cross-fill reality) — the decisive execution check

Added worst-case CROSS fills + BCS to the exit engine. Verdict:

- **At worst-case cross fills, unfiltered/stop configs are NEGATIVE.** BPS stop@2× mid
  Sharpe 1.25 → CROSS Sharpe −0.24. The edge (~$6-13/trade) is smaller than the spread.
- **The stop's Sharpe 1.25 was a MID-FILL MIRAGE.** Stops fire on fast moves when the
  spread is WIDEST, so realistic exit fills ≈ worst-case. Hold-to-expiry crosses the
  spread only ONCE (entry) and settles at exact intrinsic → far more slippage-robust.
- **Break-even fill fraction (0=mid, 1=worst cross; >1 = profitable even at worst-case):**
  - IC skip-up-gaps hold-to-exp: **f=2.59** (cross +$26.3/trade)
  - BPS skip-up-gaps hold-to-exp: **f=4.00** (cross +$25.1/trade)
  - IC all-days hold-to-exp: f=0.83 · BPS stop@2×+gap: f=1.23

**CONCLUSION (inverts Cycle 1): do NOT use intraday stops.** The gap filter alone removes
the up-gap tail, and hold-to-expiry is inherently slippage-robust. The candidate book is:
**open-anchored IC (and/or BPS), skip up-gaps > +0.2%, hold to expiry, no stop** — the only
thing tested that is positive even at worst-case fills, positive every year, and passed OOS.

Remaining doubts unchanged: gap filter in-sample (but OOS-validated + economically motivated),
VIX tailwind on recent $, zero crisis data.

### Cycle 3 ideas (queued)
1. Structural sweep: short-strike distance {0.75/1.0/1.25 EM} × width {10/25/50} — is fixed
   25pt / 1-EM optimal? (hold-to-exp, gap-filtered, mid+cross) — FAST (entry+settle only)
2. IC+BPS portfolio combine (correlation, combined equity/DD)
3. Entry-time sweep (09:30 / 10:00 / 11:00) + day-of-week (0DTE M/W/F vs Tu/Th)
4. Size-by-VIX (credit scales with VIX; does vol-targeting size help?)
5. Crisis stress: worst in-sample days + a synthetic gap-down shock

---

## Cycle 6 (gap as a DIRECTIONAL signal) — `options_0dte_gap_directional.py`

Tested on FULL SPX cash 1990-2026 (9,214 days). Gap is a MOMENTUM signal (corr +0.16,
continuation), NOT mean-reversion (that hypothesis lost, Sharpe −4). "Go with the gap,
exit at close" (|gap|>0.15%, net 0.02% cost):
- 1990-2018 Sharpe **5.94** (+132%/yr) · 2019-2022 Sharpe **3.22** · **2023-2026 Sharpe −0.06 (DEAD)**
- Classic gap-and-go, arbitraged away ~2023 (0DTE + systematic overnight flow).

**Regime insight (the real payoff):** gap-momentum (trending) and premium-selling (choppy)
are the SAME regime coin, opposite faces. The 2023-26 regime that killed momentum is exactly
what makes short-vol premium-selling pay. **If gap-momentum revives, the 0DTE premium desk
will start bleeding — it's a leading kill-switch signal for the desk.**

Not tradeable directionally now. Value = the regime read + a monitor: track rolling
gap→intraday corr; when it turns decisively positive again, cut premium-selling size.
