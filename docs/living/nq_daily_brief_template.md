# NQ Daily Brief — user's template (recovered S75)

Source: PDF the user attached in session S73-day2 ("Fetch Net GEX, OI, IV, and gamma
exposure profile for NQ1", Google Docs export), recovered from the session transcript
2026-07-15. Implemented by `scripts/nq_daily_brief.py`. Kept here verbatim-in-substance
so the template is never again only inside a chat log.

## Task

Fetch Net GEX, OI, IV, and gamma exposure profile for NQ1! for today's date. Analyze
the Net GEX distribution for NQ1! for today's date. Identify where the largest GEX
concentrations are located relative to spot price. Highlight the transition zone where
GEX flips from negative to positive. Show me the gamma exposure profile for NQ1! —
where are the key gamma walls and what price levels would trigger accelerated moves.
Include the full Option Matrix breakdown by expiry with GEX, OI P/C, Call Wall and Put
Wall for each expiry. Include Q-Score all components, Blindspot levels, and Swing
Levels. After retrieving all data, summarise into ONLY this structure. No tables. No
bullets. No narrative sections. Bold section headers only. Plain text underneath.

## Language rules (strict)

1. Never use a data term (GEX, Q-Score, OI P/C, HVL, gamma, blind spot, conviction,
   expiry pin, etc.) without explaining what it means in plain English in the same
   sentence. Write as if the reader has never heard the term before.
2. Every WHY line must reference today's actual data values and explain what those
   values mean in plain language — not just repeat the label.
3. The DEALER INTENT section must explain what dealers are doing today and why, using
   plain English. No jargon without immediate explanation.

## Mode selection rule (strict, before writing BIAS)

Decision tree in order:
Step 1: Is GEX (total dealer gamma) Positive or Negative?
  If Negative → Mode = FOLLOW MOMENTUM (dealers amplify moves).
Step 2: If GEX is Positive — Positive GEX ALWAYS means FADE EDGES regardless of pin
  width (narrow <300 points or normal/wide 300+).
Step 3: Contradiction check: FOLLOW MOMENTUM and Positive GEX cannot appear in the
  same output; narrow pin ⇒ FADE EDGES. Correct Mode before outputting.

## Structure

**BIAS**
Regime: [Positive / Negative] GEX (explained) — what this means for NQ price behaviour
today in one plain-English sentence.
Mode: [FADE EDGES / FOLLOW MOMENTUM] — one sentence, no jargon.
Conviction: [label] — based on Q-Score (0-5 rating across four factors): Momentum
[score] meaning [...], Options [score] meaning [...], Volatility [score] meaning
[...], Seasonality [score] meaning [...].
GEX shift 24h: [value] — plain-English meaning of the overnight dealer repositioning
for today's level reliability.
Why today is different from a typical session: one sentence using actual data values.

**DEALER INTENT**
Max 5 sentences, plain English, using today's actual values. Cover: dealer position
and why they hold it; what they do when price rises (reference today's call wall +
GEX value); what they do when price falls (reference put wall + GEX value); their
goal today (stabilise / reduce exposure / capture premium / manage expiry); what
single event changes their behaviour and what that looks like in price.

**STRUCTURAL LEVELS**
Red lines — resistance
R1: [level] — 0DTE Call Resistance (explained). Why mark this: [today's 0DTE GEX value].
R2: [level] — All-Exp Call Resistance (explained). Why mark this: [total chain GEX].
R3: [level] — GEX Wall ranked [n] by size today. Why: rank + GEX value + reaction strength.
R4: [level] — GEX Wall ranked [n]. Why: rank + relationship to R3.
R5: [level] — Blind Spot ranked BL[n]. Why: rank → reaction probability.
Green lines — support
S1: [level] — 0DTE Put Support (explained). Why: today's OI P/C ratio explained.
S2: [level] — All-Exp Put Support. Why: total OI P/C → significance of the floor.
S3: [level] — GEX Wall ranked [n], nearest below price. Why.
S4: [level] — GEX Wall ranked [n], second nearest below. Why.
S5: [level] — Blind Spot ranked BL[n], nearest below price. Why.
Yellow lines — key zones
FLIP: [level] — HVL 0DTE (explained). Why: distance from FLIP in points → regime safety.
HVL: [level] — HVL All-Exp. Why: difference between FLIP and HVL and why both matter.
BL1: [level] — Blind Spot ranked 1. Why: overlap with any GEX wall today.
BL_near: [level] — nearest Blind Spot to price. Why: proximity.
RANGE HIGH: [level] — session ceiling from options-implied range. Why.
RANGE LOW: [level] — session floor. Why.

**TODAY SESSION CONTEXT**
Active expiry pin: [date] | [Put wall] – [Call wall]
What expiry pin means: (fixed explanation — dealers buy at put wall, sell at call wall,
trapping price until expiry). Pin width: [points] — [narrow/normal/wide]. Why this
width matters today (pin width × 0DTE GEX size → boundary reliability). Pin expires:
[time]. If price breaks above [Call wall]: dealer response + GEX P/C ratio explained.
If price breaks below [Put wall]: dealer response + OI P/C ratio explained.

**TOMORROW PRESSURE ON TODAY**
Next expiry: [date] | GEX [value] ([%] of total chain). Gravity level: [midpoint
price]. Why it pulls today: % of chain → gravitational pull toward the midpoint.

**WEEK CONTEXT**
Largest expiry this week: [date] | GEX [value] | [% of chain]. Effect on today.
GEX trend this week: [building / decaying] — plain-English meaning for volatility and
level reliability across the week.

**SKIP TODAY IF**
One sentence, plain English: the single condition that makes NQ levels unreliable
today and why.

## Implementation notes (S75)

- All fields covered by the direct MQ API (`scripts/mq_api.py`) EXCEPT Blind Spots
  (endpoint 404s — QUIN-only). The generator prints those lines as explicitly
  unavailable rather than filling them.
- Swing Levels ARE available: `swing-levels/{sym}` (trigger / band / direction daily
  history) — appended to STRUCTURAL LEVELS.
- Generator is deterministic (no LLM at runtime): every number is an API field;
  conditional sentences are position-aware (e.g. if spot is outside the 0DTE pin band
  the text says so instead of pretending price is inside).
- Gravity level = gamma-weighted average strike of the next expiry (max-OI midpoint
  was tried and lands on far-OTM lottery strikes).
- Run: `.venv/Scripts/python.exe scripts/nq_daily_brief.py [--symbol NQ1!]` →
  `data/briefs/<SYM>_brief_<date>.md` + raw JSON snapshot.
