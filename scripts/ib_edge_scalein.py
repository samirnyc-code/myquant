"""ib_edge_scalein.py — (1) verify multileg accounting, (2) test the "E1 scratch, E2 win" scale-in.

Part 1 DIAGNOSTIC (gated book): the exits study showed multileg scale-out at an
implausible net ($878k, ~4x the 1-contract base). Engine line 670 sets multileg
RiskDollar from leg-1 only (inflates exp R ~2x); the NET also needs a controlled check:
a 2-contract book with BOTH legs exiting at 2R MUST equal exactly 2x the single-leg 2R
book. If it doesn't, multileg net is mis-scaled and all multileg results are suspect.

Part 2 USER VARIANT: scale in on a -0.5R pullback (E1 at signal, E2 on the dip), then exit
the ENTIRE position at the E1 ENTRY price. E1 exits at its own entry (= scratch), E2
(entered 0.5R better) banks ~+0.5R. High-win mean-reversion structure. Modeled as
ml_pb_r=-0.5 with t1_r=target_r=X (both legs exit X·risk from E1 entry); X=0 = exit at
E1 entry. Test X in {0.0, 0.25, 0.5, 1.0}.

Net $ and MAR (net/maxDD) are the trustworthy comparators (exp R is engine-inflated for
multileg — shown but flagged). Memory-frugal chunked load.
Out: docs/living/ib_edge_scalein_<date>.md
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
    # --- diagnostics ---
    "DIAG single 1R (1c)":        dict(target_r=1.0),
    "DIAG single 2R (1c)":        dict(target_r=2.0),
    "DIAG ML both@2R (2c)":       dict(target_r=2.0, multileg=True, t1_r=2.0, t1_action="exit", contracts_t1=1, contracts_t2=1),
    "DIAG ML scaleout 1R/2R (2c)":dict(target_r=2.0, multileg=True, t1_r=1.0, t1_action="exit", contracts_t1=1, contracts_t2=1),
    # --- user variant: scale in -0.5R, exit ALL at common level X (E1 scratch at X=0) ---
    "SCALEIN exit@E1 entry (X=0)":dict(target_r=0.0, multileg=True, t1_r=0.0, t1_action="exit", contracts_t1=1, contracts_t2=1, ml_pb_r=-0.5, scale_in_style="e2"),
    "SCALEIN exit@0.25R":         dict(target_r=0.25, multileg=True, t1_r=0.25, t1_action="exit", contracts_t1=1, contracts_t2=1, ml_pb_r=-0.5, scale_in_style="e2"),
    "SCALEIN exit@0.5R":          dict(target_r=0.5, multileg=True, t1_r=0.5, t1_action="exit", contracts_t1=1, contracts_t2=1, ml_pb_r=-0.5, scale_in_style="e2"),
    "SCALEIN exit@1.0R":          dict(target_r=1.0, multileg=True, t1_r=1.0, t1_action="exit", contracts_t1=1, contracts_t2=1, ml_pb_r=-0.5, scale_in_style="e2"),
}


def log(m): print(f"[si] {datetime.now():%H:%M:%S} {m}", flush=True)


def main() -> int:
    log("tag + gate...")
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
            acc[name].append(k)
            del res
        del tbd; gc.collect()
        log(f"  chunk {ci+1}/4")

    def stats(bk):
        bk = bk.sort_values("DateTime"); pnl = bk["NetPnL"].values
        eq = np.cumsum(pnl); dd = np.maximum.accumulate(eq) - eq
        net = float(eq[-1]); mdd = float(dd.max())
        return dict(n=len(bk), net=net, exp=net / len(bk),
                    win=float((pnl > 0).mean() * 100),
                    scratch=float((np.abs(pnl) < 1.0).mean() * 100),
                    pf=float(pnl[pnl > 0].sum() / abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else np.inf,
                    mdd=mdd, mar=net / mdd if mdd else np.inf)

    S = {name: stats(pd.concat(acc[name], ignore_index=True)) for name in CONFIGS}

    md = [f"# Keystone — Multileg Accounting Check + 'E1 scratch / E2 win' Scale-In ({datetime.now():%Y-%m-%d})\n",
          "Gated book. **Net $ and MAR are trustworthy; exp R is engine-inflated for multileg "
          "(RiskDollar uses leg-1 only, sim_engine:670) so it is omitted.**\n",
          "| variant | n | net $ | exp $/trade | win% | scratch% | PF | maxDD $ | MAR |",
          "|---|---|---|---|---|---|---|---|---|"]
    for name in CONFIGS:
        s = S[name]
        pf = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
        md.append(f"| {name} | {s['n']} | ${s['net']:,.0f} | ${s['exp']:+.0f} | {s['win']:.1f}% | "
                  f"{s['scratch']:.1f}% | {pf} | ${s['mdd']:,.0f} | {s['mar']:.2f} |")
    md.append("")

    # accounting verdict
    s1, s2 = S["DIAG single 2R (1c)"]["net"], S["DIAG ML both@2R (2c)"]["net"]
    ratio = s2 / s1 if s1 else float("nan")
    md.append("## Accounting check\n")
    md.append(f"- single 2R (1c) net = ${s1:,.0f}; ML both@2R (2c) net = ${s2:,.0f}; "
              f"ratio = **{ratio:.2f}x** (must be ~2.00 if multileg net is correctly scaled).\n")
    so = S["DIAG ML scaleout 1R/2R (2c)"]["net"]
    expect = S["DIAG single 1R (1c)"]["net"] + S["DIAG single 2R (1c)"]["net"]
    md.append(f"- ML scaleout 1R/2R net = ${so:,.0f}; expected (single1R + single2R) = "
              f"${expect:,.0f}; ratio = **{so/expect:.2f}x** (must be ~1.00).\n")

    out = _OUT / f"ib_edge_scalein_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
