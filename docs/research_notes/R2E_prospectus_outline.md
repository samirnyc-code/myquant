# REGIME-2E — Evidence Dossier / Prospectus · OUTLINE (v0, 2026-07-25)

> Outline only. Section purpose · key data · chart · visual · **honest verdict**.
> Charts referenced may predate the final parameters — the *intent* of each chart is what's fixed here.
> Voice: hard facts, plain language, no sales talk. Every section ends in a verdict, including the bad ones.

---

## Voice & framing (applies throughout)
- **No adjectives doing work numbers should do.** Every claim carries a figure and a source script.
- **Verdict-first.** Lead each section with the conclusion, then the evidence.
- **Distinguish computed vs asserted.** Anything not computed is labeled "not verified."
- **Claims we DO make** vs **claims we do NOT make** — stated explicitly on p.1 (see §0).
- Data-charts are the evidence; stock photos are chrome only (cover + section dividers), never as proof.

## Front matter
- **Cover:** title, one-line honest thesis, version + date, "research dossier — not an offer to manage money."
  - Draft thesis line: *"A mechanical, ES-only intraday system with an in-sample-significant, positive-skew
    edge that survived every standard overfitting check across five years — and has not yet traded a live
    fill. This document shows what it is, how it was built, where it breaks, and what it costs to run."*
  - [VISUAL: abstract market/data-viz cover image — licensed stock, sourced at build.]
- **Disclaimer / scope box:** backtest on ES 5-min RTH ticks 2021-06→2026-07; strict fills; net of $5 RT +
  1-tick slip; past performance ≠ future; forward-unproven.

## §0 · How to read this — what we claim and what we don't
- Two-column box. **We claim:** in-sample significance, no overfitting fingerprint, honest DD, defined scope.
  **We do NOT claim:** forward performance, generalization beyond ES, statistical certainty on ~hundreds of obs.
- **Verdict:** this is a rigor document, not a pitch. If it reads like a sales deck, we failed.

## §1 · Executive summary (verdict-first)
- One-paragraph honest verdict (real edge, ES-only, positive-skew, forward-unproven).
- **Headline table:** shipping WT-573 and three-book 678 side by side — n, net, PF, maxDD, P(PF>1), sizing.
- "Three things true / three things still unknown" box.
- [CHART: ES equity curve — hero.] [VISUAL: none — let the curve carry it.]
- **Verdict:** validated within ES; the remaining question is forward fills, not whether the edge exists in-sample.

## §2 · What the system is
- Plain-English mechanism: established trend → two-legged pullback → second-entry continuation, harvested to close.
- **The three books** table: 2EL long (BULL), 2ES short (BEAR), f2EL fade-short (BEAR) — entry/stop/why.
- Frozen parameters, condensed (regime engine, S61 signal, gap filter, 0.30×ADR / 4pt stops, retest 6t, EOD, 09-13).
- **Constituents note (governance):** 678 = 2EL(282)+2ES(291)+f2EL(105); FADE-L(121)=dead excluded;
  RevFT:BO/MC:CC4 NOT included; shipping subset = WT-573.
- [CHART: annotated 5-min example trade from the trade/fade gallery.] [VISUAL: none.]
- **Verdict:** fully mechanical and automatable; no discretion anywhere — by design (discretion eats the tail).

## §3 · The journey — from unfiltered to today  *(the credibility spine)*
- **Start with the loss.** Raw, unfiltered 2E is a LOSER: T1 PF 0.82 (−$108k), T2 0.78 (−$174k), negative in
  every regime×dir cell. Say it plainly — this is what buys trust for everything after.
- **Diagnosis:** where it bled — breakout chase (bad fills), wrong hours (14-15 ET), fixed targets clipping runners.
- **The five levers**, each independently motivated (not fit): (1) retest-limit entry, (2) 09-13 window,
  (3) 0.30×ADR vol stop, (4) EOD-hold exit, (5) regime gate + second-entry only.
- [CHART: **waterfall** — PF/net from raw 2E → +each lever → final three-book. *(to build)*]
- Landing: +$93,722 / PF 1.44 (three-book) · +$86,848 / PF 1.45 (shipping WT).
- **Verdict:** the edge came from *removing structural bleed and gating to regime*, not from mining parameters.
  The levers are mechanisms, not knobs — that is the anti-overfitting story in miniature.

