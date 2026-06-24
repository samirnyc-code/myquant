# Forensic — the multileg (2-leg) P&L bug: when it entered, why it survived

**Date:** June 24, 2026. Companion to `BUG_multileg_pnl_scaling.md`.

## Timeline (git + handoff)
- **`1fe5cdf` "feat: WFA infrastructure"** — FIRST WFA commit. `_simulate_one_multileg` is born
  here, already with `RiskDollar = risk_pts/ts * tv1` (leg-1 only). **exp-R inflation present from day one.**
- **`ebd83fe`** "add PB scale-in to tick engine" — adds pullback path; same leg-1-only RiskDollar.
- **June 8, 2026** — "2-Leg Scale-In mode" formalized (handoff spec section).
- **`d8b7046` (S17)** — "2-leg T2 E2-style" — T2 redefined blended→e2-style; P&L semantics changed.

## Proof (airtight invariant)
Scale-out D = leg1(1c→1R) + leg2(1c→2R), same entry/stop. Each leg must equal its standalone
single-leg book → correct total = single1R $162,393 + single2R $232,593 = **$394,986**.
Engine returned **$878,003 = 2.22×**. PF 1.38→2.24 (**losses under-counted**).
Also: ML both-legs@2R = $762,678 vs 2×$232,593=$465,186 (**3.28×**).

## Two confirmed defects
1. `sim_engine:670` `RiskDollar = …*tv1` (leg-1 only) but NetPnL sums both legs → exp R ~2× high.
2. Net $ over-counted ~1.6–2.2× with PF inflation → stop/loss leg mis-charged (mechanism localized
   to leg summation / stop path; exact line in the bug-file fix checklist).

## Why it survived (the lesson)
All multileg validation (`validate_oracle`, `validate_ratchet` vec==loop, `validate_scalein_sweep`
fast==oracle) checks **consistency, not magnitude**. Same conceptual error in all paths → all agree,
all wrong. **The invariant "2 identical legs = 2× one leg" was never tested.** (Parallel to the S19
look-ahead: tagging called "safe" but the signal-bar-vs-entry-bar join was never tested.)

## Historical impact
- S26 scale-out ($417–464k): inflated, but conclusion "flat 1R beats scale-out" HOLDS (scale-out
  was flattered and still lost).
- **S20 "$599k was 2-Leg mode, not a bug":** likely INFLATED by this bug. User distrusted it; the
  "legitimate config" reassurance was incomplete. Trust-relevant (S39).
- S31 ZLO/MC multileg + any saved multileg WFA/BA run: inflated ~1.6×, guilty.

## Fix order
1. Add the "2 identical legs = 2× single" invariant test FIRST (so it can't silently return).
2. Fix leg P&L + stop-leg charge in `_simulate_one_multileg`; mirror in `_simulate_one_3leg`.
3. Fix `RiskDollar` to total active risk (E1+E2), not tv1.
4. Re-validate; re-trust multileg results only after the invariant passes.
