# Seed-Swing Methodology  `[OUR ADD]` — Module 2 core

**What this is.** A concrete, teachable procedure for the ONE discretionary step
in DH's entire method: picking the seed swing (the anchor leg the first Fib is
drawn on). After the seed, everything is mechanical. DH concedes this step is
"crucial" but **never gives a rule** — Ch 2 explicitly defers it ("in-depth
starting-point selection deferred to a later chapter") and the later chapters
give examples, not a procedure. This document supplies the missing procedure,
built from his scattered criteria + our tested detector. Clearly labeled as ours;
his method is unchanged — we're only making the undefined step followable.

---

## 1. What DH actually says (the DH BASE — cite in the lesson)

- The seed is **"the significant high-low that jumps off the page"** on the chosen
  timeframe (Ch 2–3; RULEBOOK §2). It is *the only non-mechanical step*.
- **After the seed, mechanical & recursive:** new peak = prior MM's retracement
  (HWB) point; new trough = prior MM's −23.6% target. The series projects itself
  (Ch 2, Figs 2.3–2.4).
- **Confirm the extreme before drawing** (Ch 2, Fig 2.7): draw the Fib from swing
  low to swing high only once a candle closes back inside (below its own high /
  above its own low), then "wait and watch for further confirmation that the high
  will hold" before treating the Fib as valid. Price "rarely moves in a straight
  line."
- **Zones, not lines** (Ch 2): treat every level as a zone; "close but not exact"
  is the rule.
- **Top-down, every day** (Ch 3): start on the 20-year Daily → where is price vs
  the predominant trend? → 15-minute → micros. "The longer the trend, the more
  powerful it is."
- **A leg is confirmed real** when the opposing MM's **61.8% breaks** (RULEBOOK §2).
- Typical healthy series = **5–6 MMs**; most series run **2–3** to completion
  before failing (Ch 2). Use this as a sanity check on a seed (below).

> Everything above is DH. The procedure in §2 is ours, assembled to make his
> "jumps off the page" operational for someone who doesn't yet have his eye.

## 2. The procedure  `[OUR ADD]`

A novice can't yet see what "jumps off the page." Replace intuition with 5 steps.

### Step 0 — Fix the timeframe first
Seed on the timeframe you're analyzing, top-down (Ch 3). For ES (our primary
instrument): **Daily for context/direction → 15-minute for the tradeable seed →
micro only as an entry tool.** Never mix: a Daily seed and a 15-min seed are
different MMs with different levels.

### Step 1 — Find candidate legs (significant, completed)
A candidate seed is a **completed** price leg (swing low→high or high→low) whose
move is **significant** relative to recent noise — not every wiggle.
- **Significance test (objective proxy for "jumps off the page"):** the leg
  reverses price by more than a threshold. We use a **ZigZag %-reversal filter**
  (see §3); a leg only counts once price has retraced enough off its extreme to
  confirm the extreme is in. This is exactly DH's "wait for the high to hold."
- Rule of thumb for ES Daily: a leg that stands clearly above the last few weeks'
  chop. On 15-min: a leg bigger than the routine 2–4 point back-and-forth.

### Step 2 — Choose WHICH candidate (the two-seed rule)
Two legitimate seeds usually exist; they answer different questions:
- **Dominant leg (largest range)** → seeds the **direction/context.** This is your
  "where are we in the big trend" read. Use on the Daily.
- **Last completed leg (most recent)** → seeds the **active, tradeable MM.** Use on
  the 15-min for the entry.
When they conflict, the dominant leg (higher-timeframe trend) WINS for bias; you
still trade the last-leg MM, but only in the dominant leg's direction (DH: trade
with the trend / path of least resistance).

### Step 3 — Anchor to true extremes
Anchor the Fib to the **true wick high/low** of the leg, not candle bodies or
closes. (Our detector snaps to the extreme wick within the leg span.)

### Step 4 — Confirmation gate (don't act on an unconfirmed seed)
Treat the seed as valid only once the extreme is confirmed held (Step 1's retrace
+ DH's Fig 2.7 close-back-inside). Until then it's provisional — draw it lightly,
wait.

### Step 5 — Validity check (did I seed right?)
A correct seed makes the mechanical projection FIT: price should be respecting the
50% (HWB), 61.8% (failure), and −23.6% (target) as **zones**, and the series
should behave like a series (2–3+ MMs, DH's norm). If price ignores your levels —
blows through HWB without reaction, or the "target" means nothing — **you seeded
the wrong leg. Re-seed.** This self-correction is the safety net that lets a
novice recover from a bad discretionary call.

## 3. Our operationalization (the mechanical proxy)

- `scripts/draw_mm_fib.py` already implements this: a **ZigZag pivot detector**
  (threshold `ZZ_PCT`, default 4%) → `last` mode (Step 2 last-completed leg) or
  `dominant` mode (Step 2 largest-range leg) → anchors snapped to true extreme
  wicks → all Halsey levels drawn.
- **The threshold is the ONE tunable parameter.** It literally encodes "how big
  must a leg be to jump off the page." Too low → seeds noise; too high → misses
  real legs. Tune per timeframe (Daily vs 15-min need different thresholds).
- This gives the course an **example generator**: feed any ES window → auto-seed →
  auto-draw → a fresh, correct worked example or a "pick the seed" drill.

## 4. Validation plan (before this goes in the lesson)

The rule must agree with DH's own eye. We have his **key-level slides**
(`data/site/getting_started/*/keylevels/*.png`, 16 per daily post) where he
annotates his actual seeds/levels.
1. Run the detector on the same dates.
2. Compare our seeded leg + levels to his annotated ones.
3. Tune `ZZ_PCT` (Daily and 15-min separately) until agreement is high.
4. Record the agreement rate + the chosen thresholds here before teaching.
   *(PENDING — do this next.)*

## 5. Common novice mistakes (teach these explicitly)

- Seeding off **noise** (a 3-tick wiggle) instead of a significant leg.
- **Re-seeding every bar** — chasing; the seed should be stable until it fails.
- Anchoring to **bodies/closes** instead of true wicks.
- **Recency bias** — grabbing the newest tiny leg while ignoring the dominant one.
- Ignoring the **higher timeframe** — seeding a 15-min counter-trend leg against
  the Daily trend.
- Acting on an **unconfirmed** extreme (skipping Step 4).

## 6. Drills (Module 2)

- **Pick-the-seed** on 8–10 ES charts (Daily + 15-min), graded against the
  detector/DH-slide reference; pass = 6/8 in agreement (soft — score shown, not a
  hard gate, per the course's soft-gate decision).
- **Two-seed** drill: given a chart, mark BOTH the dominant and the last-leg seed
  and state which governs bias vs entry.
- **Re-seed** drill: given a chart where price has broken the levels, decide
  whether to hold or re-seed, and to what.

## 7. Status / next

- Draft complete (this doc = Module 2 DH-BASE + `[OUR ADD]` procedure).
- **NEXT:** run the §4 validation (detector vs his key-level slides), tune
  thresholds, record agreement. Only then wire into the Module 2 lesson + the
  Modern-Edition chapter.
