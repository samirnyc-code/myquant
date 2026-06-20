# Per-setup VA-imbalance WFA + open-ended threshold test
*Generated 2026-06-20 20:42 · headless · same engine · LOCKED filter, no tuning to result (PROJECT_CHARTER §4).*

## Part A — individual CC setups: baseline vs VA-filtered (OOS)
*CC1 excluded: 129 signal-days < the 315 (252 IS + 63 OOS) needed for one fold.*

| Setup | Folds B→V | OOS trades B→V (−%) | Expectancy $ B→V | Net $ B→V | Best-yr% B→V | MAR B→V | Mean PROM B→V | Med WFE% B→V |
|---|---|---|---|---|---|---|---|---|
| CC2 | 6→3 | 505→239 (−53%) | $92→$98 | $46,535→$23,308 | 93→124% | 4.13→2.29 | -0.18→-0.18 | 232→71% |
| CC3 | 10→7 | 1084→692 (−36%) | $18→$35 | $19,123→$24,299 | 60→47% | 0.94→1.49 | -0.90→-0.88 | 75→26% |
| CC4 | 11→7 | 1206→719 (−40%) | $42→$32 | $50,244→$23,230 | 66→89% | 3.29→2.01 | -0.74→-0.70 | 42→91% |
| CC5 | 8→5 | 752→443 (−41%) | $74→$99 | $55,494→$44,021 | 49→54% | 3.65→4.08 | 0.14→0.02 | 104→103% |

- **CC2:** exp ↑, PROM ↑, best-yr ↑(worse), net ↓ → 2/3 durability dims up
- **CC3:** exp ↑, PROM ↑, best-yr ↓(better), net ↑ → 3/3 durability dims up
- **CC4:** exp ↓, PROM ↑, best-yr ↑(worse), net ↓ → 1/3 durability dims up
- **CC5:** exp ↑, PROM ↓, best-yr ↓(better), net ↓ → 2/3 durability dims up

## Part B — open-ended VA-threshold framing (descriptive, OOS only)
*Pooled LOCKED baseline OOS trades across CC2, CC3, CC4, CC5 (100% matched to a VA tag). depth = |vaD_dist| in ES points.*

**Discrete location (the 3-bucket framing):**

| Location | OOS trades | Expectancy $ | Win% | Net $ |
|---|---|---|---|---|
| inside | 949 | $31.1 | 50.9% | $29,478 |
| below | 1210 | $56.7 | 52.9% | $68,658 |
| above | 1388 | $52.8 | 52.4% | $73,261 |

**Open-ended depth floor `|vaD_dist| ≥ k` (outside-VA trades only):**

| Floor k (pts) | OOS trades | Expectancy $ | Win% | Net $ |
|---|---|---|---|---|
| ≥ 0 | 2598 | $54.6 | 52.7% | $141,918 |
| ≥ 2 | 2478 | $43.6 | 52.1% | $108,016 |
| ≥ 4 | 2347 | $43.3 | 52.2% | $101,696 |
| ≥ 6 | 2210 | $44.3 | 52.4% | $97,958 |
| ≥ 8 | 2065 | $49.8 | 52.9% | $102,892 |
| ≥ 12 | 1848 | $42.8 | 52.5% | $79,106 |

- Expectancy as the floor deepens: $55 → $44 → $43 → $44 → $50 → $43.
- **No clear rise** with depth. This does NOT support a deeper-is-better threshold — the edge is in being outside the VA at all, not in how far. *(Descriptive: we report the trend; we do NOT select a k against OOS — that would be the no-feedback violation.)*
- Inside-VA expectancy **$31.1** vs outside-VA **$54.6** — the {below, above} cut is justified (it drops the weaker-expectancy bucket).