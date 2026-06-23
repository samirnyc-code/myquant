"""reversal_at_extreme_study.py — do RevFT reversal signals AT a key level have an edge?

Two user hypotheses (S37):
  Q1  REVERSALS OFF THE DEVELOPING HOD/LOD — a reversal whose rejection extreme sits
      AT the developing day extreme (long bouncing off the developing LOD / short
      rejecting the developing HOD) is a true V at the day's edge; may carry an edge.
  Q2  BALANCE-DAY FADE AT HOY/LOY — when we OPENED INSIDE yesterday's range and the
      range is still UNTESTED (balance_state), a reversal at HOY/LOY (long off LOY /
      short off HOY) is a responsive fade of the untested prior-day edge.

Signal set: ba_signals_revft.parquet (the MyReversals/RevFT export). Anchor = the
reversal point. We bucket on TWO anchors and report both:
  • SignalPrice  — the trigger price (a few ticks back inside the swing). PRIMARY.
  • StopPrice    — sits just BEYOND the rejected swing extreme; a proxy for the actual
                   high/low the reversal formed off of. Cross-check.

All level features are read from indicators.tag_signals — the S34-corrected,
look-ahead-safe chokepoint (dev_High/dev_Low/HOY/LOY/balance_state at the SIGNAL bar).

Method: descriptive ONLY. Real tick engine (pinned 1.0R single-leg BASE), then bucket
realized trades by normalized reversal->level distance (ADR units). Look for a MONOTONIC
gradient toward the AT-extreme band across a real sample (check ±95%CI). Thin = noise.

NB (S37): RevFT at 1:1 is a firm net loser (gross -$79k / net -$187k). This is a
SELECTIVITY hunt — is there a SUBSET clearing the ~$15/trade cost hurdle — not a
validation of RevFT as-is. Tables show gross context.

Run: .venv/Scripts/python.exe scripts/reversal_at_extreme_study.py
Out: docs/living/reversal_at_extreme_study_<date>.md
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

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_revft.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"

BASE = dict(entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5,
            contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
            ratchet_r=0.0, pb_round="nearest", target_r=1.0,
            multileg=False, threeleg=False, overrides=None)

# Normalized-distance bands (ADR units). For a REVERSAL anchor: 0 == reversal sits
# exactly ON the level; >0 == reversal happens INSIDE the range (above the low /
# below the high); <0 == reversal pokes BEYOND the level (a fresh extreme first).
BANDS = [(-np.inf, -0.25), (-0.25, -0.05), (-0.05, 0.05),
         (0.05, 0.15), (0.15, 0.30), (0.30, 0.60), (0.60, np.inf)]
BAND_LABELS = ["< -0.25", "-0.25..-0.05", "-0.05..0.05 (AT)",
               "0.05..0.15", "0.15..0.30", "0.30..0.60", "> 0.60"]


def log(m: str) -> None:
    print(f"[revext] {datetime.now():%H:%M:%S} {m}", flush=True)


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
    log("tagging signals (causal dev_High/dev_Low/HOY/LOY/balance_state)...")
    tagged = tag_signals(sig, bars).sort_values("DateTime").reset_index(drop=True)

    sgnL = tagged["Direction"].str.lower().str.startswith("l")        # True = Long
    adr = tagged["prior_ATR"].replace(0, np.nan)                      # ADR (points)
    sp = tagged["SignalPrice"]                                        # trigger price
    xs = tagged["StopPrice"]                                          # just beyond swing extreme

    # Q1 — REVERSAL vs developing LOD/HOD. 0 == reversal on the developing extreme,
    # >0 == reversal inside the range, <0 == poked beyond (fresh extreme first).
    rev_dev_sp = np.where(sgnL, sp - tagged["dev_Low"],
                                 tagged["dev_High"] - sp) / adr
    rev_dev_xs = np.where(sgnL, xs - tagged["dev_Low"],
                                 tagged["dev_High"] - xs) / adr
    # Q2 — REVERSAL vs prior-day LOY/HOY (the balance-day fade).
    rev_pri_sp = np.where(sgnL, sp - tagged["LOY"],
                                 tagged["HOY"] - sp) / adr
    rev_pri_xs = np.where(sgnL, xs - tagged["LOY"],
                                 tagged["HOY"] - xs) / adr

    tagged["rev_dev_sp"] = rev_dev_sp
    tagged["rev_dev_xs"] = rev_dev_xs
    tagged["rev_pri_sp"] = rev_pri_sp
    tagged["rev_pri_xs"] = rev_pri_xs

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
    bal = f["balance_state"].astype(bool)

    # ── report ────────────────────────────────────────────────────────────────
    md = [f"# Reversal-at-Extreme Study — RevFT ({datetime.now():%Y-%m-%d})\n",
          "**Hypotheses:** (Q1) reversals AT the developing HOD/LOD and (Q2) balance-day "
          "fades at HOY/LOY carry an edge. Descriptive only — pinned 1.0R single-leg, real "
          "tick engine, look-ahead-safe features (S34 `tag_signals`).\n",
          f"- Signal set: `ba_signals_revft.parquet` · {len(tagged)} signals · "
          f"filled: {len(rf)}\n",
          "- Distance is signed, ADR units (prior_ATR). 0 = reversal ON the level, "
          ">0 = reversal inside the range, <0 = poked beyond (fresh extreme first).\n",
          "- Two anchors: **SP** = SignalPrice (trigger) · **XS** = StopPrice "
          "(just beyond the rejected swing extreme).\n",
          "- **Verdict rule:** look for a MONOTONIC gradient toward the AT band across a "
          "real sample (check ±95%CI). One lucky thin bucket ≠ edge.\n",
          "- **NB (S37):** RevFT at 1:1 is a firm net loser overall — this is a "
          "selectivity hunt for a subset clearing the ~$15/trade cost hurdle.\n",
          f"\n**Baseline (ALL filled):** {row('ALL', pnl.values, rmult.values)}\n"]

    # ════ Q1 — reversal vs developing HOD/LOD ══════════════════════════════════
    md.append("\n# Q1 — Reversal off the developing HOD/LOD\n")
    for col, anc in [("rev_dev_sp", "SignalPrice anchor"),
                     ("rev_dev_xs", "StopPrice (swing-extreme) anchor")]:
        md.append(f"\n## {anc}\n")
        md.append("### Both directions\n")
        md += bucket_table(f[col], pnl, rmult, pd.Series(True, index=f.index))
        md.append("### Long only (bounce off developing LOD)\n")
        md += bucket_table(f[col], pnl, rmult, isL)
        md.append("### Short only (reject developing HOD)\n")
        md += bucket_table(f[col], pnl, rmult, ~isL)

    # ════ Q2 — balance-day reversal at HOY/LOY ═════════════════════════════════
    md.append("\n# Q2 — Balance-day reversal at HOY/LOY\n")
    md.append("_`balance_state` = opened INSIDE yesterday's range AND range still "
              "untested at the signal bar (developing range within HOY/LOY)._\n")
    md.append(f"_Subset: {int(bal.sum())} of {len(f)} filled trades in balance_state._\n")
    for col, anc in [("rev_pri_sp", "SignalPrice anchor"),
                     ("rev_pri_xs", "StopPrice (swing-extreme) anchor")]:
        md.append(f"\n## {anc} — BALANCE-STATE ONLY\n")
        md.append("### Both directions\n")
        md += bucket_table(f[col], pnl, rmult, bal)
        md.append("### Long only (fade up off untested LOY)\n")
        md += bucket_table(f[col], pnl, rmult, bal & isL)
        md.append("### Short only (fade down off untested HOY)\n")
        md += bucket_table(f[col], pnl, rmult, bal & ~isL)
    md.append("\n## Contrast — NON-balance signals (SignalPrice anchor, same feature)\n")
    md.append("_Opened outside Y, or range already broken before the signal._\n")
    md += bucket_table(f["rev_pri_sp"], pnl, rmult, ~bal)

    # ── year-by-year stability (both hypotheses' AT-band) ──────────────────────
    yr = pd.to_datetime(f["DateTime"]).dt.year
    at = lambda s: (s >= -0.05) & (s < 0.05)                          # AT-extreme band
    md.append("\n# Year-by-year stability of the AT-extreme bands\n")
    md.append("_AT band = reversal within ±0.05 ADR of the level (SignalPrice anchor)._\n")
    md += ["| year | Q1 dev AT n | Q1 exp$ | Q1 expR | Q2 bal HOY/LOY AT n | Q2 exp$ | Q2 expR |",
           "|---|---|---|---|---|---|---|"]
    q1m = at(f["rev_dev_sp"])
    q2m = at(f["rev_pri_sp"]) & bal
    for y in sorted(yr.unique()):
        a = (q1m & (yr == y)).values
        b = (q2m & (yr == y)).values
        sa = stats(pnl[a].values, rmult[a].values)
        sb = stats(pnl[b].values, rmult[b].values)
        era = "—" if np.isnan(sa["expR"]) else f"{sa['expR']:+.3f}"
        erb = "—" if np.isnan(sb["expR"]) else f"{sb['expR']:+.3f}"
        md.append(f"| {y} | {sa['n']} | ${sa['exp']:+.0f} | {era} | "
                  f"{sb['n']} | ${sb['exp']:+.0f} | {erb} |")
    md.append("")

    out = _OUT / f"reversal_at_extreme_study_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
