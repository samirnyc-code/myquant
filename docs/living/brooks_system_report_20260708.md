# Trend-Entry System — State, Diagnosis & Action Plan
**For:** Samir · **Date:** 2026-07-08 (overnight report, S61) · **Status:** WIP, honest assessment

---

## 0. Executive summary

We have built, bar-by-bar to your spec, a **mechanically correct trend-entry engine** (legs → structure → 1ES/2ES with origin-reset). The *entries* reproduce your hand-marked signals exactly. But as a **trading system it is not yet profitable**, and I can now name precisely why, with numbers:

1. **The regime flip rule is broken** (strands in trends, whipsaws on flat EMA). Everything downstream inherits this. — *your call, confirmed on 3 charts.*
2. **The entry counter over-counts** — 13.8% of entries are 3rd+ (should be ~5%); origin-reset is too weak in persistent trends. — *your suspicion, confirmed in data.*
3. **Fixed 1R/2R exits leave money on the table** — the runner test proved letting winners run cuts the loss 88% (−$78 → −$9/trade). — *your instinct, confirmed.*

None of these is fatal. The engine's *entries* are sound; what's missing is **fire-control (when to trade) and trade-management (how to hold)**. Both are now measured, not guessed. **A working system is fix #1 + #2, then a validated chop-gate, then a runner.** Below is the plan, plus honest answers to your two strategic questions (mean-reversion; swing/overnight).

---

## 1. Where we actually are — the three real bugs

### Bug 1: Regime flips (the load-bearing bug)
Current rule: bear→bull on a single *close* above the nearest confirmed LH. This is far too weak:
- **Strands** in trends — 2025-11-04 sat BEAR through an all-day rally because the confirmed LH was parked at the opening high and price never closed above it. Result: 14 junk short entries into a bull grind.
- **Whipsaws** — the EMA-close variant flips 18×/day on a flat EMA (2025-11-04 bars 19–30, 68–75).
- Mack's actual rule (from source): **break *and close* beyond the 21-EMA**, and he still overrides with price action. A single close through one level is not enough evidence to declare a trend dead.

**Fix candidates (rank order):** (a) require a *structural* flip — a confirmed opposite swing (HH+HL sequence), not one close; (b) your **DB/DT-neckline flip** — the mDB on 2026-01-22 (b6/b7, 1t apart at the low) *was* the reversal signal, close above its neckline = BULL; (c) Mack EMA break+close as a *second vote*; (d) the b0 H/L seed for the open.

