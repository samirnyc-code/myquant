# Prop-firm rules vs Regime2E — Apex · Take Profit Trader · Topstep

**Purpose:** which prop firm's rules the Regime2E setup (ES, one-per-day with-trend
2E breakout, ~0.30×ADR stop, held to EOD) can actually survive and earn on.
**Sources:** each firm's own help center, scraped verbatim —
`reports/apex_scrape/`, `reports/tpt_scrape/` (Playwright/Chrome; both KBs 403
WebFetch), Topstep via `topstep.com/express-funded-account-rules` + Intercom payout
policy. All rule quotes are from those captures. Dated: 2026-09-14.

---

## 1. The rule that decides everything: drawdown TYPE

For a book that **holds winners to the RTH close**, the single most important rule
is how the trailing drawdown is measured:

| Firm / phase | Trailing-DD basis | Effect on a held-to-EOD book |
|---|---|---|
| **Apex** legacy funded | **INTRADAY** on peak **unrealized** | brutal — a run-up you give back can liquidate you |
| **TPT PRO** (funded) | **INTRADAY** on peak realized+unrealized | brutal — same model |
| **TPT Test** (eval) | **EOD** only | friendly |
| **Topstep** Combine + XFA (funded) | **EOD** only ("highest end-of-day balance") | friendly |

- **Intraday-unrealized** (Apex funded, TPT PRO): the floor ratchets up on the
  highest *tick* of open-trade equity. Ride a trade +$5k then let it come back and
  the floor followed you up — you can be liquidated on a trade that still closes
  green. This is the killer for Regime2E, which by design lets winners run to EOD.
- **EOD** (Topstep, TPT eval): the floor only moves at the close, on realized
  end-of-day balance. Intraday give-back does not tighten it. Far more survivable.

**Headline:** Topstep's funded model is structurally compatible with Regime2E;
Apex's and TPT's funded models fight it.

---

## 2. Verified rule tables (from each firm's help center)

### Take Profit Trader — Test (evaluation)
| Size | Max contracts | Profit target | Max trailing DD (EOD) |
|---|---|---|---|
| $25K | 3 | $1,500 | $1,500 |
| $50K | 6 | $3,000 | $2,000 |
| $75K | 9 | $4,500 | $2,500 |
| $100K | 12 | $6,000 | $3,000 |
| $150K | 15 | $9,000 | $4,500 |

- **DD type:** EOD trailing, calculated only at day close; trails up to the
  starting balance then **locks**. Liquidated if balance (realized **or**
  unrealized) touches the min-account-balance intraday.
- **Consistency:** highest profit day ÷ net P/L must be **< 50%** (Apex legacy was
  30%). If over, you don't fail — target rises to `net P/L × 2`.
- **Min days:** 3 trading days. No max time.

### Take Profit Trader — PRO (funded) — **all SIM**
- **DD type:** **INTRADAY** trailing on peak balance incl. realized **and
  unrealized** gains; locks at **starting balance** (Apex locks at start+$100). DD
  amount = the DD from the test you passed. Max account **$150K → $4,500 DD**
  (Apex went to 300K / $7,500 — so TPT's biggest gives *less* cushion than Apex
  250K/300K).
- **Payouts:** 80/20 split, **day-1 and daily, no min days between payouts**
  (better than Apex). Automated (Plaid/PayPal/Wise), 5–10 s account→wallet.
  Min withdrawal $250 (≤$250 costs a $50 fee).
- **The catch — buffer:** can only withdraw once balance clears
  **start + full DD** ("buffer zone": 25K→$26,500 … 150K→$154,500). The buffer
  itself is released only on **account termination**: **50% if ≤60 trading days,
  80% if >60**. So a DD-sized chunk is held until you close after 60+ days.
- **SIM confirmed:** commissions "within the SIM environment… test and PRO"; PRO+
  is the only account "routed directly to the exchange, not on the simulation."
- **Other PRO rules:** manual only (no bots/algos), no counter positions, must be
  **flat ±1 min around FOMC / NFP / CPI** (and instrument-specific: crude
  inventories, bond auctions), no holding session-to-session, trade ≥1 day/week,
  exit before limit up/down.
- **PRO+ (live, invite-only, discretionary):** 90/10, no buffer, **EOD** DD.

### Topstep — Combine (eval) and Express Funded (XFA, funded, **SIM**)
| Size | Position (minis) | Combine target | Max Loss Limit (EOD trailing) | Daily loss limit |
|---|---|---|---|---|
| $50K | 5 | $3,000 | $2,000 | $1,000 |
| $100K | 10 | $6,000 | $3,000 | $2,000 |
| $150K | 15 | $9,000 | $4,500 | $3,000 |

- **DD type:** **EOD** trailing MLL on highest end-of-day balance, never
  decreases, locks at start. Balance may go below $0 to accommodate MLL.
