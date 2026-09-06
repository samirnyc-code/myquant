"""
Idea #4/#5 — leg GEOMETRY: how big are legs, how long, and how do they relate
through the day?  Uses the validated leg_engine (per-leg records).

Questions:
  A) Leg size (pts and /ADR) and duration (bars) by WITHIN-DAY INDEX (1st,2nd,...).
     -> is the first leg the biggest? do legs compress later?
  B) Leg size (/ADR) by TIME OF DAY (30-min buckets from the 08:30 open).
     -> open drive vs lunch compression vs close expansion?
  C) Leg-to-leg RATIO size_n / size_{n-1}: expansion vs exhaustion; does a big
     leg tend to be followed by a bigger or smaller one? (mean-reversion in size?)
  D) Does a big FIRST leg predict a big / trending day?

Writes dated CSV (per-leg table) + summary + charts.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from leg_engine import load_bars, daily_table, legs_for_day, iter_days

OUTDIR = Path(__file__).resolve().parents[2] / "leglab" / "outputs"
RUN = "20260906"


def main():
    df = load_bars()
    daily = daily_table(df)
    recs = []
    day_recs = []
    for date, g, thr in iter_days(df, daily):
        o = g["Open"].to_numpy(); h = g["High"].to_numpy()
        l = g["Low"].to_numpy(); c = g["Close"].to_numpy(); t = g["DateTime"].to_numpy()
        adr = float(daily.loc[date, "adr"])
        legs = [lg for lg in legs_for_day(o, h, l, t, thr) if lg["closed"]]
        if len(legs) < 3 or adr <= 0:
            continue
        d_open, d_close = o[0], c[-1]
        d_high, d_low = h.max(), l.min()
        d_range = d_high - d_low
        eff = abs(d_close - d_open) / d_range if d_range > 0 else np.nan
        for k, lg in enumerate(legs):
            start_min = int((pd.Timestamp(lg["t0"]) - pd.Timestamp(lg["t0"]).normalize()
                             - pd.Timedelta(hours=8, minutes=30)).total_seconds() // 60)
            recs.append({
                "date": date, "idx": k + 1, "n_legs": len(legs), "dir": lg["dir"],
                "size": lg["size"], "size_adr": lg["size"] / adr, "bars": lg["bars"],
                "start_bar": lg["i0"], "start_min": start_min,
            })
        first = legs[0]
        day_recs.append({
            "date": date, "n_legs": len(legs), "adr": adr,
            "first_size_adr": first["size"] / adr, "first_bars": first["bars"],
            "day_range_adr": d_range / adr, "eff": eff,
        })

    L = pd.DataFrame(recs)
    D = pd.DataFrame(day_recs)
    L.to_csv(OUTDIR / f"leg_geometry_legs_{RUN}.csv", index=False)

    def p(s=""):
        print(s)

    p(f"Leg geometry — ES 5M RTH.  legs={len(L)}  days={len(D)}\n")

    # A) by within-day index
    p("A) By within-day leg index (size in ADR units, duration in bars):")
    a = L[L["idx"] <= 12].groupby("idx").agg(
        n=("size_adr", "size"), size_adr=("size_adr", "mean"),
        size_adr_med=("size_adr", "median"), bars=("bars", "mean"),
    ).round(3)
    p(a.to_string())

    # B) by time of day (30-min buckets)
    L["tod"] = (L["start_min"] // 30) * 30
    p("\nB) By time-of-day bucket (minutes after 08:30 open):")
    b = L[(L["tod"] >= 0) & (L["tod"] <= 390)].groupby("tod").agg(
        n=("size_adr", "size"), size_adr=("size_adr", "mean"), bars=("bars", "mean"),
    ).round(3)
    b.index = [f"+{m}min" for m in b.index]
    p(b.to_string())

    # C) leg-to-leg ratio.  Exclude idx==1 as a denominator: leg 1 is the
    # open->first-pivot STUB (anchored at the open price, often ~0 size), not a
    # true pivot-to-pivot leg. Guard tiny denominators against inf.
    L2 = L.sort_values(["date", "idx"]).copy()
    L2["prev_size_adr"] = L2.groupby("date")["size_adr"].shift(1)
    L2["prev_idx"] = L2.groupby("date")["idx"].shift(1)
    L2 = L2[(L2["prev_idx"] >= 2) & (L2["prev_size_adr"] > 0.02)]
    L2["ratio"] = L2["size_adr"] / L2["prev_size_adr"]
    r = L2["ratio"].dropna()
    p(f"\nC) Leg-to-leg size ratio (size_n / size_(n-1)):")
    p(f"   median={r.median():.3f}  mean={r.mean():.3f}  "
      f"P(next larger)={(r>1).mean():.3f}")
    # conditional: after a BIG leg (top tercile) vs SMALL leg (bottom tercile)
    L2["prev_tercile"] = L2.groupby("date")["prev_size_adr"].transform(
        lambda s: pd.qcut(s.rank(method="first"), 3, labels=["small", "mid", "big"])
        if s.notna().sum() >= 3 else pd.Series(index=s.index, dtype="object"))
    ct = L2.dropna(subset=["ratio", "prev_tercile"]).groupby("prev_tercile", observed=True)["ratio"].agg(
        n="size", median="median", p_next_larger=lambda s: (s > 1).mean()).round(3)
    p("   next-leg ratio by previous-leg size tercile:")
    p(ct.to_string())

    # D) big first leg -> big/trend day?
    p("\nD) First-leg size vs day outcome (first_size_adr terciles):")
    D2 = D.copy()
    D2["first_q"] = pd.qcut(D2["first_size_adr"], 3, labels=["small", "mid", "big"])
    d = D2.groupby("first_q", observed=True).agg(
        n=("eff", "size"), first_size_adr=("first_size_adr", "mean"),
        day_range_adr=("day_range_adr", "mean"), n_legs=("n_legs", "mean"),
        eff=("eff", "mean"),
    ).round(3)
    p(d.to_string())
    p(f"   corr(first_size_adr, day_range_adr) Spearman = "
      f"{D['first_size_adr'].corr(D['day_range_adr'], method='spearman'):+.3f}")
    p(f"   corr(first_size_adr, eff)          Spearman = "
      f"{D['first_size_adr'].corr(D['eff'], method='spearman'):+.3f}")

    # charts
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.8))
    ax[0].bar(a.index.astype(int), a["size_adr"], color="#2b5fa8")
    ax[0].set_xlabel("within-day leg index"); ax[0].set_ylabel("mean leg size / ADR")
    ax[0].set_title("A) leg size by index")
    ax[0].grid(axis="y", alpha=0.3)
    xb = list(range(len(b)))
    ax[1].bar(xb, b["size_adr"], color="#e08a2b")
    ax[1].set_xticks(xb); ax[1].set_xticklabels([s.replace("min", "") for s in b.index], rotation=45, fontsize=8)
    ax[1].set_xlabel("min after open"); ax[1].set_ylabel("mean leg size / ADR")
    ax[1].set_title("B) leg size by time of day")
    ax[1].grid(axis="y", alpha=0.3)
    ax[2].bar(["small", "mid", "big"], ct["p_next_larger"], color="#4a8c5f")
    ax[2].axhline(0.5, color="k", ls="--", lw=1)
    ax[2].set_ylabel("P(next leg larger)"); ax[2].set_title("C) size mean-reversion")
    ax[2].grid(axis="y", alpha=0.3)
    fig.suptitle("LegLab #4/#5 — leg geometry (ES 5M RTH, 2010-2026)")
    fig.tight_layout()
    png = OUTDIR / f"leg_geometry_{RUN}.png"
    fig.savefig(png, dpi=130)
    p(f"\ncsv -> {OUTDIR / f'leg_geometry_legs_{RUN}.csv'}")
    p(f"png -> {png}")


if __name__ == "__main__":
    main()
