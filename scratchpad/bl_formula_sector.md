# Blind Spot FORMULA hunt — SECTOR-ETF hypothesis  [S75V]

**Verdict: REFUTED.** Sector ETFs do **not** explain ES/NQ Blind Spots better than chance,
and add **nothing** beyond SPY/QQQ. The genuine day-by-day confluence signal lives in the
**broad index complex (SPY/QQQ)**, not in sector ETFs.

Script: `scratchpad/bl_sector_hunt.py`  ·  raw: `scratchpad/bl_sector_raw_out.txt`
Data: `scratchpad/bl_basket_gamma.json` (38 syms, 202 days) + `data/menthorq/<SYM>_mq_blindspots_history.csv`.
Method: ES spot & each ETF spot = (1D Min+1D Max)/2 that day; map ETF gamma levels into
ES/NQ space by daily spot-ratio. **Train first 140 sessions, TEST held-out last 60.**
Two level sets: `struct` = {Call Resistance, Put Support, HVL, Gamma Wall 0DTE}; `all` = every
level incl. GEX 1..10 & 0DTE variants. Everything REAL vs NULL with win-rate z / paired t.

---

## Test A — is any SINGLE sector special? → No robust OOS effect
Real = median nearest-distance of the 10 ES BL to one sector's mapped levels; null = random
BL points in the BL band (many draws). 12 sectors × 2 sets tested (multiple-comparison aware).

**ES, struct, ranked by OUT-OF-SAMPLE ratio (lower = BL closer than random):**

| sector | IS ratio (z) | OOS ratio (z) | OOS win% |
|--------|-------------|---------------|----------|
| XLF  | 0.94 (+1.4) | 0.84 (+1.8) | 62 |
| XLRE | 0.90 (+2.2) | 0.86 (+2.3) | 65 |
| XLV  | 0.91 (+2.2) | **0.88 (+3.1)** | 70 |
| XLP  | 0.84 (+4.6) | 0.88 (+2.6) | 67 |
| … XLK/SMH/XLE/XLC | ~0.95–1.06 | ~0.95–1.06 (z≤+1 or negative) | ≤57 |

- The strongest/most consistent for ES are **XLV** and **XLP** (defensives), holding OOS at z≈+3/+2.6.
  But with 12 sectors tested, one or two at z≈+2–3 is within multiple-comparison expectation.
- **NQ kills it:** the sectors that looked good in-sample **collapse or reverse** out-of-sample —
  XLU +4.1→**−1.6**, XLV +3.7→+0.5, XLF +2.7→+0.0, XLP +1.9→**−1.6**. The only OOS-positive NQ
  sector (SMH +2.4) was *negative* in-sample. That inconsistency is the signature of noise.
- The `all`-levels set (dense, incl. GEX) sits at ratio ≈1.00 everywhere: no enrichment beyond density.

→ **No single sector is robustly special across ES *and* NQ, in *and* out of sample.**

## Test B — sector OVERLAP → does not predict BL, nor bl_index, OOS
Count distinct sectors with a mapped struct level within 0.1% of spot (~7 ES pts) of each BL.
- Mean #sectors-overlapping a BL vs random points: ES IS +0.9σ (NS), OOS +1.8σ (marginal);
  NQ IS +2.5σ but OOS **−1.7σ (reverses)**.
- Does #overlap predict the MQ internal index (BL1 = "most overlap")? corr(index, overlap):
  ES IS ρ=−0.082 p=0.002 (weak, right sign) but **OOS ρ=+0.035 p=0.39 — gone**; NQ NS both.

→ **The "BL1 = most sector overlap" idea does not survive out-of-sample.**

## Test C — do sectors ADD anything beyond SPY/QQQ? → No (density artifact)
Naively, {SPY,QQQ+sectors} med-NN to BL crushes {SPY,QQQ} alone (ES 21→5 pt, z≈+12–17). But
that is **trivial density**: a matched-count *random* null pool is just as close. Two clean controls:

- **C2 (add real sectors vs add same # of RANDOM levels to SPY/QQQ):** real is **worse**, not better —
  ES ratio 1.82–1.98, NQ 1.64–2.05, z ≈ −6 to −10, IS & OOS. Real sector levels *cluster* near
  spot/round numbers, covering the BL band worse than uniform random.
- **D (day-shuffle null — the gold standard; preserves each pool's clustering exactly, breaks only
  the day alignment):**

| pool | target | IS ratio (z, t) | OOS ratio (z, t) | verdict |
|------|--------|-----------------|------------------|---------|
| **SPY+QQQ** | ES | **0.85 (z+5.6, t−3.8)** | **0.86 (z+3.4, t−2.5)** | REAL day-alignment |
| **SPY+QQQ** | NQ | **0.84 (z+6.1, t−4.1)** | **0.90 (z+2.1, t−1.8)** | REAL day-alignment |
| SECTORS | ES | 1.02 (z+2.5, t+0.5) | 0.93 (z+2.1, t−1.3) | flat (t≈0) |
| SECTORS | NQ | 0.97 (z+2.2, t−0.9) | 1.04 (z−0.3, t+0.7) | flat / reverses |

Today's **SPY/QQQ** levels are reliably closer to today's BL than a random other day's
(ratio ~0.85, strong z **and** t, both instruments, IS **and** OOS). Sectors hover at ratio ≈1.0
with t≈0 — no day-specific alignment. (Win-rate z for sectors is mildly >0 but the effect *size*
t is null and flips sign OOS: noise, not signal.)

→ **Sectors carry no day-specific BL information beyond what SPY/QQQ already provide.**

---

## Answers to the brief
- **Do sector ETFs explain BL better than chance / better than SPY+QQQ?** No. Not better than
  chance in any way that survives out-of-sample, and clearly worse than / redundant to SPY+QQQ.
- **Which sectors?** None robustly. ES shows a weak defensive tilt (XLV, XLP) that does not
  replicate on NQ and is within multiple-comparison noise.
- **Best config + OOS error:** the winner is **SPY+QQQ struct levels, spot-ratio mapped** —
  ES OOS median nearest-distance ≈ **21.4 pts** (vs 24.9 day-shuffled, ratio 0.86); NQ OOS ≈ 118 pts
  (~0.15%). Statistical localization, **not** an exact reconstruction. Adding sectors does not lower this.

## Verdict: **REFUTED**
The sector-ETF hypothesis is refuted. BL confluence is a **broad-index** effect (SPY/QQQ, and by
extension SPX/NDX), not a sector-ETF or sector-overlap effect. This is consistent with — and
narrows — established finding #2: the "cross-asset structural confluence" is carried by the broad
index members, and sector ETFs contribute no independent signal.

### Adversarial caveat worth flagging upstream
The pooled cross-asset structural confluence (established z=+8.9) was measured against a
*random-BL* null. Sector pools beat that null weakly **only because gamma levels and BL both
cluster near spot** — when controlled with a density-and-clustering-preserving null (Test D),
sectors vanish while SPY/QQQ remain. The +8.9 pooled result should be re-checked with a
day-shuffle null; part of it may be co-clustering rather than genuine same-day pinning.