- **Consistency:** best day ≤ 50% of profit target (else target rises; no fail).
  $150 minimum "winning day."
- **Scaling plan:** position size tied to balance, start at the lowest level — a
  1-ES Regime2E book is always within the lowest level, so unaffected.
- **XFA payouts:** 5 winning days of $150+, **max payout $2k/$3k/$5k** per request,
  90/10 (100% of first $10k lifetime), min payout $125.
- **LFA (Live Funded):** live; no payout caps; daily payouts after 30 winning days.
- No explicit news-flat rule found in the XFA rules doc (unlike TPT).

---

## 3. Regime2E survival under each funded model (real trove ticks, one-per-day)

Same 294-trade Regime2E book, same COST ($17.50/RT incl. slippage) across all runs
so they are directly comparable. Scripts:
`regime2e_apex_intraday.py`, `regime2e_tpt_intraday.py`,
`regime2e_tpt_funded_mc.py`, `regime2e_topstep_eod.py`.

### TPT PRO (intraday-unrealized)
**Sequential 5-yr path:** every plan/size **blows in 2021** (deepest cushion only
−$12 to −$775 — the actual ordering hit a bad give-back early in the ramp).

**Block-bootstrap MC (4k paths, ~49 trades/yr, reshuffles the ordering):**
| plan | size | med yr $ | 10th | 90th | P(down yr) | P(blow<lock) | P(blow<1yr) |
|---|---|---|---|---|---|---|---|
| 25K | 1 | +$87 | −$918 | +$13,280 | 34% | 53.7% | 77.5% |
| 50K | 1 | +$174 | −$1,268 | +$15,220 | 41% | 47.5% | 71.6% |
| 75K | 1 | +$324 | −$1,485 | +$17,380 | 36% | 41.3% | 62.0% |
| 100K | 1 | +$695 | −$1,794 | +$18,931 | 31% | 37.2% | 53.5% |
| **150K** | **1** | **+$6,161** | −$2,065 | +$19,094 | 25% | 26.5% | **38.5%** |
| 150K | 2 | +$500 | −$2,840 | +$32,492 | 37% | 44.9% | 67.6% |
| 150K | 3 | +$382 | −$2,752 | +$40,072 | 34% | 53.5% | 77.1% |

Full output: `reports/regime2e/tpt_funded_mc_out.txt`.

### TPT vs Topstep at the only viable config (150K @ 1 ES)
| Firm (funded) | DD type | median yr $ | **P(blow <1yr)** |
|---|---|---|---|
| **Topstep XFA** | EOD trailing | +$7,818 | **26.5%** |
| **TPT PRO** | intraday-unrealized | +$6,161 | **38.5%** |

The intraday model costs ~12 pp of extra blow risk and ~$1.7k/yr — real but not
night-and-day, because Regime2E's tight ~0.30×ADR stop bounds per-trade unrealized
give-back. The dominant constraint on BOTH is the small $4,500 max DD + the
pre-lock ramp — not the DD type. Neither firm offers Apex's larger 250K/300K
accounts ($6.5k/$7.5k DD), which is where Apex's funded odds were better.

### Topstep XFA (EOD trailing) — block-bootstrap MC (10k paths, ~49 trades/yr)
| plan | size | med yr $ | 10th | 90th | P(down yr) | P(blow<lock) | P(blow<1yr) |
|---|---|---|---|---|---|---|---|
| 50K | 1 | +$251 | −$1,618 | +$17,580 | 42% | 45.8% | 61.5% |
| 100K | 1 | +$5,318 | −$2,335 | +$19,305 | 27% | 30.4% | 42.1% |
| **150K** | **1** | **+$7,818** | −$2,298 | +$19,305 | 20% | 20.9% | **26.5%** |
| 150K | 2 | +$1,140 | −$3,490 | +$37,110 | 37% | 39.7% | 54.3% |
| 150K | 3 | +$652 | −$3,540 | +$49,778 | 42% | 45.3% | 65.4% |

Sequential 5-yr path: only **150K @ 1 ES survives** (+$55,068). Everything smaller
or larger-size blows in the 2021 ramp. Even on the friendly EOD model, 1 ES needs
the 150K account, and year-1 blow risk is ~26% — **almost all of it pre-lock**
(the ramp before the floor locks at start). Sizing up sharply raises blow odds.
Full output: `reports/regime2e/topstep_eod_out.txt`.

---

## 4. Implications for Regime2E (what to actually do)

1. **Firm choice is dominated by DD type, not price or split.** Topstep's EOD
   trailing (Combine → XFA) is the only funded model that doesn't structurally
   punish holding winners to EOD. Prefer **Topstep** for Regime2E as-specified.
