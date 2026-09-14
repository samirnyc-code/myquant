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

### Other rules — ⚠️ CORRECTED 2026-09-14 (earlier draft wrongly used Apex 4.0/CURRENT rules; these are LEGACY)
Source: legacy PA payout-parameters + legacy consistency help pages (search snippets; site 403s direct fetch — verify verbatim).
- **Consistency rule = 30%** (NOT 50%): no single day > 30% of total profit balance at a payout request. STRICTER;
  our fat-tail book needs ~3.3× a big day's profit banked before that day can be withdrawn.
- **Account does NOT close after 6 payouts** (that is a 4.0 rule). Legacy: from the 6th payout on the MAX payout is
  UNLIMITED (keep min balance); early payouts are capped by a ladder, then caps drop away. Earlier "$20.5k lifetime
  ceiling then re-eval" was WRONG for legacy — one account can run indefinitely.
- Min payout **$500**; **8 trading days** before a payout; **safety-net (DD+$100) required only for the first 3
  payouts**; split **100% of first $25k per account, then 90/10**.
- Flat by the close (we're flat at RTH close — fine). No overnight. No news hedging.
- Legacy has BOTH intraday-trailing and EOD variants; screenshot "Daily DD None" ⇒ intraday. EOD-vs-intraday is
  still the decisive fit question.

## 2E-book fit — CONFIRMED: legacy FULL DD is INTRADAY (peak unrealized), scraped from Apex
Source (verbatim): Legacy Evaluation Rules — "the trailing threshold is based on the **highest live value
during trades, not on closed trade values**." So the floor ratchets on the intraday UNREALIZED peak and the
account can liquidate mid-trade. This is the WORST DD type for a hold-to-EOD book.

**INTRADAY-model survival (`regime2e_apex_intraday.py`, one_per_day, real ticks, actual 5-yr path):**
| plan | 1 ES | 2 ES | 3 ES |
|---|---|---|---|
| **150K ($5k)** | **BLOWN 2021-11-24** (deepest −$98) | BLOWN | BLOWN |
| 250K ($6.5k) | survives (+$1,402) | BLOWN | BLOWN |
| 300K ($7.5k) | survives (+$2,402) | BLOWN | BLOWN |

- 150K blows even at 1 ES (survived under the wrong EOD model at +$1,245 — the real intraday model kills it).
- Only 250K/300K survive, and ONLY at exactly 1 ES, on thin margins — and backtests flatter, so marginal.
- Any size ≥2 contracts blows every plan. No room to scale.
- ⚠️ The earlier EOD-model numbers (`regime2e_apex_sim.py`, one_per_day +$1,245/etc.) are SUPERSEDED — wrong
  DD model. Ignore them.

## Apex EOD-drawdown accounts (current 4.0 line) — checked, still too tight
Apex DOES offer EOD-drawdown accounts, but only **25K–150K (no 250K/300K EOD)**. 150K-EOD: **$4,000** DD
(recalc at 4:59 ET close, trails highest EOD balance, locks at start+$100), 10 contracts (tier-scaled),
Daily Loss Limit, 50% consistency, 6-payout close, 100% split. DD MODEL is right (no intraday-unrealized
ratchet) BUT the $4k cap is too small:
| EOD account (one_per_day, 1 ES) | result |
|---|---|
| 150K-EOD ($4,000) | survives by only **+$245** (daily basis; add intraday floor-enforcement + DLL + backtest optimism ⇒ effectively blows) |
| 100K-EOD ($3,000) | BLOWN Nov-2021 |
| 50K-EOD ($2,000) | BLOWN |

**Root cause / the real lesson:** our ramp drawdown ≈ $4.8k FROM A RUNNING PEAK is too big for ANY *trailing*
floor (Apex intraday OR EOD). It only survives a *static* floor: Apex-EOD-$4k trailing → +$245; TPT static-$4.5k
→ +$3,022. ⇒ For this book, want a **STATIC (non-trailing) end-of-day drawdown**. Apex has none. TPT-style fits.

## Recommendation — REVISED after confirming the intraday DD
**Apex legacy FULL is a poor fit for this hold-to-EOD book.** The intraday-on-unrealized trailing DD ratchets the
floor on every intraday high and can liquidate mid-trade — exactly what a book that rides winners to the close
gives back. Result: **150K blows even at 1 ES; only 250K/300K survive at strictly 1 ES on thin, backtest-flattered
margins; nothing scales past 1 contract.**
1. **Do NOT take the 150K.** It blows at 1 ES on the real DD model.
2. **250K/300K only, and only at exactly 1 ES** — and even then treat the +$1.4k/+$2.4k cushions as marginal
   (live is worse than backtest; the single historical path barely survives). Not a confident yes.
3. **No scaling ever** — 2 contracts blows every plan. That caps income at the 1-ES rate (~$10k/yr gross), against
   which the 30% consistency rule + first-5-payout caps + discretionary payouts are meaningful drags.
4. **The right vehicle for this book is an END-OF-DAY / static-drawdown firm** (e.g. the Take Profit Trader $4,500
   EOD account we modeled first — there 1 ES survived comfortably). Match the DD type to the strategy: a hold-to-
   EOD book wants an EOD-measured drawdown, not intraday-on-unrealized.
5. Watch-outs regardless of firm: 30% consistency rule (accumulate ~3.3× a big day before withdrawing), first 5
   payouts capped ($2,750 on 150K) then uncapped from the 6th, min balance to withdraw = start+DD+$100, and the
   two-partner ban on shared machines/IPs/cards + trade-copying (Samir & Thomas need fully separate setups).
