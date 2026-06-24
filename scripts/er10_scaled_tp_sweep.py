"""er10_scaled_tp_sweep.py — volatility/risk-scaled take-profit on ER10-decayed trades.

The fixed +4pt TP helped the flagged (ER10-decayed-by-EB-close) trades by ~$14/trade
and ONLY those trades (control passed). But +4pt is crude — it ignores each trade's
stop distance and the day's volatility. This sweeps targets that SCALE per trade:
  • fractional-R : k_pts = frac · RiskPts          (frac in {0.25,0.5,0.75,1.0})
  • ABR-%        : k_pts = frac · prior_ATR         (frac in {0.05,0.075,0.10,0.15})
plus the fixed +4pt reference. Each is applied at EB close as a take-profit (favorable
offset), original stop & 1R target kept as outer guards (reusing er10_block_exit_sweep).

For every spec we report the FLAGGED subset (the target group) AND, as the control,
the UNFLAGGED subset (must NOT benefit). The best flagged spec is then broken down
BY YEAR for stability. In-sample on MC — RevFT/OOS validation is a separate step.
Out: docs/living/er10_scaled_tp_sweep_<date>.md
"""
from __future__ import annotations

import sys, gc
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import massive                                                        # noqa: E402
from simulation_engine import simulate_trades                         # noqa: E402
from indicators import tag_signals                                    # noqa: E402
from data_loader import bar_num_from_dt                               # noqa: E402
from er_lookahead_tab import _er10_both_modes                         # noqa: E402
from er10_block_exit_sweep import (_overlay_gross_pts, _net,          # noqa: E402
                                   GATE, SIM_KW, N_CHUNKS)

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"

R_FRACS   = [0.25, 0.5, 0.75, 1.0]
ABR_FRACS = [0.05, 0.075, 0.10, 0.15]
# spec name -> (kind, frac); kind in {"R","ABR","FIX"}
SPECS = {f"{f:g}R": ("R", f) for f in R_FRACS}
SPECS.update({f"{f:g}xABR": ("ABR", f) for f in ABR_FRACS})
SPECS["+4pt(fix)"] = ("FIX", 4.0)


def log(m): print(f"[stp] {datetime.now():%H:%M:%S} {m}", flush=True)


def _k_points(kind, frac, risk_pts, abr) -> float:
    if kind == "R":   return frac * risk_pts
    if kind == "ABR": return frac * abr
    return frac                                # FIX → points