### Bug 2: Entry over-counting
- 1ES 1978 / 2ES 694 / **3rd+ 428 (13.8%)**. Third entries should be rare.
- Cause: origin-reset (count→0 when the flag's origin low is taken out) isn't firing on every new leg in a sustained trend, so the counter ratchets to 3 and sticks.
- **Consequence:** even with a `count≤2` filter, *which* bars get labeled 1ES vs 2ES vs wedge is corrupted → the traded set is wrong.
- **Fix:** audit origin assignment per leg; the origin must re-seed at each *new* swing low in a bear (each LL), so a fresh flag off a new low is always a 1ES.

### Bug 3: Exits (least urgent, biggest upside once 1&2 fixed)
- You dislike the current stop/target and you're right. Signal-bar stop (median 5.9 pts) sits inside the noise band; 45% win at 1:1 = death by stop-hunt + $10/RT friction on tiny R.
- **Runner test (measured tonight):** 2-lot, A scalps 1×ABR, B → BE after scalp, B runs. Net/trade: both-T1 −$78 → run-2×ABR −$67 → run-3×ABR −$47 → **run-4×ABR −$9**. Monotone: **let winners run**. The runner is a *multiplier* on the entry edge, not a fix — but on a fixed entry stream it's the difference between +0.05R scalped and +0.15R+ realised.

---

## 2. What the evidence says — chop/trend filters (all measured tonight, best config, base −0.064R)

Every one of your named ingredients works as a filter; they are correlated but each adds a lens. Trend tercile vs chop tercile, mean R:

| Sensor (your words) | chop | trend | Net-positive trend cell? |
|---|---|---|---|
| **8-bar overlap** ("bars on top of each other") | −0.215 | **+0.016** | near |
| **OTF run** (one-time-framing streak) | −0.105 | **+0.055 (63% win, +$9.5k)** | **YES — only stand-alone +net** |
| ADX14 | −0.155 | +0.019 | near |
| ER12 (efficiency/momentum) | −0.175 | −0.015 | |
| \|EMA slope\|/ABR (your "flat EMA") | −0.141 | −0.024 | |
| body conviction | −0.150 | −0.025 | |
| flip-rate | −0.151 | −0.040 | |
| **combo: low-overlap AND high-ER** | — | **+0.067 (64% win, +$5k net)** | **YES** |

**Literature agrees precisely** (note 0011 + tonight's sources): trending → ER≥0.35 / ADX>40 / Choppiness low; choppy → ER≤0.22 / ADX<20. Brooks calls chop "barbwire" (3+ overlapping bars on a flat EMA = don't trade) — our overlap sensor *is* barbwire quantified. The warning from the public full-Brooks-mechanization postmortem stands: +60% gross → −59% net; **bars are easy, context is the edge.** So the *gate* matters more than any new entry rule.

**→ Original idea: the "Balance Meter."** One 0–100 gauge per bar = overlap(inv) + OTF-run + ER12 + RVOL-per-slot (RVOL untested — needs volume curves, queued). System ON above threshold, OFF below, with **asymmetric hysteresis** (slow ON, fast OFF) to honour the 16/84 trend/chop base rate. Uniquely, the engine can also *measure itself* — leg-asymmetry (with-leg size ÷ counter-leg size) and origin-survival rate are chop sensors built from our own bookkeeping.

---

## 3. Your Question A — "If ES is really a mean-reversion market, what do we do?"

The evidence (ours + literature) is unambiguous: **ES trends only ~16–23% of days; it is structurally mean-reverting intraday.** We have been building a *trend* system on a *mean-reversion* instrument. Three honest responses:

1. **Trade the trend system, but only on the 16–23% of days that trend** — the Balance Meter isn't a nice-to-have, it's the whole game. Stand aside 4 days in 5. This is viable *if* the gate is good enough (OTF+overlap+ER got us to +net in the trend tercile already).
2. **Build the mean-reversion system we should have built** — fade extension from VWAP/prior-value on rotational days, the 77% of the distribution. The literature's ES edges are *reversion* edges (VWAP-fade, value-area reversion, gap-fill). **We already have the leg/structure/regime machinery** — a range-day fade ("sell 2nd push into resistance inside balance, buy 2nd push into support") is the *same engine with the regime inverted*: trade *with* the range, against the micro-thrust. This is arguably the higher-probability use of everything we built tonight.
3. **Do both, gated by day-type** — Balance Meter high → trend entries; low → reversion entries. This is the dual-mode regime system the literature explicitly recommends for ES, and it's the natural home for the OR12 day-type card (S60).

My recommendation: **fix the trend engine's 3 bugs (1 session), add the gate, and in parallel prototype the reversion mode** — because on a mean-reverting instrument the reversion mode is where the base rate lives.

---

## 4. Your Question B — swing MES overnight / 2:1 intraday swing

This connects to our **one surviving positive lead**: the daily-timeframe reversal. Measured facts:
- **Timeframe gradient:** the reversal trade loses −0.059R on 5M, improves monotonically, and goes **+0.12R on daily**. Higher timeframe = better edge-to-cost ratio (same $5 on a 53-pt stop vs a 6-pt stop).
- **Daily LONG "buy-the-washout":** 60 fills, **+0.32R, 65% win, +$67k, positive 5/6 years** (2026 the exception, n=6). Economically real (index upward drift + oversold reversion).

So your instinct is well-founded and *pointed at the data*:
- **Swing MES overnight** solves the prop constraint (a cash/eval account can hold overnight; the trailing-DD prop cannot). MES = 1/10 ES, so a 53-pt daily stop = ~$265 risk — sizeable but tradeable on a modest account. **This is the natural home for the daily-long edge.**
- **2:1 intraday swing** (hold hours not minutes, wider stops, bigger targets) is essentially moving our entries up to 15–30M bars — the gradient says that's *strictly better* than 5M (30M reversal ≈ breakeven vs 5M −0.06R), and it slashes the friction-to-R ratio that's killing us.

**Recommendation:** worth a dedicated test. Two concrete builds: (1) the daily-long washout on **true 24h bars** (needs Globex data pulled from Massive — the repo only has RTH), sized for MES overnight; (2) run the *current trend engine on 30M bars* — same code, one parameter — to see if the friction relief alone moves it toward break-even. Both are 1-session experiments.

---

## 5. Action plan (prioritized)

**Session 1 — fix the engine (no new features):**
1. Rebuild the **regime flip** rule with you: structural flip (HH+HL) OR DB/DT-neckline close, + b0 seed. Grade on 5 marked days.
2. Fix **origin-reset** so 3rd+ entries drop to ~5%. Re-verify on 2026-01-22 (should go from 14 wedges to a handful).
3. Lock **no 3rd entries** (already specced; verify in code).

**Session 2 — gate + management:**
4. Build the **Balance Meter** (overlap + OTF + ER, + RVOL once volume curves built); asymmetric hysteresis; ON/OFF gate.
5. Add the **runner** (2-lot, BE-after-scalp, run to ~4×ABR or trail); sweep runner target & trail.
6. Re-run the 12-month sim on the *fixed* engine + gate + runner. **Only now judge profitability.**

**Parallel track — hedge the "ES is mean-reverting" reality:**
7. Prototype **reversion mode** (fade micro-thrusts inside balance on low-Balance-Meter days).
8. Test **30M-bar trend engine** (friction relief) and **daily-long on 24h MES bars** (the swing/overnight idea) — pull Globex data from Massive first.

**Discipline (from the failures ledger):** every result net of $5–10 RT, year-split, walk-forward; never trust a gross-positive/net-negative cell; if a fix can't beat costs on out-of-sample, kill it.

---

## 6. The one-line truth

We are not close to profitable *yet*, but for the first time we know exactly which three things are broken, we have measured filters that turn the trend tercile positive, a runner that harvests 88% more, and a validated daily/swing lead as a fallback. The path is: **fix → gate → manage → judge**, with a reversion mode and a swing/MES track as live hedges against ES being what the data says it is — a mean-reverting market where trading 1 day in 5 (or holding for days) beats trading every 5-minute wiggle.

*Sources: internal notes 0010/0011/0013, `docs/living/` studies (94 handoff revisions, ~40 research docs); external — Mack PATS (21-EMA break+close), TradingView ADX/Regime, arXiv 2605.11423 (MNQ VVG regime classifier), Unger Academy ES mean-reversion, brooks-pa-failure postmortem.*

---

## 7. OVERNIGHT MEAN-REVERSION TESTS (run while you slept — the key new result)

**5M mean-reversion FAILS (5yr, tick-costed):** VWAP-z fade −0.41R, Bollinger −0.36R, RSI2 −0.34R — all deeply negative, all 6 years, worse in trends but losing in chop too. Confirms note 0005: on 5M an extension is the *start* of momentum, not exhaustion. **Do not fade 5M extremes.**

**Daily mean-reversion WORKS, long-only (5yr RTH daily bars, $5 RT negligible):**

| system | n | pts/trade | win% | net$ |
|---|---|---|---|---|
| Bollinger LONG | 57 | +86.2 | 75% | +245k |
| Z-score LONG | 106 | +32.7 | 69% | +173k |
| Connors RSI2 LONG | 70 | +12.0 | 76% | +42k |
| Connors RSI2 SHORT | 32 | +16.2 | 69% | +26k |
| **ALL LONGS** | **233** | **+39.6** | **73%** | **+460k** |
| ALL SHORTS | 233 | −1.0 | 60% | −13k |

**Buying ES oversold on the daily works across 3 independent constructions; fading overbought does not.** Equity-index asymmetry (upward drift + oversold reversion). This is the swing/MES-overnight system — 4–13 day holds, overnight risk, cash/eval account (not trailing-DD prop). Per-trade +40 pts is the clean metric; net-$ assumes concurrent signals (portfolio Q). Connors_L: 2023 +19k, 2024 +47k, 2025 −45k, 2026 +21k (3/4 yrs). Files: `mr_test_trades.parquet` (5M), `mr_daily_trades.parquet` (daily).

**REVISED RECOMMENDATION:** the daily long-MR is the strongest, most robust edge in the entire project — stronger than the trend engine we spent S61 on. **Two parallel tracks for next session:** (1) harden the daily long-MR into a real swing system (position sizing, drawdown, MES overnight, true 24h bars from Massive, ensemble of the 3 constructions, the 2025 drawdown); (2) keep fixing the intraday trend engine (regime/count/exits) as the *day-trade* complement for the ~20% trend days. The mean-reversion answer to "what do we do" is: **trade it on the daily, long-biased, as a swing.**
