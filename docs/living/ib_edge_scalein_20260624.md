# Keystone — Multileg Accounting Check + 'E1 scratch / E2 win' Scale-In (2026-06-24)

Gated book. **Net $ and MAR are trustworthy; exp R is engine-inflated for multileg (RiskDollar uses leg-1 only, sim_engine:670) so it is omitted.**

| variant | n | net $ | exp $/trade | win% | scratch% | PF | maxDD $ | MAR |
|---|---|---|---|---|---|---|---|---|
| DIAG single 1R (1c) | 1395 | $162,393 | $+116 | 56.3% | 0.0% | 1.30 | $23,468 | 6.92 |
| DIAG single 2R (1c) | 1395 | $232,593 | $+167 | 48.5% | 0.0% | 1.38 | $26,256 | 8.86 |
| DIAG ML both@2R (2c) | 1395 | $465,186 | $+333 | 48.5% | 0.0% | 1.38 | $52,511 | 8.86 |
| DIAG ML scaleout 1R/2R (2c) | 1395 | $381,798 | $+274 | 56.3% | 0.0% | 1.35 | $44,986 | 8.49 |
| SCALEIN exit@E1 entry (X=0) | 1395 | $-29,351 | $-21 | 0.0% | 0.0% | 0.00 | $29,346 | -1.00 |
| SCALEIN exit@0.25R | 1395 | $-24,389 | $-17 | 66.5% | 0.0% | 0.91 | $34,388 | -0.71 |
| SCALEIN exit@0.5R | 1395 | $5,356 | $+4 | 60.8% | 0.0% | 1.01 | $41,460 | 0.13 |
| SCALEIN exit@1.0R | 1395 | $97,519 | $+70 | 67.8% | 0.0% | 1.16 | $36,041 | 2.71 |

## Accounting check

- single 2R (1c) net = $232,593; ML both@2R (2c) net = $465,186; ratio = **2.00x** (must be ~2.00 if multileg net is correctly scaled).

- ML scaleout 1R/2R net = $381,798; expected (single1R + single2R) = $394,986; ratio = **0.97x** (must be ~1.00).
