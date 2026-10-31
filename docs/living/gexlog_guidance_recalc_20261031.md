# GEX brief guidance recalc + gap-vs-EM significance (2026-10-31)

**Status: observational only, no rule changes.** Same deferral as the setup
review — this feeds the same EOY/3-month decision point, nothing acted on now.

Script: `scripts/gexlog_guidance_recalc_20261031.py`. Parses the RAW archive
(`data/gexlog/raw/*.json`, 148 days back to 2026-04-06), not the flattened
CSV, to get `guidance.signal`, `market.spx.open` (not previously captured),
and the narrative text.

## Part 1 — recomputed P&L under the brief's own Go/Caution/Wait guidance

GexLog's methodology page states the `signal` field specifically "reflect[s]
regime context for premium-selling strategies" — i.e. it's already his
explicit answer to "should you run credit-selling structures today," which is
exactly what all 10 of our setups are. Simulated: what if we'd sat out
entirely on the days he said Wait (and separately, Wait+Caution)?

| | Actual (no avoidance) | Skip "Wait" days | Skip "Wait"+"Caution" |
|---|---|---|---|
| Total P&L | **+$9,776.68** | +$4,093.70 (-$5,683) | +$1,872.32 (-$7,904) |

Days tagged in our window: 6 Go / 39 Caution / 14 Wait (out of 59).

**Following the signal literally would have cost us more than half our
3-month profit.** This is the opposite of the naive expectation. Breaking it
down by strategy shows why — it's not uniform:

| strategy | actual | skip Wait | skip Wait+Caution |
|---|---|---|---|
| eodfly_p | -$833 | **-$3,922** (much worse) | -$172 |
| openfly_p | +$1,237 | **-$1,010** (flips negative) | -$989 |
| gx_bps | -$145 | -$320 (worse) | +$1,123 |
| eodic_p | -$945 | -$479 (improves) | +$191 |
| gx_bcs | +$1,136 | +$1,176 (flat) | +$571 |
| eodic_c / openic_c / eodfly_c / openfly_c | all positive | mostly flat-to-better | mixed, mostly worse |

`eodfly_p` and `openfly_p` specifically did **better on the days GexLog said
Wait** than on other days — the opposite of what the signal would suggest.

**Why the blanket signal doesn't transfer:** GexLog's own text reads as
calibrated for generically risky premium-selling (naked/undefined-risk
exposure to a big trending move). Our structures are all max-loss-capped
verticals — the exact tail risk the signal warns about is already bounded by
construction. A signal built for "don't sell unlimited-risk premium today" is
a different question than "don't run a defined-risk 25-wide vertical today,"
and this data says those two aren't the same decision.

**Sanity check on the signal itself:** the narrative's own "Income
structures... are misaligned" sentence doesn't cleanly reduce to the
structured `signal` field either — it appears on 62/100 "Caution" days, 22/31
"Wait" days, but also **6/15 "Go" days**. The prose and the structured signal
aren't perfectly consistent on his side, so this isn't a case of us misreading
a clean rule — the rule itself is fuzzy at the edges.

**Conclusion for now: do not use the blanket Go/Caution/Wait signal as a
sit-out filter for this book.** It would have been a net loser over this
window. If there's a usable signal in the brief, it isn't this one in this
form — worth revisiting with a longer sample and a per-strategy (not blanket)
avoidance rule, not now.

## Part 2 — does the overnight gap (open vs. prior close) relative to the EM matter?

Pulled the actual SPX open from each evening report (`market.spx.open`,
not previously captured anywhere locally) against the morning's EM band
(anchored to the prior close). `gap_frac_em = |open - prior_close| / expectedMove`.

**Yes — clean, strong, monotonic relationship with whether the EM band gets
breached that session:**

| Gap size (as % of EM) | n days | EM-hit rate (band held) |
|---|---|---|
| < 15% | 44 | **95.5%** |
| 15-30% | 39 | 89.7% |
| 30-50% | 38 | 81.6% |
| **> 50%** | 24 | **50.0%** |

