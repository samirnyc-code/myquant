# Open Questions
**Status:** Living — remove questions when resolved, never accumulate answered ones  
**Last Updated:** June 7, 2026  
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

## Scale-In Design (to resolve next session — June 8)

**Q9: What is the R reference for scale-in trades?**
After scaling in, "1R" is ambiguous. Options:
- Original risk only (signal→stop, fixed): simple, comparable across all trades
- Blended entry risk (weighted average entry → stop): accurate P&L but harder to interpret
- Per-leg risk (each leg has its own R): most granular but complex
Decision needed before the simulator is built.

**Q10: Does the stop move when we scale in?**
If we add at 0.5R pullback and the stop stays at the original level, the dollar risk on the new leg is smaller than the original (entry is closer to stop). If we widen the stop to maintain the same risk per leg, the total dollar risk grows. Which behavior do we want?

**Q11: What triggers scale-in — tick data or bar close?**
Current simulator uses tick data for entry fills (stop-order: price must trade through the level). Scale-in at a PB level likely uses the same logic. Confirm: scale-in fills are tick-based, same as initial entry.

---

## Trade Configuration UI

**Q12: Should slippage and commission be per-trade-mode or global?**
Currently each column (Single Leg, 2-Leg) has its own entry slip, exit slip, stop offset, and commission inputs. This lets you model different assumptions per mode but adds inputs to fill in. Alternative: a single shared Execution section above the columns that applies to all modes. Which is more useful in practice?

**Q13: Is the single-leg "BE Stop" sub-mode the right design, or should it be its own 2nd column?**
Currently "BE Stop" (T1 moves stop to break-even, full position exits at T2) is a radio inside the Single Leg column (`ba_sl_mode = "AIAO" | "BE Stop"`). But mechanically it uses the same 2-phase multileg path as "2-Leg" mode — the only difference is all contracts are on Leg 2. Could be argued it belongs in the 2-Leg column with `C₁=0`. Decide before building 3-leg.
