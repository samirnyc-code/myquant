# 0001 — Pullback Scale-In on the MC CC Setup — 2026-06-24
**Series:** MC Setup Research Notes · Note 0001
**Confidence:** High — 5 years, full-cost, OOS-tested by year and stress-tested on exit assumptions; the NO-GO holds throughout.

**TL;DR:** Adding a second contract when price pulls back toward your stop, then
targeting the original 1R, **is not worth it on the MC setup.** Across every test
— first-principles math, tick-by-tick path analysis on 5 years of data, per-setup
and time-of-day and context filters, a full pullback-depth sweep (0.25→1.0R), and
an execution stress test — the add never clears the bar it needs to. Its apparent
profit is an accounting artifact of marking unresolved trades at the session close;
remove that one optimistic assumption and the edge disappears at every depth.
**Recommendation: take the clean single-leg trade to 1R and skip the scale-in.**
The only durable, real finding is a *negative* one: pullbacks in the afternoon
(after 13:00 CT) are structurally bad and should be avoided regardless.

---

## 1. The setup (so this note stands alone)

**The MC CC trade.** The "MC" indicator fires a breakout signal (one of five
subtypes, **CC1–CC5**). You enter at the signal bar's close (**E1**), place a stop
a fixed distance away, and target **+1R** (1R = the entry-to-stop distance). On
ES, 1 point = $50/contract; a 10-point stop = **1R = $500**.

**The scale-in variant we're testing.** Instead of one contract, you add a
**second contract (leg 2)** if price first pulls back toward your stop by some
fraction of R — e.g. a **50% pullback** means leg 2 fills halfway between entry
and stop. Both contracts then exit at the *original* 1R target. The idea: leg 2's
cheaper entry boosts the winner.

**The three outcomes** of any scale-in attempt (a long; shorts mirror), with *p* =
pullback depth:

| Outcome | Leg 1 | Leg 2 | Total | At p=0.50 |
|---|---|---|---|---|
| **Clean win** — runs to target, never pulls back | +1R | (never added) | **+1R** | +1R |
| **Scale-in win** — pulls back, leg 2 fills, both reach 1R | +1R | +(1+p)R | **+(2+p)R** | +2.5R |
| **Scale-in loss** — pulls back, leg 2 fills, both stop | −1R | −(1−p)R | **−(2−p)R** | −1.5R |

**Cost model.** $5 round-turn commission + 1 tick ($12.50) slippage **per leg** =
$17.50/leg. The scale-in pays it twice.

---

## 2. The question

Does the pullback scale-in add money over just taking the clean single-leg trade
to 1R — and if so, at what pullback depth, in what conditions?

---

## 3. How we tested it (the menu)

1. **First-principles math** — what win rate does the add *need* to break even?
2. **Tick-by-tick path study** — what happened to all 5,580 signals over 5 years.
3. **Per-setup (CC) breakdown** — does the add help any subtype?
4. **Time-of-day** — does session phase change the picture?
5. **"Tell" hunt** — can any pre-trade signal pick the winners?
6. **Year-by-year validation** — does anything good survive out of sample?
7. **Pullback-depth sweep** — is 50% even the right depth (0.25 → 1.0R)?
8. **Execution stress test** — how much depends on optimistic exit assumptions?

Data: `ba_signals_mc.parquet` (5,580 signals, 2021-06 → 2026-06), replayed on real
continuous ticks day-by-day. 5,444–5,490 have tick coverage. All P&L net of costs.

---

## 4. Results

### 4.1 The math — the add needs a win rate it doesn't have

**Per-trade outcomes** ($500 R, full cost, 50% PB):

| Outcome | Contracts | Net $ | Net R |
|---|---|---|---|
| Clean win | 1 | +$482.50 | +0.97R |
| Scale-in win | 2 | +$1,215 | +2.43R |
| Scale-in loss | 2 | −$785 | −1.57R |

**Breakeven win rates** by structure (1R target):

