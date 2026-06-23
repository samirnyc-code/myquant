"""ib_study.py — characterize the IB (Initial Balance / OR60) properly.

Follow-up to balance_refine: do NOT prematurely cull. Two IB theses, tested with
FIXED ADR bins (stable meaning across subsets/years, unlike tertiles) and finer
resolution, on BOTH the full population (n≈5.4k, for resolution) and the balance
subset (the regime where IB rotation should matter most):

  A. IB WIDTH inverted-U — narrow=coiled/pre-breakout, MID=healthy two-sided
     rotation (best?), wide=trend/volatile. Map the curve, locate the sweet spot.
  B. IB-EDGE responsive fade — origin (MCX) at the IB extreme → fade back. Show the
     GRADIENT vs distance-to-IB-edge (not one band), both directions (symmetry check).
  C. IB extension — origin inside IB vs already beyond it.

Look-ahead-safe (OR60 frozen after first 12 bars; all causal). Pinned 1.0R single-leg,
real tick engine. CI = 1.96·SE (wide = unproven, NOT disproven).

Run: .venv/Scripts/python.exe scripts/ib_study.py
Out: docs/living/ib_study_<date>.md
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

def _bins(start, stop, step, lump_lo=True):
    """0.05-granular fixed ADR bins with an open lower lump and open upper tail."""
    edges = np.round(np.arange(start, stop + 1e-9, step), 3)
    bins, labs = [], []
    if lump_lo and start > 0:
        bins.append((0.0, start)); labs.append(f"<{start:.2f}")
    for lo, hi in zip(edges[:-1], edges[1:]):
        bins.append((float(lo), float(hi))); labs.append(f"{lo:.2f}-{hi:.2f}")
    bins.append((float(edges[-1]), np.inf)); labs.append(f">{edges[-1]:.2f}")
    return bins, labs


# 0.05-ADR granularity, fixed bins (stable across subsets/years).
IBW_BINS, IBW_LAB   = _bins(0.10, 0.75, 0.05)   # IB width / ADR
EDGE_BINS, EDGE_LAB = _bins(0.00, 0.50, 0.05)   # distance origin→same-side IB edge


def log(m): print(f"[ib] {datetime.now():%H:%M:%S} {m}", flush=True)


def stats(pnl, rmult=None):
    n = len(pnl)
    if n == 0:
        return dict(n=0, net=0, exp=0, pf=0, wr=0, expR=np.nan, ci=np.nan)
    net = float(pnl.sum())
    gw = float(pnl[pnl > 0].sum()) if (pnl > 0).any() else 0.0
    gl = float(abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else 0.0
    pf = gw / gl if gl > 0 else float("inf")
    ci = float(1.96 * pnl.std(ddof=1) / np.sqrt(n)) if n > 1 else np.nan
    expR = float(np.nanmean(rmult)) if rmult is not None and len(rmult) else np.nan
    return dict(n=n, net=net, exp=net / n, pf=pf, wr=float((pnl > 0).mean() * 100),
                expR=expR, ci=ci)


HDR = "| slice | n | net $ | exp $ | ±95%CI | exp R | PF | win% |"
SEP = "|---|---|---|---|---|---|---|---|"


def row(label, pnl, rmult):
    s = stats(pnl, rmult)
    if s["n"] == 0:
        return f"| {label} | 0 | — | — | — | — | — | — |"
    pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    ci = "—" if np.isnan(s["ci"]) else f"±{s['ci']:.0f}"
    er = "—" if np.isnan(s["expR"]) else f"{s['expR']:+.3f}"
    return (f"| {label} | {s['n']} | ${s['net']:,.0f} | ${s['exp']:+.0f} | {ci} | "
            f"{er} | {pf} | {s['wr']:.1f}% |")


def binned(label_prefix, feat, bins, labs, pnl, rmult, mask):
    md = [HDR, SEP]
    fv = feat[mask].values if hasattr(feat, "values") else feat[mask]
    p = pnl[mask].values; r = rmult[mask].values
    for (lo, hi), lab in zip(bins, labs):
        b = (fv >= lo) & (fv < hi)
        md.append(row(f"{label_prefix}{lab}", p[b], r[b]))
    md.append("")
    return md


def main() -> int:
    log("loading + tagging...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bbd = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)
    tg = tag_signals(sig, bars).sort_values("DateTime").reset_index(drop=True)

    log("ticks + sim...")
    dates = sorted(pd.to_datetime(tg["DateTime"]).dt.date.unique())
    tbd = {d: massive.load_continuous_ticks(d) for d in dates}
    tbd = {d: t for d, t in tbd.items() if not t.empty}
    res = simulate_trades(signals=tg, ticks_by_date=tbd, bars_by_date=bbd, **BASE).reset_index(drop=True)
    fl = (res["Filled"] == True).values

    f = tg.loc[fl].reset_index(drop=True)
    rf = res.loc[fl].reset_index(drop=True)
    pnl = rf["NetPnL"]
    risk = rf["RiskDollar"] if "RiskDollar" in rf.columns else None
    rmult = (rf["NetPnL"] / risk) if risk is not None else pd.Series(np.nan, index=rf.index)
    log(f"filled {len(rf)}")

    adr = f["prior_ATR"].replace(0, np.nan).to_numpy()
    isL = f["Direction"].str.lower().str.startswith("l").values
    bal = f["balance_state"].astype(bool).values
    origin = f["StopPrice"].to_numpy()
    ib_lo, ib_hi = f["OR60_Low"].to_numpy(), f["OR60_High"].to_numpy()
    ib_w = (ib_hi - ib_lo) / adr
    # distance of origin to the SAME-SIDE IB edge it would fade from:
    #   long fades up off IB-low; short fades down off IB-high
    d_edge = np.where(isL, (origin - ib_lo), (ib_hi - origin)) / adr
    # extension: origin beyond IB on its fade side (negative d_edge) vs inside
    f = f.assign(ib_w=ib_w, d_edge=d_edge)

    md = [f"# IB (Initial Balance / OR60) Study ({datetime.now():%Y-%m-%d})\n",
          "Fixed ADR bins (stable meaning), full-pop + balance. CI=1.96·SE — wide means "
          "UNPROVEN at this n, not disproven.\n",
          f"\n**Full-pop baseline:** {row('ALL', pnl.values, rmult.values)}",
          f"\n**Balance baseline:** {row('balance', pnl[bal].values, rmult[bal].values)}\n"]

    # ── A. IB width inverted-U ────────────────────────────────────────────────
    md.append("\n## A. IB width (OR60/ADR) — fixed bins, map the inverted-U\n")
    md.append("### Full population\n")
    md += binned("IBW ", f["ib_w"], IBW_BINS, IBW_LAB, pnl, rmult, np.ones(len(f), bool))
    md.append("### Balance only\n")
    md += binned("IBW ", f["ib_w"], IBW_BINS, IBW_LAB, pnl, rmult, bal)

    # ── B. IB-edge responsive fade gradient ───────────────────────────────────
    md.append("\n## B. IB-edge responsive fade — gradient vs distance to same-side IB edge\n")
    md.append("_long fades up off IB-low; short fades down off IB-high. AT=origin on the edge._\n")
    md.append("### Balance only — both directions\n")
    md += binned("edge ", f["d_edge"], EDGE_BINS, EDGE_LAB, pnl, rmult, bal)
    md.append("### Balance — LONG (origin at IB-low)\n")
    md += binned("edge ", f["d_edge"], EDGE_BINS, EDGE_LAB, pnl, rmult, bal & isL)
    md.append("### Balance — SHORT (origin at IB-high)\n")
    md += binned("edge ", f["d_edge"], EDGE_BINS, EDGE_LAB, pnl, rmult, bal & ~isL)
    md.append("### Full population — both directions (more n)\n")
    md += binned("edge ", f["d_edge"], EDGE_BINS, EDGE_LAB, pnl, rmult, np.ones(len(f), bool))

    # ── C. interaction: mid-IB-width × at-IB-edge, within balance ─────────────
    md.append("\n## C. Stacking: balance + mid IB width (0.30-0.50) + origin at IB edge (≤0.10)\n")
    midw = (f["ib_w"].values >= 0.30) & (f["ib_w"].values < 0.50)
    atedge = np.abs(f["d_edge"].values) <= 0.10
    md += [HDR, SEP,
           row("balance + mid-IBW", pnl[bal & midw].values, rmult[bal & midw].values),
           row("balance + mid-IBW + at-IB-edge", pnl[bal & midw & atedge].values, rmult[bal & midw & atedge].values),
           row("balance + mid-IBW + at-edge + LONG", pnl[bal & midw & atedge & isL].values, rmult[bal & midw & atedge & isL].values),
           row("balance + mid-IBW + at-edge + SHORT", pnl[bal & midw & atedge & ~isL].values, rmult[bal & midw & atedge & ~isL].values), ""]

    out = _OUT / f"ib_study_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
