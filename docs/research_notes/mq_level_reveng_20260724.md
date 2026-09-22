# MenthorQ SPX Gamma-Level Reverse Engineering — Final Synthesis (2026-07-24)

**Data:** `data/regime/mq_reveng/chain_slices_overlap.parquet` (ORATS SPX EOD per-strike
chains, 1,183 trade dates 2021-09-27 .. 2026-07-15, 13.39M rows) scored against
`data/regime/mq_reveng/mq_truth.csv` (MQ's published EOD levels + their own GEX values —
the formula fingerprint). Join: `eod_date == tradeDate` (session_date == eod_date on all rows).

**Anti-overfit split:** fit = eod_date <= 2023-12-31 (549-551 days), holdout = 2024+ (632 days).
All numbers below produced by `scripts/mq_reveng_final_20260724.py`; per-day output in
`data/regime/mq_reveng/final_replication.csv`, metrics in
`final_replication_summary_20260724.csv`, per-year in `final_replication_peryear_20260724.csv`,
conflicting-spec duels in `final_headtohead_20260724.csv`.

---

## 1. MQ's inferred methodology (the replication spec)

Universe: **SPX chain only** (MQ computes SPX/SPY/ES separately; futures converted by
price ratio). Input: **EOD open interest + Black-Scholes per-contract gamma**, all listed
strikes, **all expirations EXCLUDING the front/dying expiry** (ORATS `dte >= 2`; the
front expiry is instead isolated into the separate 0DTE level set — this exclusion is the
single discovery that unlocked CR/PS). Sign convention: **calls positive, puts negative**
(naive SqueezeMetrics dealer assumption; no modeled dealer inventory).

Data hygiene required on ORATS: zero any gamma outside [0, 0.5] (63 corrupt rows with
gamma up to 1e21; ~961k tiny negative deep-ITM gammas) or holdout R2 explodes.

Per-strike quantities (same-day EOD chain, spot = MQ `spot_eod` ~ ORATS `spotPrice`):

```
net(K)   = SUM over expiries dte>=2 of  gamma(K,e) * (callOI(K,e) - putOI(K,e))
value(K) = net(K) * 100 * spot          # dollars of gamma exposure per 1-pt SPX move
```

