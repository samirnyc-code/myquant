# IB-edge Gate — Equity & Drawdown Path (2026-06-23)

Stitched 1-contract gated book (origin ≤0.10 ADR inside IB edge). The DD PATH decides prop survivability — and the right TARGET is vehicle-dependent.


## Target vs drawdown-PATH tradeoff (both-dir)

Higher target = higher total/MAR but does it sit deeper, longer? (% time = fraction of trades that deep below peak.)

| target | net $ | maxDD $ | MAR | %time >$2.5k | %time >$5k | %time >$10k |
|---|---|---|---|---|---|---|
| 1.0R | $162,393 | $23,468 | 6.92 | 69% | 51% | 23% |
| 1.25R | $194,268 | $27,330 | 7.11 | 65% | 45% | 25% |
| 1.5R | $206,355 | $26,505 | 7.79 | 68% | 48% | 25% |
| 2.0R | $232,593 | $26,256 | 8.86 | 66% | 48% | 27% |


## Detail @2.0R

- trades: 1395 · monthly positive: 42/61 (69%)

### Both directions
- Net (1 contract, 5yr): **$232,593** · MAR (net/maxDD): **8.86**
- **Max drawdown: $26,256** · time underwater: 88%
- Longest DD: 59d peak→trough, 217d to recover
- Longest losing streak: 15 trades · worst trade $-3,142 · best $10,646

### Short only
- Net (1 contract, 5yr): **$95,990** · MAR (net/maxDD): **5.44**
- **Max drawdown: $17,637** · time underwater: 91%
- Longest DD: 226d peak→trough, 108d to recover
- Longest losing streak: 10 trades · worst trade $-3,142 · best $6,496


### Drawdown DEPTH distribution (both-dir) — how deep is the 'underwater'?

| drawdown band | % of trades (time) |
|---|---|
| < $250 (≈at peak) | 13% |
| $250–1k | 7% |
| $1k–2.5k | 15% |
| $2.5k–5k | 17% |
| $5k–10k | 22% |
| $10k–15k | 15% |
| > $15k | 11% |


### Worst 6 months (both-dir)
| month | $ |
|---|---|
| 2025-11 | $-12,543 |
| 2023-01 | $-10,129 |
| 2026-05 | $-9,473 |
| 2023-02 | $-9,338 |
| 2022-05 | $-8,683 |
| 2024-02 | $-4,662 |
