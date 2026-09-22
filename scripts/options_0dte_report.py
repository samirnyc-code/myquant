"""options_0dte_report.py — organize the 0DTE backtest into a drill-down report.

Reads data/options_0dte/trades_all.csv and produces:
  - per-(anchor, strategy) performance: n, win%, mean/total P&L (mid + cross fill),
    Sharpe, profit factor, max drawdown
  - CLOSE- vs OPEN-anchored head-to-head per strategy
  - GAP analysis: performance bucketed by gap% (open - prior_close), per anchor —
    answers "does anchoring on the open beat the prior close, and when?"
  - equity curves (cumulative mid P&L) per strategy x anchor -> PNG
  - a written verdict per strategy (works / doesn't / why)
Outputs a self-contained HTML report + PNGs, and prints all tables inline.

Run: .venv/Scripts/python.exe scripts/options_0dte_report.py
Out: data/options_0dte/report.html + *.png ; console tables
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
D = ROOT / "data" / "options_0dte"
TRADES = D / "trades_all.csv"
STRATS = ["bps", "bcs", "ic", "ifly"]
NAMES = {"bps": "Bull Put Spread", "bcs": "Bear Call Spread",
         "ic": "Iron Condor", "ifly": "Iron Fly"}


def perf(g, col="pnl_mid"):
    x = g[col].to_numpy()
    if len(x) == 0:
        return {}
    wins = x[x > 0].sum(); losses = -x[x < 0].sum()
    cum = np.cumsum(x); dd = (np.maximum.accumulate(cum) - cum).max()
    return {"n": len(x), "win%": round((x > 0).mean() * 100, 1),
            "mean": round(x.mean(), 1), "total": round(x.sum(), 0),
            "sharpe": round(x.mean() / x.std() * np.sqrt(252), 2) if x.std() else 0,
            "pf": round(wins / losses, 2) if losses else np.inf,
            "maxDD": round(dd, 0)}


def main():
    t = pd.read_csv(TRADES, parse_dates=["date"])
    t = t.sort_values("date")
    span = f"{t.date.min().date()} -> {t.date.max().date()}  ({t.date.nunique()} sessions)"
    html = [f"<h1>0DTE SPXW premium-selling backtest</h1><p>{span}. "
            f"Fills: MID (fair) and CROSS (worst-case). $1.30/contract/leg. "
            f"EM = prior_close x VIX/100 / sqrt(252).</p>"]

    # 1. headline table (mid fill), both anchors
    print(f"\n===== 0DTE backtest  {span} =====\n")
    print("PER STRATEGY x ANCHOR (MID fill):")
    rowsH = []
    for anc in ["close", "open"]:
        for s in STRATS:
            g = t[(t.anchor == anc) & (t.strat == s)]
            p = perf(g)
            pc = perf(g, "pnl_cross")
            rowsH.append({"anchor": anc, "strat": s, **p,
                          "mean_cross": pc.get("mean"), "total_cross": pc.get("total")})
    H = pd.DataFrame(rowsH)
    print(H.to_string(index=False))
    html.append("<h2>1. Per strategy x anchor (mid fill; cross for reference)</h2>"
                + H.to_html(index=False))

    # 2. close vs open head-to-head
    print("\nCLOSE vs OPEN (mid mean P&L per trade):")
    cmp = t.pivot_table(index="strat", columns="anchor", values="pnl_mid", aggfunc="mean").round(1)
    cmp["open_edge"] = (cmp["open"] - cmp["close"]).round(1)
    cmp = cmp.reindex(STRATS)
    print(cmp.to_string())
    html.append("<h2>2. Close- vs Open-anchored (mid mean P&L/trade)</h2>" + cmp.to_html())

    # 3. gap analysis
    bins = [-99, -1, -0.5, -0.2, 0.2, 0.5, 1, 99]
    labs = ["<-1%", "-1..-0.5", "-0.5..-0.2", "flat", "0.2..0.5", "0.5..1", ">1%"]
    t["gap_bucket"] = pd.cut(t["gap_pct"], bins=bins, labels=labs)
    print("\nGAP ANALYSIS - mean mid P&L by gap bucket (open anchor), all strats:")
    for s in STRATS:
        sub = t[(t.strat == s) & (t.anchor == "open")]
        gg = sub.groupby("gap_bucket", observed=False)["pnl_mid"].agg(["size", "mean"]).round(1)
        print(f"\n  {NAMES[s]} (open anchor):")
        print(gg.to_string())
    # close vs open edge by gap bucket (bps + ic, the promising ones)
    html.append("<h2>3. Gap analysis</h2>")
    for s in STRATS:
        piv = t[t.strat == s].pivot_table(index="gap_bucket", columns="anchor",
                                          values="pnl_mid", aggfunc="mean", observed=False).round(1)
        piv["open_edge"] = (piv["open"] - piv["close"]).round(1)
        html.append(f"<h3>{NAMES[s]} — mean mid P&L by gap bucket</h3>" + piv.to_html())

    # 4. equity curves
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    for ax, s in zip(axes.ravel(), STRATS):
        for anc, c in (("close", "#d62728"), ("open", "#1f77b4")):
            g = t[(t.anchor == anc) & (t.strat == s)].sort_values("date")
            ax.plot(g["date"], g["pnl_mid"].cumsum(), label=f"{anc} anchor", color=c, lw=1.4)
        ax.axhline(0, color="#888", lw=0.6)
        ax.set_title(NAMES[s]); ax.legend(fontsize=8); ax.grid(alpha=0.25)
    fig.suptitle("Cumulative mid P&L per contract — close vs open anchor", fontsize=13)
    fig.tight_layout()
    png = D / "equity_curves.png"
    fig.savefig(png, dpi=110); plt.close(fig)
    html.append(f"<h2>4. Equity curves</h2><img src='{png.name}' style='max-width:100%'>")
    print(f"\nsaved {png}")

    (D / "report.html").write_text("<style>body{font-family:system-ui;margin:24px;max-width:1100px}"
                                   "table{border-collapse:collapse;margin:8px 0}"
                                   "td,th{border:1px solid #ccc;padding:3px 8px;font-size:13px;text-align:right}"
                                   "</style>" + "\n".join(html), encoding="utf-8")
    print(f"saved {D/'report.html'}")


if __name__ == "__main__":
    main()
