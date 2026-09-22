"""Finalize + AUDIT the best RevFT config found:
  detection: FT_ABR>=1.0 (strong follow-through) + OB_Strict
  filter:    below prior-day SMA20-D (negative-gamma / mean-revert regime)
  exit:      EOD hold, 1 ES, no overlap, $30 RT.  All fills tick-accurate.
Prints metrics + per-year, saves trades + equity curve + trade-audit chart.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
ROOT = Path(r"c:\Users\Admin\myquant")
sys.path.insert(0, str(ROOT / "research" / "revsim")); sys.path.insert(0, str(ROOT / "research" / "scalp_swing"))
import revsim as R, revdetect as RD, engine_ticks as E
import swing_level_gated as G

df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
df5["DateTime"] = pd.to_datetime(df5["DateTime"])
sma = G.sma20d_map(df5)
sg = RD.detect(df5, {"FT_ABR": 1.0, "OB_Strict": True})
tr = R.sim(sg, entry="market", hold_eod=True, gate="below", sma=sma)
tr["d"] = pd.to_datetime(tr["Date"])

print("=== RevFT FINAL: FT_ABR>=1.0 + OB_strict + below-SMA20-D + EOD hold ===")
for lab, t in [("ALL 2021-26", tr), ("TRAIN 2021-23", tr[tr.d < '2024-01-01']), ("OOS 2024-26", tr[tr.d >= '2024-01-01'])]:
    print(f"{lab:14s}", E.metrics(t))
print("\nPER YEAR:"); print(E.by_year(tr).to_string())
print("\nBY TYPE:"); print(tr.groupby("rev").pnl.agg(["count", "sum"]).round(0).to_string())
print("BY SIDE:"); print(tr.groupby("side").pnl.agg(["count", "sum"]).round(0).to_string())
print("EXIT REASONS:"); print(tr.reason.value_counts().to_string())
tr.to_csv(ROOT / "research" / "revsim" / "TRADES_revft_final.csv", index=False)

# equity curve
t2 = tr.sort_values("etime").reset_index(drop=True); t2["cum"] = t2.pnl.cumsum()
si = int((t2.d < "2024-01-01").sum())
fig, ax = plt.subplots(figsize=(12, 5))
ax.plot(range(len(t2)), t2.cum, color="#6a1b9a", lw=1.5)
ax.fill_between(range(si), t2.cum[:si], color="#6a1b9a", alpha=0.08)
ax.axvline(si, color="gray", ls="--"); ax.text(si, t2.cum.min()*0.9, " OOS 2024-26", fontsize=9)
ax.set_title("RevFT (strong-FT + OB-strict + below-SMA20 + EOD) cum P&L (1 ES, $30 RT, tick fills). PF 1.19 / netDD 2.9")
ax.set_ylabel("Cumulative $"); ax.set_xlabel("trade #"); ax.grid(alpha=0.3)
fig.tight_layout(); fig.savefig(ROOT / "research" / "revsim" / "EQUITY_revft_final.png", dpi=110)

# trade audit: 3 win + 3 loss
wins = tr[tr.pnl > 0].sample(3, random_state=1); loss = tr[tr.pnl < 0].sample(3, random_state=3)
fig2, axes = plt.subplots(2, 3, figsize=(19, 10)); axes = axes.flatten()
for ax, (_, t) in zip(axes, pd.concat([wins, loss]).iterrows()):
    d = t["Date"]; day = df5[df5.Date == d].reset_index(drop=True)
    for i in range(len(day)):
        o, h, l, c = day.Open[i], day.High[i], day.Low[i], day.Close[i]
        col = "#26a69a" if c >= o else "#ef5350"
        ax.plot([i, i], [l, h], color=col, lw=0.6); ax.add_patch(Rectangle((i-0.3, min(o, c)), 0.6, abs(c-o)+1e-6, color=col))
    Lv = sma.get(d, np.nan)
    if np.isfinite(Lv): ax.axhline(Lv, color="#7e57c2", lw=1.1, ls="--", label=f"SMA20D {Lv:.0f}")
    et = pd.to_datetime(t["etime"]); xt = pd.to_datetime(t["xtime"])
    eb = int((et - pd.to_datetime(day.DateTime[0])).total_seconds()//300)
    xb = int((xt - pd.to_datetime(day.DateTime[0])).total_seconds()//300)
    ax.axhline(t["entry"], color="k", lw=1, label=f"entry {t['entry']:.2f}")
    ax.axhline(t["stop"], color="#d32f2f", lw=1, ls=":", label=f"stop {t['stop']:.2f}")
    ax.scatter([eb], [t["entry"]], marker="^" if t["side"] > 0 else "v", s=120, color="blue", zorder=5)
    ax.scatter([xb], [t["exitpx"]], marker="x", s=120, color="black", zorder=5)
    ax.set_title(f"{d} {t['rev']} {'L' if t['side']>0 else 'S'} {t['reason']} ${t['pnl']:.0f}", fontsize=9)
    ax.legend(fontsize=7)
fig2.suptitle("RevFT final trade audit (tick-verified): 3 win (top) / 3 loss (bottom)", fontsize=13)
fig2.tight_layout(); fig2.savefig(ROOT / "research" / "revsim" / "AUDIT_revft_trades.png", dpi=110)
print("\ncharts -> EQUITY_revft_final.png, AUDIT_revft_trades.png")
print("DONE_FINAL_REVFT")