A gap that already eats more than half the expected move roughly **doubles to
10x's** the chance of a breach versus a small gap. This is real, monotonic,
and known at the open — well before most of our fills land.

**But it does NOT show a clean link to our own day-level P&L in this sample:**

| Gap bucket | eod-anchor avg day P&L | open-anchor avg day P&L |
|---|---|---|
| < 15% EM | -$64 | +$60 |
| 15-30% EM | +$170 | +$201 |
| 30-50% EM | -$28 | +$199 |
| > 50% EM | -$45 | +$57 |

No monotonic pattern either direction. Correlation of gap-fraction vs.
same-day P&L: eod -0.15, open -0.01, gexlog -0.12 — all weak, none near
significance at n≈58.

**Likely reason, not yet tested:** this used the *unsigned* gap size.
P&L is directional — a big gap up should hurt call-sellers and help
put-sellers, and vice versa for a gap down; averaging both directions
together in one "anchor" bucket could be canceling out a real effect. The
EM-breach relationship above is clean because breach doesn't care about
direction; P&L does. A proper next step would split by gap *direction* and by
*side* (put vs call) instead of by anchor alone — not done yet, flagging as
the obvious follow-up rather than a finding.

Data: `data/options_log/_analysis/gexlog_brief_days_full_20261031.csv`,
`gexlog_gap_em_merged_20261031.csv`, `gexlog_signal_recalc_by_*_20261031.csv`.

## Follow-up (2026-11-01) — does EOD- vs Open-anchoring matter for the condor specifically?

User's inference: since EOD strikes are set from the PRIOR close (before any
gap is known) and Open strikes are set from TODAY's open (after the gap),
EOD should be more exposed to gap risk. Tested directly on `eodic`/`openic`
(the two EM-strike condors — `scripts/gap_direction_ic_test_20261101.py`),
splitting by gap direction and put/call side.

**Confirmed, but the clean story is wrong — it's not "gap size," it's
variance/tail risk, concentrated in a handful of specific days:**

- Put side on gap-DOWN days (n=23): `eod_put` total -$376 (avg -$16) vs
  `open_put` total +$848 (avg +$39). Looks like confirmation — but sorting
  the big-down-gap days individually shows `eod_put` is **wildly bimodal**:
  solidly positive ($117–$417) on 9 of 12 days, and catastrophic on exactly
  3 — **2026-10-30 (-$1,703), 2026-10-14 (-$987), 2026-10-22 (-$767)** — the
  same 3 days that already showed up as shared worst-days across the whole
  put-selling family in the earlier setup review. `open_put` stayed small
  and positive on those same 3 days (+$97, +$27, +$17). This isn't "bigger
  gap = worse EOD," it's "EOD has fat tails, Open is capped" — and the tail
  risk is 3 specific trend days, not a gap-size gradient.
- Call side on gap-UP days: the mirror-image test does **not** confirm the
  same mechanism — `eod_call` average (+$38) actually beat `open_call`
  (+$19) on big up-gaps, the opposite of the put-side pattern. One outlier
  (2026-10-02, eod_call -$582) drags the average down; excluding it,
  `eod_call` is uniformly strong on every other big-up-gap day. Small n
  (11 days in that bucket) — not confirmed either way, flagged as a puzzle.

**Honest conclusion:** `open`-anchored strikes do look more consistent/
capped across this sample (lower variance on both sides), and `eod`-anchored
strikes do carry more tail risk — but it shows up as 3-4 specific bad days,
not a smooth relationship with gap size. Don't read this as "open-anchoring
is proven structurally superior" — it's "open-anchoring missed the same 3
bad trend days that hurt everything else in this book," which is consistent
with, not independent evidence for, the gap-exposure theory. Needs more data
(more big-gap days) before trusting the mechanism itself.
