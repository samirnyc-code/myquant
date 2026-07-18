# MC Setup Research Notes

A growing library of self-contained studies on the **MC "CC" breakout setup**
(ES futures). Each note answers one question with real data, shows every way we
tested it, and ends with a plain recommendation a trader can act on. Written so a
collaborator who has *never* seen the codebase can follow it.

> These notes are the shareable, friend-facing distillation. The internal
> source-of-truth for current work remains `docs/living/handoff.md`.

## Index

| # | Note | Question | Verdict |
|---|------|----------|---------|
| 0001 | [PB scale-in](0001_pb_scalein_mc.md) | Is adding a 2nd leg on a pullback worth it? | **No — don't scale in** |
| 0002 | [ER10 look-ahead bug](0002_er10_lookahead_bug.md) | How big was the ER10 look-ahead, and can we salvage the trades it wrongly blocked? | **3.8× inflation; fix kept. Bleed is uncapturable by exit timing** |
| 0003 | [Keystone — IB-edge fade](0003_keystone_ib_edge_fade.md) | Does an MC signal's origin location (vs structural levels) predict a tradeable edge? | **Yes, one: origin at the IB edge. Modest, audited, deep-DD — a cash COMPONENT, not a standalone system** |
| 0004 | [Logan "MyReversals" decode](0004_logan_myreversals_decode.md) | What exactly is Logan's `!PROD_ES_5` reversal system — every variable, setup, and exit, translated to NinjaScript? | **Decode only (no edge claim): 17 entries + 6-rule exit faithfully translated; ~half gated on un-recovered EL functions** |
| 0005 | [RevFT trade location](0005_revft_trade_location.md) | Is there a *where* (VWAP deviation / value area) that rescues the RevFT reversal set? | **No. Fade-into-extension is the worst; RevFT is weak continuation, not reversion — break-even, one-regime. Retire it** |
| 0006 | [QuantSystems Breakouts — reproduction & edge study](0006_quantsystems_breakouts_blueprint.md) | Can Ali Moin-Afshari's breakout/reversal setups be reproduced from his actual code, and do they carry a mechanical edge? | **Detection reproduces (freqs match paper); NO mechanical edge (~0/neg, 5yr, look-ahead-audited). His SQN 6–15 = 100 hand-picked 2020 trades + discretionary 2nd-leg/scale-in — not mechanizable** |
| 0007 | [QS Breakouts build & test mechanism](0007_quantsystems_breakouts_build.md) | How do we reproduce & test the QS setups (architecture, schema, sweep, gates)? | **Living methods note (no edge claim): detection→sim→view/sweep pipeline; G1 frequency gate PASSES (~6.3 BO/day vs ~5)** |
| 0009 | [MenthorQ gamma data × MC edge](0009_menthorq_gamma_mc.md) | Does 3 months of dealer-gamma data (levels, GEX, regime, QScores) improve the MC/Stack-v2 entry edge? | **No — levels are not intraday S/R (nor are pdH/L/C, VWAP, VA, IB); "don't trade into levels" refuted. Real: neg-gamma days realize 1.18× implied (amplitude, not direction) + cluster-skip watch item. Spec stays frozen** |
| 0010 | [OR12 first-hour fingerprint → day character](0010_or12_fingerprint_daytype.md) | Can the first 12 bars + prior-day context find "twin" days that predict today's character/direction? | **Character yes (40% vs 34% chance, survives walk-forward, edge over conditional prior thin-but-real); direction NO (50%, always). Verdict: keep building as a context DISPLAY (base-rate tables + twins + confident-vote only), stop chasing prediction accuracy** |
| 0011 | [Programmatic day-type & context ID — research survey](0011_daytype_context_survey.md) | How does the world (academia + practitioners) programmatically identify day type/context in real time, and what failed? | **Survey: morning→character yes, morning→direction is a graveyard; IB-width-vs-ATR + open location are the documented conditioners (ES effect sizes catalogued); Brooks full-mechanization publicly failed −59%…−211% after costs; analog-day tools are under-built in public** |
| 0012 | [OR12 base-rate card — replication & dissection](0012_or12_baserate_card.md) | Do the published IB statistics replicate on our data, and are they real or artifacts? | **Replicate, then dissect: formation-order skew = proximity artifact (real variable = 10:30 location: 85/15 first break, 2.6:1 day-close side); "narrow IB → extension" inverts in ADR units (IB width = vol nowcast → afternoon RANGE); trend days live on WIDE IBs (38–41% vs 9–12%). 3-factor card adopted for the context screen** |
| 0013 | [RevFT i1R/PB retest trade](0013_revft_pb_retest.md) | Does the pullback-retest entry salvage the RevFT signal? | **No — 1,148–2,852 trades all ≈flat net of costs; cleaner arming → worse retest; the rev-bar stop-entry survivorship trap quantified (92.8% vs 44.3%)** |
| 0014 | [Trend-filtered STMR stochastic system](0014_stmr_stochastic_system.md) | Is the colored-stochastic mean reversion a real daily system? | **YES — %K8<15 & C>SMA100, exit >SMA5: PF 4.45, 80% win, 16/17 yrs, WFA-validated; 1-lot MES +$19k/17y, maxDD −$808** |
| 0015 | [BPS/STMR exit-rule study](0015_bps_exit_rules.md) | Which exit should the options BPS use — signal exit, tastylive 50%-take, stops, or expiry-hold? | **The SMA5 signal exit IS the edge (PF 1.74, +$14.7K); expiry-hold NEGATIVE (maxDD −$27.7K); TP50 ≈ flat; price stops poison (they sell the pre-bounce low). VIX filters rejected OOS. Enter on signal, exit on signal, nothing else** |
| 0016 | [ES × MenthorQ gamma levels + CR-0DTE fade](0016_es_gamma_levels.md) | Do MenthorQ's gamma levels give a tradeable ES edge? | **Majors hold ~80% but are rarely reached — untradeable alone. Documented retraction: back-adjusted bars (+465pt drift) fabricated an 18-trade "CR fade"; repair shipped. Survivor: CR-0DTE first-touch fade +$123/tr, ~60/yr, 36/36 sweep cells positive, OOS +$29/tr — CANDIDATE pending NQ replication + live paper** |

