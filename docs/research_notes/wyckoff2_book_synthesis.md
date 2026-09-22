# Wyckoff 2.0 (Villahermosa, book 2: Structures + Volume Profile + Order Flow) — synthesis

Source: `wyckoff-20-...book-2_compress.pdf` (342 pp), read in full by 6 parallel agents (2026-09-15),
page-cited. Complements `wyckoff_book_synthesis.md` (book 1). Drives the ES Wyckoff toolset.

## 0. What book 2 IS
Wyckoff 2.0 = a strict **division of labour** across three lenses (p.271, 300):
- **Wyckoff structure = CONTEXT** — builds the scenario / directional bias (the cornerstone).
- **Volume Profile = LOCATION** — *where* to act: entries, stops, targets (VPOC/VA/HVN/LVN/VWAP).
- **Order Flow = TRIGGER** — *when*, and only AT the pre-chosen zone (never chart-wide, p.247, 275).

4-step workflow (p.277-278): 1 context/bias → 2 zones & levels (VP) → 3 scenario (if-X-then-Y +
alternative) → 4 management (entry/stop/target).

## 1. Refinements to book-1 structure (Part 1-2)
- **The shakeout is the dominant, overriding event** — always bias to the last shock: long after a
  potential Spring, short after an Upthrust (p.28-29, 78). (Matches our retroactive engine.)
- **Labels are provisional** — a "Spring" with no follow-through (no minor-SOS) auto-relabels to a
  test of weakness (p.67-68). Only ever propose the NEXT move, not two ahead (p.68).
- New first-class events: **Structural Failure** (price fails to reach the opposite edge — LPS/LPSY
  are instances; conflating with shaking a prior low = stronger spring) (p.31-34); **Shortening of
  the Thrust** (≥3 pushes; short travel + high vol = effort/result divergence; short + low vol =
  exhaustion) (p.36-37).
- **Sloping ranges** (4 variants) and **edges are zones w/ width**; touch-count = confidence (p.40-42).
- **Bar-type guidance (critical):** on **tick charts per-bar volume is ~constant → use the Weis wave**
  (volume per swing); **never use volume charts (they disable volume analysis)**; tick/range OK; daily
  sidesteps the ETH/RTH volume bias (p.17-24). Validates our RTH/ETH trove split.

## 2. Order Flow (Part 6) — the confirmation layer (computable from our footprint exporter)
- Read **diagonally**: aggressive buys hit ASK, sells hit BID; compare BID[L] vs ASK[L+1] (p.249-251).
- **Imbalance** = 200/300/400% disparity diagonally + a min-contracts floor (calibrate to ES) (p.251-252).
- **Turning pattern = Absorption + Initiative** (p.253-257):
  - Absorption/takeover: high volume, price stops, imbalances AGAINST the close (BID at bottom for a
    spring low; ASK at top for an upthrust). "Potential" only.
  - **Initiative = the SOS/SOW bar** (wide range, close at extreme, high vol, imbalances in favour of
    close, **delta rotation**) — the *definitive* confirmation. **Initiative mandatory, absorption
    optional** (p.330-331).
- **Continuation pattern = Control + Test** (trend add + low-volume retest of a control level) (p.262-267).
- **Delta** = ASK vol − BID vol; divergence = delta sign ≠ bar direction; absorption = big |delta| + no
  progress (p.164, 176-177). HARD caveat: delta = *aggression not intent*; subordinate to structure;
  never label "buy/sell intent" (p.171-172, 180).
- **Gate OF strictly to key zones** (p.247) — the antidote to our spray.

## 3. Volume Profile (Part 5) — the location layer
- **VPOC** = highest-volume price (fairest); price above → buyers control (long bias), below → short
  (p.189-190). VPOC is always an HVN; not every HVN is the VPOC.
- **Value Area (VAH/VAL)** = **68.2%** of volume (1σ) — the book uses 68.2, not 70 (expose as param).
  VAH/VAL act as S/R (p.186).
- **HVN** = magnets → **targets**; **LVN** = rejection → **entries, stops, and structure edges**
  (Creek/Ice ≈ LVN) (p.192-196, 215-216).
- **Naked/virgin VPOC** = untested prior VPOC → magnet/target; **Developing** (live) vs **Fixed**
  profiles; scopes = session / composite / fixed-range (drag over a leg or a Wyckoff structure)
  (p.196-202). Structure profile scope = start of rotation → just before the breakout (exclude impulse).
