# Setup Inventory — master list for the trade plan (Samir + Thomas)
**Created:** 2026-09-12 (S118) · **Status:** draft v2 — names + evidence ranking · **SCOPE DECIDED (S118): the trade plan covers MANUAL ES ONLY.** §4 (options desk) stays in the doc as reference but is OUT of the plan.
**Sources scoured:** docs/living/** (all handoffs + studies), docs/research_notes/** (0001–0016 + killer-day + grimes), leglab/, tempo/, scripts/, nt8/, memory notes, PATs-Trading repo (Mack), Desktop literature (Brooks, Dalton/Steidlmayer, Ali/QuantSystems whitepaper), options playbook + sim code.

Status flags: 🟢 live/validated in-house · 📗 backtested (frozen book) · 📙 studied (result noted) · 📓 in literature/mentor material, never built · ⛔ tested-and-dead (kept so we never re-buy the same idea).

---

## 1. Brooks / Mack (PATs) price-action setups — discretionary vocabulary
*(Mack's PATs material is Brooks-derived; merged and deduped. Source: docs/living/ninetrans_study.md, scripts/mark_setups.py, PATs-Trading nuggets/02-trade-setups.md, Brooks PDFs on Desktop.)*

**With-trend**
- H1 / L1 (first entry) 📓
- H2 / L2 (second entry) 📗 — the audited REGIME-2E book (see §3)
- A2 (first 2-leg pullback) 📓
- 1PB (first pullback) 📓
- Deep-pullback (4-condition) 📓
- hH1 / hL1 (hard-trend single-leg) 📓
- G2 (deep gap pullback) 📓
- Spike & channel (channel-midline entry) 📓
- BT — breakout test continuation 📓
- BP — breakout pullback ("trade the BP not the BO") 📓
- With-trend breakout stop-entry 📙 (intraday scorecard)
- BOPBL — with-trend limit pullback 📙 (intraday scorecard)
- Soft-trend "buy every failed L2" 📓
- Opening-range BO + pullback 📓
- TFTO — trend from the open 📗 (brooks engine vocabulary)
- BOFT — breakout follow-through 📗 (brooks engine vocabulary)
- Measured-move targets (fH1/fL1 MM; two-legs) 📓

**Reversal / counter-trend**
- MTR — major trend reversal (2HH+2HL termination) 📓
- Wedge reversal (W; three pushes) 📗 (WedgeScalperV2 live-ish on NT8)
- W1P — wedge first pullback 📓
- fW — failed wedge → measured move 📓
- DT/DB — double top/bottom (third-touch fade / DP pullback variant) 📗 (engine vocabulary)
- fBO — failed breakout fade 📓
- Trap entries 📓 (Mack)
- Failed second entry as with-trend fade (f1/f2EL at range top, f1/f2ES at bottom) 📗 (f2EL is a frozen side-book)
- Wait-for-higher-low / lower-high reversal confirmation 📓 (Mack)
- Climax reversal (incl. capitulation flush) 📙 (tempo studies, §5)
- Expanding triangle (XT) breakout 📓
- Contracting triangle BO with prior trend / triangle BO + pullback 📓

**Range**
- Fade range edges only (SA≥80% / BB≤20% bands) 📙 (intraday scorecard)
- Fade every breakout in a trading range 📓
- TR-day box thirds (buy bottom third, sell top third) 📓
- TTR / barb-wire — fade breakouts out of tight ranges 📓
- BB/SA + location, BB/SA mean-reversion, BB/SA in-range only 📙 (intraday scorecard)
- Fade failed-extreme 📙 (intraday scorecard)
- Gap fill 📓

## 2. Dalton / auction-theory setups
*(docs/living/dalton_ib_tenets_20260705.md, or12_research_daytype_20260706.md, MOM/Markets-in-Profile/Steidlmayer PDFs)*
- Open-Drive · Open-Test-Drive · Open-Rejection-Reverse · Open-Auction-in-Range 📙 (OR12 day-type work)
- IB-edge fade (fade IB extremes to middle) 📗 — "Keystone" research note 0003
- IB breakout / range extension (initiative vs responsive) 📙
- Balance-day fade at range/HOY-LOY edges 📙 (reversal_at_extreme Q2)
- Value-area rules (VA location trades) 📙
- Day-type playbooks off the 6 Dalton day types 📙 (classifier built; conditioners §7)

## 3. In-house systematic ES books (backtested, specs frozen)
- **REGIME-2E: 2EL / 2ES with-trend** 📗 — THE audited book (branch regime/indep; 2021+ PF 1.46)
- f2EL fade-short side-book 📗
- 1E / 3E entry variants 📗 (measured in the 2E book metrics)
- STMR — stochastic mean-reversion (%K8<15 & >SMA100), long 📗 + regime-SHORT mirror 📙
- MC "CC" breakout CC1–CC5 (MyMicroChannel) 📗 (research-note series)
- S3_early13@3R (CC1–5 + IB-break/prior-trend/before-13:00 filters) 📗
- PB scale-in (2nd-leg pullback add on MC) 📗 (note 0001)
- RevFT / MyReversals family: subtypes Trap / IB / OB / Sneaky / BO 📗; PB-retest "i1R straight-shot" 📗; RevFT-extreme sleeve 📗
- Logan `!PROD_ES_5` reversal system (17 entries, 6-rule exit) 📙 (decoded, note 0004)
- QuantSystems / Ali (Ali Moin-Afshari): BO+FT · Big Breakout · Reversal+FT · 2nd-leg pullback scale-in 📗 (notes 0006/0007 + whitepaper)
- NR-ORB (NR4/NR7 × K opening-range breakout) 📙
- ZLO Key Retracement standalone (LizardTrader) 📙
- Always-In flip entry gate 📙 (⚠ regime/always-in ENGINE itself is flagged broken — memory rule)
- MenthorQ CR-0DTE first-touch fade (ES) ⛔ (MQ sub cancelled) · MenthorQ magnet continuation ⛔
- Daily/swing mean-reversion set: buy-the-washout · Bollinger LONG · z-score LONG · Connors RSI2 L/S 📙 (daily = works-ish; 5-min versions ⛔ FAILED)

## 4. Options / 0DTE desk (SPX-only)
**Live sim (gameplan tags)**
- `eodic` / `eodic_p` — EOD EM iron condor / puts-only 🟢
- `openic` — open EM iron condor 🟢
- `openfly` — open ATM iron fly 🟢
- `eodfly` — EOD off-center fly 🟢 but RETIRE-CANDIDATE (killer-day study: fly dies in rising vol)
- `puts` credit-band 0.5–2.5 — the robust flip from the TD backtest 📗
- `bps_stmr` — STMR bull put spread (flagship options expression) 🟢
- `gx_bps` / `gx_bcs` — gamma-wall-anchored credit spreads 🟢
- Active-close profit-taking rule (trigger daemon) 🟢
- Killer-day advisory variants (NOT live rules): IC call-leg-drop cr_c>2–3 · total_cr<1.0 floor · skip_FOMC · puts_band −$1,000 breaker 📙

**Older playbook / gameplan-era**
- `sell_0dte_gamma` (PS0/CR0 credit spreads) · `cr0_fade` · `ps0_fade` ⛔ (MQ-era)
- `fly_gw_0dte` — butterfly at the pin 📙
- `straddle_0dte` / `straddle_event` — long ATM straddle, gap/event-armed 📙
- `condor_0dte` inside the walls 📙
- `bull_cs_wk` / `bear_cs_wk` weekly directional verticals 📙
- `put_cal_wk` weekly put calendar 📙
- Weekly 7-DTE VIX-EM-band iron condor (L0/L1) 📙

## 5. Studied signals with a confirmed (small) edge — candidates for setup-conditioning
- Climax-at-high reversal (20-bar extreme + tempo≥p95): +3.6pp, z=3.3, positive all 6 years 📙
- First-hour tempo quintile → rest-of-day range forecast (0.63→0.94 ADR monotone) 📙 — SIZING input, not entry
- Fast+wide PDH/PDL touches reject more (+5.3pp, 5/6 yrs, but 2026=0) 📙
- LONG wedge + climax capitulation-flush cell (post-hoc, awaiting pre-registered retest) 📙

## 6. Tested and DEAD — never re-trade without new evidence
- Naked EM condor ⛔ (−$24–25k, twice independently)
- `condor_stmr` ⛔ · `gamma_level_fade` ⛔ · static far-OTM tail hedge ⛔ · gap-directional/gap-and-go ⛔ (post-2023)
- All MenthorQ level-anchored setups ⛔ (sub cancelled 2026-08-04)
- GexLog playbook-following (touch/hold15/cross15) ⛔ (board 14: no robust edge)
- Iron-fly book baseline ⛔ (−$200k across 4yr backtest; live openfly under watch)
- S55 killed intraday menu: ORB · Donchian · VWAP-fade · PDHL · PMDRIFT · DON15 · GAPGO ⛔
- 5-min mean-reversion (VWAP-z/Bollinger/RSI2) ⛔
- Big-ES-day 85% continuation claim (Tim F) ⛔ refuted
- Leg-count as DIRECTION signal ⛔ (LegLab null ×5) — legs = volatility only
- Tempo as DIRECTION signal ⛔ (Stage-2 H4/H5 null) — tempo = activity only
- Intraday combined breakers on IC ⛔ (whipsaw pays back savings)
- XSP: retired, not part of any list.

## 7. Conditioners / filters / sizers (not standalone setups — trade-plan modifiers)
- Gap-skip |RTH gap| > 0.54% (2E book) · HVL↔SMA20_D gate (93% agree) · phase-machine regime (BULL/BEAR/NEUTRAL)
- Sizing candidates list: balance-state size-up · prior-inside-day · ZLO confluence · ER10 gradient · size-down day-after-trend-day
- Dalton 6-day-type classifier · OR12 fingerprint + 3-factor base-rate card · IB width/order
- Gamma regime (neg/pos, walls, flip) · EM band · VIX band scaling · event calendar (FOMC/CPI/OpEx)
- Tempo engine states (CLIMAX/EXPAND/CHURN/ACTIVITY/GRIND/BALANCE/MIXED) — observational overlay
- Leg count as vol-clock/trend-day confirmer · OTF one-time-framing · ER/ADX/overlap "barbwire" gauge · RVOL per slot
- Order-flow backlog (footprint POC/VA, imbalance, absorption, CVD divergence, naked VPOC magnet, iceberg/sweep at level) — PAUSED, unbuilt
- Mack execution rules (not setups): signal-bar quality veto · room-to-scalp 4-tick gate · don't-chase rule

---

## Evidence ranking — manual ES scope (S118)
**What this is:** the in-house tested setups sorted by their own research-note verdicts and numbers (source: notes 0001–0015d, s85 book metrics, living studies — extracted 2026-09-12). **What it is not:** a rank of the ~40 literature-only Brooks/Mack names — those have NO in-house numbers and cannot be ranked, only listed (Tier C). Scorecard numbers are gross/optimistic (252d bench, scalp +2) — directional only.

**Tier A — validated, positive, would anchor the plan**
| rank | setup | evidence | caveat |
|---|---|---|---|
| 1 | REGIME-2E 2EL/2ES | 2021+ n=540 PF 1.54 (+$15.0k/yr ES), v1.1+gap PF 1.64–1.70, 16yr PF 1.33, maxDD −$10.2k, audited real-tick | lives on branch regime/indep; 2ES below SMA20 loses (PF 0.76) — the gate IS the setup |
| 2 | STMR long (daily) | 17yr n=184 win 80% PF 4.45 +$1,064/ES exp, 16/17 yrs green, walk-forward "fixed beats fitted" | DAILY swing w/ overnight holds — conflicts with prop flat-by-15:00-CT rule; check account fit |
| 3 | Keystone IB-edge fade | n=1,395 PF 1.38 ExpR +0.159 (honest fwd +0.09–0.12R), positive every year 2021–26, survived look-ahead audit | note's own verdict: "modest — sized COMPONENT, not standalone"; sole survivor of ~85 buckets |
| 4 | S3_early13@3R | frozen S55 WF survivor, OOS n=1,858 +0.107R PF 1.24, 3.75/4 yrs positive | fails the PF≥1.3 bar at MES costs; ~$2.5–3k/yr per MES |
| 5 | f2EL fade sleeve | PF 1.35, BEAR-gated, frozen spec | n=105 only |

**Tier B — modest/conditional evidence (component or thin)**
- MC CC1–CC5 base book — all-signals PF 1.14 n=5,444 (+$47/tr): the signal POOL the Tier-A filters mine, weak unfiltered
- 3E entries — PF 1.30 +$20.8k/yr but overlaps 2E legs (don't stack blindly)
- Scorecard LIMIT-entry family (BB/SA+location, fade edges, BB/SA mean-rev) — +$20–23k gross each; robust pattern = LIMIT pullbacks win / STOP breakouts lose (−$122k)
- Balance-day fade — beats baseline 9/14 OOS folds ($149 vs $94 exp) — a conditioner more than a setup
- WedgeScalper signal-bar CLOSE entry — PF 1.04–1.16, real but thin, slippage-sensitive (breakout entry is ⛔ PF 0.76); LookBack-12 redo pending
- Climax-at-high reversal — +3.6pp z=3.3 all 6 years, event-level only, no P&L claim
- RevFT filtered/portfolio — combined book PF 1.29 n=1,730 BUT 0015b destroyed RevFT as a *signal* (random-time null p=0.12; edge = regime beta) — only tradeable as the gated portfolio, not as a standalone signal

**Tier C — no in-house evidence (literature/decode only — pick on discretionary grounds, then the log builds the evidence)**
All §1 Brooks/Mack names not listed above (H1/H2/L1/L2 manual, MTR, wedge, DT/DB, fBO, traps, spike&channel, BP, TR plays, gap fill…), Dalton open types + VA rules, Logan MyReversals (decode only, zero edge claims), Always-In flip (no saved stats; negative as a gate).

**Tier D — tested NEGATIVE for manual ES (do not put in the plan)**
PB scale-in (NO-GO, add is negative-expectancy) · RevFT PB-retest i1R (retire, all variants) · fade-EMA-thrust (retire, 12-trade mirage) · RevFT as counter-trend fade (−$114.9k, loses every year) · reversal-at-developing-HOD/LOD (both hypotheses negative) · NR-ORB (real R-edge but redundant, ~$1k/yr) · ZLO KeyRet standalone (PF 0.97; works only as MC filter) · QS BO+FT / Rev+FT mechanical (ExpR −0.026/−0.028; Ali's numbers = 100 hand-picked trades; 0007's +$359k VOIDED look-ahead bug) · wedge BREAKOUT entry (PF 0.76) · with-trend breakout STOP entries generally (scorecard −$122k) · 1E adds / 1ES (PF ≤1.04) · 2ES below SMA20 (PF 0.76)

## Trade log → journal (first sketch, S118)
Per-trade fields (superset; log everything, journal renders):
`date, entry_time, exit_time, instrument, direction, qty, entry_px, exit_px, stop_px (initial), target_px, risk_$ / risk_R, pnl_$ / pnl_R, MAE, MFE, post-exit MFE, commissions, setup_tag (from THIS inventory — controlled vocabulary), regime_tags (day-type, gamma regime, tempo state, VIX band), plan_compliance (in-plan Y/N + rule broken), grade (A–C), screenshots, notes, missed-trade flag`.
- Key design decision: **setup_tag must come from the frozen trade-plan list** — that is what makes the log joinable to this inventory and gradeable ("did we stick to the plan").
- Reference product: scstudies.com/trading-journal — captures the same field set + NT8 auto-import AddOn, MP4 per trade, R-based KPIs, rule-enforcement panel, local-first. Build-vs-buy TBD with Thomas.
- We already have in-house precedents for the review half: `book_review.py` (chart marking + grades) and `tempo_review.py` (A–C grade + good/cons per mark) — a journal is these plus an executions feed.
