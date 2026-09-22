"""
Idea #1 — does EARLY leg count predict the rest of the day?
(Tim's "actual tradeable version" of leg counting.)

For each RTH day, count legs CLOSED within the first 60 min (12 bars) and first
90 min (18 bars = Tim's 18-bar range). Then relate that early count to rest-of-day
behaviour:
  efficiency  = |close-open| / day_range        (1 = clean trend, 0 = pure chop)
  close_loc   = (close-low)/day_range            (0 = close on low, 1 = on high)
  |loc-0.5|   = how far the close finished from mid (trend-ish vs balanced)
  expansion   = day_range / early_range          (how much range came AFTER open)
  rest_range  = high/low of bars after the cutoff (points, and /ADR)
  continue    = did the post-cutoff move continue the pre-cutoff direction?

Hypothesis: FEW early legs -> trend forming (join); MANY early legs -> rotation (fade).

Reads via leg_engine. Writes dated CSV + a bucketed chart.
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
C60, C90 = 12, 18   # bar cutoffs (5-min bars from the 08:30 open)


def main():
    df = load_bars()
    daily = daily_table(df)
    rows = []
    for date, g, thr in iter_days(df, daily):
        o = g["Open"].to_numpy(); h = g["High"].to_numpy()
        l = g["Low"].to_numpy(); c = g["Close"].to_numpy(); t = g["DateTime"].to_numpy()
        n = len(g)
        if n < C90 + 5:
            continue
        legs = [lg for lg in legs_for_day(o, h, l, t, thr) if lg["closed"]]
        e60 = sum(1 for lg in legs if lg["i1"] < C60)
        e90 = sum(1 for lg in legs if lg["i1"] < C90)
        full = len(legs)

        d_open, d_close = o[0], c[-1]
        d_high, d_low = h.max(), l.min()
        d_range = d_high - d_low
        if d_range <= 0:
            continue
        eff = abs(d_close - d_open) / d_range
        close_loc = (d_close - d_low) / d_range
        early_hi, early_lo = h[:C90].max(), l[:C90].min()
        early_range = early_hi - early_lo
        rest_hi, rest_lo = h[C90:].max(), l[C90:].min()
        rest_range = rest_hi - rest_lo
        px_cut = c[C90 - 1]
        morning_dir = np.sign(px_cut - d_open)
        after_dir = np.sign(d_close - px_cut)
        cont = int(morning_dir != 0 and morning_dir == after_dir)
        adr = float(daily.loc[date, "adr"])

        rows.append({
            "date": date, "adr": round(adr, 2), "thr": round(thr, 2),
            "early_legs_60": e60, "early_legs_90": e90, "full_legs": full,
            "eff": round(eff, 4), "close_loc": round(close_loc, 4),
            "loc_from_mid": round(abs(close_loc - 0.5), 4),
            "early_range": round(early_range, 2), "rest_range": round(rest_range, 2),
            "expansion": round(d_range / early_range, 3) if early_range > 0 else np.nan,
            "rest_range_adr": round(rest_range / adr, 3) if adr > 0 else np.nan,
            "continue": cont, "trend_day": int(eff >= 0.5),
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUTDIR / f"leg_early_classifier_{RUN}.csv", index=False)

    def p(s=""):
        print(s)

    p(f"Early-leg classifier — ES 5M RTH, n={len(out)} days")
    p(f"cutoffs: 60min={C60} bars, 90min={C90} bars\n")

    # correlations (Spearman — monotonic)
    p("Spearman corr vs early_legs_90:")
    for col in ["eff", "loc_from_mid", "expansion", "rest_range_adr", "full_legs", "continue"]:
        r = out["early_legs_90"].corr(out[col], method="spearman")
        p(f"  {col:>14}: {r:+.3f}")
    p("")

    # bucket by early_legs_90 into Few / Med / Many (terciles)
    out["bucket"] = pd.qcut(out["early_legs_90"], 3, labels=["Few", "Med", "Many"])
    agg = out.groupby("bucket", observed=True).agg(
        n=("eff", "size"),
        early90_range=("early_legs_90", lambda s: f"{s.min()}-{s.max()}"),
        eff=("eff", "mean"),
        trend_day_pct=("trend_day", "mean"),
        loc_from_mid=("loc_from_mid", "mean"),
        expansion=("expansion", "mean"),
        rest_range_adr=("rest_range_adr", "mean"),
        full_legs=("full_legs", "mean"),
        continue_pct=("continue", "mean"),
    ).round(3)
    p("By early-leg bucket (first 90 min):")
    p(agg.to_string())

    # finer: mean efficiency + trend-day% by exact early_legs_90
    fine = out.groupby("early_legs_90").agg(
        n=("eff", "size"), eff=("eff", "mean"),
        trend_pct=("trend_day", "mean"), full_legs=("full_legs", "mean"),
    ).round(3)
    fine = fine[fine["n"] >= 30]
    p("\nBy exact early_legs_90 (n>=30):")
    p(fine.to_string())

    # redundancy check: is early LEG COUNT better than early RANGE at
    # predicting rest-of-day range? (partial corr controlling for early_range)
    out["early_range_adr"] = out["early_range"] / out["adr"]
    sub = out[["early_legs_90", "early_range_adr", "rest_range_adr"]].dropna()
    r_legs = sub["early_legs_90"].corr(sub["rest_range_adr"], method="spearman")
    r_rng = sub["early_range_adr"].corr(sub["rest_range_adr"], method="spearman")

    def partial(a, b, ctrl, d):
        # residualize a and b on ctrl (rank-based), then correlate residuals
        rk = d[[a, b, ctrl]].rank()
        ra = rk[a] - np.polyval(np.polyfit(rk[ctrl], rk[a], 1), rk[ctrl])
        rb = rk[b] - np.polyval(np.polyfit(rk[ctrl], rk[b], 1), rk[ctrl])
        return np.corrcoef(ra, rb)[0, 1]

    pr = partial("early_legs_90", "rest_range_adr", "early_range_adr", sub)
    p("\nRedundancy — predicting rest_range/ADR:")
    p(f"  early_legs_90 (raw)                 : {r_legs:+.3f}")
    p(f"  early_range/ADR (raw)               : {r_rng:+.3f}")
    p(f"  early_legs_90 | control early_range : {pr:+.3f}  (near 0 => legs add nothing over range)")

    # chart
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.2))
    xf = fine.index.astype(int)
    ax[0].bar(xf, fine["trend_pct"], color="#2b5fa8")
    ax[0].set_xlabel("legs closed in first 90 min"); ax[0].set_ylabel("P(trend day: eff>=0.5)")
    ax[0].set_title("Fewer early legs -> more trend days")
    ax[0].grid(axis="y", alpha=0.3)
    ax[1].bar(xf, fine["eff"], color="#e08a2b")
    ax[1].set_xlabel("legs closed in first 90 min"); ax[1].set_ylabel("mean day efficiency |net|/range")
    ax[1].set_title("Early legs vs day efficiency")
    ax[1].grid(axis="y", alpha=0.3)
    fig.suptitle("LegLab #1 — early leg count predicts rest-of-day (ES 5M RTH, 2010-2026)")
    fig.tight_layout()
    png = OUTDIR / f"leg_early_classifier_{RUN}.png"
    fig.savefig(png, dpi=130)
    p(f"\ncsv -> {OUTDIR / f'leg_early_classifier_{RUN}.csv'}")
    p(f"png -> {png}")


if __name__ == "__main__":
    main()
