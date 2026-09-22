"""Graph the Apex 150K funded-account MES scaling over the full 5.1-yr backtest.
Reuses cached trades (regime2e_apex_mes.py). FUNDED account, intraday $5,000 DD.

  python scripts/regime2e_apex_scale_chart.py
Output: reports/regime2e/apex_scale_chart.png
"""
import pickle
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MES_PT = 5.0; MES_FEE = 1.02 + 1.25; T = 5000.0; MAXC = 100
REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "reports" / "regime2e" / "apex_mes_trades.pkl"
OUT = REPO / "reports" / "regime2e" / "apex_scale_chart.png"


def series(trades, base, R):
    realized = 0.0; peak = 0.0
    rows = []
    for t in trades:
        floor = 100.0 if peak >= T + 100 else peak - T
        cushion = realized - floor
        size = base if R is None else int(max(base, min(MAXC, cushion // R)))
        u = t["sgn"] * (t["seg"] - t["entry"]) * MES_PT * size
        eq = realized + u
        runpk = np.maximum(peak, np.maximum.accumulate(eq))
        fl = np.where(runpk >= T + 100, 100.0, runpk - T)
        mc = float((eq - fl).min())
        peak = float(runpk[-1])
        realized += t["gross_pts"] * MES_PT * size - MES_FEE * size
        rows.append((t["date"], realized, size, mc))
    df = pd.DataFrame(rows, columns=["date", "equity", "size", "cushion"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def main():
    trades = pickle.load(open(CACHE, "rb"))
    configs = [("flat 5 MES", 5, None, "#888888"),
               ("flat 8 MES", 8, None, "#1565c0"),
               ("base5 +1c/$1,000 cushion", 5, 1000, "#2e7d32"),
               ("base5 +1c/$500 cushion", 5, 500, "#ef6c00")]
    data = {name: series(trades, b, R) for name, b, R, _ in configs}

    fig, ax = plt.subplots(3, 1, figsize=(13, 11), sharex=True)
    fig.suptitle("Apex FUNDED 150K PA — 2E book in MES, intraday $5,000 trailing DD\n"
                 "full backtest 2021-07 → 2026-09 (5.1 yr real ticks) · NOT the eval",
                 fontsize=13, weight="bold")

    for name, b, R, c in configs:
        df = data[name]
        ax[0].plot(df["date"], df["equity"], label=name, color=c, lw=1.5)
    ax[0].axhline(0, color="#aaa", lw=0.7)
    ax[0].set_ylabel("account profit ($)")
    ax[0].set_title("Account equity — profit accumulated (assumes NO withdrawals)")
    ax[0].legend(fontsize=9, loc="upper left")

    for name, b, R, c in configs:
        df = data[name]
        ax[1].step(df["date"], df["size"], where="post", label=name, color=c, lw=1.3)
    ax[1].set_ylabel("position size (MES)")
    ax[1].set_title("Contract size over time — stays small through the ramp, grows with the cushion")
    ax[1].legend(fontsize=9, loc="upper left")

    for name, b, R, c in configs:
        df = data[name]
        ax[2].plot(df["date"], df["cushion"], label=name, color=c, lw=1.1)
    ax[2].axhline(0, color="#c62828", lw=1.5, ls="--", label="0 = ACCOUNT BLOWN")
    ax[2].set_ylabel("cushion to floor ($)")
    ax[2].set_title("Distance to the blow-up floor per trade — stays above 0 = survives")
    ax[2].legend(fontsize=8, loc="upper left")
    ax[2].set_ylim(-1000, 8000)

    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(OUT, dpi=120)
    print(f"chart: {OUT}")
    # plain-English summary
    for name, b, R, c in configs:
        df = data[name]
        print(f"  {name:<26} end profit ${df['equity'].iloc[-1]:+,.0f}  peak size {df['size'].max()}c  "
              f"min cushion ${df['cushion'].min():+,.0f}")


if __name__ == "__main__":
    main()
