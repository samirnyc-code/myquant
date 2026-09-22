# 0015b — RevFT × Regime: Validation Battery & Go-Live Roadmap — 2026-07-25
**Series:** MC Setup Research Notes · Note 0015b (companion to 0015)
**Confidence:** ⚠️ **DOWNGRADED — read §DESTROYER FIRST.** The battery below tested whether the REGIME
GATE is informative (it is: permutation null on the labels p<0.0001) — but it NEVER tested whether the
RevFT SIGNAL itself adds value. A later red-team (`revft_bookb_destroy.py`) shows it does not: a
random-time entry on the same day/direction/exit reproduces ~69% of the return (p=0.12, signal loses to
random timing on 60% of trades), and the entire profit is 20 of 908 trades (remove them → negative).
**Book B is destroyed as a RevFT *signal* edge; what remains is negative-gamma trend-day drift capture
(regime beta), tail-concentrated. Not a deployable signal edge.**

## ⚠️ DESTROYER (adversarial red-team, conservative $30/tr) — `revft_bookb_destroy.py`
1. **Random-time null (kill):** replace each entry with a random 09-13 bar, SAME day/direction/exit.
   Book B $125,198 vs random-time null mean $86,365 (95% $21k–$150k). **p(null≥actual)=0.12 (ns)**;
   signal beats random timing on only 40% of trades. ⇒ ~69% of the return is drift capture; the RevFT
   entry timing adds nothing significant. (The null was HANDED RevFT's direction, so this kills the
   timing claim; even so it reproduces 69% of return.)
2. **Tail jackknife:** remove top-10 → $40k (68% of profit in 10 trades); **top-20 → −$7k (negative)**;
   top-30 → −$46k. The entire edge is ~20 of 908 trades. A few-trend-day mirage, same as 2ES.
3. **Recent decay:** the one it survives — 2025 PF 1.32, 2026 PF 1.35, last-12mo PF 1.38 (not decayed).

**Verdict:** the 0015b battery proved the GATE (which days to trade) is real; it did not prove the
SIGNAL is. The signal fails the random-time null and the whole book is 20 tail trades. Retire Book B as
a standalone signal edge. Residual = "neg-gamma with-trend/neutral drift, hold to close" = regime beta,
tail-dependent (needs the big trend days), not RevFT-specific. Everything below is the (now-superseded)
gate-level battery, kept for the record.

---

_Original battery (gate-level; DOES NOT test the signal — superseded by the destroyer above):_

**Method mirrors the S83 2E book's 10-test battery** (`R2E_system_config_v1.md`, worktree
`regime/indep`) — the same bar that graduated REGIME-2E to rc1. RevFT has almost no fitted
parameters (drop-CT, neg-gamma, EOD-hold are all param-free; the 0.30×ADR stop is *inherited* from
the 2E book, not fit to RevFT), so 8 of 10 tests are analytic from the per-trade table
(`data/regime/revft_regime_full_20260725.parquet`) — no tick re-sim. `scripts/revft_regime_stress.py`.

**Books under test** (native next-tick entry, wide 0.30×ADR stop, hold-to-EOD, $5 RT + 1t):
- **A = DROP-CT** (drop counter-trend, all gamma) — n=2,742, +$123.5k, PF 1.12.
- **B = NEG-gamma & DROP-CT** (headline) — n=1,171, +$144.7k, PF 1.27.

---

## Results (2026-07-25)

