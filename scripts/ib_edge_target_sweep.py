"""ib_edge_target_sweep.py — does a better exit rescue the IB-edge gate?

The gate (origin ≤0.10 ADR inside same-side IB edge) has real trade-SELECTION value
but only +0.11R at a dumb 1:1 exit. Here we sweep the target on the GATED book only,
judging on Exp R AND drawdown (a higher target deepens DD as win% falls), and we check
whether the best target is STABLE across years — an optimum that wanders = overfit.

n is constant across targets (target changes only the exit, not whether the entry fills),
so this is a clean apples-to-apples comparison. Stop fixed (1 tick beyond MCX).

DISCIPLINE: picking the argmax target on the same data that selected the gate is double
in-sample selection — treat any winner as an UPPER bound, not the forward number.

Run: .venv/Scripts/python.exe scripts/ib_edge_target_sweep.py
Out: docs/living/ib_edge_target_sweep_<date>.md
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
            ratchet_r=0.0, pb_round="nearest", multileg=False, threeleg=False,
            overrides=None)
EDGE_MAX = 0.10
TARGETS = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0]


def log(m): print(f"[tgt] {datetime.now():%H:%M:%S} {m}", flush=True)


def max_dd(equity: np.ndarray) -> float:
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return float((peak - equity).max())


def srow(label, pnl, rmult, dt):
    n = len(pnl)
    if n == 0:
        return f"| {label} | 0 | — | — | — | — | — | — | — |"
    net = float(pnl.sum()); exp = net / n
    gw = float(pnl[pnl > 0].sum()) if (pnl > 0).any() else 0.0
    gl = float(abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else 0.0
    pf = gw / gl if gl > 0 else float("inf")
    wr = float((pnl > 0).mean() * 100)
    expR = float(np.nanmean(rmult))
    ciR = 1.96 * np.nanstd(rmult, ddof=1) / np.sqrt(n) if n > 1 else np.nan
    order = np.argsort(dt)
    dd = max_dd(np.cumsum(pnl[order]))
    mar = net / dd if dd > 0 else float("inf")
    pfs = "∞" if pf == float("inf") else f"{pf:.2f}"
    mars = "∞" if mar == float("inf") else f"{mar:.2f}"
    cir = "—" if np.isnan(ciR) else f"±{ciR:.3f}"
    return (f"| {label} | {n} | ${net:,.0f} | {expR:+.3f} | {cir} | {pfs} | "
            f"{wr:.1f}% | ${dd:,.0f} | {mars} |")


HDR = "| target | n | net $ | exp R | ±CI R | PF | win% | maxDD $ | net/DD |"
SEP = "|---|---|---|---|---|---|---|---|---|"


def main() -> int:
    log("loading + tagging...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bbd = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)
    tg = tag_signals(sig, bars).sort_values("DateTime").reset_index(drop=True)

    adr = tg["prior_ATR"].replace(0, np.nan).to_numpy()
    isL_all = tg["Direction"].str.lower().str.startswith("l").values
    origin = tg["StopPrice"].to_numpy()
    d_edge = np.where(isL_all, origin - tg["OR60_Low"].to_numpy(),
                               tg["OR60_High"].to_numpy() - origin) / adr
    G = (d_edge >= 0) & (d_edge <= EDGE_MAX)

    # Memory-frugal: simulate ONLY gated signals, and stream ticks in DATE CHUNKS so peak
    # memory is one chunk (the full 5yr tick dict won't fit alongside the running app).
    import gc
    gtg = tg.loc[G].reset_index(drop=True)
    gtg["_date"] = pd.to_datetime(gtg["DateTime"]).dt.date
    log(f"gated signals: {len(gtg)} (of {len(tg)})")
    gdates = sorted(gtg["_date"].unique())
    CHUNKS = 4
    date_chunks = np.array_split(np.array(gdates, dtype=object), CHUNKS)

    acc = {t: {"pnl": [], "rmult": [], "dt": []} for t in TARGETS}
    for ci, chunk in enumerate(date_chunks):
        cset = set(chunk.tolist())
        sub = gtg[gtg["_date"].isin(cset)].reset_index(drop=True)
        log(f"chunk {ci+1}/{CHUNKS}: {len(sub)} signals, {len(cset)} dates — loading ticks...")
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        subL = sub["Direction"].str.lower().str.startswith("l").values
        for t in TARGETS:
            res = simulate_trades(signals=sub, ticks_by_date=tbd, bars_by_date=bbd,
                                  target_r=t, **BASE).reset_index(drop=True)
            fl = (res["Filled"] == True).values
            rf = res.loc[fl]
            pnl = rf["NetPnL"].values
            risk = rf["RiskDollar"].values if "RiskDollar" in rf.columns else np.full(len(rf), np.nan)
            acc[t]["pnl"].append(pnl)
            acc[t]["rmult"].append(pnl / risk)
            acc[t]["dt"].append(pd.to_datetime(sub.loc[fl, "DateTime"]).values)
            acc[t]["_isL"] = acc[t].get("_isL", []) + [subL[fl]]
            del res, rf
        del tbd; gc.collect()

    per_year_expR = {}
    rows_both, rows_short = [], []
    for t in TARGETS:
        pnl = np.concatenate(acc[t]["pnl"])
        rmult = np.concatenate(acc[t]["rmult"])
        dt = np.concatenate(acc[t]["dt"])
        lf = np.concatenate(acc[t]["_isL"])
        yr = pd.to_datetime(dt).year
        rows_both.append(srow(f"{t}R", pnl, rmult, dt))
        rows_short.append(srow(f"{t}R short", pnl[~lf], rmult[~lf], dt[~lf]))
        per_year_expR[t] = {int(y): float(np.nanmean(rmult[yr == y]))
                            for y in sorted(np.unique(yr))}

    md = [f"# IB-edge Gate — Target Sweep ({datetime.now():%Y-%m-%d})\n",
          "Gated book only (origin ≤0.10 ADR inside same-side IB edge). Stop fixed, only "
          "the target varies → n constant, clean comparison. **Judge Exp R + net/DD, look "
          "for a PLATEAU.** Double in-sample selection — winner = upper bound, not forward.\n",
          "\n## Both directions\n", HDR, SEP, *rows_both, "",
          "\n## Short only (the year-robust side)\n", HDR, SEP, *rows_short, ""]

    # stability: best target by year
    md.append("\n## Best target by year (by Exp R) — does the optimum wander?\n")
    years = sorted({y for d in per_year_expR.values() for y in d})
    md += ["| year | " + " | ".join(f"{t}R" for t in TARGETS) + " | best |",
           "|---|" + "---|" * (len(TARGETS) + 1)]
    for y in years:
        vals = [per_year_expR[t].get(y, np.nan) for t in TARGETS]
        best = TARGETS[int(np.nanargmax(vals))]
        cells = " | ".join(f"{v:+.3f}" for v in vals)
        md.append(f"| {y} | {cells} | **{best}R** |")
    md.append("")

    out = _OUT / f"ib_edge_target_sweep_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