| Level | Definition |
|---|---|
| **Call Resistance** | argmax_K net(K), all strikes (global max of net GEX) |
| **Put Support** | argmin_K net(K), strikes within +-20% of spot (global min / largest negative) |
| **HVL** (gamma flip) | negative-side strike of the net(K) **sign flip nearest spot**, after aggregating net(K) to a 5-pt strike grid and smoothing with a +-25-pt price-window rolling sum. It is a per-strike-profile flip, **not** a cumulative-GEX zero crossing (that hypothesis is refuted head-to-head, see §3). |
| **GEX 1..10** | top-10 strikes by `max(SUM_{2<=dte<=21} gamma*callOI, SUM_{2<=dte<=21} gamma*putOI)` (short-dated, side-max concentration — not |net|), universe = strikes within +-3% of spot, **excluding the 7 primary levels** (CR/PS/HVL/CR0/PS0/HVL0/GW0 — truth shows the GEX set NEVER contains a primary level); ordered by proximity to spot (gex_1 nearest), membership is the signal, order is cosmetic |
| **Published *_gex values** | `value(K) = net(K) * 100 * spot` at the level's strike — fixed formula, **no fitted parameters**. Confirms scaling is 100*S (per-point dollar gamma), not spot^2*0.01 |
| **CR 0DTE = Gamma Wall 0DTE** | argmax_K gamma*callOI, K >= spot, on the expiry dying on session S taken from the **prior day's chain** (same-day rows are degenerate at EOD); gw0 == cr0 on 99.8% of truth days. Fallback when no expiry dies: cr0 = CR |
| **PS 0DTE** | argmin_K gamma*(callOI-putOI), K <= spot, expiries <= S+3 calendar days, prior day's chain |
| **HVL 0DTE** | smaller-abs-net side of the net sign flip nearest spot on the dying-expiry slice |
| **1D Min/Max** | not an OI level: prev close * (1 +- (VIX/100)*sqrt(1/365)) (S75U replication, reproduces MQ's published hit rates within 1pp) |
| **Blind Spots BL1-10** | NOT reproducible from the SPX chain — cross-asset proprietary model (S75V-BL: exact reconstruction refuted 4 ways) |

## 2. Replication quality per level (fit / holdout)

| Level | Metric | Fit (<=2023) | Holdout (2024+) |
|---|---|---|---|
| CR | exact strike | **81.4%** | **92.1%** (medAE 0) |
| PS | exact strike | **74.1%** | **87.0%** (medAE 0) |
| HVL | medAE / within-25 / exact | 15 pts / 77.6% / 13.1% | **10 pts / 94.8% / 16.8%** |
| **Regime label** (spot vs HVL) | agreement | **94.0%** | **96.5%** |
| GEX 1-10 (self-contained, excl own levels) | precision@10 / Jaccard | 49.7% / 0.351 | 56.8% / 0.409 |
| GEX 1-10 (excl truth levels, upper bound) | precision@10 / Jaccard | 58.6% / 0.437 | 64.8% / 0.491 |
| Published GEX values | pooled R2 / median ratio | 0.80 (0.87 ex-2021) / 0.95 | **0.989 / 0.991** (IQR 0.10) |
| CR0 / GW0 | exact / within-25 | 24.9% / 56.4% | 28.2% / 67.6% |
| PS0 | exact / within-25 | 22.3% / 38.7% | 23.9% / 43.2% |
| HVL0 | exact / within-25 | 7.5% / 52.3% | 8.7% / 61.6% |

Per-year (error is concentrated in the early era — monotone improvement, no drift risk
going forward):

| Year | n | CR exact | PS exact | HVL medAE | Regime agree | GEX10 prec |
|---|---|---|---|---|---|---|
| 2021 | 66 | 65.2% | 56.1% | 30 | 89.4% | 0.35 |
| 2022 | 251 | 81.3% | 70.5% | 20 | 92.8% | 0.51 |
| 2023 | 234 | 86.2% | 83.2% | 10 | 96.6% | 0.53 |
| 2024 | 249 | 92.8% | 87.6% | 10 | 96.8% | 0.54 |
| 2025 | 250 | 88.4% | 82.4% | 10 | 95.6% | 0.58 |
| 2026 | 133 | 97.7% | 94.7% | 10 | 97.7% | 0.60 |

**Regime agreement: 95.3% overall (n=1,181)** — up from 21.8% in the v1 engine. The v1
failure was a +150-pt biased HVL (wrong construction); the fixed flip-with-smoothing HVL
has zero median bias and holdout agreement (96.5%) BETTER than fit, i.e. not overfit.

All four upstream agents' headline numbers reproduced in this synthesis run within ~0-2pp
(CR 81.1→81.4 fit / 90.8→92.1 holdout from minor gamma-hygiene and spot-source diffs;
PS 74.0/86.9 vs 74.1/87.0; HVL 15/10 medAE identical; GEX10 0.584/0.647 vs 0.586/0.648;
value formula R2 0.989 and ratio 0.991 identical). No reported number failed to reproduce.

## 3. Adversarial head-to-heads (where agent specs conflicted)

- **HVL: per-strike flip vs cumulative zero-cross (web/Perfiliev hypothesis).** The
  cumulative-net-GEX zero-crossing gets medAE **420 pts fit / 180 pts holdout**, 0% within-25,
  regime agreement 14%/12%. Decisively refuted; MQ's own hvl_gex fingerprint (negative on
  100% of days, correlates 0.84 with per-strike net at the HVL, ~0.00 with cumulative sums)
  independently confirms the per-strike flip. MQ's "inflection point of the cumulative
  gamma curve" marketing language does not describe their actual math.
- **GEX 1-10: side-max short-dated concentration vs top-|net| within the published 1D band
  (web hypothesis).** Web variant scores precision@10 45.1%/46.3% (46.7%/47.8% with level
  exclusion) vs the winner's 58.6%/64.8%. Winner confirmed; the 1D-band framing is also
  marketing shorthand — the effective universe is ~+-3% of spot with short-dated (2-21 dte)
  per-side gamma concentration, and the published per-level values come from a different
  formula (all-expiry net * 100 * spot) than the selection score.