| # | Test (breaks it if…) | Book A | Book B | Verdict |
|---|---|---|---|---|
| N1 | **Permutation null** — permute reg+mq labels 2000×, re-gate. *Breaks if the real gate sits inside the null (edge = lucky subset).* | real $45 vs null μ≈2 [p97.5=22] | real $124 vs null μ≈2 [p97.5=50] | ✅ **p<0.0001 both** — gate is informative |
| N2 | **Gamma train/test inversion** — the exact trap that killed the 2E pos/neg label (tr PF 2.07/te 0.91). *Breaks if train PF≫test PF.* | — | train PF 1.15 / **test 1.39**; neg-lift +$76→+$196/tr | ✅ stable, test-stronger |
| 1 | **Rolling OOS quarters** (param-free rule). *Breaks if mostly red.* | 57% green, worst −$15k | 65% green, worst −$11k, med +$6.4k | ⚠️ ok (2E bar 78%) |
| 2 | **Cost stress** $10 RT + 2t both sides. *Breaks if PF<~1.1.* | PF 1.12→**1.01** | PF 1.27→**1.17** (+$95k) | A FAIL · B PASS |
| 3 | **Pessimistic fills** +1t slip, drop 10–25% MC. *Breaks if edge evaporates.* | +$22–81k med | +$59–117k med, worst-5% +$59k | ✅ |
| 5 | **Engine invariance** re-gate with pt_old. *Breaks if a legit engine kills it.* | $45.0→$45.5/tr | $123.6→$113.4/tr | ✅ not fit to one engine |
| 6 | **Block-bootstrap DD** 5-trade blocks. *Sets the honest sizing #.* | real −$35k, worst-1% −$92k | real −$32k, worst-1% **−$59k** | ⚠️ size off −$59k |
| 7 | **Param neighborhood** stop 0.20/0.30/0.50×ADR × EOD. *Breaks if a fragile peak.* | all +, $95k→$156k | all +, $123k→$160k | ✅ plateau |
| 8 | **LOYO + tail jackknife**. *Breaks if one year / few trades carry it.* | LOYO min +$83k; top-20→**−$9k** | LOYO min +$100k; top-20→+$12k | ⚠️ tail-concentrated |

### Interpretation
- **N1 is the headline.** The permutation null already accounts for "one of ~26 searched subsets" —
  it asks whether a *random* equal-size gate does as well. It does not (null μ≈$2/tr, real $124, p<1e-4).
  The regime/gamma label carries genuine information; the edge is not a multiple-testing artifact.
- **N2 clears the 2E trap.** The 2E book's own gamma label inverted train↔test and was retired. RevFT's
  is the opposite — the neg-gamma advantage is *larger* out-of-sample (+$76 train → +$196 test /tr).
- **Book A is marginal; retire as standalone.** It dies under realistic costs (PF→1.01) and turns
  negative when the top-20 winners are removed. The negative-gamma filter is **load-bearing** — it is
  what gives the ~2.7× $/tr and the cost cushion. Trade **B**, not A.
- **Two quantified risks carry forward:** (1) **tail-concentration** — top ~20 of 1,171 trades ≈ all
  profit (same signature as the 2E book) ⇒ no discretionary exits, hold every runner to EOD, expect
  high variance; (2) **honest DD worst-1% = −$59k / 1 ES** ⇒ the sizing constraint (1 ES needs to
  survive −$59k; scale to MES accordingly).

---

## Go-live roadmap — the remaining gates (blocked here)

**Tier 3 — external data / live (each is a hard gate before capital):**
- **#4 Independent-data cross-check (Databento).** Our ticks are NT/massive-derived (~20 bad closes
  2021–23 on record). Re-run B on clean Databento ES ticks. *Breaks it if the edge doesn't replicate.*
- **#10 Out-of-period + cross-instrument.** (a) ES 2010–2020 (Databento) — does the edge exist outside
  2021–26? (b) NQ / MES — needs a **RevFT (MyReversals) signal export on those instruments** (the
  signal set is ES-only today). This is the strongest test that it isn't period/instrument-specific.
- **#9 NT8 reconciliation → forward MES.** Signal-diff the phase-machine gate (C# `RegimePhaseMachine`)
  vs the research engine trade-for-trade (the S84b marks-diff harness already exists), confirm the gamma
  regime is available live (MQ daily label), then a **forward MES paper period logging actual fills vs
  model**. *Breaks it if real fills ≠ model.*

**Sequencing:** #4 (cheap, confirms the sample isn't a data artifact) → #10a period + #10b instrument
(the generalization gate) → #9 (deployment gate). Only after #4+#10 should NT8 wiring + forward MES
begin. Do **not** deploy on the 8-of-10 in-sample battery alone — the same battery passed the 2E book
in-sample too, and the honest DD (−$59k) plus tail-concentration mean a bad forward stretch is
survivable only if the sizing respects the bootstrap number.

## Reproduce
- `scripts/revft_regime_stress.py` — the full battery (reads `revft_regime_full_20260725.parquet`).
- Base study + per-trade table: note 0015 (`revft_regime_full.py`, `revft_regime_deep.py`).
- 2E battery this mirrors: `myquant-regime/docs/research_notes/R2E_system_config_v1.md` +
  `regime_2e_stress_battery.py`.
