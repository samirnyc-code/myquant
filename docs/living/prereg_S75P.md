# Pre-registration — S75P gamma tests (written 2026-07-18, BEFORE running)

Written first so the spec can't drift after seeing results. Both tests use data
already on disk. No parameter sweeping: one spec each, stated below.

---

## Test A — CR/PS intraday repulsion

**Question:** do our CR/PS levels repel intraday price more than an arbitrary level
at the same distance from spot?

**Sample:** every session where ES 5-min bars, SPX daily (for basis) and prior-session
ORATS levels all exist. Expected n ~1,159 sessions (2021-06-18 .. 2026-07-09).

**Gate:** only sessions where the level sits within **1.0%** of the prior close
(levels beyond that are unreachable — 58% of days — and dilute the test).

**Trigger:** first 5-min bar whose High reaches within **5 pts** of the level (CR)
or whose Low reaches within 5 pts (PS).

**Outcome (race):** from that bar forward — REJECT if price travels **10 pts** away
from the level before travelling **10 pts** through it; BREAK otherwise. Unresolved
sessions are discarded.

**Control:** permutation — same day's spot, but the level-distance borrowed from a
random other qualifying day. 20 shuffles, averaged. This holds distance constant and
destroys only the link to the actual gamma wall.

**Success criterion:** reject rate exceeds the permutation control by **> 2 standard
errors**. Anything less = no edge, and CR/PS is closed.

**Conversion:** ES = SPX + that day's basis (prior-day basis, no lookahead).

---

## Test B — does gamma add anything beyond price / vol / trend?

**Question:** does dealer-gamma information improve prediction of next-session
realized range, over a baseline built only from free price and volatility data?

**Target:** next-session realized range, `(High-Low)/Close * 100`.

**Baseline features (all free, all known at prior close):**
- VIX close
- distance of close from its 20-day MA (%)
- realized range over trailing 5 and 20 sessions

**Gamma features added (all from ORATS prior-session chain):**
- signed distance from close to HVL (%)
- signed distance to CR and to PS (%)
- total net GEX (sum of the profile)
- profile concentration (share of |GEX| in the top 3 strikes)

**Model:** gradient boosting, fixed hyperparameters, no tuning.

**Split:** train 2021-09..2024-12, test 2025-01..2026-07. Strictly chronological,
no shuffling, no peeking at the test set.

**Metric:** out-of-sample R² and MAE on the test period.

**Success criterion:** the gamma model beats the baseline on out-of-sample R² by a
margin larger than the spread across 5 random seeds. If gamma adds < that, the honest
conclusion is that gamma contributes nothing beyond VIX + trend.

---

## Committed interpretations (so results can't be re-spun)
- If A fails: CR/PS as repulsion levels is closed. No further zone/threshold variants.
- If B fails: gamma adds nothing measurable beyond free data at daily resolution.
  We do NOT then go hunting at other horizons to rescue it in the same breath —
  any new horizon becomes a new pre-registration.
- The 2007-2021 ORATS pull stays UNPULLED until something here survives.
