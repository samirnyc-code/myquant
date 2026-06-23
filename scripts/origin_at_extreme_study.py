"""origin_at_extreme_study.py — does an MC that ORIGINATES at a key level have an edge?

Hypothesis (user, S35): MC signals whose channel ORIGINATED at or near a structural
extreme (developing day low/high, or prior-day low/high) may carry an edge.

Two structural readings, tested + reported SEPARATELY:
  • REVERSAL    — the MC's defining extreme (StopPrice = MCX, the swing the channel
                  formed from) sits AT the same-side extreme. Long whose channel-low
                  == day low (bounce off support); short whose channel-high == day high.
  • CONTINUATION— the breakout point (SignalPrice) punches THROUGH the breakout-side
                  extreme. Long breaking to a new day high; short to a new day low.

Levels (per user): developing LOD/HOD (intraday) and HOY/LOY (prior-day).
All features are read from indicators.tag_signals — the S34-corrected, look-ahead-safe
chokepoint (dev_High/dev_Low/HOY/LOY at the SIGNAL bar, not the entry bar).

Method: descriptive ONLY. Run the REAL tick engine (pinned 1.0R single-leg BASE),
then bucket realized trades by normalized origin→level distance. We are NOT picking a
threshold — we look for a MONOTONIC gradient across a real sample. Thin buckets = noise.

Run: .venv/Scripts/python.exe scripts/origin_at_extreme_study.py
Out: docs/living/origin_at_extreme_study_<date>.md
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                                                       # noqa: E402
from simulation_engine import simulate_trades                        # noqa: E402
from indicators import tag_signals                                   # noqa: E402
from data_loader import bar_num_from_dt                              # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"

BASE = dict(entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5,
            contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
            ratchet_r=0.0, pb_round="nearest", target_r=1.0,
            multileg=False, threeleg=False, overrides=None)

# Normalized-distance bands (in ADR units). Signed: 0 == origin sits exactly on the
# level; for reversal positive == origin is INSIDE the range (above the low / below
# the high); negative == origin pokes BEYOND (a fresh extreme). For continuation
# positive == breakout punches THROUGH the extreme (new high/low).
BANDS = [(-np.inf, -0.25), (-0.25, -0.05), (-0.05, 0.05),
         (0.05, 0.15), (0.15, 0.30), (0.30, 0.60), (0.60, np.inf)]
BAND_LABELS = ["< -0.25", "-0.25..-0.05", "-0.05..0.05 (AT)",
               "0.05..0.15", "0.15..0.30", "0.30..0.60", "> 0.60"]


def log(m: str) -> None:
    print(f"[origin] {datetime.now():%H:%M:%S} {m}", flush=True)


# ── stats ─────────────────────────────────────────────────────────────────────

def stats(pnl: np.ndarray, rmult: np.ndarray | None = None) -> dict:
    n = len(pnl)
    if n == 0:
        return dict(n=0, net=0, exp=0, pf=0, wr=0, expR=np.nan, ci=np.nan)
    net = float(pnl.sum())
    gw = float(pnl[pnl > 0].sum()) if (pnl > 0).any() else 0.0
    gl = float(abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else 0.0
    pf = gw / gl if gl > 0 else float("inf")
    wr = float((pnl > 0).sum() / n * 100)
    exp = net / n
    # 95% CI half-width on mean $ (standard error × 1.96) — flags noisy buckets
    ci = float(1.96 * pnl.std(ddof=1) / np.sqrt(n)) if n > 1 else np.nan
    expR = float(np.nanmean(rmult)) if rmult is not None and len(rmult) else np.nan
    return dict(n=n, net=net, exp=exp, pf=pf, wr=wr, expR=expR, ci=ci)


HDR = "| band (ADR) | n | net $ | exp $ | ±95%CI | exp R | PF | win% |"
SEP = "|---|---|---|---|---|---|---|---|"


def row(label: str, pnl: np.ndarray, rmult: np.ndarray | None) -> str:
    s = stats(pnl, rmult)
    if s["n"] == 0:
        return f"| {label} | 0 | — | — | — | — | — | — |"
    pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    ci = "—" if np.isnan(s["ci"]) else f"±{s['ci']:.0f}"
    er = "—" if np.isnan(s["expR"]) else f"{s['expR']:+.3f}"
    return (f"| {label} | {s['n']} | ${s['net']:,.0f} | ${s['exp']:+.0f} | {ci} | "
            f"{er} | {pf} | {s['wr']:.1f}% |")


def bucket_table(feat: pd.Series, pnl: pd.Series, rmult: pd.Series,
                 mask: pd.Series) -> list[str]:
    """One bucketed table for a feature over the rows in `mask`."""
    md = [HDR, SEP]
    f = feat[mask]
    p = pnl[mask].values
    r = rmult[mask].values
    md.append(row("ALL", p, r))
    for (lo, hi), lab in zip(BANDS, BAND_LABELS):
        b = (f >= lo) & (f < hi)
        md.append(row(lab, p[b.values], r[b.values]))
    md.append("")
    return md


def main() -> int:
    log("loading signals + bars...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)

    # ── look-ahead-safe features via the S34-corrected chokepoint ──────────────
    log("tagging signals (causal dev_High/dev_Low/HOY/LOY/prior_ATR)...")
    tagged = tag_signals(sig, bars).sort_values("DateTime").reset_index(drop=True)

    sgnL = tagged["Direction"].str.lower().str.startswith("l")        # True = Long
    adr = tagged["prior_ATR"].replace(0, np.nan)                      # ADR (points)
    sp = tagged["SignalPrice"]
    xo = tagged["StopPrice"]                                          # MCX origin/extreme

    # REVERSAL: origin (MCX) vs the same-side extreme. 0 == origin on the level,
    # >0 == origin sits inside the range, <0 == origin is a fresh extreme.
    rev_intraday = np.where(sgnL, xo - tagged["dev_Low"],
                                   tagged["dev_High"] - xo) / adr
    rev_prior    = np.where(sgnL, xo - tagged["LOY"],
                                   tagged["HOY"] - xo) / adr
    # CONTINUATION: breakout (SignalPrice) vs the breakout-side extreme. >0 == punches
    # THROUGH to a new extreme, 0 == right at it, <0 == still inside the range.
    cont_intraday = np.where(sgnL, sp - tagged["dev_High"],
                                    tagged["dev_Low"] - sp) / adr
    cont_prior    = np.where(sgnL, sp - tagged["HOY"],
                                    tagged["LOY"] - sp) / adr

    tagged["rev_intraday"]  = rev_intraday
    tagged["rev_prior"]     = rev_prior
    tagged["cont_intraday"] = cont_intraday
    tagged["cont_prior"]    = cont_prior

    # ── real tick engine (pinned 1.0R single-leg) ─────────────────────────────
    log("loading ticks...")
    dates = sorted(pd.to_datetime(tagged["Date"]).dt.date.unique()) \
        if "Date" in tagged.columns else \
        sorted(tagged["DateTime"].dt.date.unique())
    ticks_by_date = {d: massive.load_continuous_ticks(d) for d in dates}
    ticks_by_date = {d: t for d, t in ticks_by_date.items() if not t.empty}

    log(f"simulating {len(tagged)} signals (pinned 1.0R single-leg)...")
    res = simulate_trades(signals=tagged, ticks_by_date=ticks_by_date,
                          bars_by_date=bars_by_date, **BASE).reset_index(drop=True)
    filled = res["Filled"] == True
    log(f"filled: {int(filled.sum())} / {len(res)}")

    f = tagged.loc[filled].reset_index(drop=True)
    rf = res.loc[filled].reset_index(drop=True)
    pnl = rf["NetPnL"]
    risk = rf["RiskDollar"] if "RiskDollar" in rf.columns else None
    rmult = (rf["NetPnL"] / risk) if risk is not None else pd.Series(np.nan, index=rf.index)
    isL = f["Direction"].str.lower().str.startswith("l")

    # ── report ────────────────────────────────────────────────────────────────
    md = [f"# Origin-at-Extreme Study ({datetime.now():%Y-%m-%d})\n",
          "**Hypothesis:** MC signals whose channel originated at/near a structural "
          "extreme carry an edge. Descriptive only — pinned 1.0R single-leg, real tick "
          "engine, look-ahead-safe features (S34 `tag_signals`).\n",
          f"- Signals: {len(tagged)} · filled: {len(rf)}\n",
          "- Distance is signed, in ADR units (prior_ATR). For **reversal**: 0 = MCX "
          "sits on the level, >0 = inside the range, <0 = fresh extreme. For "
          "**continuation**: >0 = breakout punches through to a new extreme.\n",
          "- **Verdict rule:** look for a MONOTONIC gradient toward the AT-extreme band "
          "across a real sample (check ±95%CI). One lucky thin bucket ≠ edge.\n",
          f"\n**Baseline (ALL filled):** {row('ALL', pnl.values, rmult.values)}\n"]

    feats = [("rev_intraday",  "REVERSAL — MCX origin vs developing LOD/HOD"),
             ("rev_prior",     "REVERSAL — MCX origin vs prior-day LOY/HOY"),
             ("cont_intraday", "CONTINUATION — breakout vs developing HOD/LOD"),
             ("cont_prior",    "CONTINUATION — breakout vs prior-day HOY/LOY")]

    for col, title in feats:
        md.append(f"\n## {title}\n")
        feat = f[col]
        md.append("### Both directions\n")
        md += bucket_table(feat, pnl, rmult, pd.Series(True, index=f.index))
        md.append("### Long only\n")
        md += bucket_table(feat, pnl, rmult, isL)
        md.append("### Short only\n")
        md += bucket_table(feat, pnl, rmult, ~isL)

    # ── prior-day reversal CONDITIONED on balance_state ────────────────────────
    # The HOY/LOY reversal hypothesis only makes structural sense when we opened
    # INSIDE yesterday's range AND have NOT yet broken it this session (balance_state
    # = inside_open & rotation). Then MCX-near-LOY (long) / -near-HOY (short) is a
    # responsive fade of the still-UNTESTED prior-day edge — not a post-breakout retest.
    bal = f["balance_state"].astype(bool)
    md.append("\n## REVERSAL — MCX vs prior-day LOY/HOY — BALANCE-STATE ONLY "
              "(opened inside Y, range still untested)\n")
    md.append(f"_Subset: {int(bal.sum())} filled trades in balance_state._\n")
    md.append("### Both directions\n")
    md += bucket_table(f["rev_prior"], pnl, rmult, bal)
    md.append("### Long only (fade up off untested LOY)\n")
    md += bucket_table(f["rev_prior"], pnl, rmult, bal & isL)
    md.append("### Short only (fade down off untested HOY)\n")
    md += bucket_table(f["rev_prior"], pnl, rmult, bal & ~isL)
    # contrast: the SAME feature for NON-balance signals (already broke / opened outside)
    md.append("### Contrast — NON-balance signals (same feature)\n")
    md += bucket_table(f["rev_prior"], pnl, rmult, ~bal)

    # ══════════════════════════════════════════════════════════════════════════
    # PRIOR-DAY RANGE CONTEXT — balance / failed-breakout / accepted (look-ahead-safe)
    # All from causal columns already on f: dev_High/dev_Low (strictly prior),
    # HOY/LOY, SignalPrice (current price at decision). No new merge.
    # ══════════════════════════════════════════════════════════════════════════
    yr  = pd.to_datetime(f["DateTime"]).dt.year
    cur = f["SignalPrice"]
    ever_above = f["dev_High"] > f["HOY"]      # session traded above Y-high before now
    ever_below = f["dev_Low"]  < f["LOY"]
    above_now  = cur > f["HOY"]
    below_now  = cur < f["LOY"]
    ctx = np.where(above_now.values, "accepted_above",
          np.where(below_now.values, "accepted_below",
          np.where((ever_above & ever_below).values, "failed_both",
          np.where(ever_above.values, "failed_high",      # broke above, back inside
          np.where(ever_below.values, "failed_low", "balance")))))
    ctx = pd.Series(ctx, index=f.index)

    md.append("\n## Prior-day RANGE CONTEXT (look-ahead-safe, vs HOY/LOY)\n")
    md.append("What has the session done to yesterday's range *before* the signal bar "
              "(dev_High/dev_Low strictly prior)? `balance`=never left Y · "
              "`failed_high`=poked above HOY then back inside (look-above-&-fail) · "
              "`failed_low`=poked below LOY then back · `failed_both`=both sides · "
              "`accepted_*`=currently trading outside Y.\n")
    md += ["| context | n | net $ | exp $ | ±95%CI | exp R | PF | win% |", SEP]
    for c in ["balance", "failed_high", "failed_low", "failed_both",
              "accepted_above", "accepted_below"]:
        m = (ctx == c).values
        md.append(row(c, pnl[m].values, rmult[m].values))
    md.append("")

    md.append("### Directional failed-breakout thesis (fade the failure)\n")
    md += ["| setup | n | net $ | exp $ | ±95%CI | exp R | PF | win% |", SEP]
    for lab, m in [
        ("failed_high + SHORT (look-above-&-fail)", (ctx == "failed_high") & ~isL),
        ("failed_high + LONG  (go-with)",           (ctx == "failed_high") &  isL),
        ("failed_low + LONG  (look-below-&-fail)",  (ctx == "failed_low")  &  isL),
        ("failed_low + SHORT (go-with)",            (ctx == "failed_low")  & ~isL)]:
        md.append(row(lab, pnl[m.values].values, rmult[m.values].values))
    md.append("")

    # ── balance_state YEAR BY YEAR (bull-drift check) ──────────────────────────
    md.append("\n## balance_state — YEAR BY YEAR (is it bull-drift?)\n")
    md += ["| year | bal n | bal exp$ | bal expR | bal PF | nonbal n | nonbal exp$ | nonbal PF |",
           "|---|---|---|---|---|---|---|---|"]
    for y in sorted(yr.unique()):
        by = ((yr == y) & bal).values
        ny = ((yr == y) & ~bal).values
        sb = stats(pnl[by].values, rmult[by].values)
        sn = stats(pnl[ny].values, rmult[ny].values)
        pfb = "∞" if sb["pf"] == float("inf") else f"{sb['pf']:.2f}"
        pfn = "∞" if sn["pf"] == float("inf") else f"{sn['pf']:.2f}"
        erb = "—" if np.isnan(sb["expR"]) else f"{sb['expR']:+.3f}"
        md.append(f"| {y} | {sb['n']} | ${sb['exp']:+.0f} | {erb} | {pfb} | "
                  f"{sn['n']} | ${sn['exp']:+.0f} | {pfn} |")
    md.append("")

    out = _OUT / f"origin_at_extreme_study_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
