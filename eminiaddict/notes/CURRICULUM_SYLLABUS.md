# EminiAddict Curriculum — Syllabus Blueprint (v1, for approval)

**Purpose.** A structured, ground-up course that teaches David Halsey's (DH)
Measured-Move (MM) method to a complete novice in a logical sequence, using his
own material as the authoritative base and layering our scaffolding, worked
examples, quizzes, and gap-fills on top. Dual audience: (1) the user, learning
it properly; (2) a suggested teaching sequence to hand to DH, who concedes new
customers don't know where to start.

**Status.** BLUEPRINT ONLY. No interactive build until this outline is approved.
Decisions locked (2026-08-10):
- **Format:** written syllabus first (this doc), then build in order.
- **Voice:** DH's voice preserved as the base; our commentary layered around it.
- **Rollout:** full outline approved before building any module.
- **Book:** incorporate it FULLY — quote it verbatim where it teaches, and cite
  every reference down to Chapter · Figure · page. "I want everything." The book
  is the spine of the DH BASE layer, alongside the webinars and diagrams.
- **Two outputs, one base (2026-08-10):** every module is built ONCE and yields
  BOTH (a) an interactive gated lesson and (b) a **Modern-Edition prose chapter**.
  Shared research, no duplication. See §10.
- **Modern Edition audience:** a **pitch to David Halsey** — a re-sequenced,
  modernized manuscript of his own book (current charts + his later webinar
  teaching folded in + our editorial scaffolding, clearly labeled). This framing
  also fixes copyright: we're proposing to the rights holder, not distributing a
  rewrite. NOT a public/commercial product unless DH is on board.
- **Scope of additions:** expansive — fold in everything (webinar refinements,
  our gap-fills), all clearly marked `[OUR ADD]` so his method stays separable.

---

## 1. Design principles (the pedagogy DH's material lacks)

1. **Atom-first.** Nothing compound until the single building block (one Fib on
   one leg) is automatic. DH drops novices into full setups too early.
2. **Teach the discretionary step hardest.** Seeding the swing is the ONLY
   judgment call; everything downstream is mechanical. It gets its own module
   with an explicit heuristic + drills (DH barely teaches it — our biggest add).
3. **One idea, one place.** DH teaches each concept 5× across book/webinars/
   videos, never in order. Each concept gets ONE home; other sources are cited,
   not re-taught.
4. **Woven practice.** A short mastery quiz GATES each module (not one quiz at
   the end). Plus a running spaced-repetition review deck.
5. **Every lesson, same shape:** Objective → Prereq check → Concept (plain) →
   *DH in his own words* (cited quote/diagram/clip) → 1–2 worked examples on real
   annotated charts → Common mistakes → "Your turn" drill → gating quiz.
6. **Honesty layer.** Flag what's mechanical vs discretionary, what DH assumes
   you already know, and realistic expectations (win-rate / risk-of-ruin math).
7. **Faithful attribution.** Anything we add that isn't DH is boxed and labeled
   `[OUR ADD]` so the DH-facing version stays clearly separable from his method.

## 2. Voice convention (how the two layers are marked)

- **DH BASE** — leads each concept: his exact wording (book quote, webinar clip,
  or teaching diagram), attributed to chapter/webinar/diagram. His voice carries
  the authority.
