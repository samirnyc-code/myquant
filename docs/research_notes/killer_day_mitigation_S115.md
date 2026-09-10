# Killer-Day Mitigation — S115 Definitive Research Note

**Date:** 2026-09-10 (S115, chat B) · **Branch state:** files only, not committed tonight per instruction
**Data:** `data/options_sim/backtest_full/killer_context.csv` (1,080 days, 2022-05-16 → 2026-09-04), `rows.csv` (vix252 streams), `fly_rows.csv`
**Scripts:** `scripts/killerday/` (forensics per day, 6 family sweeps, stack, adversarial audit) · **Results CSVs:** `data/options_sim/backtest_full/killerday/`
**Split everywhere below:** train = 2022–2024 (661 days), test = 2025–2026 (419 days). Baselines (train/test): ic −21,720/−3,203 · fly −125,857/−74,691 · puts_band +11,781/+3,146.

---

## 1. Executive summary — can catastrophic days be mitigated?

**Partially — and less than the raw sweeps claim.**

- **33 killer days** were forensically dissected (news reconstruction + local trade rows). **22 of 33 (67%) were flaggable before the 08:30 CT entry** — by the vol regime, the calendar, or our own entry credits. **11 of 33 (33%) were pure intraday ambushes** with a quiet open, calm VIX, and no scheduled event: no day-level filter can touch them.
- **~26 of 33 killer days opened with |gap| < 0.5%.** The quiet open is the trap signature, not a safety signal.
- The rule sweeps produced dozens of "ROBUST" filters, but **adversarial verification (random-skip Monte-Carlo null + Bonferroni ×395 comparisons, `scripts/killerday/adversarial_audit.py`) kills almost all of them: only 21/174 audited rule×book combos survive, and 16 of those 21 are on the fly book.** Zero ic single rules and zero puts_band single rules survive as proven.
- **The one strongly confirmed mechanism** (p_bonf ≈ 2e-6): the **fly book is destroyed in elevated/rising-vol regimes** (skip_vix>25 fly, prior_ret≤−1.0, cr_p>3.0, total_cr>3.0 all confirm the same factor). The correct action is **retire the fly book** (−$200k baseline, still −$20k after its best stack), not filter it.
- **The one safe-by-construction rule:** the **puts_band −1000 intraday flatten** — pessimistic fill bound ≈ $0 cost, MID estimate +3,183/+3,966 train/test, 0 winners lost. Adoptable now (advisory-desk terms).
- **The best unproven hypotheses** — surgical **ic call-leg drop when call credit is rich (>2.0–3.0)** (+4.2–4.8k train / +6.4–7.7k test, joint p 0.003–0.005, Bonferroni-dead) and the **FOMC 12:30 CT flatten** (currently an accounting upper bound, ic +12.1k/+5.6k vs honest skip_FOMC +2.1k/+2.0k) — go to **stage-2 tomorrow**: minute-level ThetaData sim on the v2 engine.
- Headline stack numbers (ic −24.9k → +45.5k total) are **selection artifacts** (greedy accepted/pruned on marginal TEST delta) and must not be booked. Direction is real on a few members; magnitudes are not validated.
- Per the desk hard rule, everything here is **advisory-only — no trade is ever blocked**; survivors ship as flags and are judged on the forward record.

---

## 2. The killer-day dossier

### 2a. One row per day

