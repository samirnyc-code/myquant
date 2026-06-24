# 0003 — Keystone: The Initial-Balance Edge Fade — 2026-06-24
**Series:** MC Setup Research Notes · Note 0003
**Confidence:** Medium — 5 years MC, full-cost, PASSED a look-ahead audit, and positive in every calendar year (a quasi-out-of-sample check). Held back from High because it is still in-sample on MC only, was selected among ~85 tested filters (so the forward edge is the conservative end of the range), and carries a deep drawdown.

**TL;DR:** We searched for whether an MC signal's *location* — where its channel originated relative to structural levels — predicts a tradeable edge. Almost everything failed (reversal-at-extreme, prior-day levels, volume nodes, single prints, value-area edges, an IB-width "sweet spot" that turned out to be a stop-size illusion). **One survived: signals whose origin sits within 0.10 ADR of the day's Initial Balance (first-hour) edge — a responsive fade back into value.** At a fixed 2.0R exit it makes **+0.159 R/trade (PF 1.38, 1,395 trades, ~$233k on one contract over 5yr)**, the filter *concentrates* the edge (the rest of the book is flat), it works long and short, and it survives realistic costs and a look-ahead audit. **But it is a thin, deep-drawdown edge** (~$26k max DD/contract; realistic forward ~+0.09–0.12R after costs and selection bias). **Recommendation: a sized *component* for a well-capitalized cash account — not a standalone automated prop system.**

---

## 1. The setup (so this note stands alone)

**The MC CC trade.** The "MC" indicator fires breakout signals (subtypes CC1–CC5) on 5-minute ES. You enter at the first tick after the signal bar's close, place a stop at the channel's protective level (the MCX extreme), and exit at a fixed multiple of **R** (R = entry-to-stop distance). ES: 1 point = $50/contract, 1 tick = $12.50.

**Initial Balance (IB).** The IB is the **high/low of the first 60 minutes** of the RTH session — the auction's opening agreed-upon range. In Auction Market Theory, a move that launches off the IB boundary and rotates back in is a **responsive** trade: the market tested the early extreme and rejected it.

**Keystone, in one sentence.** Keep only those MC signals whose **channel origin** (the `StopPrice`/MCX extreme — the swing the channel formed from) sits **within 0.10 ADR of the same-side IB edge**: longs whose origin is at the IB *low*, shorts whose origin is at the IB *high*. Then trade them with a plain fixed **2.0R** target, single contract, both directions.

**Distance metric.** `d = |origin − IB edge| / ADR`, where ADR = prior-day ATR(14) in points. The gate is `0 ≤ d ≤ 0.10`. Normalising by ADR makes the threshold regime-independent.

**Cost model.** $4.36 round-turn commission + 1 tick entry slippage, 0 exit (the MC pin; slightly lighter than the house default of $5 + 1 tick/leg — immaterial, and we stress heavier costs in §4.7). All sims replay **real continuous ticks day-by-day**. Signal set: `ba_signals_mc.parquet` (5,580 signals, 2021-06 → 2026-06). Features are tagged **causally** through the S34-corrected `tag_signals` chokepoint (see Note 0002 for the look-ahead fix this depends on).

---

## 2. The question

1. **Does an MC signal's origin location, relative to a structural level, select winners?** We pre-committed a menu of level families rather than fishing one bucket at a time.
2. **For the one family that worked (the IB edge): can we make it better** — a different threshold, exit, management rule, leg structure, direction, or filter stack — or is the simple version the best version?
3. **Is the surviving edge real, or another look-ahead / overfit artifact?**

---

## 3. How we tested it (the menu)

**Finding it — location families (each = a descriptive bucket study on the real tick engine, pinned 1.0R single-leg, ±95% CIs, by-year):**