- **OUR LAYER** — set off visually (callout box / different color at build time):
  - `▸ Plain English:` the same idea for a novice.
  - `▸ Why it works:` the mechanism (auction/order-flow, who's on the other side).
  - `▸ DH assumes you know:` the unstated prerequisite.
  - `▸ Watch out:` the common novice mistake.
  - `[OUR ADD]` — material DH doesn't provide at all.

## 3. Source inventory (everything we draw from)

- **Book** (16 chapter notes `notes/chNN_*.md` + `notes/RULEBOOK.md` synthesis).
  Copyrighted; we quote sparingly and cite.
- **11 method webinars** (transcripts + our key-point nuggets
  `data/site/webinars/nuggets/{03,08,09,10,11,12,16,20,21,22,25}.md`).
- **16 teaching diagrams** (`data/site/_diagrams/`) incl. the **two flowcharts**:
  #5 Measured Move Flow Chart (decision tree), #8 Market Analysis Flow Chart.
  Plus 4 reference tools (Signal Alignment Checklist, Gap Fill Statistics,
  Dollar/Indices Correlation, Position Sizing Calculator).
- **Daily analysis videos** (`data/daily/*/transcript.txt`) — real, dated worked
  examples of him running the process live.
- **Our chart engine** — tick/bar archive lets us generate UNLIMITED fresh
  annotated examples + drills (draw-the-MM, spot-the-seed, compute-the-levels).

## 3a. Book citation map (every chapter → figures → module)

Citation standard: cite as **`(Halsey 2014, Ch N — "Chapter Title", Fig N.N, p NNN)`**;
quote verbatim where the book actually teaches; paraphrase filler. Figure/page
anchors below are from the number-exact chapter notes (`notes/chNN_*.md`); pull
exact page numbers from those notes at build time. `†` = figure exists in the
chapter, title to confirm against the PDF render.

| Ch | Title | Key figures / anchors | Feeds module(s) |
|----|-------|----------------------|-----------------|
| 1  | Today's Trading Environment (pit→screen) | no figs; Flash Crash 5/6/2010; quant 60–80% | M0 |
| 2  | Fibs & the Measured Move | MM geometry; the 50/61.8/123.6 levels | **M1** |
| 3  | The Road Map | swing definition; correlation intro | M2, M8 |
| 4  | Tools of the Trade | tape/time&sales; platform tools | M0, M9 |
| 5  | Execution | order mechanics | M4, M5 |
| 6  | The Three Setups | **Fig 6.1** (setup diagram), Fig 6.2 (inverse) | **M3** |
| 7  | Using Multiple Time Frames | **Fig 7.1** Weekly Trad. MM Short (p107–108, *a monthly chart*), **Fig 7.2** Daily MM Long (p108), **Fig 7.3** 15-min MM Long (p109–110), **Fig 7.4** Micro (p110) | **M7** |
| 8  | Entries | entry sequence; ES tick table | **M4** |
| 9  | Seasonality | seasonal patterns | M11 |
| 10 | Tools for the NYSE | Bank (417-sec index), Breadth, Tick, Tick Hook, Time&Sales, Trend | **M9** |
| 11 | Tick Extremes & Divergences | reversal-tick vs divergence-tick (2008-crash origin) | **M9** |
| 12 | Gap Fills | **Fig 12.1** gap-fill stats table | **M10** |
| 13 | Position Management | profit-taking methods | M5 |
| 14 | Risk Management | position-sizing figs; 1% / free-trade brackets | M5 |
| 15 | The Inner Trader | **Fig 15.1/15.2** Four Phases + −23.6% overshoot | M12 (+ M1/M6 for the phases model) |
| 16 | The Trading Plan | p182 four rule categories; the 31 rules; setups priority | **M13** |

Every module's **DH BASE** layer must open from the relevant book chapter above,
then bring in the matching webinar(s) and diagram(s). Where the book is SILENT on
something he later taught (VIX, the 5-signal checklist, the gold/CL gotcha, the
confirmation-vs-series distinction, the history/replay framework), the modern
chapter marks it explicitly as a **post-book addition from his webinars**, not a
book citation.

## 4. Course map — 5 stages, 14 modules

```
STAGE A · ORIENTATION
  0  What this is (and isn't) + the map + setup

STAGE B · THE ATOM
  1  The Measured Move — one Fib on one leg
  2  Reading structure — swings + SEEDING the move  [our biggest add]

STAGE C · SETUPS & MECHANICS
  3  The three setups — Traditional / Extension / 61.8% Failure
  4  Entries — the fixed order
  5  Exits & risk — 4 exits, free trade, ≤1%, 2:1

STAGE D · PUTTING IT TOGETHER
  6  The series — how MMs chain (Measured Move Flow Chart ⭐)
  7  Multi-timeframe — weekly→daily→15m→micro
  8  The daily process — Market Analysis Flow Chart ⭐
  9  Signal alignment — VIX/Indices/TICK/BANK/USD

STAGE E · PLAYBOOKS, MIND, PLAN
  10 Playbooks — gap fills · sessions/timing · instrument idiosyncrasies
  11 History as roadmap — past predicts future
  12 The inner trader — psychology
  13 CAPSTONE — build your plan + sim→live graduation ladder
```

Mastery gate at the end of each stage; a module can't unlock until its prereq
quiz is passed.

---

## 5. Module specifications

> Each spec lists: **Objective · Prereqs · DH sources · Concept · DH-in-his-words ·
> Worked examples · Common mistakes · Drills · Quiz · Gate.**

### Module 0 — What this is (and isn't) + the map + setup
- **Objective:** understand what the method claims, what it does NOT (not
  indicators, not prediction — reading auction structure), who's on the other
  side of the trade, realistic expectations, and how to set up to follow along.
- **Prereqs:** none (true entry point).
- **DH sources:** Ch 1 (Descent of the Pit / Ascent of the Screen); Ch 4 (tools);
  diagrams #9/#10 Knowns-Unknowns (+ table), #13 Basic Balance, #14 Extended
  Imbalance, #15 Hedgers-Speculators; webinar 16 intro ("Groundhog Day").
- **Concept:** markets are ~90% logical MMs / ~10% news noise (Ch 15 90/10);
  programs attach to the same structural levels; our edge is reading that
  structure and knowing when programs are offside. Balance vs imbalance framing
  (diagrams 13–14) = the "why."
- **DH in his own words:** the casino-not-gambler thesis; "large orders move
  price"; "the proof is in the price — a valid 50% will be defended."
- **Worked examples:** annotate one clean ES day showing structure vs a news-spike
  day showing noise.
- **Common mistakes / `▸ DH assumes you know`:** what a futures contract/ES tick
  is, what a Fib retracement tool is, a charting platform. `[OUR ADD]` a short
  "prerequisites you actually need" primer (platform, ES/MES, chart setup).
- **Drills:** classify 6 charts as "structure" vs "noise."
- **Quiz:** 5 Q — what the method is/isn't; 90/10; who's on the other side.
- **Gate:** ≥4/5 to unlock Stage B.

### Module 1 — The Measured Move (one Fib on one leg)  ⭐ the atom
- **Objective:** draw ONE MM cold and compute every level from memory.
- **Prereqs:** M0.
- **DH sources:** Ch 2 (Fibs & the MM); RULEBOOK §1 (geometry); diagrams #2
  Types of Moves, #3 Basic Moves, #4 Levels; Ch 15 "Four Phases."
- **Concept:** for an up-leg from swing low L to high H, range R:
  `100%=L (start) · 61.8%=L+0.382R (FAILURE) · 50%=L+0.500R (HWB=entry) ·
  0%=H (end) · 123.6%=H+0.236R (TARGET, seeds next swing)`. Down-leg mirrors.
  The Four Phases (Ch 15): P1 entry at 50% (must hold 61.8%) → P2 → P3 → P4 target.
- **DH in his own words:** his fibs are drawn "backwards"; the 50% is man-made
  "halfway back," not a real Fib number (webinar 09).
- **Worked examples:** 2 auto-generated from ticks (one up-leg, one down-leg),
  every level labeled with the arithmetic shown.
- **Common mistakes / `▸ Watch out`:** anchoring to bodies not true wick extremes;
  confusing 123.6% and −23.6% naming (same target — `[OUR ADD]` glossary note).
- **Drills:** live **MM level calculator** (enter L/H → all levels); "draw the MM"
  on 5 blank legs; numeric compute quiz.
- **Quiz:** 6 Q incl. 2 numeric level computations.
- **Gate:** compute all 5 levels correctly on 2 fresh legs.

### Module 2 — Reading structure: swings + SEEDING the move  `[OUR biggest ADD]`
- **Objective:** identify a valid swing and pick the seed swing consistently —
  the one discretionary decision in the whole method.
- **Prereqs:** M1.
- **DH sources:** Ch 2–3 (what defines a swing; the road map); RULEBOOK §2;
  diagram #16 MM Cycle. **Note:** DH is deliberately vague here — this module is
  mostly OUR construction from his scattered hints + our own tested heuristic.
- **Concept:** after the seed, all swing points are mechanical (prior MM's
  retracement high = new peak; prior MM's 123.6% = new trough). Only the seed is
  discretionary.
- **DH in his own words:** "the only discretionary step is the seed swing"; the
  dominant/most-recent leg guidance from the daily videos.
- **`[OUR ADD]` seed-swing methodology:** a concrete, teachable rule set (e.g.
  significance by leg size/wick, last-completed vs dominant, tie-breakers) with a
  decision checklist — the thing DH never spells out. Draft the rule, then
  validate it against his own annotated daily charts before teaching it.
- **Worked examples:** 3 charts where we show 2 candidate seeds and adjudicate.
- **Common mistakes:** seeding off noise; re-seeding every bar; recency bias.
- **Drills:** "pick the seed" on 8 charts, graded against DH's own draws where we
  have them (his key-level slides).
- **Quiz:** 5 Q + 3 seed-picks.
- **Gate:** seed 6/8 in agreement with reference.

### Module 3 — The three setups
- **Objective:** recognize Traditional, Extension, and 61.8% Failure on sight and
  know the trend order.
- **Prereqs:** M2.
- **DH sources:** Ch 6 (the three setups); RULEBOOK §3; diagrams #6 Long Series,
  #7 Short Series, #17 MM Cycle+Move; webinar 09 (#2 50% retracement/trend
  failure), webinar 22 intro.
- **Concept:** Traditional = 50% pullback MM; Extension = target blown through
  with no 50% pullback (bull/bear flag; drawn highs-to-highs / lows-to-lows);
  61.8% Failure = the trend-change signal. Order: **traditionals → extensions →
  straight up (or down)**; a 61.8% failure flips it.
- **DH in his own words:** "extensions are like a black swan — you can't identify
  them ahead of time"; "if extensions confuse you, trade ONLY traditionals."
- **Worked examples:** one long series and one short series, each labeled setup by
  setup, from his diagrams + a fresh generated one.
- **Common mistakes:** drawing extensions on the way down; forcing an extension
  before a target is blown through.
- **Drills:** label-the-setup on 10 charts; order-the-progression drag drill.
- **Quiz:** 6 Q.
- **Gate:** ≥5/6.

### Module 4 — Entries (the fixed order)
- **Objective:** apply the three entries in fixed order with correct tick offsets.
- **Prereqs:** M3.
- **DH sources:** Ch 8 (entries + ES tick table); Ch 5 (execution); RULEBOOK §4;
  diagram #12 Standing Orders; webinars 08/10/11 (front-run mechanics).
- **Concept:** **First Test → Front-Run of the 2nd Test → Trend Break & Next MM.**
  All limit orders front-run the 50%. Per-instrument ticks (ES: front-run +2,
  stop −6→−4, 1st target +2; euro/gold/CL front-run +4, first target +6).
- **DH in his own words:** "the second test is the most dangerous test"; stop one
  tick past the 61.8% break (webinar 12).
- **Worked examples:** the same MM entered three ways; a second-test/"gotcha"
  failed-breakout (from webinar 21) shown tick by tick.
- **Common mistakes:** chasing after the first test fails; wrong tick table per
  instrument.
- **Drills:** "place the order" (mark entry/stop/target) on 6 setups.
- **Quiz:** 6 Q incl. tick-offset computations.
- **Gate:** ≥5/6.

### Module 5 — Exits & risk
- **Objective:** take profit correctly and never risk >1%.
- **Prereqs:** M4.
- **DH sources:** Ch 13 (position management), Ch 14 (risk); RULEBOOK §5;
  webinar 22 (Manage Positions), webinar 21 (profit-taking); Position Sizing
  Calculator tool.
- **Concept:** four exits — **Distance Formula** (|50%−38.2%| = 0.118·R, use the
  38.2% line), **trail the 61.8%**, **confirmation-of-trend partials** (opposing
  MM's 61.8% breaks → take partial, expect full halfway-back), **−23.6% target**.
  Take profit on the timeframe you entered on. Free trade + ≤1% risk + 2:1 floor.
- **DH in his own words:** "greed kills the trade"; "one tick / one pip is all we
  need"; the series-vs-confirmation distinction = did the 61.8% break.
- **`[OUR ADD]` expectations math:** given his 4t-target/6t-stop bracket, the
  break-even win-rate and a simple risk-of-ruin table (same honesty lens we used
  on PATs). Flagged as ours.
- **Worked examples:** the three profit-take methods on one big trend (webinar 22
  charts); a 1% position-size computation.
- **Common mistakes:** promoting a small setup into a swing; moving a stop wider.
- **Drills:** position-size calculator; "which exit applies" on 6 scenarios.
- **Quiz:** 6 Q incl. a sizing calc.
- **Gate:** ≥5/6; correct size on 2 scenarios. **End Stage C mastery check (mixed).**

### Module 6 — The series (how MMs chain)  ⭐ the "aha"
- **Objective:** follow a trend from seed to break using the decision tree.
- **Prereqs:** M5.
- **DH sources:** **Diagram #5 Measured Move Flow Chart** (the decision tree);
  RULEBOOK §§1–3; Ch 15 (the series progression); webinars 09, 25.
- **Concept:** draw a basic MM → enter at HWB → tick-by-tick → target → beyond
  target? → next MM… A trend break routes to STOP → draw the all-the-way-halfway
  back (ATW-HWB) of the whole series as the possible limit → reverse.
- **DH in his own words:** "the market ALWAYS comes halfway back after a trend
  break"; fractal cascade — "micros fail → the 15-min can fail → the daily is in
  jeopardy" (webinar 09).
- **Worked examples:** walk diagram #5 end-to-end on one real series.
- **Common mistakes:** drawing the next MM before the −23.6% target is hit;
  hunting a new 50 after an extension fails instead of expecting halfway-back.
- **Drills:** "what's the next node" flow-chart drill on 6 states.
- **Quiz:** 6 Q.
- **Gate:** ≥5/6.

### Module 7 — Multi-timeframe (weekly→daily→15m→micro)
- **Objective:** run top-down analysis; know why the weekly leads.
- **Prereqs:** M6.
- **DH sources:** Ch 7 (timeframes); RULEBOOK §7; diagram #11 Nested Moves;
  webinars 08, 09, 11 (always-know-your-weekly).
- **Concept:** hierarchy weekly > daily > 15m > micro; same MM math on each
  ("price is the same across all timeframes"); the weekly (largest zoom, 10–20yr)
  sets the path of least resistance; you enter it by drilling down.
- **DH in his own words:** "respect the weekly trends the most and the micros the
  least"; the daily MMs give the entry into the weekly target.
- **`▸ DH assumes you know` / `[OUR ADD]`:** terminology fix — his "weekly" is the
  largest trend (Fig 7.1 is actually a *monthly* chart); disambiguate.
- **Worked examples:** one instrument shown at all four scales with the same
  structure highlighted.
- **Common mistakes:** managing a big trade on a tiny timeframe; trading against
  the weekly.
- **Drills:** "with or against the weekly?" on 6 nested charts.
- **Quiz:** 6 Q.
- **Gate:** ≥5/6.

### Module 8 — The daily process (Market Analysis Flow Chart)
- **Objective:** run the repeatable daily routine unaided.
- **Prereqs:** M7.
- **DH sources:** **Diagram #8 Market Analysis Flow Chart**; Ch 3 (road map);
  the daily analysis video transcripts (him doing it live).
- **Concept:** Daily → last completed MM → is there a series/trend? → identify the
  Active MM & phase → identify the larger opposing MM → drop to 15-min for the
  entry at the new 50%.
- **DH in his own words:** his actual daily-video walkthroughs (dated examples).
- **Worked examples:** replay one dated daily video as an annotated,
  step-by-the-flowchart case study.
- **Common mistakes:** skipping the top-down; no plan before the bell.
- **Drills:** run the flowchart on 3 fresh daily charts.
- **Quiz:** 6 Q.
- **Gate:** ≥5/6.

### Module 9 — Signal alignment (internals gate)
- **Objective:** gate ES trades on internals, not the ES fib alone.
- **Prereqs:** M8.
- **DH sources — SPLIT (verified 2026-08-10; sourcing matters for the DH pitch):**
  - **BOOK-BACKED core:** Ch 10 (Tools for the NYSE — Bank = Nasdaq banking index
    of 417 securities; Breadth; the Tick; Tick Hook; Time & Sales; Trend — used
    together to "build a case to a jury"); **Ch 11 (Tick Extremes & Divergences —
    his flagship: reversal-tick vs divergence-tick, from the 2008 crash)**;
    Ch 16 §C filter rules (breadth strong→longs only; Bank must confirm; Tick
    times the entry). RULEBOOK §7.
  - **WEBINAR/SITE-ONLY additions (NOT in the book — 0 VIX mentions in 226 pp):**
    the packaged **5-signal Alignment Checklist** (VX/Indices/TICK/BANK/USD), the
    **VIX** input entirely, the "ES bullish only while VIX < ~18.85 & DXY falling"
    rule, Dollar/Indices Correlation tool, webinar 11. Mark these clearly as
    later refinements when writing the modern chapter.
- **Concept:** the book teaches internals CONFLUENCE to confirm the ES MM —
  built from **TICK + BANK + breadth**, read at the 50% HWB, not arbitrary swings.
  The site/webinar layer adds VIX + USD into a named 5-part gate.
- **DH in his own words:** Ch 11 tick-divergence definition verbatim; "read the
  TICK only at the 50% HWB pullback"; the checklist from the traders'-checklist
  diagram.
- **`▸ Honesty note` / `[OUR ADD]`:** flag that the coarse-bar TICK tests were
  inconclusive (S93) — the method lives at 1-min/intrabar; teach it as context,
  not a mechanical trigger. And be explicit in the DH pitch that VIX/checklist are
  his post-book teaching, so the chapter is an honest *addition*, not invention.
- **Worked examples:** one aligned long and one misaligned (stand-aside) day.
- **Common mistakes:** taking the ES fib without the gate; reading TICK anywhere.
- **Drills:** "aligned or stand aside?" on 6 checklists.
- **Quiz:** 6 Q. **End Stage D mastery check (mixed).**
- **Gate:** ≥5/6.

### Module 10 — Playbooks (gaps · sessions · instruments)
- **Objective:** apply the specialized playbooks correctly.
- **Prereqs:** M9.
- **DH sources:** Ch 12 (gap fills), Ch 16 §B (gap rules); webinars 03/12/20
  (gaps), 21 (crude/gold), 08/10/11 (euro); Gap Fill Statistics tool.
- **Concept (3 playbooks):**
  - **Gap fills:** pre-market only (8:00–9:30 ET); 5–10pt band; the 10-pt
    gap-and-go line; series-holds-vs-breaks decides fill vs professional gap;
    the morning yes/no filter; avoid opt-ex/rollover/first-of-month/narrow-range.
  - **Sessions/timing:** US 8:00–11:30 & 13:30–16:00 ET; no-trade 9:30–10:00 &
    after 15:45; half-size Mon/Fri/opt-ex/rollover; euro 3:00–11:30 ET.
  - **Instrument idiosyncrasies:** ES (slow/technical) vs euro (cleanest trends,
    all-extensions) vs gold/CL (monster ranges, the **second-test "gotcha"**
    failed-breakout, deep 50% dips, micros dangerous, never over-leverage).
- **DH in his own words:** the nuggets we just wrote (12/20/21) verbatim leads.
- **Worked examples:** one gap-fill day; one gold/CL gotcha; one half-size day.
- **Common mistakes:** trading the fill at the open; over-leveraging CL; chasing
  a late micro fill.
- **Drills:** run the gap-fill filter on 5 mornings.
- **Quiz:** 8 Q (one per playbook cluster).
- **Gate:** ≥6/8.

### Module 11 — History as roadmap
- **Objective:** use historical replay and seasonals as context (not a trigger).
- **Prereqs:** M10.
- **DH sources:** Ch 9 (seasonality); webinars 16 (past-predicts-future), 25
  (dead-cat/trend-changes).
- **Concept:** the ES replays its own patterns with date precision; meta-trends
  (trend OF failures / of blown-past targets / seasonal); tops decided by the
  extension break at a full 50% short. "Don't fight the trend — whatever KIND."
- **DH in his own words:** "Groundhog Day"; the 2000≈2008 date-aligned replay;
  Churchill quote.
- **`▸ Watch out`:** this is context/narrative, weakest on mechanics — teach as a
  bias-former, explicitly not a standalone entry.
- **Worked examples:** the 2000 vs 2008 overlay; one seasonal (gold July).
- **Drills:** identify the meta-trend type on 4 ranges.
- **Quiz:** 5 Q.
- **Gate:** ≥4/5.

### Module 12 — The inner trader (psychology)
- **Objective:** adopt the casino mindset and the rule-following habit.
- **Prereqs:** M11.
- **DH sources:** Ch 15 (the inner trader); scattered webinar asides
  ("make yourself mechanical even when it doesn't feel good").
- **Concept:** casino-not-gambler; emotional capital; proactive vs reactive
  ("if you see the move and you're not in it, the trade is over"); the two
  equations (money-mgmt + emotion → decisions); daily review; 10,000 hours.
- **DH in his own words:** the two equations verbatim; "trade well, not for
  profit"; switch DOM from dollars to ticks.
- **`[OUR ADD]`:** a practical daily-review template + a pre-trade checklist
  wired to Module 8's routine.
- **Worked examples:** a rules-followed vs rules-broken day, same setups.
- **Drills:** journal one simulated day against the template.
- **Quiz:** 5 Q.
- **Gate:** ≥4/5.

### Module 13 — CAPSTONE: build your plan + graduation ladder
- **Objective:** produce a personal written trading plan and a sim→live path.
- **Prereqs:** M12 (and all prior gates).
- **DH sources:** Ch 16 (the trading plan — the 31 rules, 4 legs, setups priority,
  journal mandate); RULEBOOK §8.
- **Concept:** the four legs (money mgmt / entries / profit-taking / statistical
  rules); DH's 31 rules as the template; setups priority Daily>15m>Micro; journal
  mandate.
- **DH in his own words:** the four-legs framing; "the most important rule is to
  use a trading journal."
- **`[OUR ADD]` graduation ladder:** explicit sim → paper → small-live stages with
  pass criteria (e.g. N logged trades, rule-adherence %, expectancy > threshold)
  before risking real size — the piece DH never gives a novice.
- **Deliverable:** the learner fills a plan template (their instruments, sessions,
  risk %, setup priority, half-size days, journal cadence).
- **Final assessment:** cumulative exam drawing from all stages + submit the plan.
- **Gate:** pass exam + completed plan = course complete.

---

## 6. Cross-cutting components (built once, used everywhere)

- **Glossary / cheat-sheet** — disambiguates DH's drifting terms (50%=HWB;
  61.8%=failure; 38.2%=distance-formula exit; 123.6%≡−23.6%=target; "weekly"=
  largest trend; distance formula = |50%−38.2%|). Always one tap away.
- **Spaced-repetition review deck** — flip cards accumulate across modules; a
  "review" surface resurfaces older cards.
- **Live-usable checklist / flowchart** — the Module 8 routine + Module 9 gate as
  a trade-by-trade checklist you can run in real time.
- **MM level calculator** — reused in M1, M4, M5.
- **Progress tracker** — per-module completion + quiz scores (per-browser
  localStorage, matching the tool's existing notes/tags model).
- **Example generator** — pulls fresh legs from the tick/bar archive so drills
  aren't a fixed set (anti-memorization).

## 7. What we ADD that DH doesn't provide (consolidated `[OUR ADD]` list)

1. Prerequisites primer (platform, ES/MES, chart/Fib setup) — M0.
2. **Seed-swing methodology** with a concrete rule + graded drills — M2. *(biggest)*
3. Terminology disambiguation glossary — cross-cutting + M7.
4. Realistic-expectations / risk-of-ruin math — M5.
5. Honesty flags on unproven pieces (coarse-bar TICK) — M9.
6. Daily-review + pre-trade checklist templates — M12.
7. Sim→paper→live graduation ladder with pass criteria — M13.
8. Unlimited auto-generated annotated examples & drills — all modules.
9. Woven gating quizzes + spaced-repetition — all modules.

## 8. Build plan (after approval)

1. Lock the module list + gate thresholds (this doc).
2. Draft the **seed-swing rule** (M2) and validate against DH's own key-level
   slides before writing that module (highest-risk content).
3. Build cross-cutting components first (glossary, calculator, quiz+SRS engine,
   progress tracker, example generator).
4. Build modules in order 0→13. **Each module produces two outputs from one
   research pass** (see §10): (a) the interactive gated lesson, (b) the
   Modern-Edition prose chapter draft.
5. Home for output (a): a new **"Learn / Curriculum"** tab in
   `eminiaddict_tool.html` that supersedes the Academy hub; one shareable file;
   sync to Drive.
6. Assemble output (b) into the **Modern Edition manuscript** (§10) — the pitch
   to DH.

## 9. Decisions — RESOLVED (2026-08-10)

- Additions scope = expansive/everything; audience = pitch to DH; outputs = one
  base → two.
- **Instrument:** **ES-primary for now.** Teach on ES throughout; euro/gold/CL are
  Module-10 playbooks only. (Revisit if the euro emphasis is wanted later.)
- **Assessment:** **soft gates.** Quizzes are recommended checkpoints; the learner
  can navigate freely. (Still show score + a "you may not be ready" nudge, but
  never block.)
- **Length:** **deep / multi-week course.** ~30+ min per module, thorough worked
  examples and drills; not a 3-hr skim.
- **Modern Edition order:** **improved 14-module sequence + a crosswalk table** to
  his original 1–16 so DH can compare directly (what moved, and why).

## 10. Modern Edition track — the pitch to David Halsey

**What it is.** A modernized, re-sequenced edition of *Trading the Measured Move*
— his book as the spine, his later webinar teaching folded into the relevant
chapters, current charts throughout, and our scaffolding as clearly-labeled
editorial notes. Framed as a **proposal to DH** to update his own material.

**One base, two outputs.** Every module (§5) is researched once and emits both an
interactive lesson AND a prose chapter. The module's DH BASE layer ≈ the chapter
body; the `[OUR ADD]` boxes ≈ editorial sidebars.

**Per modern chapter, deliver:**
- Faithful teaching of the chapter's method, quoting the book verbatim where it
  teaches (cited per §3a), paraphrasing filler (e.g. Ch 1 history compressed).
- **Current charts** replacing 2014 thinkorswim/2000–2008 examples — COVID-2020,
  2022 bear, live ES ~6500 — auto-generated from our tick/bar archive.
- **Folded-in webinar material** the 2014 book lacks, marked as post-book: VIX +
  the 5-signal checklist (M9), the gold/CL second-test "gotcha" (M10),
  confirmation-vs-series profit-taking (M5), history-as-roadmap/dead-cat (M11).
- **Editorial sidebars** (`[OUR ADD]`): the seed-swing methodology, terminology
  fixes, realistic-expectations math, honesty flags on unproven pieces.

**Chapter order.** Recommend the improved 14-module sequence (Stage A→E), NOT his
original 1–16 (his order is the very thing the user found unteachable). Include a
**crosswalk table** mapping new chapters → his original chapters so DH sees exactly
what moved and why. (Pending open-question #4.)

**Positioning / copyright.** Explicitly a suggestion to the rights holder — the
safe posture. Cover note frames it as "here's a way to onboard new customers you
said don't know where to start." No public/commercial distribution without DH.

**Honesty.** Present his method faithfully as his; mark every editorial addition;
do not dress the abandoned backtests (S92) or inconclusive TICK study (S93) as
proven. Credibility with DH depends on this.

**Format.** Chapters drafted as markdown in `eminiaddict/modern_edition/chNN_*.md`
(committed, work-product); final assembly → a single readable artifact (PDF/HTML)
for the pitch.
