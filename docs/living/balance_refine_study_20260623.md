# Balance-State Refinement (2026-06-23)

Conditioning balance_state (opened inside Y, still rotating) on IB / gap / Y value area. Look-ahead-safe, pinned 1.0R single-leg, real tick engine. Balance subset = **916 filled**. Thin cells flagged by n.


**Balance baseline:** | balance ALL | 916 | $82,306 | $+90 | ±69 | +0.100 | 1.24 | 54.6% |

**Full-pop baseline (context):** | ALL filled | 5444 | $258,314 | $+47 | ±24 | +0.041 | 1.14 | 52.1% |


## 1. IB width (OR60/ADR) tertiles  _cuts: 0.30 / 0.45 ADR_

| slice | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| IB low (narrow→wide) | 302 | $22,921 | $+76 | ±70 | +0.152 | 1.32 | 57.0% |
| IB mid (narrow→wide) | 294 | $46,393 | $+158 | ±126 | +0.115 | 1.42 | 55.1% |
| IB high (narrow→wide) | 298 | $16,838 | $+57 | ±154 | +0.045 | 1.11 | 52.7% |

### IB-extreme responsive fade (origin at IB edge)

| slice | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| LONG, origin at IB-low (≤0.05) | 182 | $21,819 | $+120 | ±158 | +0.182 | 1.29 | 59.9% |
| SHORT, origin at IB-high (≤0.05) | 184 | $23,960 | $+130 | ±163 | +0.165 | 1.31 | 58.7% |


## 2. Open location inside Y range (gap proxy)

| slice | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| open low third of Y | 306 | $53,591 | $+175 | ±131 | +0.185 | 1.50 | 59.5% |
| open mid third of Y | 309 | $9,515 | $+31 | ±104 | +0.036 | 1.08 | 52.1% |
| open high third of Y | 301 | $19,200 | $+64 | ±121 | +0.078 | 1.17 | 52.2% |

### Opened relative to Y value area

| slice | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| above_Y-VAH | 119 | $7,506 | $+63 | ±181 | +0.062 | 1.16 | 53.8% |
| inside_Y-VA | 692 | $59,183 | $+86 | ±81 | +0.096 | 1.23 | 54.3% |
| below_Y-VAL | 105 | $15,617 | $+149 | ±182 | +0.163 | 1.47 | 57.1% |


## 3. Origin vs Y value area (vaD)

| slice | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| above_VAH | 128 | $14,829 | $+116 | ±169 | +0.179 | 1.33 | 60.2% |
| at_VAH | 103 | $18,863 | $+183 | ±185 | +0.187 | 1.57 | 61.2% |
| inside_VA | 491 | $19,834 | $+40 | ±99 | +0.038 | 1.10 | 50.3% |
| at_VAL | 97 | $23,952 | $+247 | ±197 | +0.229 | 1.85 | 61.9% |
| below_VAL | 97 | $4,827 | $+50 | ±202 | +0.084 | 1.13 | 54.6% |

### PRE-COMMITTED responsive fades (fade Y-VA edge → POC)

| slice | n | net $ | exp $ | ±95%CI | exp R | PF | win% |
|---|---|---|---|---|---|---|---|
| LONG, origin at/below Y-VAL | 161 | $19,998 | $+124 | ±163 | +0.106 | 1.34 | 55.9% |
| SHORT, origin at/above Y-VAH | 170 | $25,059 | $+147 | ±152 | +0.122 | 1.40 | 56.5% |
| LONG, origin near Y-POC (≤0.10) | 106 | $15,613 | $+147 | ±245 | +0.170 | 1.44 | 60.4% |
| SHORT, origin near Y-POC (≤0.10) | 92 | $6,274 | $+68 | ±169 | +0.102 | 1.22 | 57.6% |