- **VWAP** (session/weekly/monthly) ± 1σ/2σ; author's favourite combo = **weekly VWAP + structure
  VPOC** (p.190-192, 222). Long-bias when price > VWAP AND VPOC; short when below both (p.221).
- **Last HVN = the bias line** — trade with the last-developed HVN; flip only on its effective break
  (p.218-220). THE master gating object.
- **5 value-area trading principles** (p.236-245): range-fade (target VPOC → opposite VA edge);
  **80% reversion** (fail to hold outside VA on re-entry → opposite edge); breakout-test continuation
  (fail to enter VA → imbalance away); failed-reversion (rejected at VPOC → cancel). D/P/b shapes =
  Phase A/B; bP = accumulation, Pb = distribution (p.209-214, 225-228).
- **Volume Profile (volume) preferred over Market Profile (time/TPO)** (p.204-207). VP is built from
  contracts-per-price → **bar-type agnostic** (tick+time parity).

## 4. Integrated setups (Part 7-8) — structure × VP × OF
Four contexts, each needing all three lenses to align:
1. **Range at extreme (reversal):** Spring at VAL / Upthrust at VAH (edges ≈ LVN) → OF absorption+
   initiative → entry on the shakeout test.
2. **Range inside (Phase D):** move to opposite extreme; HVN bias; entries at LVN/VWAP/VPOC.
3. **Trend, breakout test (BUEC/LPS):** at the broken Creek/Ice (an LVN); 3-trace genuineness
   (shakeout depth · post-break displacement+vol · non-reentry + VPOC migration).
4. **Trend, pullback (Phase E):** at prior VA / weekly VWAP / prior-impulse VPOC / LVN.

Management (p.300-311): **entry = SOS/SOW bar via a STOP order** (never a limit — "only one move at a
time"); **stop** at far side of the trigger/structure snapped to the nearest LVN/VAL/VPOC/VWAP;
**target = next untested HVN→its VPOC**, then naked/developing VPOC, then liquidity highs/lows; R:R
computed; breakeven at first VA target. Always hold an **alternative scenario** (p.299-300).
ES-specific worked case = §8.3 (2020-07-17): prior-day VAL/VWAP test → 5-min Spring+test+Weis →
footprint delta trigger → target opposite VA edge.

## 5. What this means for our build (data assets we already have)
- **Footprint/delta exporter (validated)** → gives us the Volume-Ladder input for imbalance/absorption/
  initiative/delta-rotation. Missing layers to compute: diagonal imbalance flags, delta rotation,
  imbalance-vs-close location, finished-auction test. Gate to key zones only.
- **RTH+ETH tick troves + tickdata.py** → compute Volume Profiles (VPOC/VA/HVN/LVN/naked VPOC) per
  session/composite/structure in python; export levels for the NT8 indicator to draw. Bar-agnostic.
- **Tick vs time:** build everything bar-agnostic; VP levels computed from tick data are identical on
  any chart. Recommend **time chart (daily/H1) for macro context + VP levels, 2k-tick for execution/
  trigger** (or overlay higher-TF VP levels on the 2k chart). Effort via Weis-wave (not per-bar vol).

## 6. Proposed toolset (staged)
- **Stage 1 — Foundation engine (levels + effort):** Volume Profile (VPOC/VAH/VAL/HVN/LVN/naked VPOC,
  session+composite+fixed-range, developing+fixed) computed from tick troves → drawn in NT8; VWAP
  session/weekly ±σ; Weis-wave effort; delta/absorption/initiative from footprint. Last-HVN bias line;
  price-vs-VWAP/VPOC state. Everything else references these.
- **Stage 2 — Structure tools:** "Wyckoff TR Box" drawing tool (user draws; auto phase A-E partition;
  edges as zones snapped to LVN) + retroactive event engine (climax=range edge; spring/upthrust
  confirmed only by opposite-edge breakout; test = No Supply/No Demand; structural failure; SOT).
- **Stage 3 — Trigger + management (Wyckoff 2.0 integration):** at an armed zone (structure edge / VAL/
  VAH / broken Creek-Ice LVN) evaluate OF absorption+initiative + SOS/SOW bar → propose stop-entry, SL
  at LVN, TP at HVN-VPOC/naked VPOC, R:R + alternative scenario.

Design contract (from the book): structure sets the scenario, VP sets location/targets/stops, OF only
times the trigger at the zone — never let OF originate a trade, never trade against the last-HVN bias,
never spray marks chart-wide. This is the explicit antidote to our earlier over-labelling.