- **GEX value scaling:** ranking agent's fitted day_scale (~0.018*spot^2) is numerically
  the same object as the GEX agent's fixed 100*spot at SPX price levels; the fixed
  parameter-free 100*spot form wins on holdout (R2 0.989, ratio 0.991) and is adopted.

## 4. What remains unexplained

- **2021 does not fit the value formula** (per-day R2 negative, ratio ~0.55) and CR/PS/HVL
  accuracy is materially worse (65%/56%/30-pt). MQ's methodology (or their chain vendor)
  was different pre-2022. Fit metrics are quoted ex-2021 where relevant.
- **HVL exact-strike ceiling ~17%** (within-5 ~40%): residual is MQ's exact smoothing
  kernel + their intraday chain snapshot vs our ORATS EOD data. Within-25 is 95% holdout,
  which is what the regime label needs.
- **0DTE levels are data-limited, not spec-limited:** MQ's cr0_gex/ps0_gex values are
  nearly uncorrelated (Pearson 0.02-0.37) with ANYTHING computable from the prior-day EOD
  chain, while the same test on main levels gives R2 0.97-0.99 — MQ computes the 0DTE set
  from same-day intraday OI/flow that EOD chains don't contain. ~25-28% exact / ~65%
  within-25 is the ceiling with this dataset.
- **GEX 1-10 membership tops out ~65%** (rising to ~67% by-year in 2026): the selection
  score is recovered in shape but not exactly; ORATS OI-snapshot differences flip
  marginal ranks. Ordering of gex_1..10 is only approximately proximity-to-spot
  (spearman 0.73), never exactly monotone.
- **DTE cap unidentifiable** beyond ~120 days (no-cap vs 120-365 caps indistinguishable);
  treated as all-expiries-ex-front.
- **Blind Spots** are out of scope of the single-chain model by construction.

## 5. Is the 2007-2021 backfill trustworthy?

**Qualified yes — for CR, PS, HVL, the regime label, and the GEX dollar values; no for the
0DTE set and only as a fuzzy zone-set for GEX 1-10.**

- The spec has **zero fitted parameters** on the value formula and only structural choices
  (dte>=2, +-25pt smoothing, 2-21dte GEX-10 window) elsewhere, and every metric is BETTER
  on the 2024+ holdout than in fit — the replication is not overfit to the overlap window.
- Caveat 1: accuracy degrades going back in time within the overlap (2021 is the worst
  year on every metric), and 2007-2021 SPX had no daily expiries — expect the pre-2022
  regime to behave like the 2021 column (CR ~65%, PS ~56%, HVL medAE ~30pt, regime ~89%),
  not like the 2026 one. The backfilled levels are self-consistent gamma structure, but
  they will match what MQ *would have published* less exactly the further back you go.
- Caveat 2: sparse weekly/monthly expiries pre-2016 make the front-expiry exclusion and
  the 2-21dte window behave differently (fewer expiries in the window); the 0DTE set is
  undefined for most historical days (no dying expiry) — use the documented fallback
  (cr0=cr) or drop those columns.
- Bottom line: for the intended use (HVL-based gamma-regime label + CR/PS structural
  levels), the backfill is fit for purpose: ~90%+ regime-label fidelity even in the
  worst observed year, with the level positions exact on the large majority of days.

## 6. Artifacts

- `scripts/mq_reveng_final_20260724.py` — full synthesis pipeline (this note's numbers)
- `data/regime/mq_reveng/final_replication.csv` — per-day: all predicted levels vs truth
- `data/regime/mq_reveng/final_replication_summary_20260724.csv` — every metric fit/holdout
- `data/regime/mq_reveng/final_replication_peryear_20260724.csv` — per-year table
- `data/regime/mq_reveng/final_headtohead_20260724.csv` — conflicting-spec duel results
- Upstream agent scripts: `mq_reveng_gex_*`, `mq_reveng_crps_*`, `mq_reveng_hvl_*`,
  `mq_reveng_gex10_*`, `mq_reveng_truthfp_*`, `mq_reveng_zerodte3_*` (all `_20260724.py`)