| Structure | Win | Loss | Breakeven win% |
|---|---|---|---|
| **No scale-in** (clean 1 contract) | +$482.50 | −$517.50 | **51.8%** |
| **Scale-in @ 50%, 1R target** | +$1,215 | −$785 | **39.3%** |
| Scale-in @ 50%, **breakeven exit** (the trap) | +$240 | −$785 | **76.0%** |
| **Leg 2 alone** (the marginal add decision) | +$732.50 | −$267.50 | **26.8%** |

Read: on its own, the second contract only needs to reach 1R on **~27%** of the
pullbacks it joins to be worth adding. Hold that 27% — it's the bar for everything
below. (The marginal bar widens as the pullback gets shallower: it equals
(1−p)/2, i.e. 37.5% at 0.25R, 33.5% at 0.33R, 25% at 0.50R, 17% at 0.66R.)

### 4.2 The path study — what actually happened (50% pullback, N=5,490)

| Outcome | Count | % of all |
|---|---|---|
| Clean win (straight to 1R) | 1,684 | 30.7% |
| **Scale-in win (PB → 1R)** | 538 | **9.8%** |
| **Scale-in loss (PB → stop)** | 1,829 | **33.3%** |
| Clean EOD (no pullback, no target) | 789 | 14.4% |
| Pullback then EOD (unresolved) | 604 | 11.0% |

- **54% of signals pull back** to the 50% level, but only **18% of those then reach
  1R** (538 / 2,971). The biggest single outcome of *any* signal is **PB → stop
  (33%)** — the pullback usually precedes a loss, not a bounce.
- Among *resolved* pullbacks (1R vs stop), the win rate is **22.7%** — **below the
  ~27% the add needs.** On its own bet, the second contract loses.
- Full population: scale-in net **$306,256** vs single-leg **$268,868** → the add
  *appears* to add **+$37,388**. §4.8 shows that's a marking artifact.

### 4.3 Per-setup (CC) — no subtype rescues it

50% PB, full cost. SI = scale-in, SL = single-leg.

| CC | N | PB→1R (% all) | PB-touch% | SI net | SL net | **Add value** | SI expR | SI PF |
|---|---|---|---|---|---|---|---|---|
| CC1 | 132 | 5.3% | 47.0% | $23,185 | $25,108 | **−$1,922** | 0.061 | 1.39 |
| CC2 | 906 | 10.7% | 51.5% | $65,260 | $52,170 | +$13,090 | 0.049 | 1.16 |
| CC3 | 1,633 | 11.0% | 57.5% | $61,930 | $44,612 | +$17,318 | 0.020 | 1.08 |
| CC4 | 1,656 | 10.0% | 55.0% | $80,810 | $72,685 | +$8,125 | 0.058 | 1.10 |
| CC5 | 1,163 | 7.7% | 51.0% | $75,071 | $74,292 | **+$779** | 0.073 | 1.15 |

The add is negative for CC1, ~zero for CC5 (the strongest standalone setup), and
only meaningfully positive for CC2/CC3 — and §4.8 dissolves even those.

### 4.4 Time-of-day — the one strong pattern (CME Central Time)

| Phase | N | Clean win | PB-touch | **PB→1R (of all)** | Resolved win% |
|---|---|---|---|---|---|
| Open (08:30–11:30) | 2,338 | 33.7% | 60.7% | 12.4% | 23.8% |
| Mid (11:30–13:00) | 1,189 | 37.1% | 57.3% | 12.7% | 26.7% |
| Late (13:00–14:45) | 1,443 | 29.0% | 54.3% | **6.7%** | 17.5% |
| Close (14:45–15:15) | 575 | 6.4% | 15.3% | **0.0%** | — |

The whole setup decays through the session. **Open+Mid = 24.7%** resolved (N=1,782)
vs **Late+Close = 16.6%** (N=585). At 50% depth the add makes **+$76,924 in
Open+Mid** but loses **−$39,535 in Late+Close** — netting the +$37k above. The
afternoon eats more than half the morning's add.

### 4.5 The "tell" hunt — full feature ranking (resolved binary, base 22.7%, N=2,367)

Every cheap pre-trade feature, best-to-worst bucket. `<<<` = ≥6 pts over base,
`(low)` = ≥6 under. Causal (look-ahead-safe) tags via `tag_signals`.