def main() -> int:
    log("load + tag (ER both modes + prior_ATR) ...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bbd = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)

    tagged = _er10_both_modes(sig, bars)
    atr = tag_signals(sig, bars)[["SignalNum", "prior_ATR"]]
    tagged = tagged.merge(atr, on="SignalNum", how="left")

    causal_pass = tagged["ER10_causal"] >= GATE
    cur_pass    = tagged["ER10_current"] >= GATE
    flag = causal_pass & ~cur_pass
    g = tagged.loc[causal_pass].copy()
    g["FilterStatus"] = "ok"
    g["flagged"] = flag.loc[g.index].to_numpy()
    g["_date"] = pd.to_datetime(g["DateTime"]).dt.date

    rows = []
    dates = sorted(g["_date"].unique())
    for ci, chunk in enumerate(np.array_split(np.array(dates, object), N_CHUNKS)):
        cset = set(chunk.tolist())
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        sub = g[g["_date"].isin(cset)].drop(columns="_date").reset_index(drop=True)
        res = simulate_trades(sub, ticks_by_date=tbd, bars_by_date=bbd, **SIM_KW)
        filled = res[res["Filled"] == True].copy()
        for r in filled.itertuples(index=False):
            t = tbd.get(r.Date)
            abr = float(getattr(r, "prior_ATR", np.nan))
            rec = {"flag": bool(r.flagged), "year": pd.Timestamp(r.EntryTime).year,
                   "net_base": _net(r.GrossPnLPts)}
            for name, (kind, frac) in SPECS.items():
                if t is None or t.empty or (kind == "ABR" and not np.isfinite(abr)):
                    rec[name] = _net(r.GrossPnLPts)
                else:
                    k = _k_points(kind, frac, r.RiskPts, abr)
                    rec[name] = _net(_overlay_gross_pts(r, t, k))
            rows.append(rec)
        del tbd; gc.collect()
        log(f"  chunk {ci+1}/{N_CHUNKS} done")

    df = pd.DataFrame(rows)
    df.to_parquet(_OUT / "er10_scaled_tp_pertrade.parquet")   # per-trade net by target spec
    F, U = df[df["flag"]], df[~df["flag"]]
    base_f, base_u = F["net_base"].sum(), U["net_base"].sum()
    expb_f = F["net_base"].mean()

    # rank specs by flagged mean delta
    spec_stats = []
    for name in SPECS:
        fΔ = F[name].mean() - expb_f
        uΔ = U[name].mean() - U["net_base"].mean()
        spec_stats.append((name, F[name].sum(), F[name].mean(), fΔ,
                           F[name].sum() - base_f, uΔ))
    spec_stats.sort(key=lambda x: x[3], reverse=True)
    best = spec_stats[0]

    md = [f"# ER10 scaled take-profit sweep — flagged trades ({datetime.now():%Y-%m-%d})\n",
          "Take-profit applied at EB close (when the entry-bar ER10 is legitimately known) "
          "to the ER10-DECAYED 'flagged' trades, target SCALED per trade by risk (R) or "
          "volatility (prior_ATR). Control column = same target on UNFLAGGED trades (must "
          "not help). In-sample MC.\n",
          f"**Set:** `ba_signals_mc.parquet`  **Gate:** {GATE:.2f}  "
          f"**flagged n:** {len(F):,}  **unflagged n:** {len(U):,}  "
          f"**flagged baseline:** ${base_f:,.0f} (exp ${expb_f:,.2f}/trade).\n",
          "## Scaled-target results (ranked by flagged mean Δ/trade)\n",
          "| target | flagged net $ | flagged exp $ | flagged Δ/trade $ | flagged total Δ $ "
          "| UNFLAGGED Δ/trade $ (control) |",
          "|---|---|---|---|---|---|",
          f"| BASELINE (1R only) | ${base_f:,.0f} | ${expb_f:,.2f} | — | — | — |"]
    for name, net, exp, fΔ, ftot, uΔ in spec_stats:
        flagm = "  ⭐" if name == best[0] else ""
        md.append(f"| {name}{flagm} | ${net:,.0f} | ${exp:,.2f} | ${fΔ:,.2f} | ${ftot:,.0f} "
                  f"| ${uΔ:,.2f} |")

    # by-year stability for the best spec
    bn = best[0]
    md += ["", f"## By-year stability — best target `{bn}` (flagged only)\n",
           "| year | n | baseline net $ | baseline exp $ | overlay net $ | overlay exp $ | Δ/trade $ |",
           "|---|---|---|---|---|---|---|"]
    for yr, d in F.groupby("year"):
        b, o = d["net_base"], d[bn]
        md.append(f"| {yr} | {len(d):,} | ${b.sum():,.0f} | ${b.mean():,.2f} | "
                  f"${o.sum():,.0f} | ${o.mean():,.2f} | ${o.mean()-b.mean():,.2f} |")
    md += ["",
           f"**Best:** `{bn}` → flagged exp ${best[2]:,.2f}/trade "
           f"(Δ ${best[3]:,.2f}, total ${best[4]:,.0f}); control UNFLAGGED Δ ${best[5]:,.2f}/trade "
           "(should be ≤ 0). Positive flagged Δ with negative control Δ every year = robust; "
           "a year that flips = fragile.\n"]
    out = _OUT / f"er10_scaled_tp_sweep_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    log(f"BEST {bn}: flagged Δ ${best[3]:.2f}/trade (total ${best[4]:,.0f}), "
        f"control unflagged Δ ${best[5]:.2f}/trade")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
