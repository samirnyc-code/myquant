# Apex Trader Funding — rules + 2E-book fit (S118, 2026-09-14)
Researched from 2026 rule references (apextraderfunding.com blocks bots). VERIFY on the live site before buying.

## ⚠️ Apex ≠ Take Profit Trader. The DD TRAILS your peak — it is NOT the static floor we modeled for TPT.

### Two drawdown models (this choice decides everything for a hold-to-EOD book)
- **Intraday** (classic/legacy "FULL"; **"Daily Drawdown: None" in the screenshot ⇒ these ARE intraday**):
  trails the real-time peak balance **including UNREALIZED open profit**, every tick. Harsh for a book
  whose winners take heat and give back intraday.
- **EOD**: trails the highest **end-of-day** balance − threshold; recalculated 4:59 PM ET. Has a Daily Loss Limit.

### Lock / Safety Net (both models)
- Threshold stops trailing once EOD balance reaches **Safety Net = start + threshold + $100**; then the
  floor **locks at start + $100** forever. Pre-safety-net contract cap = **half** the max.

### Plans (legacy FULL, from screenshot)
| plan | start | threshold | contracts | eval profit goal | cost/mo (coupon) | PA fee |
|---|---|---|---|---|---|---|
| 150K | $150k | $5,000 | 17 (8 pre-SN) | $9,000 | $49.70 | $125 |
| 250K | $250k | $6,500 | 27 | $15,000 | $59.70 | $125 |
| 300K | $300k | $7,500 | 35 | $20,000 | $69.70 | $125 |
- Daily drawdown: None (⇒ intraday). Scaling: None.

### Other rules
- **Consistency rule (PA only, not eval):** no single day > **50%** of total profit since last payout. Resets per
  payout, gone after the 6th. **A problem for our lumpy book — one big trend day can defer a payout.**
- Payouts: min **$500**; **8 trading days** between payouts (eval needs ~5–7 qualifying days); **6 payouts then
  the account closes**; 100% of first $25k then 90/10.
- Flat + orders cancelled by **4:59 PM ET** (we're flat at the RTH close — fine). No overnight. No news hedging.

## 2E-book fit — `scripts/regime2e_apex_sim.py` (EOD model, 1 ES, net of $17.50/tr)
Survives all plans because the big drawdowns land AFTER the floor locks; the binding risk is the **un-locked ramp**.

| mode | 150K margin-to-floor | 250K | 300K | eval-pass (1 ES) |
|---|---|---|---|---|
| **one_per_day** | +$1,245 | +$2,745 | +$3,745 | 150K ~9mo / 250K ~1yr / 300K ~3yr |
| flip | **+$235** (too thin) | +$1,735 | +$2,735 | later (needs a big day) |

- Worst EOD peak-to-trough drawdown ≈ **−$7.3k–7.7k**, but it occurs post-lock (floor = start+$100), so it survives.
- **one_per_day is far safer on Apex** than flip (smaller ramp DD). flip on 150K clears the floor by only $235 — no.
- **INTRADAY model (what the legacy FULL actually is): our measured intraday equity DD ~$7–9k exceeds every
  threshold, and unrealized peaks ratchet the floor — a hold-to-EOD book is a BAD fit. Use the EOD variant.**

## Recommendation
1. **Confirm the account is EOD, not intraday.** If only intraday FULL is on offer, this book is a poor fit there.
2. On **EOD**: **150K, one-per-day** is the value pick — smallest eval goal ($9k, fastest to pass at low size),
   survives with ~$1.2k ramp margin, cheapest. **250K** buys ~$1.5k more ramp cushion for +$10/mo and a $15k eval
   — the conservative choice if the thin backtest margin worries us (it should; backtests flatter).
3. Pass the eval faster by sizing up **during eval only** (cap allows 8/13/17), then drop to 1 ES on the PA.
4. Plan payouts around the 50% consistency rule (request often; a single FOMC-type day can block a withdrawal).