| Feature | Bucket (win% / N), best → worst |
|---|---|
| **ext_ema** (entry vs EMA20, trade dir) | far-pullback-side 30.5/174 `<<<` · below 27.1/59 · ≈EMA 25.0/76 · above 22.8/149 · chasing-extended 21.8/1909 |
| **session phase** | Mid 26.7/565 · Open 23.8/1217 · Late 17.5/555 (low) |
| **balance_state** | True 25.9/437 · False 22.0/1930 |
| **dir_streak** (consecutive same-dir) | 4+ 25.9/555 · 1 22.6/957 · 2 20.9/512 · 3 20.7/343 |
| **AID_DirMatch** (Always-In) | against-regime 25.7/451 · with-regime 22.0/1916 |
| **prior_ER** (prior-day trend) | ≥.5 26.2/515 · ≤.2 23.5/729 · .2-.35 21.3/550 · .35-.5 20.6/472 |
| **ER_intra_6** | .2-.35 25.3/344 · .35-.5 25.2/408 · ≤.2 24.8/302 · ≥.5 20.8/1303 |
| **ER_intra_12** | ≤.2 24.4/746 · .35-.5 23.2/453 · .2-.35 22.1/485 · ≥.5 20.9/670 |
| **is_deep_pullback** | True 24.3/515 · False 22.3/1852 |
| **AID_State** | up +1 23.9/1234 · down −1 21.4/1133 |
| **dow** | Wed 27.3/477 · Mon 24.8/408 · Tue 20.9/487 · Fri 20.7/492 · Thu 20.5/503 |
| **SignalType** | CC2 24.2/401 · CC4 23.0/718 · CC3 22.9/780 · CC5 21.3/423 · CC1 15.6/45 |
| **is_long** | long 23.5/1255 · short 21.9/1112 |
| **AID_bars** since flip | 1-3 25.0/541 · 11+ 22.6/1082 · 4-10 21.4/401 · on-flip 21.3/343 |
| **ext_vwap** | >1σ 23.4/1423 · -1..0 22.3/341 · <-1σ 20.0/110 · 0..1σ 20.0/380 |
| **prior_inside_day** | False 23.1/2156 · True 19.4/211 |
| **prior_adr_ext** (prior trend day) | False 23.3/2033 · True 19.5/334 |

**Best 2-feature combos clearing 30% (N≥60):** Mid+balance 37.5/72 · Mid+CC4 31.5/178
· CC2+against-regime 31.0/100 · Mid+AID-1-3-bars 30.9/123 · CC5+balance 30.4/79.

All single tells are weak (3–8 pts). Two notes: the streak only helps at **4+**
(2–3 are *worse* than singletons); Always-In points **counter-trend** — using it as
continuation confirmation hurts (consistent with its prior shelving as a gate). The
30%+ combos sit on N≈70–130 with ±11-pt confidence bands overlapping the base —
**overfit, not signal.**

### 4.6 Year-by-year — only the negative survives

**Resolved win% (1R vs stop) by year × phase:**

| Year | Open | Mid | Late | Open+Mid | Late+Close |
|---|---|---|---|---|---|
| 2021 | 23.5 (119) | 24.2 (62) | 18.3 (71) | **23.8** | 17.3 |
| 2022 | 22.7 (247) | 21.6 (125) | 22.2 (144) | **22.3** | 21.9 |
| 2023 | 29.0 (259) | 29.5 (105) | 12.0 (108) | **29.1** | 11.3 |
| 2024 | 19.6 (240) | 30.7 (101) | 12.0 (100) | **22.9** | 11.4 |
| 2025 | 23.7 (249) | 31.3 (131) | 20.8 (96) | **26.3** | 18.9 |
| 2026 | 24.3 (103) | 14.6 (41) | 19.4 (36) | **21.5** | 18.4 |

**Whole-population PB→1R share (of all signals) by year × phase:**

| Year | Open+Mid | Late+Close |
|---|---|---|
| 2021 | 11.8% (363) | 5.3% (245) |
| 2022 | 11.2% (739) | 6.9% (465) |
| 2023 | 15.9% (665) | 3.1% (418) |
| 2024 | 11.9% (656) | 3.7% (328) |
| 2025 | 13.0% (770) | 5.2% (381) |
| 2026 | 9.3% (334) | 3.9% (181) |

