"""Compare footprint from the FootprintExporter (recorder) vs footprint rebuilt from the
L2 depth-recorder TAPE, over the same RTH window. Session volume-profile method (per-price
buy/sell totals) — robust to volume-bar boundary differences. Validates that the depth
recording alone can reconstruct footprint (and by extension, so can Databento MBO)."""
import glob, os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = "c:/Users/Admin/myquant"
WIN_START = pd.Timestamp("2026-07-20 08:30:00")
WIN_END = pd.Timestamp("2026-07-20 15:15:00")

FP = sorted(glob.glob(f"{ROOT}/data/footprint/ES*6500V*footprint*.csv"), key=os.path.getmtime)[-1]
TAPE = f"{ROOT}/data/depth/ES_09-26_depth_2026-07-20.csv"

# ---- recorder footprint ----
fp = pd.read_csv(FP)
fp["BarTime"] = pd.to_datetime(fp["BarTime"], errors="coerce")
fpw = fp[(fp.BarTime >= WIN_START) & (fp.BarTime <= WIN_END)]
fp_prof = fpw.groupby("Price").agg(bid=("BidVol", "sum"), ask=("AskVol", "sum"))

# ---- tape-rebuilt footprint (from L2 depth recorder) ----
tp = pd.read_csv(TAPE, usecols=["Time", "Ev", "Side", "Price", "Size"],
                 dtype={"Ev": "category", "Side": "category"}, on_bad_lines="skip")
tp = tp[tp.Ev == "T"].copy()
tp["Time"] = pd.to_datetime(tp["Time"], errors="coerce")
tpw = tp[(tp.Time >= WIN_START) & (tp.Time <= WIN_END)]
tp_bid = tpw[tpw.Side == "B"].groupby("Price")["Size"].sum()   # sell aggressor -> BidVol
tp_ask = tpw[tpw.Side == "A"].groupby("Price")["Size"].sum()   # buy  aggressor -> AskVol
tp_prof = pd.DataFrame({"bid": tp_bid, "ask": tp_ask}).fillna(0)

# ---- align ----
P = fp_prof.join(tp_prof, lsuffix="_fp", rsuffix="_tp", how="outer").fillna(0).sort_index()

fb, fa = P.bid_fp.sum(), P.ask_fp.sum()
tb, ta = P.bid_tp.sum(), P.ask_tp.sum()
print(f"window {WIN_START.time()}-{WIN_END.time()} CT  ·  {len(fpw)} fp-rows/{fpw.BarIdx.nunique()} bars  ·  {len(tpw):,} tape prints")
print(f"  RECORDER (FootprintExporter):  BidVol {fb:>10,.0f}  AskVol {fa:>10,.0f}  total {fb+fa:>11,.0f}")
print(f"  TAPE-REBUILD (L2 depth):       BidVol {tb:>10,.0f}  AskVol {ta:>10,.0f}  total {tb+ta:>11,.0f}")
print(f"  DELTA:                         BidVol {tb-fb:>+10,.0f}  AskVol {ta-fa:>+10,.0f}  "
      f"({100*(tb+ta-fb-fa)/(fb+fa):+.3f}% total)")

# per-price agreement (correlation on the matched grid)
bid_r = np.corrcoef(P.bid_fp, P.bid_tp)[0, 1]
ask_r = np.corrcoef(P.ask_fp, P.ask_tp)[0, 1]
# rows where the two disagree by >5% of that price's volume
tot_fp = P.bid_fp + P.ask_fp
tot_tp = P.bid_tp + P.ask_tp
mism = (np.abs(tot_fp - tot_tp) > 0.05 * np.maximum(tot_fp, 1)).sum()
print(f"  per-price corr: bid r={bid_r:.5f}  ask r={ask_r:.5f}  ·  prices >5% off: {mism}/{len(P)}")

# ---- visuals ----
BG, FG, MUT, GRID = "#0d1117", "#e6edf3", "#8b949e", "#222831"
BUY, SELL = "#26a69a", "#ef5350"
fig = plt.figure(figsize=(15, 8.6), facecolor=BG)
fig.suptitle("Footprint validation — FootprintExporter (recorder)  vs  rebuilt from L2 depth tape",
             color=FG, fontsize=15, fontweight="bold", x=0.5, y=0.975)
fig.text(0.5, 0.935, f"ES 09-26 · 2026-07-20 RTH 08:30–15:15 CT · session volume profile "
         f"(per-price buy/sell) · total match {100*(tb+ta)/(fb+fa):.3f}%",
         color=MUT, fontsize=10.5, ha="center")

# panel 1: mirrored volume profile (recorder solid, tape outline)
ax = fig.add_axes([0.06, 0.08, 0.5, 0.82]); ax.set_facecolor(BG)
pr = P.index.values
ax.barh(pr, -P.bid_fp, height=0.22, color=SELL, alpha=0.85, label="recorder BidVol (sells)")
ax.barh(pr, P.ask_fp, height=0.22, color=BUY, alpha=0.85, label="recorder AskVol (buys)")
ax.barh(pr, -P.bid_tp, height=0.22, facecolor="none", edgecolor=FG, lw=0.7, label="tape rebuild (outline)")
ax.barh(pr, P.ask_tp, height=0.22, facecolor="none", edgecolor=FG, lw=0.7)
ax.axvline(0, color=MUT, lw=0.8)
ax.set_ylabel("Price", color=FG); ax.set_xlabel("← sells    volume    buys →", color=MUT)
ax.tick_params(colors=MUT); ax.grid(color=GRID, lw=0.5, axis="x")
ax.legend(loc="upper left", facecolor=BG, edgecolor=GRID, labelcolor=FG, fontsize=8)
for s in ax.spines.values():
    s.set_color(GRID)
ax.set_title("Volume profile — bars=recorder, white outline=tape rebuild (should coincide)",
             color=FG, fontsize=10)

# panel 2: scatter fp vs tape per (price, side) — perfect rebuild = y=x
ax2 = fig.add_axes([0.63, 0.08, 0.33, 0.82]); ax2.set_facecolor(BG)
ax2.scatter(P.bid_fp, P.bid_tp, s=18, color=SELL, alpha=0.7, label=f"bid/sell  r={bid_r:.4f}")
ax2.scatter(P.ask_fp, P.ask_tp, s=18, color=BUY, alpha=0.7, label=f"ask/buy  r={ask_r:.4f}")
m = max(P[["bid_fp", "ask_fp", "bid_tp", "ask_tp"]].max())
ax2.plot([0, m], [0, m], color=FG, lw=1, ls="--", alpha=0.6, label="perfect match (y=x)")
ax2.set_xlabel("recorder volume", color=MUT); ax2.set_ylabel("tape-rebuild volume", color=MUT)
ax2.tick_params(colors=MUT); ax2.grid(color=GRID, lw=0.5)
ax2.legend(loc="upper left", facecolor=BG, edgecolor=GRID, labelcolor=FG, fontsize=9)
for s in ax2.spines.values():
    s.set_color(GRID)
ax2.set_title("Per-price agreement (on y=x ⇒ identical)", color=FG, fontsize=10)

out = f"{ROOT}/scratchpad/fp_compare.png"
fig.savefig(out, dpi=120, facecolor=BG)
print("WROTE", out)
