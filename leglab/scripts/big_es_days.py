"""
Validate Tim's "Big ES days — what follows" (independent of the leg thesis).

Tim: big day = daily bar range >= ~3.3x ABR8; of 14 cases, 12 got a same-direction
2nd leg the NEXT day = 85%. Enter 50% pullback next day, stop beyond big-day bar.

We have 16y ES 5M RTH -> aggregate to daily RTH bars and test on a real sample
(hundreds of big days, not 14). Test K = 2.0 / 2.5 / 3.0 / 3.3 x ABR8.

Outcomes next day (dir = sign(big_day close - open)):
  same_close   : next day closes in the same direction it opened (next-day trend)
  cont_close   : next day's CLOSE continues past the big day's close (dir)
  extend_extreme: next day makes a new extreme beyond the big day's extreme (dir)
Compare each big-day bucket to the base rate over all days.

Reads the ES 5M RTH parquet directly (daily aggregation). Writes CSV + summary + chart.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
BARS = ROOT / "data" / "bars" / "_db_es_5m_rth.parquet"
OUTDIR = ROOT / "leglab" / "outputs"
RUN = "20260906"


def main():
    df = pd.read_parquet(BARS)
    df["DateTime"] = pd.to_datetime(df["DateTime"])
    df["date"] = df["DateTime"].dt.date
    d = df.groupby("date").agg(
        o=("Open", "first"), c=("Close", "last"), h=("High", "max"), l=("Low", "min"),
    )
    d["range"] = d["h"] - d["l"]
    d["abr8"] = d["range"].shift(1).rolling(8).mean()
    d["rng_x"] = d["range"] / d["abr8"]
    d["dir"] = np.sign(d["c"] - d["o"]).astype(int)

    # next-day fields
    d["n_o"] = d["o"].shift(-1); d["n_c"] = d["c"].shift(-1)
    d["n_h"] = d["h"].shift(-1); d["n_l"] = d["l"].shift(-1)
    d = d.dropna(subset=["abr8", "n_c"]).copy()

    dir_ = d["dir"]
    d["same_close"] = (np.sign(d["n_c"] - d["n_o"]) == dir_).astype(int)
    d["cont_close"] = (np.sign(d["n_c"] - d["c"]) == dir_).astype(int)
    d["extend_extreme"] = np.where(dir_ > 0, d["n_h"] > d["h"], d["n_l"] < d["l"]).astype(int)
    # next-day continuation return in the big-day direction (points)
    d["cont_ret"] = (d["n_c"] - d["c"]) * dir_

    def p(s=""):
        print(s)

    base = {
        "same_close": d["same_close"].mean(), "cont_close": d["cont_close"].mean(),
        "extend_extreme": d["extend_extreme"].mean(), "cont_ret": d["cont_ret"].mean(),
    }
    p(f"Big ES days — ES 5M RTH daily, n={len(d)} days (2010-2026)\n")
    p(f"BASE RATE (all days): same_close={base['same_close']:.3f}  "
      f"cont_close={base['cont_close']:.3f}  extend_extreme={base['extend_extreme']:.3f}  "
      f"cont_ret={base['cont_ret']:+.2f} pts\n")

    rows = []
    for K in [2.0, 2.5, 3.0, 3.3]:
        big = d[d["rng_x"] >= K]
        rows.append({
            "K": K, "n": len(big),
            "same_close": round(big["same_close"].mean(), 3),
            "cont_close": round(big["cont_close"].mean(), 3),
            "extend_extreme": round(big["extend_extreme"].mean(), 3),
            "cont_ret_pts": round(big["cont_ret"].mean(), 2),
        })
    res = pd.DataFrame(rows)
    p("Big-day buckets (range >= K x ABR8):")
    p(res.to_string(index=False))
    p(f"\nTim's claim: ~85% same-direction 2nd leg next day at ~3.3x (n=14).")

    # split by direction of the big day (up-big vs down-big) at K=2.5
    p("\nAt K=2.5, split by big-day direction:")
    b25 = d[(d["rng_x"] >= 2.5) & (d["dir"] != 0)].copy()
    b25["dir_lbl"] = np.where(b25["dir"] > 0, "big-UP day", "big-DOWN day")
    sp = b25.groupby("dir_lbl").agg(
        n=("cont_close", "size"), cont_close=("cont_close", "mean"),
        extend_extreme=("extend_extreme", "mean"), cont_ret=("cont_ret", "mean"),
    ).round(3)
    p(sp.to_string())

    d.reset_index().to_csv(OUTDIR / f"big_es_days_{RUN}.csv", index=False)

    # chart
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.2))
    x = res["K"].astype(str)
    for col, c in [("same_close", "#2b5fa8"), ("cont_close", "#e08a2b"), ("extend_extreme", "#2b7a3f")]:
        ax[0].plot(x, res[col], "o-", label=col, color=c)
        ax[0].axhline(base[col], ls="--", lw=1, color=c, alpha=0.6)
    ax[0].set_xlabel("K (range / ABR8)"); ax[0].set_ylabel("P(next-day continuation)")
    ax[0].set_title("Big-day follow-through vs K (dashed = base)")
    ax[0].legend(fontsize=8); ax[0].grid(alpha=0.3); ax[0].set_ylim(0.3, 0.8)
    ax[1].bar([f"K={k}\nn={n}" for k, n in zip(res["K"], res["n"])], res["cont_close"], color="#2b5fa8")
    ax[1].axhline(base["cont_close"], ls="--", color="k", label=f"base {base['cont_close']:.2f}")
    ax[1].axhline(0.85, ls=":", color="red", label="Tim 0.85")
    ax[1].set_ylabel("P(next close continues)"); ax[1].set_title("Continuation vs Tim's 85%")
    ax[1].legend(fontsize=8); ax[1].grid(axis="y", alpha=0.3)
    fig.suptitle("LegLab — Big ES days, what follows (ES 5M RTH, 2010-2026)")
    fig.tight_layout()
    png = OUTDIR / f"big_es_days_{RUN}.png"
    fig.savefig(png, dpi=130)
    p(f"\ncsv -> {OUTDIR / f'big_es_days_{RUN}.csv'}")
    p(f"png -> {png}")


if __name__ == "__main__":
    main()
