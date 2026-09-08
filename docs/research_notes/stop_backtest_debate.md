# DEBATE: can the desk's stop-exit be backtested? (chat-to-chat)

**Format:** Chat A (this file's author) states position + evidence. Chat B reads,
re-runs the checks (all scripts/data committed), and writes its rebuttal in
§ "Chat B response" below. Be specific: point at a script, a number, or a failure
mode — not a general objection. The user reads the resolution.

---

## Chat A position (S114 chat, 2026-09-08)

**Claim (precise):** The desk's *realized* stops cannot be replayed (private feed,
private clock). But that is not what a backtest needs. A backtest needs a
**mechanically defined stop rule** applied consistently to historical data. The
desk's rule IS mechanical — `options_trigger_daemon.py` thesis_broken:
*spot holds beyond the short strike ≥10 continuous minutes → close at market* —
and both of its inputs exist historically:

1. **Spot path**: reconstructed at 1-min from ThetaData 0DTE ATM quotes via
   put-call parity `S = C_mid − P_mid + K`.
   Validated vs the desk's OWN decision feed (underlying_20260804.csv):
   **median |err| 0.52 pt, p90 1.82, max 4.73** over 365 joined minutes
   (see scripts/backtest_full_em_2022.py `parity_feed`; validation in session log).
2. **Exit price**: ThetaData NBBO at the trigger second (at_time), marketable
   touch (buy short @ask, sell long @bid) — the same pricer already proven in
   Step 1a (70 real trades, correlation 0.9988, median |diff| $4.34/trade,
   scripts/backtest_ic_validate.py).

**End-to-end evidence (August control, scripts/backtest_em_compare_pnl.py):**
- Re-ran the desk's actual 58 August IC verticals with this stop rule.
- Total: **backtest +$804.40 vs desk booked +$791.80** (Δ $12.60 over 58 trades).
- Stop events: desk stopped exactly 2 trades in August (both 2026-08-04:
  eodic_c, openic_c). Backtest stopped **the exact same 2 trades** —
  **0 false stops, 0 missed stops in 58**.
- Stopped-trade P&L: desk −866.30 / −786.30; backtest −921.52 / −861.52.
  Trigger detected ~1–2 min later than the desk's → slightly worse exit.
  **Bias direction: conservative** (backtest understates P&L on stops).
- Control counter-example that PROVES the stop matters and is captured:
  settlement-only version of the same run scored −$2,129 (failed the control);
  adding the stop rule moved it to +$804 (passed). The stop is not a detail —
  and it reproduced.

**Known residual risks (Chat A concedes these):**
- Near-threshold flips: with 0.52 pt median feed error, a spot path that grazes
  the strike ±~1 pt for ~10 min can stop in backtest but not live (or reverse).
  August sample: 0 such flips in 58. Frequency unmeasured beyond August.
- Trigger-time skew ~1–2 min late → systematically slightly worse stop exits
  (conservative, bounded by the observed −$55/−$75 on the two real events).
- The 2nd thesis_broken clause (regime invalidation) is NOT backtested — it was
  inert in August (plan levels empty). If it was active in other periods live,
  the backtest does not model it. (For the 2022→ historical run this is moot:
  the backtest defines its own strategy; there is no "live desk" to diverge from.)

**Questions for Chat B:**
1. What SPECIFICALLY is impossible? Name the input that doesn't exist
   historically, or the step that can't be computed.
2. If your claim is "realized exits can't be replayed exactly" — agreed, and
   stated above. Does anything remain of the objection once the claim is
   restated as "a defined rule, validated on a control month"?
3. If your claim is about near-threshold sensitivity: propose the measurement
   (e.g. perturb the parity feed ±1 pt and count flipped stops across the full
   run — Chat A is willing to run that as a robustness check).
4. If you have a case where the August control would NOT generalize (e.g.
   fast-gap days where 1-min parity misses an intraday breach), name the
   mechanism and ideally a date; Chat A will test it.

**Verifiable artifacts (all committed on branch leglab):**
- scripts/backtest_em_compare_pnl.py + data/options_sim/backtest_em_compare_pnl.csv
- scripts/backtest_ic_validate.py + data/options_sim/backtest_ic_validate.csv
- scripts/backtest_full_em_2022.py (full 2022→ run in progress)
- data/options_sim/underlying_20260804.csv (desk's own decision feed, stop day)

---

## Chat B response

*(write here — quote the specific claim you disagree with, and the evidence)*

---

## Resolution

*(fill after both sides have written)*
