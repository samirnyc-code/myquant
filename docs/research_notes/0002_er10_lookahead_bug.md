# 0002 — The ER10 Look-Ahead Bug: Fix, Impact, and the Failed Salvage — 2026-06-24
**Series:** MC Setup Research Notes · Note 0002
**Confidence:** Medium — 5 years MC, full-cost. The *bug impact* is definitional (high confidence). The *"you can't salvage the wrongly-blocked trades by exit timing"* verdict rests on a structural causality argument plus a by-year robustness check, but is in-sample on MC only (not yet re-run on RevFT).

**TL;DR:** A feature-tagging join in the pipeline accidentally read each signal's ER (and other indicators) from the *next* bar — one interval in the future. This made an ER10 "skip the chop" gate look brilliant: at a 0.70 threshold it showed **61.7% wins / $192 a trade / PF 1.78**. The fix (sample each feature causally, at the signal bar) collapses that to **52.4% wins / $51 a trade / PF 1.17** — the honest edge. We then asked the natural follow-up: the bug's only "skill" was *declining to take* ~2,100 trades whose efficiency had decayed; can we recover that by **exiting** those trades once the decay is legitimately known? Across an exit-level sweep, a controlled take-profit test, volatility-scaled targets, and a 1-minute drill-down — **no.** The information that flags a trade as bad arrives *after* the trade has already gone against you (97% are underwater by the time it's known), and the one rule that looked like it worked at 1-minute resolution turned out to be the same look-ahead in disguise. **The bug's gain was uncapturable; the resulting bleed cannot be fixed with an exit rule.**

---

## 1. The setup (so this note stands alone)

**The MC CC trade.** The "MC" indicator fires a breakout signal (subtypes CC1–CC5). You enter at the signal bar's close, place a stop a fixed distance away, and target **+1R** (1R = entry-to-stop distance). ES: 1 point = $50/contract, 1 tick = $12.50.

**ER10 — the gate under study.** ER10 is the **intraday Kaufman Efficiency Ratio** over a ~10-minute window (a 2-bar ER on 5-minute bars: net move ÷ sum of bar-to-bar moves, 0 = pure chop, 1 = a clean straight-line move). The idea of an **ER10 ≥ 0.70 gate** is to *only take signals firing into an efficient, trending tape* and skip the chop.

**What "look-ahead" means here.** To gate on ER10 you must attach each signal a value of ER10. The pipeline did this with an as-of join (`merge_asof`) of the per-bar ER series onto the signal's timestamp. **Bars are open-stamped; MC signals are close-stamped.** A signal stamped at a bar's *close* shares its timestamp with the *next* bar's *open* — so the backward as-of join landed each signal on the **entry bar**, whose close is **one interval (5 min) in the future**. The gate was therefore deciding whether to trade using the efficiency of a bar that hadn't happened yet. The same join fed VWAP bands, EMA20, session levels, and market structure — all leaked.

**Cost model used in this note.** The original ER10 study's pin: **$4.36 round-turn commission + 1 tick entry slippage, 0 exit slippage**, 1 contract, 1.0R single-leg target. (Slightly lighter than the house default of $5 + 1 tick/leg; immaterial here — the effects we measure dwarf the cost difference.) All sims replay **real continuous ticks day-by-day**. Signal set: `ba_signals_mc.parquet` (5,580 signals, 2021-06 → 2026-06). Gate tested at **ER10 ≥ 0.70**.

---

## 2. The question

1. **How much did the look-ahead inflate the ER10 gate's results, and what's the honest (causal) number?**
2. **The bug's edge was *not trading* ~2,100 signals whose ER had decayed by the entry-bar close. Causally we can't decline them (at decision time their ER was ≥ gate). But the decayed ER becomes legitimately known a few minutes later. Can we use it as an *exit* to recover the loss those trades bleed?**

---

## 3. How we tested it (the menu)

1. **Reproduce the bug headless** — run the exact same 1R sim twice: pre-fix ER10 (look-ahead) vs causal ER10, at the 0.70 gate.
2. **Identify & size the "phantom-block" set** — the trades the causal book *takes* but the bug *skipped* (causal ER ≥ gate, entry-bar ER < gate). Measure their P&L drag.
3. **Exit-level sweep** — once the decayed ER is known (at the entry bar's close), exit those trades: flat at market, tightened stops (entry−8…entry−1), breakeven, and take-profits (+1…+6 pts).
4. **Control** — is the best take-profit *ER10-specific* or just a generically good exit? Apply it to the *whole* book and split the per-trade effect by flagged / unflagged / random.
5. **Volatility-scaled targets** — replace fixed points with **fractional-R** (0.25–1.0R) and **ABR-%** (0.05–0.15 × prior ATR) take-profits; check **by year**.
6. **1-minute drill-down** — does a finer (1-minute) ER give an *earlier, causal* exit, beating the 5-minute readout? Measure when 1M-ER first drops below gate and where price is at that moment.

Engine: tick-by-tick first-touch (entry at first tick after the signal; stop/target by tick crossing). The fix is one helper, `_causal_at_signal_bar()`, that shifts each developing per-bar feature back one row before the join, wired into all five merge paths (commit `8cbca3e`).

---

## 4. Results

### 4.1 The bug vs the fix — a 3.8× inflation (ER10 ≥ 0.70, 5,580 signals)

| Metric | Pre-fix (look-ahead) | Causal (now live) |
|---|---|---|
| Win % | **61.7%** | 52.4% |
| Expectancy $/trade | **$192.21** | $50.91 |
| Expectancy R | **0.212** | 0.052 |
| Profit Factor | **1.78** | 1.17 |
| SQN | **2.51** | 0.60 |
| Net P&L | **$629,692** | $269,863 |
| Trades (filled) | 3,276 | 5,301 |

The look-ahead inflated per-trade expectancy **3.8×** and added ~**$360k** of phantom net. **How it cheated is the key:** of signals with a defined causal value, the gate flipped its decision on **40.7%** — but almost entirely by **phantom-blocking 2,148 trades** (vs only 118 phantom-passes). It wasn't sneaking chop *in*; it was reading the *future* entry-bar efficiency to **throw out trades that hadn't yet turned choppy at decision time.** Survivorship by time-travel: it traded 38% fewer signals, each pre-vetted with data it couldn't have known. Avg win/loss sizes were identical between modes — the entire "edge" was *selection*, not execution.

### 4.2 The wrongly-blocked trades are genuinely bad — and a big drag

Splitting the causal book (5,301 filled): **3,183 unflagged** (ER still ≥ gate at entry-bar close) vs **2,118 flagged** (the phantom-block set).

| Group | n | Net $ | Exp $/trade |
|---|---|---|---|
| Unflagged (ER held) | 3,183 | **+$629,597** | +$197.80 |
| Flagged (ER decayed) | 2,118 | **−$359,734** | −$169.85 |
| **Whole causal book** | 5,301 | +$269,863 | +$50.91 |

The flagged trades are a **−$360k bleed**; without them the book makes +$630k. So the flag *does* identify bad trades — the bug's instinct was right. The question is whether we can act on it **causally**.

### 4.3 Exit-level sweep — exiting on the flag doesn't help (it mostly hurts)

The decayed ER is known at the **entry bar's close (EB close, ~5 min after entry)**. Applying an exit there to the flagged trades (original stop/target kept as guards; already-closed trades untouched):

| Exit rule | flagged net $ | flagged win % | whole-book net $ |
|---|---|---|---|
| **baseline (no overlay)** | −359,734 | 37.6% | **269,863** |
| flat @ EB close (market) | −381,434 | **3.3%** | 248,163 |
| tighten stop → entry−2pt | −391,009 | 3.2% | 238,588 |
| breakeven stop (entry+0) | −383,409 | 0.6% | 246,188 |
| **take-profit @ entry+4pt ⭐** | −330,222 | 58.2% | **299,375** |

Two reads. **(a)** The `flat @ EB close` win% of **3.3%** is the headline finding: ~**97% of flagged trades are already underwater by the time the flag is known.** The move failed *inside the first 5-minute bar*, before the signal arrives. **(b)** Every stop-tightening row is *worse* than baseline (you forfeit the ~38% that recover to 1R). Only a tight **take-profit** helps, peaking weakly at +4pt: ~**+$30k** whole-book, ~11% over baseline. (Note: an earlier version showed a fake +$355k "recovery" — an artifact of stops filling *at* a level already breached at the decision tick, i.e. booking underwater trades at breakeven. Fixed by filling at market when the level is already passed; the artifact vanished.)

### 4.4 Control — the +4pt take-profit *is* ER10-specific (good news, sort of)

Apply the +4pt take-profit to the **whole** book; split the per-trade delta:

| group | n | mean Δ $/trade |
|---|---|---|
| **FLAGGED** (ER decayed) | 2,118 | **+$13.93** ✅ |
| UNFLAGGED (ER held) | 3,183 | **−$73.86** ❌ |
| RANDOM (size-matched) | 2,118 | −$38.64 ❌ |

The take-profit *helps* the flagged trades and **badly hurts** everything else (it caps the good trades' 1R winners). So the ER10-decay flag genuinely selects the "won't reach 1R — scalp it" trades. The effect is real and not generic — but it only makes bad trades **less bad** (−$170 → −$156), it doesn't make them profitable.

### 4.5 Volatility-scaled targets — no extra juice, and it fails out-of-regime

Replacing fixed points with risk/volatility-scaled take-profits (control = same target on unflagged, must be ≤ 0):

| target | flagged Δ/trade | flagged total Δ | control (unflagged Δ) |
|---|---|---|---|
| **0.05×ABR ⭐** | +$15.57 | +$32,968 | −$73.59 |
| +4pt (fixed) | +$13.93 | +$29,512 | −$73.86 |
| 0.25R | +$12.25 | +$25,953 | −$66.66 |
| ≥ 0.5R | ≈ $0 | ≈ $0 | — |

Scaling by ATR or R **barely beat the crude fixed target** ($33k vs $30k); the edge lives in *tight scalps* however you size them, and anything ≥0.5R is worthless. Worse — **by year** it isn't robust:

| year | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|
| Δ/trade (0.05×ABR) | +$30.76 | **+$47.40** | +$6.71 | **−$10.44** | +$0.08 | +$22.62 |

The +$33k is **carried by 2022** (a high-volatility bear year — ~$22k of the total), is **negative in 2024** and **null in 2025**. That's a regime-dependent artifact, not a durable rule.

### 4.6 1-minute drill-down — the "earlier exit" is look-ahead in disguise

Hope: a 1-minute ER detects the decay *before* the 5-minute close, while price is still salvageable.

| group | % with 1M-ER<gate | median trigger minute | median excursion @ trigger | 1M-exit Δ/trade |
|---|---|---|---|---|
| FLAGGED | **100%** | **min 1** | −0.081R | **+$95.77** |
| UNFLAGGED (control) | **99.2%** | **min 1** | +0.000R | **−$174.96** |

That +$95.77/trade is **not real**, for two reasons:
1. **The 1M-ER isn't a signal.** It's below gate at minute 1 for ~**99% of *all* trades** — flagged and unflagged alike. It carries essentially no information about which trades are bad; the rule degenerates to "exit at +1 minute."
2. **It's non-causal.** The flagged/unflagged label is defined by the **5-minute entry-bar ER, not known until minute 5.** But the overlay exits at **minute 1** — acting on minute-5 knowledge four minutes early. That's the *same look-ahead as the original bug.* The honest causal version (apply to everyone, since you can't tell them apart at minute 1) blends to **−$66.8/trade** — it murders the good trades to save the doomed ones.

So the finer resolution doesn't break the wall — it confirms it. At minute 1 price still *looks* salvageable (−0.08R), but you have no causal way to know *which* trades to bail until minute 5, by which point they're gone (§4.3).

---

## 5. Why it fails

The bug's entire ~$360k "edge" was the act of **not taking** ~2,100 signals whose efficiency decayed. That decision is **unavailable to you causally**: at entry these signals *passed* the gate (their signal-bar ER was ≥ 0.70); the thing that later marks them bad — the entry-bar's efficiency — isn't known until the entry bar closes. And by then **the trade has already failed** (97% underwater at the 5-minute close; the damage happens inside the first bar). Every exit rule we tried is therefore trying to escape a trade that's *already* gone wrong, with information that *only confirms* what price already told you. A tight take-profit shaves the loss a little, but only in violent-chop regimes (2022) and never enough to matter. The 1-minute idea seemed to break this, but only by quietly reusing the future label. **The flag is a good *diagnosis* and a useless *prescription*: it tells you a trade was bad, after it's too late to do anything but ride the stop.**

---

## 6. Recommendation

> **1. Keep the causal fix. Never reintroduce the look-ahead.** The honest ER10≥0.70 book is ~$51/trade, PF 1.17 — a thin real edge, not the $192/PF-1.78 fantasy. Any pre-S34 backtest, WFA run, or saved study that used the tainted features is invalid and must be re-run (the contaminated WFA store is already quarantined).
>
> **2. Do not deploy any exit overlay to "rescue" the wrongly-blocked trades.** Exiting on the ER-decay flag is futile for a structural reason — the signal arrives after the loss. The only thing that survived scrutiny (a tight ~+4pt / 0.05×ABR take-profit on flagged trades) is worth ~$30k in-sample, is **carried by one year (2022)**, goes **negative in 2024**, and adds nothing over a fixed target. Not worth the complexity or the overfit risk.
>
> **3. The bleed is an *entry* problem, not an *exit* problem.** These trades are −EV and you're already in them before you can tell. If anything reduces this drag it will be a **causal pre-trade filter** that declines such signals *at entry* using information available *then* — which is the general MC filter-research line (ER×CC, balance, location, etc.), not an exit hack on this artifact-defined set.

---

## 7. Caveats & open questions

- **In-sample, MC only.** Every salvage test is on `ba_signals_mc.parquet`. None has been re-run on **RevFT** or split into a held-out period beyond the by-year view. The *bug impact* (§4.1) is definitional and needs no OOS; the *salvage negative* (§4.3–4.6) would be strengthened by a RevFT replication — though §4.6's look-ahead argument is structural and regime-independent.
- **The "flagged" set is defined by the (removed) look-ahead** (entry-bar ER < gate). It is a forward-looking label, so it is *not* a causal target you could filter on directly — reinforcing recommendation #3.
- **We tested the *exit* family exhaustively** (flat, stops, fixed & scaled take-profits, finer-resolution timing) and a structural reason explains the uniform failure. We have **not** tested a causal *entry* filter aimed at this drag — that's the open lever.
- **Costs** here are slightly lighter than the house default ($4.36 RT + 1 tick entry vs $5 + 1 tick/leg). The bleed (−$170/trade) and the bug inflation (+$141/trade) are an order of magnitude larger than the cost difference, so conclusions are not cost-sensitive.
- **Fill realism:** overlay stops/targets fill at their level on a mid-path crossing, but at *market* when the level is already breached at the decision tick (the §4.3 artifact fix). Real fills sit between.

---

## 8. Reproduce

Scripts (headless, day-by-day tick replay; import the bug-reproduction helpers from `er_lookahead_tab.py` and drive the production engine — no production code changed):

- `scripts/er10_lookahead_rerun.py` — pre-fix vs causal, full metric table (§4.1)
- `scripts/er10_block_exit_sweep.py` — phantom-block set + EB-close exit-level sweep (§4.2–4.3)
- `scripts/er10_tp_control.py` — is the +4pt TP ER10-specific? (§4.4)
- `scripts/er10_scaled_tp_sweep.py` — fractional-R / ABR-% targets + by-year (§4.5)
- `scripts/er10_1m_leadlag.py` — 1-minute lead/lag drill-down (§4.6)

Saved artifacts (in `docs/living/`): `er10_lookahead_rerun_20260624.md`,
`er10_block_exit_sweep_20260624.md`, `er10_tp_control_20260624.md`,
`er10_scaled_tp_sweep_20260624.md`, `er10_1m_leadlag_20260624.md`.

The fix itself: `indicators._causal_at_signal_bar()` wired into all five `tag_signals` merge paths (commit `8cbca3e`).
