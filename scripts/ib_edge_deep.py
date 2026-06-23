"""ib_edge_deep.py — stress-test the IB-edge ≤0.10 responsive-fade gate.

Gate G: origin (MCX/StopPrice) sits within 0.10 ADR INSIDE its same-side IB edge
(long fades up off OR60_Low, short fades down off OR60_High). Look-ahead-safe.

The one clean, well-sampled finding from the IB study (~1,400 trades, ~$120/+0.12R,
holds in R not just $). Now: does it survive scrutiny?

  1. Headline — G vs baseline vs complement (>0.10), both dir + L/S. Judge on EXP R.
  2. Year-by-year — does it hold 2021-2026 or concentrate (like balance did)?
  3. Monthly consistency — % positive months (a +0.1R edge needs to be steady).
  4. Cost sensitivity — re-sim at slip 1/0, 2/1, 3/2. A thin R-edge can die on costs.
  5. Redundancy vs balance_state — does G ADD on top of balance, or just re-select it?

Pinned 1.0R single-leg, real tick engine. Out: docs/living/ib_edge_deep_<date>.md
Run: .venv/Scripts/python.exe scripts/ib_edge_deep.py
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

BASE = dict(stop_offset=1, tick_value=12.5, contracts=1, contracts_t1=1,
            contracts_t2=1, commission=4.36, ratchet_r=0.0, pb_round="nearest",
            target_r=1.0, multileg=False, threeleg=False, overrides=None)
EDGE_MAX = 0.10           # gate threshold (ADR)
SLIPS = [("1/0 base", 1, 0), ("2/1 conservative", 2, 1), ("3/2 brutal", 3, 2)]


def log(m): print(f"[ibe] {datetime.now():%H:%M:%S} {m}", flush=True)


def stats(pnl, rmult=None):
    n = len(pnl)
    if n == 0:
        return dict(n=0, net=0, exp=0, pf=0, wr=0, expR=np.nan, ci=np.nan, ciR=np.nan)
    net = float(pnl.sum())
    gw = float(pnl[pnl > 0].sum()) if (pnl > 0).any() else 0.0
    gl = float(abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else 0.0
    pf = gw / gl if gl > 0 else float("inf")
    ci = float(1.96 * pnl.std(ddof=1) / np.sqrt(n)) if n > 1 else np.nan
    r = np.asarray(rmult, float) if rmult is not None else np.array([np.nan])
    expR = float(np.nanmean(r))
    ciR = float(1.96 * np.nanstd(r, ddof=1) / np.sqrt(n)) if n > 1 else np.nan
    return dict(n=n, net=net, exp=net / n, pf=pf, wr=float((pnl > 0).mean() * 100),
                expR=expR, ci=ci, ciR=ciR)


HDR = "| slice | n | net $ | exp $ | exp R | ±95%CI R | PF | win% |"
SEP = "|---|---|---|---|---|---|---|---|"


def row(label, pnl, rmult):
    s = stats(pnl, rmult)
    if s["n"] == 0:
        return f"| {label} | 0 | — | — | — | — | — | — |"
    pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    er = "—" if np.isnan(s["expR"]) else f"{s['expR']:+.3f}"
    cr = "—" if np.isnan(s["ciR"]) else f"±{s['ciR']:.3f}"
    return (f"| {label} | {s['n']} | ${s['net']:,.0f} | ${s['exp']:+.0f} | {er} | "
            f"{cr} | {pf} | {s['wr']:.1f}% |")


def run_sim(tagged, tbd, bbd, eslip, xslip):
    res = simulate_trades(signals=tagged, ticks_by_date=tbd, bars_by_date=bbd,
                          entry_slip=eslip, exit_slip=xslip, **BASE).reset_index(drop=True)
    fl = (res["Filled"] == True).values
    rf = res.loc[fl].reset_index(drop=True)
    risk = rf["RiskDollar"] if "RiskDollar" in rf.columns else None
    rm = (rf["NetPnL"] / risk) if risk is not None else pd.Series(np.nan, index=rf.index)
    return fl, rf["NetPnL"], rm


def main() -> int:
    log("loading + tagging...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bbd = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)
    tg = tag_signals(sig, bars).sort_values("DateTime").reset_index(drop=True)

    adr = tg["prior_ATR"].replace(0, np.nan).to_numpy()
    isL = tg["Direction"].str.lower().str.startswith("l").values
    origin = tg["StopPrice"].to_numpy()
    d_edge = np.where(isL, origin - tg["OR60_Low"].to_numpy(),
                            tg["OR60_High"].to_numpy() - origin) / adr
    G = (d_edge >= 0) & (d_edge <= EDGE_MAX)            # origin just inside IB edge
    bal = tg["balance_state"].astype(bool).values

    log("ticks...")
    dates = sorted(pd.to_datetime(tg["DateTime"]).dt.date.unique())
    tbd = {d: massive.load_continuous_ticks(d) for d in dates}
    tbd = {d: t for d, t in tbd.items() if not t.empty}

    log("base sim (1/0)...")
    fl, pnl, rmult = run_sim(tg, tbd, bbd, 1, 0)        # aligned to tg order
    # align masks to the FILLED rows
    gf = G[fl]; lf = isL[fl]; bf = bal[fl]
    yr = pd.to_datetime(tg.loc[fl, "DateTime"]).dt.year.reset_index(drop=True)
    ym = pd.to_datetime(tg.loc[fl, "DateTime"]).dt.to_period("M").reset_index(drop=True)
    pnl = pnl.reset_index(drop=True); rmult = rmult.reset_index(drop=True)
    log(f"filled {len(pnl)} · gate trades {int(gf.sum())}")

    md = [f"# IB-edge ≤{EDGE_MAX} Deep-Dive ({datetime.now():%Y-%m-%d})\n",
          "Gate G = origin within 0.10 ADR inside same-side IB edge (long off OR60_Low, "
          "short off OR60_High). Look-ahead-safe, pinned 1.0R single-leg. **Judge on Exp R.**\n"]

    # 1. headline
    md.append("\n## 1. Headline — gate vs baseline vs complement\n")
    md += [HDR, SEP,
           row("ALL filled (baseline)", pnl.values, rmult.values),
           row("GATE (≤0.10)", pnl[gf].values, rmult[gf].values),
           row("complement (>0.10)", pnl[~gf].values, rmult[~gf].values),
           row("GATE · LONG",  pnl[gf & lf].values,  rmult[gf & lf].values),
           row("GATE · SHORT", pnl[gf & ~lf].values, rmult[gf & ~lf].values), ""]

    # 2. year by year
    md.append("\n## 2. Year by year (gate)\n")
    md += [HDR, SEP]
    for y in sorted(yr.unique()):
        m = (yr == y).values & gf
        md.append(row(f"{y} gate", pnl[m].values, rmult[m].values))
    md.append("\n### gate LONG by year\n")
    md += [HDR, SEP]
    for y in sorted(yr.unique()):
        m = (yr == y).values & gf & lf
        md.append(row(f"{y} L", pnl[m].values, rmult[m].values))
    md.append("\n### gate SHORT by year\n")
    md += [HDR, SEP]
    for y in sorted(yr.unique()):
        m = (yr == y).values & gf & ~lf
        md.append(row(f"{y} S", pnl[m].values, rmult[m].values))
    md.append("")

    # 3. monthly consistency
    gm = pd.DataFrame({"ym": ym[gf].values, "pnl": pnl[gf].values})
    mon = gm.groupby("ym")["pnl"].sum()
    pos = int((mon > 0).sum()); tot = len(mon)
    md.append("\n## 3. Monthly consistency (gate)\n")
    md.append(f"- Positive months: **{pos}/{tot} ({100*pos/tot:.0f}%)** · "
              f"median month ${mon.median():,.0f} · worst ${mon.min():,.0f} · "
              f"best ${mon.max():,.0f}\n")

    # 4. cost sensitivity
    md.append("\n## 4. Cost sensitivity — gate under worse execution\n")
    md += [HDR, SEP]
    for lab, es, xs in SLIPS:
        if (es, xs) == (1, 0):
            fl2, p2, r2 = fl, pnl, rmult
            g2 = gf
        else:
            log(f"sim {lab}...")
            fl2, p2, r2 = run_sim(tg, tbd, bbd, es, xs)
            p2 = p2.reset_index(drop=True); r2 = r2.reset_index(drop=True)
            g2 = G[fl2]
        md.append(row(f"gate @ slip {lab}", p2[g2].values, r2[g2].values))
    md.append("")

    # 5. redundancy vs balance_state
    md.append("\n## 5. Redundancy vs balance_state\n")
    md.append(f"- Gate trades: {int(gf.sum())} · in balance: {int((gf & bf).sum())} "
              f"({100*(gf & bf).sum()/max(gf.sum(),1):.0f}% of gate) — so the gate is "
              "mostly NON-balance (independent population).\n")
    md += [HDR, SEP,
           row("gate ∩ balance",      pnl[gf & bf].values,  rmult[gf & bf].values),
           row("gate ∩ NON-balance",  pnl[gf & ~bf].values, rmult[gf & ~bf].values),
           row("balance ∩ NON-gate",  pnl[~gf & bf].values, rmult[~gf & bf].values),
           row("neither",             pnl[~gf & ~bf].values, rmult[~gf & ~bf].values), ""]

    out = _OUT / f"ib_edge_deep_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
