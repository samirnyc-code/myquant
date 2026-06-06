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