1. Reversal off the **developing day extreme** (LOD/HOD).
2. Origin at the **prior-day high/low** (LOY/HOY), incl. conditioned on a balance day.
3. **Balance state** (opened inside yesterday's range and still rotating).
4. **Failed-breakout fade** ("look above/below and fail").
5. Origin at prior **volume nodes** (HVN / LVN) and **single/zero prints** — built a profile-node extractor for this.
6. Origin at the prior **value-area edge** (VAH / VAL).
7. **IB width** "sweet spot" (is rotation cleanest at a mid IB width?).
8. Origin at the **IB edge** — the survivor.

**Improving it (on the IB-edge book):** a 0.05-ADR **threshold sweep** (where to draw the gate line); a **target sweep** 0.5R–4R; **active management** (breakeven, lock-in trail); **2-leg scale-in / scale-out**; **direction** split; **filter stacking** with balance.

**Breaking it (the audit):** a **session-timing split** (does the edge live only where the IB is still forming?), **cost stress** to 3-tick slippage, and a **StopPrice causality** sanity check.

Engine: tick-by-tick first-touch (entry at first tick after the signal; stop/target by tick crossing). Memory-frugal 4-chunk tick load for the full-population sims.

---

## 4. Results

### 4.1 The location search — Keystone was the lone survivor

| Hypothesis (origin / location vs a level) | Verdict |
|---|---|
| Reversal off developing day low/high (LOD/HOD) | REJECT — long-only, drift-suspected |
| Origin at prior-day low/high (LOY/HOY) | REJECT — nothing beyond "balance" |
| Balance state (opened inside Y, still rotating) | WEAK — real but fails 2023–24 |
| Failed-breakout "look above/below & fail" fade | REJECT — the canonical fade LOSES |
| Origin at prior volume nodes (HVN / LVN) | REJECT — null |
| Origin at single / zero prints (profile gaps) | REJECT — null |
| Origin at prior value-area edge (VAH / VAL) | WEAK — suggestive but thin (n≈100) |
| IB width "sweet spot" (inverted-U in dollars) | REJECT — a stop-size illusion in $ |
| **Origin at the IB edge (≤0.10 ADR) = KEYSTONE** | **SURVIVED everything below** |

Across ~85 buckets, almost everything died honestly. Reporting the failures is the point: it shows the survivor was not cherry-picked from one lucky look. (The IB-width case is instructive — it looked great in *dollars* because wider IB days have wider stops, i.e. more $ per winning R; in *R* the apparent peak vanished. We judge everything in R for exactly this reason.)

### 4.2 Headline performance (1 contract, ~5 yr, 2.0R)

| Trades | Net P&L | Exp R | Profit Factor | Win % | Net / MaxDD |
|---|---|---|---|---|---|
| 1,395 | $232,593 | +0.159 | 1.38 | 48.5% | 8.86 |

716 long / 679 short; ~280 trades/year (about one per session).

### 4.3 The filter does real work — selection value at 2.0R

| Population | Trades | Exp R | Profit Factor |
|---|---|---|---|
| Keystone gate | 1,395 | **+0.159** | 1.38 |
| Everything else (non-gate) | 4,049 | +0.026 | 1.08 |
| All signals (baseline) | 5,444 | +0.060 | 1.17 |

Same 2.0R exit for all three rows. **The non-gated remainder is essentially flat** — the gate *concentrates* the edge rather than slicing an already-good book. That clean separation (gate vs the inert rest) is the core evidence the filter carries real information.

### 4.4 Where to draw the gate line — a CLIFF at 0.10 ADR, not a knob

Sweeping origin-to-IB-edge distance in 0.05-ADR bands (full population, 1.0R basis):

| Distance to IB edge (ADR) | Exp R | Profit Factor |
|---|---|---|
| 0.00 – 0.05 | +0.097 | 1.25 |
| 0.05 – 0.10 (gate keeps ≤0.10) | +0.156 | 1.51 |
| 0.10 – 0.20 | −0.02 | 0.99 |
| 0.20 – 0.35 | +0.04 | 1.13 |

The edge is concentrated within 0.10 ADR and **falls off a cliff** beyond it. 0.10 is a *structural boundary*, not a fitted peak — there is no smooth knob to tune. Tighter (0.05) throws away half the trades for no better R.

### 4.5 The exit target — a plateau, not a tuned peak

| Target | Exp R | Profit Factor | Net / MaxDD |
|---|---|---|---|
| 1.0R | +0.112 | 1.30 | 6.9 |
| 1.5R | +0.136 | 1.34 | 7.8 |
| 2.0R (chosen) | +0.159 | 1.38 | 8.9 |
| 3.0R | +0.161 | 1.35 | 8.3 |
| 4.0R | +0.169 | 1.37 | 9.1 |

Expectancy rises and then **plateaus from ~2R**. 2.0R sits on a flat shelf — a tuned peak would tower over its neighbours; this doesn't. We take 2.0R as the conservative entry to the plateau.

### 4.6 Improving it further — nothing beat the simple version

**Active management** (gated book, 2.0R):

| Exit rule | Exp R | Net / MaxDD |
|---|---|---|
| Plain 2.0R (chosen) | +0.159 | 8.9 |
| + break-even after +1R | +0.161 | 9.4 |
| + trail (lock +0.5R after +1.5R) | +0.158 | 8.5 |

Break-even is a hair better on MAR but trades win-rate for it and adds moving parts — the gain is inside the noise.

**Two-leg scale-in / scale-out.** Adding a second contract on a pullback (including the "E1 scratches, E2 wins" structure) and scaling a partial out at 1R **both underperformed plain single-leg 2.0R on net AND drawdown** — the pullback-add piles size into the losers, deepening the DD. (This work also uncovered and fixed a P&L mis-scaling bug in the 2-leg engine; see `BUG_multileg_pnl_scaling.md`. Keystone is single-leg and unaffected.)

**Direction.** Long-only +0.091R, short-only +0.133R, **both positive in every year**. We trade both — the symmetry is itself evidence the edge is structural; dropping a side to flatter the curve would be fitting.

**Stacking with balance.** Layering the "balance day" context lifts the gate to +0.168R — but balance alone is weak and regime-dependent, and it halves the trade count. We keep the gate **standalone** (more trades, cleaner); balance is an optional conviction add, not part of the core rule.

> The pattern across all of §4.6: **the edge lives in *selection* (which trade to take), not in *management* after entry.** The simplest config is the best config.

### 4.7 Consistency, costs, and the look-ahead audit

**By year (Exp R, 2.0R):**

| 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| +0.315 | +0.207 | +0.034 | +0.121 | +0.198 | +0.174 |

Positive every year, including the 2022 bear. 2023 is the softest (thin positive); no single year carries the result.

**Execution cost stress (Exp R, 2.0R):**

| Slippage assumption | Exp R | Profit Factor |
|---|---|---|
| 1 tick in / 0 out (base) | +0.159 | 1.38 |
| 2 in / 1 out (realistic-conservative) | +0.123 | 1.30 |
| 3 in / 2 out (brutal) | +0.092 | 1.24 |

Stays clearly positive even under pessimistic fills (lower 95% CI bound above zero at brutal).

**Look-ahead audit — the decisive test (PASSED).** If the edge came from peeking at the *final* IB before it formed, it would concentrate in signals fired DURING the first hour (IB still developing) and vanish AFTER it. The opposite holds:

| Subset | Trades | Exp R | Profit Factor |
|---|---|---|---|
| After first hour (IB fully PAST) | 603 | +0.203 | 1.62 |
| During first hour (IB developing) | 792 | +0.126 | 1.27 |

The edge is **stronger** where the IB is indisputably in the past. OR60 is causal in code (developing running range during the first hour, frozen after — `indicators.py:263-274`); no as-of merge can land on the entry bar; StopPrice is 100% on the correct side of the signal. The signature of a *real* effect, not a leak.

---

## 5. Why it works (and why it's thin)

**Why it works.** The IB edge is a level the whole session references. An MC channel that *originates* there — i.e. forms off the first-hour high or low — is a structurally-located responsive trade: the market reached the early boundary, was rejected, and the breakout carries it back toward developing value. That the effect is *symmetric* (both sides), *every-year-positive*, and *stronger once the IB is fully formed* all point to a genuine auction mechanic rather than a data artifact.

**Why it's thin.** It is a selection edge on a base population that, corrected for look-ahead, has almost no standalone edge (Note 0002). A filter can only *concentrate* existing structure, not manufacture it — so the ceiling is modest. After realistic costs and the winner's-curse haircut from testing ~85 buckets, the honest forward number is the **+0.09–0.12R** end, not +0.159R. And the drawdown is deep and **regime-clustered** (the losers arrive in runs during weak years), which no exit choice repairs — it is intrinsic to what the gate selects.

---

## 6. Recommendation

> **1. Keystone is a real, audited, *modest* edge — deploy it only as a sized COMPONENT.** Single-leg, 2.0R, both directions, gate at 0.10 ADR, no per-period optimization. It is **not** a standalone automated prop system: on one contract the worst drawdown was ~$26k and the book sits >$5k below its high-water mark ~48% of the time, with a ~9-month recovery. That path will trip a tight trailing-DD prop account. It suits a **well-capitalized cash account** (~$75–100k of capital per ES contract) or a **sizing/selection overlay** on a broader book where its bleeds dilute.
>
> **2. Keep it simple — do not add management.** Every improvement we tried (break-even, trail, scale-in, scale-out, direction-pruning, filter-stacking) failed to beat the plain version risk-adjusted. The edge is in *selection*; management only adds overfit surface.
>
> **3. Before committing capital:** confirm out-of-sample on truly held-out data (and on RevFT), then run the prop/cash account simulator with contract scaling and the never-blow floor for blow-up probability and net-to-trader — **the drawdown path, not the average, is the binding constraint.**

---

## 7. Caveats & open questions

- **In-sample, MC only.** All figures are over the full 2021–2026 MC history. The by-year positivity is a quasi-OOS reassurance, not a true held-out test. Not yet replicated on RevFT.
- **Selection bias.** Found among ~85 tested buckets; the look-ahead audit clears *leakage* but not *multiple-testing* — hence the conservative forward read.
- **StopPrice residual.** The origin comes from the NT MC indicator export; its internal causality can't be audited from the Python side. Low risk (it's the same stop every MC strategy uses, and it is 100% on the correct side of the signal), but not zero.
- **Deep, regime-clustered drawdown** is the real obstacle, and it is **target-invariant** — 1R through 4R all carry ~$25k max DD. This is an entry/selection property, not an exit one.
- **Costs** here are slightly lighter than the house default; §4.7 shows the edge survives to 3-tick slippage, so conclusions are not cost-sensitive.

