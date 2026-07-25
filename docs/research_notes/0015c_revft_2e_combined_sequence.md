# 0015c — RevFT-B + 2E: Combined Portfolio & RevFT→2E Sequence Edge — 2026-07-25
**Series:** MC Setup Research Notes · Note 0015c (companion to 0015 / 0015b)
**Confidence:** Combined-portfolio result is solid (both books validated separately). The
sequence/confluence findings are **exploratory** — in-sample, small cells, no permutation-null/OOS.

**Book B spec updated:** adopt the **hours 09–13 filter** (same window as the 2E book). B+hours =
n=908, **+$136,548, $/tr +$150.4, PF 1.30, maxDD −$28.6k** (was +$144.7k / PF 1.27 unfiltered — the
trim removes ~afternoon dead-weight, higher $/tr and PF at slightly lower total).

## 1. Combined portfolio: 2E three-book + RevFT-B (hours)
2E final three-book = WT-L + WT-S + FADE-S (FADE-L excluded, dead). `revft_2e_combined.py`.

| | n | Total $ | $/tr | PF | maxDD | block-boot DD 1% |
|---|---|---|---|---|---|---|
| 2E three-book | 822 | +84,940 | +103 | 1.29 | −17,260 | −44,398 |
| RevFT B (hours) | 908 | +136,548 | +150 | 1.30 | −28,605 | −59,259 |
| **Combined** | 1,730 | **+221,488** | +128 | 1.29 | **−39,860** | −61,151 |

- Combined green every year except **2023 (−$15.4k, the shared soft year)**: 2021 +6.3k · 2022 +75.0k
  · 2023 −15.4k · 2024 +62.7k · 2025 +57.2k · 2026 +35.7k.
- **Diversification is modest:** daily-P&L correlation **+0.39 on the 170 both-trade days**
  (+0.17 over the 0-filled union); combined maxDD −$39.9k vs −$45.9k summed → saves only ~$6k. The
  combined tail DD (−$61k) ≈ RevFT's alone. Both are regime/trend-driven and co-move — this is
  *additive return*, not a strong hedge. Size the pair for ~−$61k / (1 ES + 1 ES).
- Caveat: `combined_books_20260724.csv` is near-final, not the frozen 2E geometry — its FADE-S is
  ~breakeven here vs the spec's PF 1.35, so 2E totals run below the spec's +$93.7k / PF 1.44.

## 2. RevFT → 2E sequence edge  `revft_2e_sequence.py`
Alignment: 2E `fill_bar` and RevFT signal bar are both indices into the same RTH-day bars.

**A. Confluence (strongest finding).** 2E entries with a RevFT signal in the prior X bars beat those
without, at every window:

| within X bars | preceded=YES | preceded=NO | preceded + EMA-cross |
|---|---|---|---|
| 6 | $139/tr PF 1.38 (238) | $87 PF 1.24 (574) | $120 PF 1.32 (62) |
| 12 | $119 PF 1.33 (377) | $88 PF 1.24 (435) | $132 PF 1.36 (136) |
| 24 | **$131 PF 1.37 (505)** | $55 PF 1.14 (307) | **$157 PF 1.43 (275)** |

A RevFT within ~24 bars before a 2E entry marks the better 2E trades (PF 1.37 vs 1.14); an EMA cross
in between sharpens it (1.43). Candidate **2E sizer/filter**.

**B. Neutral-RevFT → fade (Samir's hypothesis) — real but book-specific (X=12):**

| 2E book | all | preceded by NEUTRAL RevFT |
|---|---|---|
| **FADE-S (f2EL)** | −$6.8/tr PF 0.98 | **+$120.7/tr PF 1.30 (n=70)** |
| WT-S (2ES) | +$174 PF 1.48 | −$106 PF 0.73 (n=32) |
| WT-L (2EL) | +$124 PF 1.40 | −$65 (n=18) |

A neutral RevFT specifically **rescues the f2EL fade** (breakeven → PF 1.30) — matches "RevFT in
neutral precedes a rotation, then the fade fires." It *hurts* the with-trend books (they don't want
preceding chop). Book-specific, not blanket.

**C. Forward.** ~32–34% of RevFT signals are followed by a 2E within 24 bars (median gap 8–13). The
follower is regime-aligned: RevFT-BEAR → **2ES $196/tr PF 1.55 (n=150)**; RevFT-BULL → 2EL $136 PF
1.46 (n=141). Neutral RevFT leans **short** (both short books +, long −$79/tr) — weak support for
"neutral precedes a downside trend change."

## 3. Actionable leads (all need the 0015b treatment before use)
1. **RevFT-preceded confluence as a 2E sizer** (n=505, PF 1.37 vs 1.14 unpreceded) — strongest.
2. **Neutral-RevFT as an f2EL enabler** (n=70, breakeven → PF 1.30) — Samir's idea; narrow, small-n.
3. Run the permutation-null + train/holdout (as in 0015b) on both before trusting — exploratory now.

## Reproduce
- `scripts/revft_2e_combined.py` → `docs/living/revft_2e_combined_equity_20260725.png`.
- `scripts/revft_2e_sequence.py` → `data/regime/revft_2e_sequence_20260725.parquet`.
- 2E trades: `myquant-regime/data/regime/combined_books_20260724.csv` (exclude FADE-L).