**Robust:** Late+Close is worse in **6/6 years** (morning pullbacks reach 1R ~2×
more often). **Fragile:** "Open+Mid is a positive edge" clears the ~27% bar in only
**2 of 6 years** (2023, 2025); 2022 had no phase edge at all. "Mid is the sweet
spot" is a 2023–25 artifact (great those years, weak/noise 2021/22/26) — does not
generalize.

### 4.7 Pullback-depth sweep (0.25 → 1.0R) — shallower looks better… but see §4.8

**All signals** (single-leg baseline net = $268,868), exits marked at session close:

| PB depth | Touch% | PB→1R (all) | Add hit% (1R/touch) | Bar to beat | PB→stop% | SI net | **Add value** |
|---|---|---|---|---|---|---|---|
| **0.25R** | 71.5% | 20.8% | 29.1% | 37.5% | 33.6% | $371,812 | **+$102,945** |
| 0.33R | 64.6% | 16.2% | 25.1% | 33.5% | 33.6% | $329,227 | +$60,360 |
| 0.50R | 54.6% | 9.9% | 18.1% | 25.0% | 33.6% | $306,256 | +$37,389 |
| 0.66R | 46.4% | 5.2% | 11.3% | 17.0% | 33.6% | $238,047 | −$30,821 |
| 0.75R | 42.6% | 3.3% | 7.7% | 12.5% | 33.6% | $230,041 | −$38,826 |
| 1.00R | 33.6% | 0.0% | 0.0% | 0.0% | 33.6% | $236,860 | −$32,008 |

**Add value ($) by CC × depth:**

| CC | 0.25 | 0.33 | 0.50 | 0.66 | 0.75 | 1.00 |
|---|---|---|---|---|---|---|
| CC1 | +9,546 | +7,848 | −1,922 | −5,228 | −4,634 | −665 |
| CC2 | +36,284 | +33,126 | +13,090 | −5,884 | −3,701 | −5,320 |
| CC3 | +26,568 | +15,342 | +17,318 | −3,373 | −859 | −10,518 |
| CC4 | +6,625 | +1,365 | +8,125 | −17,829 | −35,597 | −9,678 |
| CC5 | +23,922 | +2,679 | +779 | +1,493 | +5,964 | −5,828 |

**Add hit-rate (PB→1R / touched) by session × depth:**

| Phase | 0.25 | 0.33 | 0.50 | 0.66 | 0.75 |
|---|---|---|---|---|---|
| Open+Mid | 33.8% | 29.3% | 21.0% | 13.4% | 9.3% |
| Late+Close | 19.4% | 15.7% | 11.1% | 5.9% | 3.7% |

**Add value ($) by session × depth:**

| Phase | 0.25 | 0.33 | 0.50 | 0.66 | 0.75 | 1.00 |
|---|---|---|---|---|---|---|
| Open+Mid | +134,012 | +109,518 | +76,924 | +16,701 | −2,047 | −23,468 |
| Late+Close | −31,068 | −49,159 | −39,535 | −47,521 | −36,779 | −8,540 |

Add value falls monotonically with depth and goes negative beyond ~0.5R. **Red
flag:** at *every* depth the add's hit rate is **below the bar it needs** (29.1% vs
37.5% at 0.25R). The directional bet loses at all depths — the positive numbers must
come from somewhere other than reaching the target.

### 4.8 Execution stress test — the kill shot

The positive add value comes entirely from **unresolved pullbacks marked at the
session close** (optimistic: price drifts back and you flatten at 15:15). We
re-priced unresolved adds three ways — **close** (mark at session close), **be**
(leg 2 exits flat at its entry, neutral), **stop** (count as a full stop, worst):

**Add value ($) — ALL signals (N=5,444):**

| PB | close | breakeven | stop (worst) |
|---|---|---|---|
| 0.25R | +102,945 | −60,746 | −782,705 |
| 0.33R | +60,360 | −127,164 | −680,190 |
| 0.50R | +37,389 | −182,418 | −494,086 |
| 0.66R | −30,821 | −206,005 | −344,933 |
| 0.75R | −38,826 | −185,970 | −262,201 |

