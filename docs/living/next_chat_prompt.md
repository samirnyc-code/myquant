# Next-chat prompt — chart-marking workflow + touch-band exploration (from S75J)

Copy-paste from here down into the new chat.

---

Read `docs/living/handoff.md` FIRST — the S75J block (2026-07-17) at the top is current
state. Also skim `docs/living/orderflow_edge_backlog.md` and memory (`free-footprint-pipeline`,
`backtest_fill_realism`, `keep_in_check`).

**Where we are:** `scripts/orderflow_at_levels.py` runs the first touch/signature/outcome
study of ES order flow at MenthorQ levels (75 episodes over 7/13–7/16, chart-audited —
an episode-detection bug was found and fixed BY the audit; the per-day audit chart is now
mandatory before trusting any table). 4-day readout: H2 (HVN≡level) soft-positive; H5
(absorption) mis-defined — the day's best fades all showed heavy counter-delta into the
level with ~1pt heat, so absorption should be **delta-per-point-of-progress**, not a range
cap; H1 untestable at n=2. Data: `data/footprint/ES_footprint.csv` (ladder, dedupe on
load — exporter APPENDS on re-run), `ES_bars.csv` (2000-lot volume bars + tick-order
fields), `ES_metrics.csv`, `level_touches.csv`; ES1! MQ levels through 7/16 (native ES
points — no basis adjust needed within the 2-yr futures-levels window).

**THIS SESSION — two workstreams, in order:**

**1. Chart-marking workflow (design carefully with me before building — I'm not yet clear
on the best way to do this).** The idea: I mark great trade setups on charts (BOPB /
breakout-pullbacks, second-entry fades at levels), you find what they have in common in
the footprint/level data. Agreed guardrails (hold me to them): I mark the SETUP by my
rules — including ones that then failed — NOT the outcome (hindsight leak); analysis =
marked setups vs **matched controls** (unmarked touches, same days/levels); whatever
discriminates becomes a pre-registered rule tested on unmarked history — marks are
hypothesis generation only. Proposed build: a local click-to-annotate page (stdlib
http.server, command-center pattern — NO Streamlit) showing per-day ES bars + MQ levels;
click a bar → tag setup type (BOPB / 2nd-entry fade / other), direction, optional A/B
grade → append to `data/annotations/marks.csv` with the exact bar timestamp. Day picker +
keyboard shortcuts so a mark takes seconds. Open design questions to work through with me:
what context I need on the marking chart (footprint delta? CVD? or deliberately price-only
to avoid anchoring me on the features we're testing?), one-sided vs graded labels, how
many days before first feature-ranking pass, and how to randomize/blind day order.
Calibrate the whole loop on 7/13–7/16 first (footprint already on disk) before I invest
hours of marking.

**2. Touch-band size exploration.** The ±4-tick band was arbitrary-but-pre-committed.
Run the sensitivity pass (±2 / ±4 / ±8 ticks — an effect that only exists at one width is
not real) AND explore a **volatility-normalized band**: fixed points mean different things
in different regimes, so test band = k × ABR (avg bar range) or k × ADR% (avg daily
range) — pick the definition and k BEFORE looking at outcome tables, and say explicitly
which normalization is used for the 5-yr run. The 5-yr window includes 2022 vol — a
1-pt band there is a different instrument than in 2026.

**WHY (both goals, keep them in view):** (a) find actual ES setups worth trading; (b) find
better ways to trade the OPTIONS strategies — level-hold/break signatures should condition
0DTE structure choice, entry timing, and the fly proximity gate (S75H finding: fly fired
50pts off-center; criteria FROZEN, changes need backtest + sign-off).

**Blocked/parked:** 5-yr NT8 footprint export needs the exporter truncate-on-start fix
first (else chunks append into a mess) — bundle with `BidVolLarge/AskVolLarge` ≥10-lot
columns (unlocks a real H5 test) into ONE recompile for me. MzPack 14-day trial running
(extract VolumeProfile/VolumeDelta). ORATS calibration owed when data lands. Databento
paused awaiting sales reply.

**Hard rules:** real fills only; chart-audit before reporting any result; treat PF>3 as a
bug until proven; `_continuous_UNADJ` bars for anything price-level; day-clustered stats
(one choppy day gave 26/75 episodes — independent-sample stats are fake precision);
present all results inline as tables (I can't see tool output); every PNG gets `code`-opened;
challenge my research direction and flag overfitting/fishing explicitly.