2. **If using Apex/TPT funded, the setup must change** — cap unrealized give-back
   (e.g. lock a portion at +Xk, or trail intraday) so a run-up can't ratchet the
   floor past the close. That contradicts the validated "hold to EOD" spec, so it
   needs its own backtest before adoption. Do NOT assume the EOD edge survives an
   intraday-protective exit.
3. **News-flat rule (TPT explicit; check Topstep):** Regime2E holds through the
   day incl. FOMC/NFP/CPI. On TPT PRO you must be flat ±1 min around those — model
   a forced flat/skip on those dates before quoting funded results.
4. **Account size:** TPT tops out at 150K/$4,500 — smaller cushion than Apex
   250K/300K. If staying on an intraday-DD firm, Apex's larger accounts survive
   better (per the Apex MC). Topstep also tops at 150K/$4,500 but EOD, so cushion
   is effectively much larger in practice.
5. **Payout mechanics:** TPT = daily, no min-days, but buffer withheld until 60+
   days. Topstep XFA = 5×$150 winning days + per-payout caps ($5k on 150K). For a
   ~$10k/yr 1-ES book, Topstep's caps and winning-day rule pace withdrawals; TPT's
   buffer delays the first real payout until start+DD is cleared.

---

## 4b. MES fractional sizing — the actual fix (funded phase)

Both firms permit **MES** (0.1× ES; comm $1.50 vs $4.50 ES). 1 ES sits at the edge
of the $4,500 DD — so the lever is to trade a *fraction* of an ES via micros.
Funded blow-risk vs median annual $ (4k-path MC, real ticks,
`regime2e_micro_sizing.py` → `reports/regime2e/micro_sizing_out.txt`):

| Acct | size | **Topstep (EOD)** P(blow<1yr) / med $ | **TPT (intraday)** P(blow<1yr) / med $ |
|---|---|---|---|
| 150K | 0.3 ES (3 MES) | 0.0% / +$2,771 | 0.1% / +$2,758 |
| **150K** | **0.5 ES (5 MES)** | **2.6% / +$4,565** | 6.4% / +$4,468 |
| 150K | 0.7 ES (7 MES) | 11.1% / +$6,255 | 19.3% / +$5,700 |
| 150K | 1.0 ES (10 MES) | 28.2% / +$7,742 | 38.0% / +$6,342 |
| 100K | 0.5 ES | 13.4% / +$4,481 | 20.3% / +$4,171 |
| 50K | 0.5 ES | 30.9% / +$3,715 | 42.7% / +$2,537 |

- **Sweet spot: 150K @ 0.5 ES (5 MES)** — cuts blow risk to ~3% (Topstep) while
  still earning ~$4.5k/yr. At 1 ES it was 28–38%.
- **Topstep (EOD) beats TPT (intraday) at every size**, gap widening with size.
- Smaller accounts can't reach the safe zone without also crushing P&L.

## 4c. Topstep Combine (eval): time to pass + odds

`regime2e_topstep_combine.py` → `reports/regime2e/topstep_combine_out.txt`.
Conditional pass-odds = pass ÷ (pass+blow); target fixed $3k/$6k/$9k, EOD DD +
consistency (best day ≤50% of target). **Eval wants the OPPOSITE size to funded**:
no real capital at risk (only fees + cheap resets), so size UP to pass, then size
DOWN once funded.

| Acct | size | pass-odds | median time |
|---|---|---|---|
| 150K | 1.0 ES | 73% | ~9.5 mo |
| 150K | 1.5 ES | 56% | ~6.2 mo |
| 100K | 0.7 ES | 73% | ~8.9 mo |
| 50K | 0.7 ES | 53% | ~3.9 mo |

Topstep official 2025 base rates (all traders): 16.8% of Combines passed, 51.8% of
people eventually passed, 33.3% of funded got a payout. Fees: Combine ~$49/$99/$199
mo + $149 activation; commissions $4.50 ES / $1.50 MES; 30–40% promo codes common.

---

## 5. Bottom line
- **Only viable config on TPT or Topstep: 150K @ 1 ES.** Sizing up or smaller
  accounts blow >60% of years-1. Even the best config carries ~27% (Topstep) /
  ~39% (TPT) year-1 blow risk, almost all in the pre-lock ramp.
- **Topstep ≻ TPT for Regime2E** (EOD DD, ~12 pp lower blow, +$1.7k/yr) — but both
  are capped at $4,500 DD, which is the real limiter.
- **Apex still wins on cushion** via its 250K/300K accounts; its downside was the
  30% consistency rule and intraday funded DD.
- All numbers use COST $17.50/RT (commission+slippage) for cross-firm parity;
  TPT/Topstep real ES commission is lower ($4.50 / comparable), so live edges up.
- Caveats: block-bootstrap assumes trade-order exchangeability within 15-trade
  blocks; the news-flat rule (TPT) is NOT yet modeled and would force flats/skips
  on FOMC/NFP/CPI days.
