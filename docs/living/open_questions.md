# Open Questions
**Status:** Living — remove questions when resolved, never accumulate answered ones  
**Last Updated:** June 8, 2026  
**Rule:** A question lives here until it has a definitive answer. Once answered, move the decision to the relevant architecture doc and delete it here.

---

## Blocking — Phase A (Data Layer)

**Q1: scid exact binary struct**
Sierra Charts scid is a binary format. The struct must be confirmed from ACSIL documentation before building the parser. Do not guess.
Action: Read ACSIL reference, confirm field sizes, byte order, timestamp format.

**~~Q2: RTH session exact boundaries~~** ✅ Resolved June 3, 2026
Confirmed 08:30–15:15 CT from ESM6 CME tick data. Used this boundary in Streamlit app with correct results.

**Q3: Rollover handling in scid files**
Are scid files per quarterly contract or a continuous stitched series? If quarterly, Python must stitch and handle gaps.
Action: Check what Delani provides. Check SC continuous contract settings.

---

## Blocking — Phase C (Strategy Simulator)

**~~Q4: New signal while already in a trade (same direction)~~** Partially resolved June 7
Scale-in is in scope. The scale-in entry is NOT triggered by a new signal — it is triggered by price pulling back to a predefined PB level (0.25×–1.00× of original stop distance from signal price) after initial entry. New signals while in a trade are still TBD — likely ignored for now.

**Q5: Max concurrent positions**
Options: 1 / 2 / unlimited
Decide on position sizing principles first.

**Q6: Max daily loss rule**
Options: Hard stop $ / No limit
If hard stop, what threshold and based on what?

---

## Blocking — Phase D (Optimizer)

**Q7: Regime classifier timeframe**
5M native (noisy, lookahead risk) vs higher TF (30M, 60M — more stable, cleaner).
Must be decided and documented before scan ranges are defined. Cannot be changed after optimization runs start.

---

## Non-blocking

**Q8: Massive.io purchase**
Deferred until Phase E complete. Used for crosscheck only.

---

## ~~Scale-In Design~~ ✅ Resolved June 8, 2026

**~~Q9: R reference for scale-in trades~~** — T1 uses original R. T2 uses blended R (blended entry → original stop). Blended entry = `(E1_price × tv1 + E2_price × tv2) / tv_total`. Implemented in `_simulate_one_bars_multileg`.

**~~Q10: Does the stop move when we scale in?~~** — Stop stays at original level after E2 fills. Dollar risk on E2 is smaller (entry is closer to stop). This is the implemented behavior.

**~~Q11: Scale-in trigger — tick or bar close?~~** — Bar-based: PB fill is detected when a bar's low (long) trades through the PB level. Same bar-priority rule: Stop > T1 > PB (conservative — T1 wins if both reachable on same bar).

---

## Trade Configuration UI

**Q12: Should slippage and commission be per-trade-mode or global?**
Currently each column (Single Leg, 2-Leg) has its own entry slip, exit slip, stop offset, and commission inputs. This lets you model different assumptions per mode but adds inputs to fill in. Alternative: a single shared Execution section above the columns that applies to all modes. Which is more useful in practice?

**Q13: Is the single-leg "BE Stop" sub-mode the right design, or should it be its own 2nd column?**
Currently "BE Stop" (T1 moves stop to break-even, full position exits at T2) is a radio inside the Single Leg column (`ba_sl_mode = "AIAO" | "BE Stop"`). But mechanically it uses the same 2-phase multileg path as "2-Leg" mode — the only difference is all contracts are on Leg 2. Could be argued it belongs in the 2-Leg column with `C₁=0`. Decide before building 3-leg.
