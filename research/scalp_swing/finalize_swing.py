"""Finalize + AUDIT the chosen swing: SMA20-D-gated IB breakout, hold to close, 2:1.
Config: ib12 (60-min IB), risk 10pt (target 20pt), min_dist 3pt, cutoff bar 54.
Prints full metrics + per-year (train/oos), saves trade list, and charts sample
winning & losing trades on 5M candles WITH tick-verified entry/stop/target/exit.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
ROOT = Path(r"c:\Users\Admin\myquant"); sys.path.insert(0, str(ROOT / "research" / "scalp_swing"))
import engine_ticks as E
import swing_level_gated as G

df5 = pd.read_parquet(ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet")
sma = G.sma20d_map(df5)
IB, RISK, RR, MD, CUT = 12, 10, 2.0, 3.0, 54
_f = G.make_level_ib(sma, IB, RISK, rr=RR, cutoff_bar=CUT, min_dist=MD, tag="sma20d")


def f(day):  # LONG-ONLY (shorts were pure drag; beta-checked)
    s = _f(day)
    s.loc[s["side"] == -1, ["side", "entry", "stop", "target", "etype", "expiry"]] = [0, np.nan, np.nan, np.nan, "", 0]
    return s
f.__name__ = "swing_final_LONGONLY"
tr = E.run(df5, f, max_hold_minutes=None, min_rr=2.0)
tr["d"] = pd.to_datetime(tr["Date"])
trn = tr[tr.d < "2024-01-01"]; oos = tr[tr.d >= "2024-01-01"]

print("=== CHOSEN SWING: SMA20-D-gated IB(60m) breakout, 10pt stop / 20pt tgt, hold to close ===")
for lab, t in [("ALL 2021-26", tr), ("TRAIN 2021-23", trn), ("OOS 2024-26", oos)]:
    print(f"{lab:16s}", E.metrics(t))
print("\nPER YEAR:"); print(E.by_year(tr).to_string())
print("\nEXIT REASONS:"); print(tr.reason.value_counts().to_string())
print("SIDE SPLIT:"); print(tr.groupby("side").pnl.agg(["count", "sum"]).to_string())
tr.to_csv(ROOT / "research" / "scalp_swing" / "TRADES_swing_final.csv", index=False)
print(f"\nsaved {len(tr)} trades -> TRADES_swing_final.csv")

# ---- chart audit: 3 wins + 3 losses, spread across years ----
wins = tr[tr.reason == "target"].sample(3, random_state=1) if (tr.reason == "target").sum() >= 3 else tr[tr.pnl > 0].head(3)
loss = tr[tr.reason == "stop"].sample(3, random_state=2) if (tr.reason == "stop").sum() >= 3 else tr[tr.pnl < 0].head(3)
sample = pd.concat([wins, loss])

fig, axes = plt.subplots(2, 3, figsize=(19, 10)); axes = axes.flatten()
for ax, (_, t) in zip(axes, sample.iterrows()):
    d = t["Date"]; day = df5[df5.Date == d].reset_index(drop=True)
    x = np.arange(len(day))
    for i in range(len(day)):
        o, h, l, c = day.Open[i], day.High[i], day.Low[i], day.Close[i]
        col = "#26a69a" if c >= o else "#ef5350"
        ax.plot([i, i], [l, h], color=col, lw=0.6)
        ax.add_patch(Rectangle((i - 0.3, min(o, c)), 0.6, abs(c - o) + 1e-6, color=col))
    L = sma.get(d, np.nan)
    if np.isfinite(L):
        ax.axhline(L, color="#7e57c2", lw=1.2, ls="--", label=f"SMA20D {L:.0f}")
    ax.axhline(t["entry"], color="black", lw=1, ls="-", label=f"entry {t['entry']:.2f}")
    ax.axhline(t["stop"], color="#d32f2f", lw=1, ls=":", label=f"stop {t['stop']:.2f}")
    ax.axhline(t["target"], color="#388e3c", lw=1, ls=":", label=f"tgt {t['target']:.2f}")
    # entry/exit bar index by time
    et = pd.to_datetime(t["etime"]); xt = pd.to_datetime(t["xtime"])
    ebar = int(((et - pd.to_datetime(day.DateTime[0])).total_seconds()) // 300)
    xbar = int(((xt - pd.to_datetime(day.DateTime[0])).total_seconds()) // 300)
    ax.scatter([ebar], [t["entry"]], marker="^" if t["side"] > 0 else "v", s=120,
               color="blue", zorder=5)
    ax.scatter([xbar], [t["exitpx"]], marker="x", s=120, color="black", zorder=5)
    ax.axvspan(0, IB, color="gray", alpha=0.08)  # IB region
    sidestr = "LONG" if t["side"] > 0 else "SHORT"
    ax.set_title(f"{d}  {sidestr}  {t['reason']}  P&L ${t['pnl']:.0f}", fontsize=10)
    ax.legend(fontsize=7, loc="best")
fig.suptitle("Gated LONG swing trade audit (tick-verified fills): 3 winners (top) / 3 losers (bottom)", fontsize=13)
fig.tight_layout()
out = ROOT / "research" / "scalp_swing" / "AUDIT_swing_trades.png"
fig.savefig(out, dpi=110); print(f"chart -> {out}")

# ---- equity curve, train vs oos ----
fig2, ax2 = plt.subplots(figsize=(12, 5))
t2 = tr.sort_values("etime").reset_index(drop=True)
t2["eq"] = t2.pnl.cumsum()
split = (t2.d < "2024-01-01")
ax2.plot(range(len(t2)), t2.eq, color="#1565c0", lw=1.5)
si = split.sum()
ax2.axvline(si, color="gray", ls="--"); ax2.text(si, t2.eq.min(), " OOS start 2024", fontsize=9)
ax2.fill_between(range(si), t2.eq[:si], color="#1565c0", alpha=0.08)
ax2.set_title("Gated LONG swing — cumulative P&L (1 ES, $30 RT, tick fills). Left=train, right=OOS holdout")
ax2.set_ylabel("Cumulative $"); ax2.grid(alpha=0.3)
out2 = ROOT / "research" / "scalp_swing" / "EQUITY_swing_final.png"
fig2.tight_layout(); fig2.savefig(out2, dpi=110); print(f"equity -> {out2}")
