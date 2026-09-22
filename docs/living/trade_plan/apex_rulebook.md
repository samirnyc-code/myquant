# Apex Legacy 150K — VERIFIED RULEBOOK (build the sim to THIS)
**S118 · 2026-09-14 · every rule quoted verbatim from Apex's own pages (scraped via Playwright; the site 403s
bots). Source .txt files in `reports/apex_scrape/`. Read this BEFORE any further simulation.**

Ordering note (self-critique, honest): the sims in `apex_account_analysis.md` were built BEFORE this rulebook.
Two funded-account rules below (30% MAE, 5:1 RR) were never modeled → **all FUNDED numbers there are provisional.**
The EVAL numbers are NOT affected (the 5 trading rules are PA-only — see §B).

---

## A. DRAWDOWN — legacy FULL = INTRADAY trailing (eval AND funded)
Source: `legacy-evaluation-rules`, `legacy-pa-payout-parameters`, `legacy-performance-account-pa-trading-rules`.
- **Intraday, on unrealized highs (verbatim):** "the trailing threshold is based on the **highest live value during
  trades, not on closed trade values**." Enforced in real time; if balance (incl. unrealized) touches it → liquidation.
- **Funded uses the SAME rule as eval** (both intraday-trailing). Legacy FULL is NOT EOD. (Apex's EOD DD is a
  separate current-4.0 product, not this.)
- **Lock:** "The trailing drawdown in a PA account stops at the starting balance plus $100." Triggered once EOD
  balance reaches start + drawdown + $100 (150K → $155,100 → floor locks at $150,100).
- **150K drawdown = $5,000; max 17 minis / 170 micros.**
- **Platform eval difference:** RITHMIC — "the drawdown stops trailing when the threshold balance reaches your
  profit target." TRADOVATE — "the trailing drawdown continues to trail in evaluations and does not stop."

## B. FUNDED-PA-ONLY TRADING RULES ("These rules only apply to the Legacy Performance Accounts")
Source: `legacy-performance-account-pa-trading-rules`.
1. **Contract Scaling:** "restricted to trading **half** of their maximum allowed contracts until they reach the
   trailing threshold stop." (150K → 85 MES until safety net.) NOT binding for us (we'd trade ≤8 MES).
2. **⚠ 30% Negative P&L Rule (MAE):** "the **live, unrealized, open negative P&L cannot exceed 30% of the account's
   profit balance at the start of the day**." Relaxes to 50% once EOD profit ≥ 2× safety net. **NOT MODELED.**
3. **⚠ 5:1 Risk-Reward Rule:** "your **stop loss should not exceed five times the amount of your profit target**."
   **NOT MODELED** — and our hold-to-EOD book has NO fixed target + a ~17pt stop, so this may not even permit our
   order structure as-is. Needs interpretation/confirmation.
4. **Hedging Rule:** no simultaneous long+short on same/correlated instrument. (We're single-position — fine.)
5. **One Direction Rule:** only one direction at a time, no both-sides orders. (Fine.)
- Violations → "payout request denials, account resets, fund removals or placement on trader probation."

## C. PAYOUTS (funded) — Source: `legacy-pa-payout-parameters`, `legacy-safety-net-requirement-rule`
- **Split:** "100% of the first $25,000 per account… and 90% after that." Separately: "To qualify for 100% payouts,
  traders must first complete **five approved payouts**. Starting with the sixth payout, you can withdraw 100%."
- **Max payout, first 5 (verbatim table):** 150K = **$2,750**. "**No Maximum After Fifth Payout**… provided the
  minimum balance threshold remains." (Account does NOT close after 6 — that's a 4.0 rule, not legacy.)
- **Min payout $500.** Requirements: "**8 Trading Days**" + "**Profit on 5 Days** (≥$50)."
- **Safety net (first 3 payouts only):** balance must exceed start+DD+$100; encroachment ≤ $500 allowed.
- **Min balance to request (150K): $155,100.**
- **30% Consistency Rule (windfall):** "no single trading day accounts for **more than 30%** of the total profit
  balance at the time of a payout request." Formula: Highest Day ÷ 0.3 = min total profit needed. Applies until the
  6th payout or transfer to Live.

## D. EVAL — Source: `legacy-evaluation-rules`
- **7 trading days minimum** (non-consecutive), **no maximum time**. Profit goal 150K = **$9,000, net of commissions**.
- **Resets unlimited** ("as many times as necessary"); must still log 7 days. (Reset fee ~$80 — verify.)
- Consistency rule "applies mainly to PA and Funded accounts" — **not the eval.** The 5 PA trading rules (§B) are
  PA-only → **eval sims are unaffected by MAE/5:1.**
- **All trades flat by 4:59 PM ET; "Holding trades through the close is not permitted."** (We flatten at the RTH
  close ~4:00 ET — compliant.)

## E. FEES — Source: `rithmic-commissions-instruments`
- **ES $1.99/side = $3.98 RT. MES $0.51/side = $1.02 RT.** Deducted from balance at trade time. (No $200/mo sub on
  legacy — just the monthly account fee, 150K = $49.70 w/ coupon.)

## F. STRUCTURAL — Source: risk disclosure + prohibited activities (`legacy-pa-payout-parameters`)
- **"Reward payouts are discretionary."** Simulated environment, no real capital / no live execution.
- **Inactivity rule** (PA can go dormant/closed) — verify exact threshold for legacy.
- **Prohibited:** using the trailing threshold as a stop; small-target/large-stop; "**stockpiling evaluation
  accounts… to cycle through and intentionally 'blow up' accounts**"; **sharing MAC/computers/IPs/credit cards or
  trade copying with other traders** (⇒ Samir & Thomas need fully separate everything); deviating from professional
  standards.

---

## G. IMPACT ON OUR SIMS — what's valid, what's provisional (blunt)
- **VALID:** eval pass-time by MES size (`regime2e_apex_eval_mes.py`) — eval has intraday DD (modeled) and none of
  the PA-only rules. 5 MES 0%-blow/~14.5mo … 20 MES 60%-blow/~2mo stands.
- **PROVISIONAL / likely WRONG:** every funded number (`regime2e_apex_mes.py`, `_scale.py`, `_scale_math.py`,
  `regime2e_apex_intraday.py`). Reasons:
  - **30% MAE not modeled.** Early ramp, profit is small → 30% of it is a tiny allowed open loss. Our stop at 5 MES
    ≈ $425; if start-of-day profit < ~$1,400, a normal stop VIOLATES the rule. This likely forces even smaller size
    (or skipping trades) exactly when the account is smallest → slower ramp, maybe unviable at the sizes I quoted.
  - **5:1 RR not modeled** and may forbid a no-target, wide-stop hold-to-EOD order outright. Open question.
- **NEXT (only after sign-off):** one funded sim that enforces §A + §B (esp. 30% MAE) + §E fees. Expect it to be
  WORSE than the provisional funded numbers, possibly materially. Do not trust the ~$8–12k/yr funded figure until then.

## H. OPEN QUESTIONS to confirm with Apex (not in scraped pages / ambiguous)
1. 5:1 RR with a hold-to-EOD, no-fixed-target order — how is "profit target" defined? Does our structure comply?
2. Exact legacy inactivity threshold.
3. Legacy reset fee (assumed ~$80).
4. Does the 30% MAE use profit balance = (balance − start), and is it checked tick-by-tick intraday?
