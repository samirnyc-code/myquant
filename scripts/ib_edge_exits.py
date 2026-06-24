"""ib_edge_exits.py — do better exits / 2-legged scale-in entries improve Keystone?

On the gated book (origin <=0.10 ADR inside same-side IB edge), test exit & entry
variants the target sweep didn't cover:
  A. 2.0R fixed (baseline)
  B. 2.0R + breakeven after +1R       (ratchet to BE)
  C. 2.0R + trail: lock +0.5R after +1.5R
  D. scale-OUT: half at 1R, half at 2R (2 contracts)
  E. scale-IN: E1 at signal + E2 on -0.5R pullback, both target 2R (up to 2c)

Prior (S33): post-entry management FAILED for the cluster gate. Confirm or refute here.
Compare on net$, exp$/trade, and MAR (net/maxDD — contract-count invariant, the fair
cross-config metric). Memory-frugal chunked tick load. Pinned, look-ahead-safe.

Run: .venv/Scripts/python.exe scripts/ib_edge_exits.py
Out: docs/living/ib_edge_exits_<date>.md
"""
from __future__ import annotations

import sys, gc
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
EDGE_MAX = 0.10

COMMON = dict(entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5, contracts=1,
              commission=4.36, pb_round="nearest", overrides=None)
CONFIGS = {
    "A. 2.0R fixed (base)":        dict(target_r=2.0, contracts=1),
    "B. 2.0R + BE@1R":             dict(target_r=2.0, contracts=1, ratchet_r=1.0, ratchet_dest="BE"),
    "C. 2.0R + trail(lock0.5@1.5)":dict(target_r=2.0, contracts=1, ratchet_r=1.5, ratchet_dest="Lock-in", ratchet_lock_r=0.5),
    "D. scale-OUT 1R/2R (2c)":     dict(target_r=2.0, multileg=True, t1_r=1.0, t1_action="exit", contracts_t1=1, contracts_t2=1),
    "E. scale-IN -0.5R pb (2c)":   dict(target_r=2.0, multileg=True, t1_r=2.0, t1_action="exit", contracts_t1=1, contracts_t2=1, ml_pb_r=-0.5, scale_in_style="e2"),
}


def log(m): print(f"[ex] {datetime.now():%H:%M:%S} {m}", flush=True)


def main() -> int:
    log("tagging + gating...")
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
    G = (d_edge >= 0) & (d_edge <= EDGE_MAX)
    gtg = tg.loc[G].reset_index(drop=True)
    gtg["_date"] = pd.to_datetime(gtg["DateTime"]).dt.date

    acc = {k: [] for k in CONFIGS}
    for ci, chunk in enumerate(np.array_split(np.array(sorted(gtg["_date"].unique()), object), 4)):
        sub = gtg[gtg["_date"].isin(set(chunk.tolist()))].reset_index(drop=True)
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        for name, cfg in CONFIGS.items():
            res = simulate_trades(signals=sub, ticks_by_date=tbd, bars_by_date=bbd,
                                  **{**COMMON, **cfg}).reset_index(drop=True)
            fl = res["Filled"] == True
            k = res.loc[fl, ["DateTime", "NetPnL"]].copy()
            k["R"] = res.loc[fl, "NetPnL"].values / res.loc[fl, "RiskDollar"].replace(0, np.nan).values
            acc[name].append(k)
            del res
        del tbd; gc.collect()
        log(f"  chunk {ci+1}/4")

    def stats(bk):
        bk = bk.sort_values("DateTime")
        pnl = bk["NetPnL"].values
        eq = np.cumsum(pnl); dd = np.maximum.accumulate(eq) - eq
        net = float(eq[-1]); mdd = float(dd.max())
        return dict(n=len(bk), net=net, exp=net / len(bk),
                    expR=float(np.nanmean(bk["R"].values)),
                    pf=float(pnl[pnl > 0].sum() / abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else np.inf,
                    win=float((pnl > 0).mean() * 100), mdd=mdd,
                    mar=net / mdd if mdd else np.inf)

    md = [f"# Keystone — Exit & Entry Variants ({datetime.now():%Y-%m-%d})\n",
          "Gated book. MAR (net/maxDD) is the fair cross-config comparator (invariant to "
          "contract count). D & E use up to 2 contracts. Prior (S33): management hurt the "
          "cluster gate — does it hurt Keystone?\n",
          "| variant | n | net $ | exp $ | exp R | PF | win% | maxDD $ | MAR |",
          "|---|---|---|---|---|---|---|---|---|"]
    base_mar = None
    for name in CONFIGS:
        s = stats(pd.concat(acc[name], ignore_index=True))
        if base_mar is None:
            base_mar = s["mar"]
        pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
        md.append(f"| {name} | {s['n']} | ${s['net']:,.0f} | ${s['exp']:+.0f} | {s['expR']:+.3f} | "
                  f"{pf} | {s['win']:.1f}% | ${s['mdd']:,.0f} | {s['mar']:.2f} |")
    md.append(f"\n_Baseline MAR = {base_mar:.2f}. Higher MAR = better risk-adjusted; "
              "exit/entry change is an improvement only if MAR rises without wrecking net._\n")

    out = _OUT / f"ib_edge_exits_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