| Date | Cause (≤8 words) | Sched. event? | Flag by 08:30? | Signals that fired |
|---|---|---|---|---|
| 2022-05-20 | OpEx whipsaw at bear-market touch, no news | OpEx | YES | EM 1.85%, VIX 29, post −4% day, put cr 0.95 vs call 4.80 |
| 2022-06-07 | Down-gap faded; one-way rip through calls | — | no | call cr 0.10 (thin gate), gap-down w/ flat VIX |
| 2022-06-09 | Hawkish ECB premarket; CPI-eve grind-down | ECB + claims | YES | ECB out pre-entry, put:call credit 8:1 (2.85/0.35), CPI-eve |
| 2022-11-08 | Election drift; FTX rescue reversal | Midterms (not in cal) | no | election not in calendar; FTX crypto-only premarket |
| 2023-02-14 | Hot CPI; two-way travel, flat close | CPI | YES | CPI flag + hot print pre-entry, put cr 5.4 vs 0.85, EM rich vs quiet tape |
| 2023-03-13 | SVB Monday; regional-bank whipsaw | — (bank crisis) | YES | VIX 24.8 rising, put cr 6.70 vs 0.95, gap-down despite backstop |
| 2023-05-02 | Regional-bank rout on FOMC-eve | FOMC-eve, JOLTS | YES | call cr 0.00 (broken gate), FRC seizure 24h old, FOMC-eve |
| 2023-09-15 | Triple witching + TSMC + UAW drift | Quarterly OpEx | YES | put:call credit 44:1 (2.20/0.05), VIX 12.8 complacency, OpEx |
| 2023-10-12 | Hot CPI + tailed 30y auction | CPI + 30y auction | YES | CPI flag, hot print pre-entry, 3y/10y auctions already tailed |
| 2023-12-20 | 0DTE put-flow flush at 52wk highs | — | no | none; VIX 12.5, gap −0.08%, call cr 0.05 only |
| 2024-04-09 | CPI-eve de-risk round trip | — (CPI next day) | no | CPI-eve not flagged; gold record/Iran watch soft only |
| 2024-04-30 | Hot ECI on FOMC-eve, month-end | ECI, FOMC-eve | YES | ECI hot at 07:30 CT, call cr 0.05 vs put 1.75, month-end |
| 2024-05-31 | MSCI rebalance two-sided whipsaw | PCE, MSCI rebal | no | rebalance calendar only; VIX 14.5, thin credits |
| 2024-08-01 | ISM 46.8 ambush after claims spike | ISM (not in cal), claims | YES | claims 249k pre-entry, BOJ/yen stress, post-FOMC euphoria entry |
| 2024-12-18 | FOMC hawkish cut, dot-plot shock | FOMC + SEP | YES | FOMC flag; VIX creep 13.8→15.9 at highs; call cr 0.50 into binary |
| 2024-12-20 | Cool PCE relief rip, triple witching | PCE + OpEx | YES | PCE out pre-entry, VIX 24 falling post-shock, call cr 0.2 vs put 2.6 |
| 2025-02-21 | OpEx + PMI/UMich stagflation prints | OpEx + data 08:45/09:00 | no | data slate post-entry; call cr 0.05; VIX 15.7 calm |
| 2025-02-28 | Month-end melt-up through calls | PCE, Zelensky, mo-end | YES | prior range 2.30% vs EM 1.33%, VIX 21 +2, desk bleeding 4 days |
| 2025-03-03 | Tariff D-day eve; afternoon confirmation | ISM + tariff deadline | YES | tariff effective-date public since 2/27, realized >> implied |
| 2025-03-26 | Midday auto-tariff announcement | — | no | VIX 17 falling, gap −0.09%; call cr 0.10 only (wrong wing) |
| 2025-04-07 | Crash day 3; fake-pause 8% whipsaw | — | YES | VIX 45→60 premkt, Nikkei −7.8%, EM 2.9%, put cr 12.3 vs 0.4 |
| 2025-04-08 | Relief gap fully reversed; 104% confirmed | — (de facto deadline) | YES | VIX 47, gap +2.6% into unresolved binary, call cr 13.9 vs 0.35 |
| 2025-04-09 | Real 90-day pause; +9.5% melt-up | — (FOMC min., 10y auct.) | YES | VIX 52.3, EM 3.3%, back-to-back 7–8% ranges, fat 2-sided credits |
| 2025-10-10 | Trump China-tariff post from ATH | — (shutdown blackout) | no | VIX 16.4, gap +0.08%; only soft tell = unanswered MOFCOM escalation |
| 2025-10-22 | Reuters software-curb exclusive midday | — | no | call cr −0.05 (broken); gold −6% prior day (soft); VIX 17.9 falling |
| 2025-12-12 | AVGO −11%; Oracle/OpenAI delay report | — | no | VIX 14.9 falling day-after-record; call cr 0.00; single-name only |
| 2026-01-21 | Greenland walk-back relief rip | — (Trump at Davos) | YES | day-after −2.06% shock, VIX 20 +4.2, call cr 1.45 = richest in window |
| 2026-02-12 | AI-displacement contagion de-gross | — (claims benign) | no | credits 0.2/0.3 thin; software rout was sector-level, not in features |
| 2026-03-09 | Oil-shock morning; peace-headline V-reversal | — | YES | VIX 29.5 +24%, WTI→$119 overnight, gap-down on −1.33% day, EM 1.86% |
| 2026-03-31 | Iran peace melt-up +2.9% | Cons. conf. (minor), Q-end | YES | VIX 30.6 war regime, gap +0.82% after −8%, put cr 0.05 vs call 3.90 |
| 2026-06-09 | Midday AI air pocket, full recovery | — | YES | prior2_ret −2.64% (NFP crash), put cr 0.05/0.25, CPI-eve stacking |
| 2026-06-17 | Warsh debut FOMC; dot-plot hike flip | FOMC + SEP + debut | YES | FOMC flag; event credits 1.7/1.6 vs 0.45/0.5 prior day; VIX silent |
| 2026-07-29 | FOMC hold; 30y-yield-spike dump | FOMC | YES | FOMC flag; put cr 3.0 vs call 0.7; EM 85pts on flat tape |

