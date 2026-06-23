"""balance_refine_study.py — can we sharpen balance_state with IB / gap / Y value area?

balance_state (opened inside yesterday's range, still rotating inside it) is the one
modest-but-real responsive context from S35. This conditions it on three classic Dalton
levers, ALL look-ahead-safe (causal columns from indicators.tag_signals):

  1. IB (Initial Balance = OR60_High/Low, the 60-min opening range)
       • IB width / ADR  (narrow IB → tight rotation → cleaner balance day?)
       • origin (MCX) at the IB extreme → responsive fade of the IB edge
  2. GAP / open location  (no prior-close col → use OOD inside Y range / vs Y VA)
       • open location in Y range (low/mid/high third)
       • opened above Y-VAH / inside Y-VA / below Y-VAL
  3. Y VALUE AREA  (vaD_VAH/VAL/POC = PRIOR session's value area)
       • origin location vs Y VA (above VAH / at VAH / inside / at VAL / below VAL)
       • PRE-COMMITTED responsive trade: LONG off vaD_VAL, SHORT off vaD_VAH (fade to POC)

Subset is ~916 filled trades → tertiles/categories only, sample flagged. Descriptive,
pinned 1.0R single-leg, real tick engine. Judge on coherent direction + sample.

Run: .venv/Scripts/python.exe scripts/balance_refine_study.py
Out: docs/living/balance_refine_study_<date>.md
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

AT = 0.05    # "at the level" band, in ADR units


def log(m): print(f"[bal] {datetime.now():%H:%M:%S} {m}", flush=True)


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


def main() -> int:
    log("loading + tagging...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}
    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)
    tg = tag_signals(sig, bars).sort_values("DateTime").reset_index(drop=True)

    log("loading ticks + simulating...")
    dates = sorted(pd.to_datetime(tg["DateTime"]).dt.date.unique())
    tbd = {d: massive.load_continuous_ticks(d) for d in dates}
    tbd = {d: t for d, t in tbd.items() if not t.empty}
    res = simulate_trades(signals=tg, ticks_by_date=tbd,
                          bars_by_date=bars_by_date, **BASE).reset_index(drop=True)
    fl = res["Filled"] == True

    f = tg.loc[fl].reset_index(drop=True)
    rf = res.loc[fl].reset_index(drop=True)
    pnl = rf["NetPnL"]
    risk = rf["RiskDollar"] if "RiskDollar" in rf.columns else None
    rmult = (rf["NetPnL"] / risk) if risk is not None else pd.Series(np.nan, index=rf.index)
    log(f"filled {len(rf)}")

    # ── restrict to balance_state ─────────────────────────────────────────────
    bal = f["balance_state"].astype(bool).values
    b = f.loc[bal].reset_index(drop=True)
    bpnl = pnl[bal].reset_index(drop=True)
    brm = rmult[bal].reset_index(drop=True)
    isL = b["Direction"].str.lower().str.startswith("l").values
    adr = b["prior_ATR"].replace(0, np.nan).to_numpy()

    # features (causal)
    ib_w     = (b["OR60_High"] - b["OR60_Low"]).to_numpy() / adr
    y_rng    = (b["HOY"] - b["LOY"]).replace(0, np.nan).to_numpy()
    open_loc = (b["OOD"] - b["LOY"]).to_numpy() / y_rng        # 0=Y-low .. 1=Y-high
    origin   = b["StopPrice"].to_numpy()
    vah, val, poc = b["vaD_VAH"].to_numpy(), b["vaD_VAL"].to_numpy(), b["vaD_POC"].to_numpy()
    d_val = (origin - val) / adr                               # >0 inside, ~0 at VAL, <0 below
    d_vah = (vah - origin) / adr                               # >0 inside, ~0 at VAH, <0 above

    # origin location vs Y value area
    va_loc = np.where(origin > vah + AT * adr, "above_VAH",
             np.where(origin > vah - AT * adr, "at_VAH",
             np.where(origin < val - AT * adr, "below_VAL",
             np.where(origin < val + AT * adr, "at_VAL", "inside_VA"))))

    def tert(x):
        q = np.nanquantile(x, [1/3, 2/3])
        return np.where(np.isnan(x), "nan",
               np.where(x <= q[0], "low", np.where(x <= q[1], "mid", "high"))), q

    md = [f"# Balance-State Refinement ({datetime.now():%Y-%m-%d})\n",
          "Conditioning balance_state (opened inside Y, still rotating) on IB / gap / Y "
          "value area. Look-ahead-safe, pinned 1.0R single-leg, real tick engine. "
          f"Balance subset = **{len(b)} filled**. Thin cells flagged by n.\n",
          f"\n**Balance baseline:** {row('balance ALL', bpnl.values, brm.values)}\n",
          f"**Full-pop baseline (context):** {row('ALL filled', pnl.values, rmult.values)}\n"]

    # 1. IB width
    ibt, ibq = tert(ib_w)
    md.append(f"\n## 1. IB width (OR60/ADR) tertiles  _cuts: {ibq[0]:.2f} / {ibq[1]:.2f} ADR_\n")
    md += [HDR, SEP]
    for t in ["low", "mid", "high"]:
        m = ibt == t
        md.append(row(f"IB {t} (narrow→wide)", bpnl[m].values, brm[m].values))
    md.append("")
    md.append("### IB-extreme responsive fade (origin at IB edge)\n")
    d_iblo = (origin - b["OR60_Low"].to_numpy()) / adr
    d_ibhi = (b["OR60_High"].to_numpy() - origin) / adr
    md += [HDR, SEP,
           row("LONG, origin at IB-low (≤0.05)",  bpnl[(np.abs(d_iblo) <= AT) & isL].values, brm[(np.abs(d_iblo) <= AT) & isL].values),
           row("SHORT, origin at IB-high (≤0.05)", bpnl[(np.abs(d_ibhi) <= AT) & ~isL].values, brm[(np.abs(d_ibhi) <= AT) & ~isL].values), ""]

    # 2. open location
    md.append("\n## 2. Open location inside Y range (gap proxy)\n")
    olt, olq = tert(open_loc)
    md += [HDR, SEP]
    for t in ["low", "mid", "high"]:
        m = olt == t
        md.append(row(f"open {t} third of Y", bpnl[m].values, brm[m].values))
    md.append("")
    md.append("### Opened relative to Y value area\n")
    open_va = np.where(b["OOD"].to_numpy() > vah, "above_Y-VAH",
              np.where(b["OOD"].to_numpy() < val, "below_Y-VAL", "inside_Y-VA"))
    md += [HDR, SEP]
    for c in ["above_Y-VAH", "inside_Y-VA", "below_Y-VAL"]:
        m = open_va == c
        md.append(row(c, bpnl[m].values, brm[m].values))
    md.append("")

    # 3. Y value area
    md.append("\n## 3. Origin vs Y value area (vaD)\n")
    md += [HDR, SEP]
    for c in ["above_VAH", "at_VAH", "inside_VA", "at_VAL", "below_VAL"]:
        m = va_loc == c
        md.append(row(c, bpnl[m].values, brm[m].values))
    md.append("")
    md.append("### PRE-COMMITTED responsive fades (fade Y-VA edge → POC)\n")
    md += [HDR, SEP,
           row("LONG, origin at/below Y-VAL", bpnl[(d_val <= AT) & isL].values, brm[(d_val <= AT) & isL].values),
           row("SHORT, origin at/above Y-VAH", bpnl[(d_vah <= AT) & ~isL].values, brm[(d_vah <= AT) & ~isL].values),
           row("LONG, origin near Y-POC (≤0.10)", bpnl[(np.abs((origin - poc) / adr) <= 0.10) & isL].values, brm[(np.abs((origin - poc) / adr) <= 0.10) & isL].values),
           row("SHORT, origin near Y-POC (≤0.10)", bpnl[(np.abs((origin - poc) / adr) <= 0.10) & ~isL].values, brm[(np.abs((origin - poc) / adr) <= 0.10) & ~isL].values), ""]

    out = _OUT / f"balance_refine_study_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
