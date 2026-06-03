# Open Questions
**Status:** Living — remove questions when resolved, never accumulate answered ones  
**Last Updated:** June 3, 2026  
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

**Q4: New signal while already in a trade (same direction)**
Options: Ignore / Scale in / Reset
Decision changes results materially. Must be decided before simulator is built.

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
