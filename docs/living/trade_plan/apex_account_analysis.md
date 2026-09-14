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

## ✅ CORRECTION (2026-09-14): sized in MES it WORKS — earlier "poor fit" was a whole-ES artifact
The fix I missed: size in MICROS *below* 1-ES-equiv so the $ ramp DD fits the trailing floor. Official Apex
Rithmic fees: **ES $3.98 RT / MES $1.02 RT** (my earlier MES $6.25 was ~6× too high; no $200/mo sub on legacy,
just $49.70). `regime2e_apex_mes.py`, legacy 150K intraday $5,000, real ticks:
| size | =ES | result | deepest cushion | net/yr |
|---|---|---|---|---|
| 5 MES | 0.5 | SURVIVES | +$2,420 | ~$5,230 |
| 8 MES | 0.8 | SURVIVES | +$872 | ~$8,370 |
| 10 MES (=1 ES) | 1.0 | BLOWN | −$160 | — |
| ≥12 MES | ≥1.2 | BLOWN | neg | — |

- **Apex legacy 150K IS viable at ≤8 MES.** 5 MES = safe (+$2.4k cushion, ~$5.2k/yr); 8 MES = ~$8.4k/yr but thin
  (+$872, backtest-flattered). 10 MES (=1 ES) is the cliff. Max survivable ~8–9 MES.
- Same picture on the EOD $4k model (5 MES +$1,919 / 8 MES +$670). All blow risk is the pre-lock ramp (Nov-2021).
- Scale income via MULTIPLE 150K accounts at 5–8 MES each (Apex allows many) — but separate machine/IP/card per
  account (two-partner sharing/copy ban). Post-lock (banked $5,100) the floor is BE+$100, so sizing up after the
  lock is feasible — trade small through the ramp, larger once locked.
- ⇒ The whole-ES sims above ("150K blows at 1 ES") stand for 1 ES but are NOT the verdict — micro-sizing is.

## Dynamic MES scaling (trade small through ramp, grow with cushion) — `regime2e_apex_scale.py`
Sizer: size = clamp(base, floor(cushion/R), cap); cushion = realized − floor. It STAYS at base through the ramp
(cushion small) and scales only after the cushion builds → same ramp safety as flat-base, big income upside.
| rule | result | final | ~/yr | peak size | deepest cushion |
|---|---|---|---|---|---|
| flat 5 MES | survives | +$26.8k | $5.2k | 5c | +$2,420 |
| **base5 +1c/$1,000 cush** | survives | +$99.6k | **$19.5k** | 100c | **+$2,420 (= flat-5, no added ramp risk)** |
| base5 +1c/$750 | survives | +$134k | $26.2k | 100c | +$2,320 |
| base5 +1c/$500 | survives | +$159k | $31.1k | 100c | +$1,434 |
| base8 +1c/$500 | survives | +$187k | $36.5k | 100c | +$772 |

- ⚠️⚠️ CORRECTION: the "$99k / $19.5k-yr" was OVERSTATED — a COMPOUNDING MIRAGE. The equity "explosion" is the
  SIZE growing 5→100 MES (fixed-fractional), NOT the edge (the book's edge was weaker in 2026 than 2024). Fees are
  trivial ($2.27/contract; $227 at 100 MES). The problems: (a) 100 MES on a 150K acct is reckless — one bad day ≈
  −$25k, a −40pt trend day ≈ −$20k; the "survival" was PATH LUCK (no killer sequence hit at max size); (b) assumes
  ZERO withdrawals; real payout caps ($2,750 first-5) + 30% consistency force withdrawals that shrink cushion→size.
- **Realistic with a sane size cap (`regime2e_apex_scale_math.py`):** cap 10 MES → +$41.6k / ~$8.1k/yr; cap 20 MES
  → ~$12.3k/yr. Scaling with the cushion DOES beat flat-5 (~$5k/yr) with no added ramp risk — but the honest
  number is **~$8–12k/yr at a 10–20 MES cap**, not $19.5k+. NEXT: model withdrawals for true take-home.

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