### 2b. Narratives by type

**Type A — scheduled-event kills (the calendar knew).** FOMC days are the purest case: [2024-12-18](https://www.cnbc.com/2024/12/18/fed-meeting-live-updates-traders-await-december-interest-rate-cut.html) (hawkish-cut dot plot, −2.95%, VIX +74%), [2026-06-17](https://www.cnbc.com/2026/06/17/warsh-fed-meeting-stock-market.html) (Warsh debut, dot plot flipped to a hike), [2026-07-29](https://www.cnn.com/2026/07/29/business/bond-yields-fed-warsh) (hold read as behind-the-curve, 30y to 2007 highs). In all three the morning was dead flat and 100% of the damage came after the 13:00 CT statement — the 08:30 WAIT gate structurally cannot touch it. CPI killed twice ([2023-02-14](https://www.zacks.com/stock/news/2054132/pre-markets-treat-strong-cpi-as-good-news) two-way travel with a flat close — all fly, every IC settled green; [2023-10-12](https://www.nasdaq.com/articles/treasuries-us-yields-rise-after-inflation-data-weak-30-year-bond-auction) where the real killer was the tailed 30-year auction at 12:00 CT). Data our calendar does not carry did the rest: ECB ([2022-06-09](https://www.ecb.europa.eu/press/pr/date/2022/html/ecb.mp220609~122666c272.en.html)), ISM ([2024-08-01](https://www.prnewswire.com/news-releases/manufacturing-pmi-at-46-8-july-2024-manufacturing-ism-report-on-business-302211321.html), 2025-03-03), ECI ([2024-04-30](https://www.cnbc.com/amp/2024/04/30/treasury-yields-rise-ahead-of-fed-meeting.html)), OpEx/rebalance days ([2022-05-20 ~$1.9T](https://www.bloomberg.com/news/articles/2022-05-19/battered-stock-traders-get-ready-for-1-9-trillion-option-expiry), [2023-09-15](https://www.kiplinger.com/investing/stocks/stock-market-today-uaw-strike-sends-stocks-lower), [2024-05-31 MSCI](https://www.nbcnews.com/business/markets/dow-closes-570-points-higher-post-best-day-2024-stocks-rcna154986), [2024-12-20 ~$6.6T](https://www.cboe.com/insights/posts/index-insights-december-2024/), 2025-02-21), elections (2022-11-08 — event column blank).

**Type B — crash/headline-regime continuation (the tape knew).** The April 2025 tariff cluster ([04-07 fake-pause 8% whipsaw](https://www.politifact.com/factchecks/2025/apr/08/tweets/trump-hassett-tariff-pause-stock-market-rally-x/), [04-08 relief gap fully reversed](https://www.cnbc.com/2025/04/08/stock-market-today-live-updates-.html), [04-09 real pause +9.52%](https://www.cbsnews.com/news/stock-market-today-dow-jones-china-tariffs-trump-04-09-25/)), the 2026 Iran war ([03-09 oil to $119 then V-reversal](https://fortune.com/2026/03/09/trump-iran-war-end-very-soon-oil-sanctions-strait-hormuz-navy-escort/), [03-31 peace melt-up +2.91%](https://www.pbs.org/newshour/economy/wall-street-hits-record-as-sp-500-continues-2-week-rally-boosted-by-hopes-for-iran-wars-end)), SVB Monday ([2023-03-13](https://www.cnbc.com/2023/03/13/first-republic-drops-bank-stocks-decline.html)), the Greenland walk-back ([2026-01-21](https://www.nbcnews.com/business/economy/trump-pauses-greenland-tariffs-rcna255270)), day-2-after-crash ([2026-06-09](https://edition.cnn.com/2026/06/09/investing/nasdaq-sp500-dow-drop-ai)), and the month-end squeeze inside a deteriorating tape (2025-02-28). Common signature: VIX ≥ 20–52 and/or prior ranges ≥ 2× EM, extreme one-sided credits (8:1 to 44:1), unresolved binary headline risk. Every mechanical vol/regime feature we carry fired. **Note the direction lesson: 8+ of these kills were UPSIDE (calls run over) — a downside-only defense loses a third of the time.**

**Type C — intraday ambushes (nothing knew).** [2025-10-10](https://www.cnbc.com/2025/10/11/trump-post-costs-stocks-2-trillion-in-single-day.html) (Trump post at 09:57 CT from 2 pts off ATH, VIX 16), [2023-12-20](https://www.barchart.com/story/news/22887500/zero-day-options-in-spotlight-for-sp-500s-sharp-decline) (0DTE put-flow cascade, no news at all), [2026-02-12](https://finance.yahoo.com/news/live/stock-market-today-dow-sp-500-nasdaq-sink-as-tech-gets-hit-as-ai-disruption-fears-grow-gold-bitcoin-sink-210353533.html) (AI-displacement contagion), [2025-03-26](https://www.cnn.com/2025/03/26/economy/auto-tariffs-announcement) (midday auto-tariff presser), [2025-10-22](https://ca.finance.yahoo.com/news/exclusive-us-considering-curbs-exports-192758229.html) (Reuters exclusive), [2025-12-12](https://www.cnbc.com/2025/12/12/broadcom-tumbles-10percent-after-earnings-as-ai-trade-sells-off-.html), 2022-06-07, 2022-11-08, 2024-04-09, 2024-05-31, 2025-02-21. Signature: gap < 0.3%, VIX < 18 and often falling, no Tier-1 event, frequently a broken/near-zero credit on ONE side (the only in-system tell, and it flags the structure, not the day). These are unfixable at day level; they are the case for the intraday circuit breaker and for sizing as the primary tail control ([Cboe/Schwartz](https://www.cboe.com/insights/posts/henry-schwartzs-zero-day-spx-iron-condor-strategy-a-deep-dive), [Vilkov 0DTE](https://github.com/vilkovgr/0dte-strategies/blob/main/docs/paper/paper-annotated.md)).

---

## 3. What the forensics say statistically

- **22/33 (67%) detectable by 08:30 CT**; 11/33 (33%) ambushes.
- **What flagged the detectable ones** (overlapping):
  - **Vol regime** (VIX ≥ ~20–25, spike, or prior-range ≥ 2× EM): ~13 days — the whole Type-B family.
  - **Calendar carried by the engine** (FOMC/CPI/NFP): only **5 of 33** (3 FOMC + 2 CPI). **Calendar gaps caused misses on at least 8 more:** ECB, ISM (×2), ECI, OpEx/witching (×5), MSCI rebalance, elections, Treasury auctions, tariff effective-dates.
  - **Own entry credits** (broken ≤0, thin <0.10, or extreme skew ≥ ~3:1): fired on ~17 of 33 days — the single most frequent tell, and the only one that also fires on some ambush days (10-22, 12-12, 02-21, 03-26 flagged the *structure* even when the day looked calm).
- **The quiet-open trap:** ~26/33 killer days opened with |gap| < 0.5%. Gap-based filters alone are near-useless on this population.
- **Direction:** ~8 kills were upside/call-side, ~10 were two-sided whipsaws, remainder downside. Several losses were **stop-manufactured, not settlement losses** (2024-12-20 close never breached the short call; 2026-06-09 every stopped put finished OTM; 2023-02-14 all ICs settled green; 2022-11-08 and 2024-05-31 EM-width ICs survived while flies died) — the loss mode is often *travel + stop width vs credit*, which no day-skip fixes.
- **Timing:** on FOMC days and several headline days, all damage is post-13:00 CT; on Type-B days it is continuous; on ambush days it is a 30–90-minute midday air pocket.

---

## 4. Rules that SURVIVED adversarial verification (per book)

Verification = re-run reproduction (all 7 scripts regenerate CSVs byte-identical, no lookahead found) **plus** random-skip Monte-Carlo null + Bonferroni across ~395 comparisons (`adversarial_audit_20260910.csv`). Survivors are few.

### fly — one confirmed mechanism, terminal conclusion
| Rule | Train Δ | Test Δ | p_bonf | Verdict |
|---|---|---|---|---|
| skip_vix>25 | +37,188 | +23,616 | **2e-6** | CONFIRMED — genuine selectivity (skipped days avg −$483 vs −$186 base) |
| prior_ret≤−1.0 / \|prior_ret\|≥1.0 | +30,853/+60,109 | +29,832/+34,610 | 3e-5 / 0.023 | CONFIRMED — fly needs quiet days |
| skip_day_if_cr_p>2.5/3.0 | +35,011/+31,808 | +35,896/+34,517 | 0.047/0.0002 | CONFIRMED — fly dies when puts are bid |
| skip_day_if_total_cr>3.0 | +51,869 | +55,530 | 0.001 | CONFIRMED — vol-regime selectivity |
| vixchg>3 / accel2d>3 / 2day_both_up1 / vix-vs-5dma/10dma | various | various | 0.0002–0.012 | CONFIRMED — same rising-vol factor, count as ONE |

**Economic story:** all of these are correlated expressions of a single factor — the ATM fly is structurally short realized vol and gets destroyed whenever vol is elevated or rising. The stacked fly still ends **−$20.2k** total with 903 days zeroed. **Action: retire the fly book.** That is the entire actionable content of the fly column.

### puts_band — one safe rule
| Rule | Train Δ | Test Δ | Bounds | Verdict |
|---|---|---|---|---|
| flatten at day P&L ≤ −1000 (intraday breaker) | +3,183 (MID) | +3,966 (MID) | PESS −47/0 · OPT +6,799/+7,685 | **CONFIRMED by dominance** — worst-case fill cost ≈ $0, 0 winners lost |
| skip_day_if_total_cr<1.0 (dead-tape floor) | +1,165 | +5,145 | joint p 0.024, fails ×395 | WEAKENED — coherent, cheap hygiene; dollar value unproven |

**Economic story:** the credit band already filters entries, so a −$1,000 day means both put spreads stopped on a real selloff with nothing left to recover — flattening forfeits ~nothing even under worst fills. This is the only rule in the entire study whose **sign is safe without further data**.

### ic — nothing proven; two live hypotheses
| Hypothesis | Train Δ | Test Δ | Status |
|---|---|---|---|
| ic_drop_call_leg_if_cr_c>2.0/2.5/3.0 (surgical) | +4.8k/+4.2k/+3.8k | +7.7k/+7.3k/+6.4k | WEAKENED — direction consistent (test>train all thresholds, ex-April +4.5–5.7k), joint p 0.0034–0.0047, but train contribution ≈ random and the 3 thresholds are one correlated rule. **Stage-2 candidate.** |
| flatten at day P&L ≤ −1000 (breaker) | +7,398 (MID) | +10,547 (MID) | WEAKENED — 40/60 killer days caught, 0 winners lost, but PESS bound is **−16,435/−6,380**: the sign flips under pessimistic fills. **Stage-2 decides.** |
| FOMC close-12:30 | +12,132 (bound) | +5,627 (bound) | Not tested — accounting upper bound; honest bracket is [skip_FOMC +2,080/+2,042, bound]. **Stage-2 decides.** |

**Zero ic whole-day skip rules survive.** The S114 rich-credit premise holds asymmetrically at best: call-side only, as a leg-level hypothesis.

---

## 5. Rules that FAILED — and why (honesty section)

The sweep's ROBUST criterion (delta>0 in both halves, no significance test, no multiplicity control) **approves noise by design**. Failure modes, with the worst offenders:

- **April-2025 cluster fits.** The tariff week (≤7 skips) carries 50–100% of test deltas across the vol/gap/range families. Ex-April: skip_vix>25 ic **−378**, total_cr>3.0 ic **−1,813**, vix/5dma>1.10 ic **−3,387**, prior_range≥3&gap **−2,771**, prior_range≥4.0 combined **exactly 0**. These are one week wearing a rule costume.
- **Single-day deltas.** Event-family test deltas have top-1-day shares ≥ 1.0: skip_FOMC ic 1.32 (ex-top1 negative), skip_ANY_EVENT ic 2.3, skip_NFP ~1.0–1.2. One day exceeds the whole claimed OOS edge → REFUTED across the board, including all skip_flies_* variants.
- **Beta masquerading as alpha.** On a book losing $186–195/day, skipping anything "works." Several claimed-ROBUST rules were *worse than skipping random days* (train MC p>0.8): band_c_0.5-2.5 fly (p 0.998 — the fly stack's #1 member), fly thin-credit floors (p 0.94–0.9999), combined loss-stand-downs (p 0.82–0.90).
- **Fitted families.** skip_event_if_credit_ABOVE and _BELOW both claimed robust on the same ~50 event days — the signature of a threshold grid fitted to noise. All 15+ variants refuted.
- **Both-directions VIX rules on ic.** Every ic vol-skip fails (ex-April negative on most); ic day-skips on credit richness fail (half of each test delta is one day). puts_band is *hurt* by every VIX filter — its profits concentrate on high-vol fat-credit days, consistent with [Vilkov's high-VIX-tercile result](https://github.com/vilkovgr/0dte-strategies/blob/main/docs/paper/paper-annotated.md) that binary high-VIX skips discard the best-paid days.
- **Day-after stand-downs on ic/puts.** The day after a killer is a *recovery* day for ic (avg +$48, 67% win) and puts_band (+$100, 67%) — consistent with [Kaminski & Lo](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=968338): stop/halt rules only pay when losses cluster, and ours don't on those books (they do on fly).
- **Pooled circuit breakers.** All fly and pooled ic+fly breakers DEAD at every threshold — fly stop churn trips the trigger 188–424 days and forfeits the settle recoveries that pay for the book.
- **The stacks.** Greedy add/prune keyed on marginal TEST delta = optimizing on the holdout twice; LOYO was measured on membership chosen with all years visible; two unverified components (breaker MID, FOMC bound) sit inside all four stacks. The fly (+180k "recovered", still −20k) and combined (+173.8k, still −36.7k) stacks are bookkeeping on a dead sleeve.

---

## 6. Recommended stack per book (with the required caveats)

**Do not book the deltas below as validated P&L** — membership was test-selected (§5). They are the best current *candidate configuration*, to be shipped advisory-only and judged forward.

| Book | Configuration | Train Δ | Test Δ | Killer days avoided | Book total before → after | maxDD |
|---|---|---|---|---|---|---|
| **ic** | drop call leg if cr_c>2.0/2.5/3.0 + breaker −1000 (stage-2 pending) + total_cr<1.0 floor + FOMC 12:30 exit (stage-2 pending) + loss<−1500-until-VIX-down | +32,533 | +37,904 | 35 | −24.9k → +45.5k | 32.6k → 12.3k |
| **puts_band** | total_cr<1.0 floor + breaker −1000 + FOMC 12:30 exit + cr_p<0.5 floor | +5,976 | +10,010 | 8 | +14.9k → +30.9k | 8.4k → 3.3k |
| **fly** | **RETIRE** (best stack still −20.2k with 903 days zeroed) | — | — | — | −200.5k → 0 by not trading | — |
| **combined** | do not run a pooled book; run ic + puts_band separately | — | — | — | — | — |

Killer-day before/after detail: `data/options_sim/backtest_full/killerday/stack_killer_days_20260910.csv` (all 193 baseline killer days < −$1,500, baseline vs stacked); per-rule marginals in `stack_rules_20260910.csv`; LOYO in `stack_loyo_20260910.csv` (positive all 20 book-years — with the selection caveat above).

**What is adoptable tonight vs pending:**
- Adoptable (advisory flags): fly retirement decision on record; puts_band −1000 breaker; dead-tape credit floors as hygiene.
- Pending stage-2 (tomorrow): ic breaker sign, FOMC 12:30 flatten value, call-leg-drop confirmation.
- Live-build gaps found in the executability audit: daemon needs a both-sides pre-fire quote stage, gap-at-fire computation, cross-day cooldown state file, live day-P&L aggregation + flatten-all action; backtest credits are ThetaData marks vs live IB quotes (thresholds transfer approximately).

---

## 7. What we cannot fix at day level — and the stage-2 plan

**Unfixable at day level:**
1. **The 11 ambush days** (§2c): quiet open, calm VIX, no event, kill arrives midday. Only an intraday marked-book breaker, structural sizing, or wing width touches these. Practitioner consensus says sizing is the primary tail control, not stops ([Schwartz: "set-and-forget with proper position sizing"](https://www.cboe.com/insights/posts/henry-schwartzs-zero-day-spx-iron-condor-strategy-a-deep-dive); [Vilkov: size to expected-shortfall budgets](https://github.com/vilkovgr/0dte-strategies/blob/main/docs/paper/paper-annotated.md)).
2. **The FOMC afternoon.** Statement 13:00 CT, presser 13:30 CT; pre-announcement hours have *below*-normal vol ([Lucca-Moench](https://www.bostonfed.org/-/media/Documents/conference/PDF/Lucca_preFOMCDrift.pdf)); ~65% of first moves reverse by the close. A morning entry gate provides zero protection; the intervention must be a 12:30 flatten and/or a post-presser re-entry ([OptionAlpha: FOMC days 2.0% vs 1.25% avg move, close at extremes](https://optionalpha.com/blog/trading-the-fomc-meeting-0dte-next-day-strategies)).
3. **Stop-whipsaw losses inside the EM** (2024-12-20, 2026-06-09, 2023-02-14 type): the stop rule, not the market, manufactured the loss. This is a stop-width/credit design question, only testable on intraday marks (double-stop rate ~8.6% and rising per the [MEIC live records](https://www.thetaprofits.com/tammy-chambless-explains-her-meic-strategy-for-trading-0dte-options/)).

**Stage-2 (runs tomorrow, ThetaData terminal free, v2 engine):**
- **R5/R6/R7 breaker sim:** 1-min mid marks for our exact historical strikes, trigger at −2×/−3×/−5× morning credit, 1/2/5-min debounce, exits charged at natural + 0.10–0.25/leg slippage, no same-day re-entry; freeze-only vs close-all variants; false-trigger rate by VIX tercile. Decides the ic breaker sign (current bracket OPT +39k/+31k vs PESS −16k/−6k).
- **FOMC 12:30 CT repricing:** actual buyback cost at 12:30 on all 34 FOMC days + optional 13:45 re-entry credit — replaces the accounting bound with a number.
- **Call-leg-drop confirmation:** minute-level v2 rerun with the cr_c>2.5 gate to verify the +7.3k test delta survives real fills.
- **Stop-width study:** per-side stop = total IC credit (MEIC standard) vs current multiples, double-stop frequency measured, on the same marks.

---

## 8. Data shopping list (from the research phase)

| Item | What it enables | Cost/source |
|---|---|---|
| **VIX9D daily history** | Term-structure inversion gate — best-supported pre-open signal ([SSRN 6752518](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6752518): inversion depth adds 2.4–6.9pp R² for forward realized vol) | FREE — [Cboe CDN CSV](https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX9D_History.csv) |
| **VIX3M daily history** | VIX/VIX3M backwardation regime flag (~7.7% of days; [Simon & Campasano](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2094510)) | FREE — [Cboe CDN](https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv) |
| **VVIX daily history** | Vol-of-vol divergence early warning ([Fed FEDS 2013-54](https://www.federalreserve.gov/pubs/feds/2013/201354/index.html)) | FREE — Cboe CDN |
| **SKEW daily history** | Low priority; test-to-reject | FREE — [Cboe CDN](https://cdn.cboe.com/api/global/us_indices/daily_prices/SKEW_History.csv) |
| **VIX close 20d-dispersion** (already have VIX) | Thrasher "volatility tsunami" complacency trigger ([SSRN 2949847](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2949847)) — warns of first-day shocks the coincident family misses | $0 — computable tonight from `data/vix_daily.csv` |
| **ES overnight/Globex 1-min bars** | Overnight-range gate — the truest pre-open signal ([NY Fed SR917](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr917.pdf)); would have caught 04-07-25-class days without VIX | Databento ($125 credit on file) |
| **ThetaData 1-min SPX option quotes, 2022–2026 strike sets** | Stage-2 breaker/FOMC/stop-width sims — **the gating purchase**; terminal free after tonight | Existing ThetaData sub |
| **VIX1D history** | Per-event richness gate (event-week variance priced ~3.8–4.2× realized vs 1.5–1.6× normal) | FREE — Cboe |
| **Calendar upgrades** (no data purchase) | Add: OpEx/quarterly witching, MSCI/S&P rebalance dates, ECB/BOJ, ISM, ECI, Treasury auction slate, US elections, tariff effective-dates. These caused ≥8 of the 33 misses. | $0 — public schedules |

---

## Provenance

- Forensics: 33 per-day investigations, each persisted under `scripts/killerday/` with evidence CSVs in `data/options_sim/backtest_full/killerday/`; web sources cited inline above and in the per-day scripts.
- Sweeps: `test_credit.py`, `test_gap-prior.py`, `test_vix.py`, `test_event.py`, `test_cluster.py`, `test_breaker.py` → family results CSVs (all rules reported including losers).
- Stack: `test_stack.py` → `stack_{steps,final,rules,killer_days,loyo}_20260910.csv`.
- Adversarial audit: `adversarial_audit.py` → `adversarial_audit_20260910.csv` (174 rule×book recomputes, random-skip MC null, Bonferroni ×395).
- Reproduction audit: all 7 scripts regenerate their CSVs byte-identical; no lookahead found (all inputs prior-close / morning-entry / advance-known calendar).
- Constraints honored tonight: no ThetaData requests, no git commits, no system-state changes.

---

## STAGE-2 UPDATE (2026-09-10, post-workflow): exact intraday circuit-breaker simulation

The day-level breaker bounds above are now superseded by an EXACT event-driven
simulation (`scripts/killerday/breaker_sim_v2.py`): every stop's real timestamp
rebuilt from the parity feed, breaker fires when cumulative REALIZED day P&L hits
-X, all open legs closed at the real ThetaData touch at the breach minute, entries
after breach skipped. Zero missing quotes in the final run. Implementable verbatim
in the live daemon (keys on booked losses, not marks).

**Results (delta vs baseline, $ 1-lot, 2022-05-16 -> 2026-09-04; train=22-24 / test=25-26):**

| book | level | breach days | total | train | test | killer-day delta | verdict |
| --- | --- | --- | --- | --- | --- | --- | --- |
| puts_band | -1000 | 35 | **+3,342** | +942 | +2,400 | +4,070 | **ADOPT (advisory) — positive both halves** |
| puts_band | -1500 | 14 | +60 | +60 | 0 | +60 | neutral |
| puts_band | -2000/-3000 | 10/1 | 0 | 0 | 0 | 0 | never binds |
| ic | -1000 | 119 | -969 | -1,596 | +627 | +5,908 | NO — whipsaw pays back the killer savings |
| ic | -1500/-2000/-3000 | 67/30/2 | -1,473/-639/-104 | neg | mixed | neg | NO |
| combined (incl fly) | -1000 | 427 | -9,683 | -12,193 | +2,510 | +76,352 | NO |
| combined | -1500 | 199 | -720 | -3,950 | +3,230 | +26,138 | NO |
| combined | -2000 | 106 | +4,964 | -1,383 | +6,347 | +11,953 | not robust (train negative) |
| combined | -3000 | 36 | -1,195 | -1,220 | +25 | -1,090 | NO |

**puts_band -1000 breach-day detail (all 35):** 9 saves totaling +$4,070
(2025-03-03 +1,060 tariff-eve, 2026-06-17 +610 FOMC/Warsh, 2024-08-01 +650 ISM,
2022-05-20 +580 OpEx, 2025-02-27 +540, 2026-01-29 +150, 2024-12-18 +60 FOMC,
2025-12-12 +40, 2022-10-14 +380), 2 whipsaw costs (2023-01-03 -478,
2024-03-08 -250), 24 days delta 0 (breach at/near the final exit anyway).
Breach times spread 10:33-15:45 CT-shifted-ET — real intraday triggers, not
end-of-day artifacts. Full rows: `killerday/breaker_v2_days_20260910.csv`.

**Corrections to the day-level breaker section above:** the stage-1 optimistic
bounds overstated the ic/combined breaker; exact simulation shows the ic breaker
net-negative at every level and any fly-containing aggregate strongly negative
at -1000/-1500. The single adoptable breaker is **puts_band at -1000 realized**:
+$3.3k/4.3yr on top of the +$14.9k base (~+22%), maxDD relief on 9 of the 33
killer days, cost 2 whipsaw days. Advisory-only per the desk rule.