## ⚠️ Numbering is coordinated across chats — RESERVE FIRST

Multiple chats write these notes in parallel. The **authoritative number ledger is the
RESEARCH NOTES REGISTRY at the top of `docs/living/handoff.md`** — NOT this file. The
Index table below is a convenience mirror and can lag. **Before creating a note: open the
handoff registry, take the NEXT FREE NUMBER, and add your claim row there.** Do not infer
the next number from this README.

## Workflow — how every note in this series is made (STANDARD, follow it)

0. **Reserve your number** in the handoff registry (above rule).
1. Write the study as `NNNN_topic.md` here, using the house template below.
2. Render + export: `python scripts/render_note_pdf.py docs/research_notes/NNNN_topic.md`
   (or `--all` to rebuild every note). This produces the PDF next to the `.md`
   **and** mirrors it to the off-repo shareable folder
   `C:\Users\Admin\Documents\MC_Setup_Research_Notes\` (index README copied too).
3. Add the note to the Index table above.

The `.md` is the source of record; the PDF is the friend-facing deliverable. Do
**not** hand-build PDFs — always go through `scripts/render_note_pdf.py` so the
whole series stays visually identical.

## House template (copy for new notes)

```
# NNNN — <Topic> — <YYYY-MM-DD>
**Series:** MC Setup Research Notes · Note NNNN
**Confidence:** <High | Medium | Low> — <one line: sample, cost-realism, OOS status>
**TL;DR:** 2–4 sentences: the answer + the recommendation, for skimmers.

## 1. The setup (so this note stands alone)
   - what the signal/trade is, the key terms, the cost model.
## 2. The question
## 3. How we tested it  (one line per method — the menu)
## 4. Results  (one subsection per test, each = short read + table)
## 5. Why it works / fails  (the synthesis)
## 6. Recommendation  (bold, actionable)
## 7. Caveats & open questions
## 8. Reproduce  (scripts + saved artifacts)
```

## Conventions used across notes
- **Instrument/costs:** ES, $50/point, 1 tick = $12.50. Default friction unless
  stated: **$5 round-turn commission + 1 tick slippage per leg** ($17.50/leg).
- **R** = initial risk = |entry − stop| (in points → ×$50 = $/contract).
- **Session phases (CME Central Time):** Open 08:30–11:30 · Mid 11:30–13:00 ·
  Late 13:00–14:45 · Close 14:45–15:15.
- **CC1–CC5** = the five MC breakout signal subtypes (`SignalType`).
- **±95%** on a rate = 1.96·SE. Wide band = *unproven at this n*, not disproven.
- Sims score trades independently (unlimited-positions assumption).
- **Confidence line** (top of each note) tells a reader how much to trust it:
  - **High** — multi-year, full-cost, survives an out-of-sample / robustness check.
  - **Medium** — decent sample but cost-sensitive or only partly OOS-tested.
  - **Low** — suggestive, thin sample or single regime; a hypothesis, not a rule.