## §4 · Performance & the shape of returns
- Headline metrics; per-year table (green every year in-sample); $/trade; frequency (~11/mo, lumpy).
- Positive-skew introduced here: mean > median, fat right tail.
- [CHART: equity curve + per-year bars.] [CHART: per-trade P&L distribution (skew).] [CHART: underwater/DD curve.]
- **Verdict:** consistent in-sample, positive-skew — many small results, few large winners. Not smooth. By nature.

## §5 · The overfitting question  *(dedicated, plain-language — the confidence section)*
- **Plain definition:** overfitting = tuning to the past until profit appears, with nothing real underneath.
- **How you'd fake it, and its fingerprints:** sharp parameter peaks, train ≫ test, one-lucky-period dependence.
- **What we actually see (each with a chart):**
  - test PF **≥** train PF at every stop  [CHART: train-vs-test bars]
  - broad **plateau**, not a peak  [CHART: stop×gap plateau heatmap]
  - drop **any** year → rest holds 1.35–1.50  [CHART: leave-one-year-out]
  - **15/19 quarters green**, params re-derived each window  [CHART: quarterly PF / walk-forward]
  - bootstrap **P(PF>1)=99.7–99.9%**, CI does not straddle 1.0  [CHART: bootstrap PF/net CI]
  - [USE the two built figures: overfit_evidence_significance.png, overfit_evidence_fingerprint.png]
- **Intellectual-honesty note (this earns trust):** we found and corrected our OWN pessimistic errors — the
  "~20 effective observations" and "PF CI straddles 1.0" claims were wrong (real: Kish n_eff 115; P(PF>1)≈99.7%).
  A seller inflates; we deflated ourselves and then corrected with data.
- **Honest residual:** the *build* involved heavy search (many candidates tried) → multiple-comparisons risk.
  Mitigated by the held-out test period + walk-forward holding, **not eliminated.** The forward test is the arbiter.
- **Verdict:** by every standard diagnostic, NOT overfit. The only honest caveat is selection-from-search, and the
  only thing that closes it is live fills — not another backtest.

## §6 · Drawdown, droughts, and what it demands of you
- Honest DD ladder: realized −$9,502 · MC worst-1% −$24k · **block-bootstrap worst-1% −$35.4k (the number to size on)**.
- Droughts: median flat stretch 143 trades, worst-1% ~493 (~44 months). Rolling PF < 1 ~25% of the time (normal).
- Tail dependence: drop top-40 → loss. Concentration curve + Kish n_eff = 115 (286 winners).
- [CHART: block-bootstrap DD distribution.] [CHART: profit-concentration / Kish curve.] [VISUAL: none.]
- **Verdict:** a positive-skew book. It requires capital sized to −$35k and the discipline to sit through ~year-long
  flats. If you can't hold through the drought, you can't have the tail — and the tail is the edge.

## §7 · What we tested and REJECTED  *(discipline = confidence)*
- Rejected, with one line each: fixed targets (all), regime-flip exits, first entries, 1m/15m/30m/60m & vol bars,
  ETH/overnight, BE-move/scale-out/stop-tighten (fill fantasy), gamma-regime label (inverts OOS), 0DTE (VIX-redundant),
  VIX conditioning & inverted-U (non-stationary), **the per-side quarterly kill rule** (−$24k; disabled shorts before
  2025Q4 +$15.6k), 2 MES on a $4,500 prop.
- HVL 2:1 lean = the *one* survivor of the gamma work — held as a candidate, not shipped.
- **Verdict:** the survivors survived because we killed almost everything else. This list is the point, not an aside.

## §8 · Scope & limitations  *(honest, unflinching)*
- **ES-specific.** Does NOT transfer to NQ, even re-tuned on NQ's own train (best 1.24 → test 1.0).
  [CHART: ES-vs-NQ per-year / PF bars.]
- **Forward-unproven** — zero live fills to date.
- **Out-of-window unproven** — pre-2021 & independent-vendor untested (Databento parked by choice).
- **Power** — effective N in the low hundreds; positive skew widens finite-sample uncertainty.
- **Verdict:** validated *within ES 2021-26*. ES-only, forward-unproven, out-of-window untested. Stated as facts, not softened.