**Add value ($) — Open+Mid only, the best case (N=3,453):**

| PB | close | breakeven | stop (worst) |
|---|---|---|---|
| 0.25R | +134,012 | **+19,347** | −339,575 |
| 0.33R | +109,518 | −24,575 | −322,357 |
| 0.50R | +76,924 | −91,458 | −279,651 |
| 0.66R | +16,701 | −118,831 | −203,712 |
| 0.75R | −2,047 | −112,103 | −157,909 |

**Add value ($) — Late+Close (N=1,991):**

| PB | close | breakeven | stop (worst) |
|---|---|---|---|
| 0.25R | −31,068 | −80,092 | −443,130 |
| 0.33R | −49,159 | −102,589 | −357,834 |
| 0.50R | −39,535 | −90,960 | −214,435 |
| 0.66R | −47,521 | −87,174 | −141,221 |
| 0.75R | −36,779 | −73,867 | −104,292 |

Strip the optimism and **every configuration goes negative except one** — 0.25R in
the morning, at a trivial **+$19,347 over five years** (~$6/trade). 50% depth swings
from +$77k to **−$91k**. Late+Close is negative under every policy and depth.

---

## 5. Why it fails

The pullback-to-stop is **more often the start of a loss than a dip to be bought.**
On the MC setup, a 50% retrace reaches the original 1R target only ~18% of the time
and stops out ~62% of the time — far below the ~27% the second contract needs. So
the add is a **negative-expectancy directional bet** that *looks* profitable only
because the backtest marks the leftover unresolved trades at a favorable session
close — a drift you can't reliably capture live. Shallower depths don't fix it; they
just amplify the same artifact. The math we started with predicted exactly this: a
low-hit-rate add against a −1.5R downside can't clear its own bar.

---

## 6. Recommendation

> **Don't scale in. Take the clean single-leg MC trade to 1R and skip the second
> contract.** It needs ~52% wins to break even, the standalone setup is in that
> range, and you avoid doubling risk into a move that's already against you.
>
> **If you scale in anyway:** only ever at a **shallow (~0.25R) pullback**, only in
> the **morning (08:30–13:00 CT)**, and understand you're playing for break-even,
> not edge.
>
> **The one rule worth keeping from all this is negative:** **avoid the afternoon.**
> Pullbacks after 13:00 CT are structurally bad — they reach target half as often,
> every year tested. This applies to the base trade too, not just the scale-in.

---

## 7. Caveats & open questions

- **EOD marking is the swing variable.** "Close-mark" is optimistic; "breakeven" is
  neutral; reality is in between. The *ranking* (shallow ≫ deep, morning ≫
  afternoon) is robust; the absolute $ is not.
- The sim scores trades **independently** (unlimited concurrent positions) — real
  capital/overlap constraints would only make the marginal add look worse.
- Path levels use raw signal/stop prices; entry slippage is captured via cost, not
  geometry.
- `with_trend` (structural-trend agreement) was broken in this run and excluded —
  worth a clean re-test, though §4.5 makes a strong tell there unlikely.
- Open follow-up: does avoiding the afternoon improve the **base** single-leg MC
  trade enough to matter? (Suggested by §4.4 but not isolated here.)

---

## 8. Reproduce

Scripts (all headless, day-by-day tick replay):
- `scripts/pb_to_1r_path_study.py` — path buckets + scale-in vs single-leg P&L (§4.2–4.3)
- `scripts/pb_tell_hunt.py` — TOD, full tell hunt, year split (§4.4–4.6)
- `scripts/pb_level_compare.py` — pullback-depth sweep, per-CC & per-session (§4.7)
- `scripts/pb_eod_stress.py` — EOD policy stress test, all scopes (§4.8)
- `scripts/render_note_pdf.py <note.md>` — renders any note in this series to PDF

Saved artifacts: `docs/living/pb_to_1r_paths.parquet`,
`docs/living/pb_tell_features.parquet`, `docs/living/pb_level_compare.parquet`.