---

## 8. Reproduce

Scripts (headless, day-by-day tick replay against the production engine; no production code changed except the documented 2-leg P&L fix):

- `scripts/origin_at_extreme_study.py` — LOD/HOD & LOY/HOY reversal buckets (§4.1)
- `scripts/balance_refine_study.py` — balance state, IB / gap / value-area conditioning (§4.1, §4.6)
- `scripts/profile_node_study.py` — HVN/LVN/single-print origin (§4.1)
- `scripts/ib_study.py` — IB width inverted-U + the IB-edge distance gradient (§4.1, §4.4)
- `scripts/ib_edge_deep.py` — gate vs complement, symmetry, year-by-year, cost, redundancy (§4.3, §4.6, §4.7)
- `scripts/ib_edge_target_sweep.py` — target sweep / plateau (§4.5)
- `scripts/ib_edge_exits.py` — break-even / trail / scale-in / scale-out (§4.6)
- `scripts/ib_edge_scalein.py` — the "E1 scratch / E2 win" scale-in + 2-leg accounting check (§4.6)
- `scripts/ib_edge_equity.py` — stitched equity & drawdown path (§5, §6)
- `scripts/keystone_audit.py` — session-timing split, cost stress, StopPrice sanity (§4.7)

Saved artifacts (in `docs/living/`): `origin_at_extreme_study_20260623.md`, `balance_refine_study_20260623.md`, `profile_node_study_20260623.md`, `ib_study_20260623.md`, `ib_edge_deep_20260623.md`, `ib_edge_target_sweep_20260623.md`, `ib_edge_exits_20260624.md`, `ib_edge_scalein_20260624.md`, `ib_edge_equity_20260623.md`, `keystone_audit_20260624.md`.

Gate definition (look-ahead-safe): `d = (StopPrice − OR60_Low)/ADR` for longs, `(OR60_High − StopPrice)/ADR` for shorts; keep `0 ≤ d ≤ 0.10`. ADR = `prior_ATR`; OR60/ADR via the S34-fixed `tag_signals`.