## §9 · Benchmark — vs SPX buy-and-hold (same capital, same period)
- SPX +83% total-ret (12.8% CAGR, −25% maxDD) 2021-26. flat-1 ES ≈ ties (+89%, edge +$6.3k); lean +115% (+$49k).
- The real edge is **risk + independence:** −9% realized DD vs −25%; correlation −0.15.
- [CHART: vs_spx account-value curves + correlation scatter.]
- **Verdict:** not an index-beater on raw return over a bull; a low-drawdown, uncorrelated return stream best run
  *alongside* an index position on the same margin, not instead of it.

## §10 · Capital & economics
- **One sizing number:** ~$105k/ES (33% tol) / ~$137k (25%) on −$35.4k DD. $30–35k and $70–85k are superseded.
- MES economics ($3 RT), prop EOD-trail: 1 MES fits $4,500 (thin, −$4.2k daily-block); 2 MES does not.
- [CHART: required-capital & ROC bars (flat-1 / flat-2 / lean).]
- **Verdict:** ES is a six-figure instrument. MES is the small-account / prop route, at proportionally small dollars.

## §11 · Paths forward by account size  *(the practical map)*
- Table — tier → what to run → expected/yr → stress DD → caveat → verdict:
  - **$4,500 prop (EOD-trail):** 1 MES flat. ~+$1.5k/yr. −$4.2k worst-1%. Thin cushion. *Proof-of-discipline, not income.*
  - **$20–50k personal:** 1–3 MES flat, no lean. Scales linearly; still micro dollars. *Build the track record here.*
  - **$105–140k:** 1 ES flat — the sizing sweet spot (DD-matched). ~18% CAGR. *The intended home of the system.*
  - **$150k+:** 1 ES + 2:1 HVL lean (ROC ~23%) OR scale contracts. *Only where you can size UP near-HVL; lean unproven forward.*
- **Verdict:** match the instrument to the account's drawdown tolerance first; returns follow from correct sizing, not leverage.

## §12 · The path to "live-validated" — what remains
- Status: **v1.0-rc1** (backtest-validated), not v1.0.
- Remaining gates: (a) NT8 signal-diff (port fires identical signals — fade stop currently mis-wired, fix first);
  (b) forward paper period logging actual vs modeled fills; (c) optional YM/RTY to test "ES-like auction" scope.
- **Verdict:** everything a backtest can establish is done. What's left needs live fills and calendar time — and we
  say so rather than dress rc1 up as finished.

## §13 · Final verdict & kill criteria
- Restate: real, ES-specific, positive-skew, in-sample-significant edge; forward-unproven; size at ~$105k/ES.
- **Kill criteria (pre-committed):** live DD breaches bootstrap worst-1% −$35.4k; or rolling ~500-trade net stays
  negative; or live fills diverge materially from modeled. Written down BEFORE going live, on purpose.
- **Verdict:** move forward only as a forward-validation exercise at small size, with the kill criteria armed.

## Appendices
- A. Full frozen parameter spec (the config, verbatim).
- B. Data provenance & reproducibility — tick source, every script name, "run these to reproduce every number."
- C. Methodology — causality audit (no lookahead), fill realism (strict through-fill), engine invariance.
- D. Glossary — 2E / regime / PF / positive skew / block bootstrap / Kish N / EOD-trail — plain definitions.
- E. Chart index — every figure, the script that builds it, and whether it's on final params.

## Chart & visual inventory (what we already have vs to-build)
- HAVE: ES equity; overfit_evidence_significance; overfit_evidence_fingerprint; walkforward_20260725;
  vs_spx_20260725; lean_es / lean_contracts; fade_gallery (trade examples); regime_tracker; per-trade skew &
  concentration (in effective_n); NQ cross-instrument bars.
- TO BUILD: the §3 lever **waterfall**; a clean underwater/DD curve; ES-vs-NQ per-year bar; required-capital/ROC bar.
- STOCK PHOTOS (chrome only, sourced at build): cover; §-divider images for §3 (path/ascent), §5 (magnifying-glass/audit),
  §8 (boundary/edge), §11 (staircase/tiers). Never captioned as evidence.
