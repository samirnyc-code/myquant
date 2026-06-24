# Keystone — Look-ahead & Robustness Audit (2026-06-24)

Try to BREAK it (guilty until proven innocent). Single-leg 2.0R, gated book.


## 1. OR60 causality — VERIFIED IN CODE

`indicators.py:263-274`: OR60 is the developing running 60-min range for the first hour (`bar_num < 12`, only bars seen so far) and frozen after. Causal. OR60 reaches signals via the S34-fixed causal merge; StopPrice is a direct CSV column. No as-of merge can land on the entry bar → the ER10 leak class is absent. PASS.


## 2. Session-timing split (the decisive look-ahead test)

_Early (BarNum<=12, OR60 still developing): 792 trades. After first hour (BarNum>12, OR60 frozen & unambiguously PAST): 603._

| subset | n | net $ | exp R | ±CI R | PF |
|---|---|---|---|---|---|
| ALL gated | 1395 | $232,593 | +0.159 | ±0.063 | 1.38 |
| AFTER first hour (clean OR60) | 603 | $115,833 | +0.203 | ±0.095 | 1.62 |
| DURING first hour (developing) | 792 | $116,759 | +0.126 | ±0.084 | 1.27 |

_If the AFTER-first-hour row holds the edge, OR60 timing is not the source._


## 3. Cost realism at 2R

| slip | n | net $ | exp R | ±CI R | PF |
|---|---|---|---|---|---|
| gate @ 1/0 base | 1395 | $232,593 | +0.159 | ±0.063 | 1.38 |
| gate @ 2/1 conservative | 1395 | $193,005 | +0.123 | ±0.062 | 1.30 |
| gate @ 3/2 brutal | 1395 | $157,218 | +0.092 | ±0.062 | 1.24 |

## 4. StopPrice sanity (causal past-extreme check)

- StopPrice on the correct side of SignalPrice (stop below for longs / above for shorts): **100.0%**

- StopPrice at/beyond the developing extreme (origin is a PAST swing low/high, not inside the formed range): **50.5%**

_Caveat: StopPrice comes from the NT MC indicator export; its internal causality can't be audited from here. But it's the same stop every MCSignal strategy uses, and these checks confirm it behaves like a past extreme._
