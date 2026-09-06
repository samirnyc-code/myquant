"""
Idea #3 — a real day-type taxonomy (Tim's unsolved problem).

Tim classifies days as trend / channel / range / spike-and-sideways but has "no
finished method". #1/#4 showed leg count measures VOLATILITY, not direction — so
the taxonomy is built from DIRECTIONAL structure, and leg count is used only to
VALIDATE it (his finding: trend days ~12 legs, balanced ~15-16).

Per RTH day:
  rls  = up_travel / (up_travel + down_travel)      up_travel=high-open, down=open-low
         (0.5 balanced, ->1 one-sided up, ->0 one-sided down)
  eff  = |close-open| / range                        (trend vs rotational)
  close_loc = (close-low)/range

Taxonomy (directional):
  Trend-Up   : eff>=0.55 and net>0
  Trend-Down : eff>=0.55 and net<0
  Channel    : 0.30<=eff<0.55        (directional but with pullbacks)
  Range      : eff<0.30              (rotational / balanced)

Then the payoff test Tim asked for: % of days per bucket, legs per bucket (validate),
and DOES today's type predict tomorrow (transition matrix + next-day continuation)?

Writes dated CSV + summary + charts.
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


def classify(eff, net):
    if eff >= 0.55:
        return "Trend-Up" if net > 0 else "Trend-Down"
    if eff >= 0.30:
        return "Channel"
    return "Range"


def main():
    df = load_bars()
    daily = daily_table(df)
    rows = []
    for date, g, thr in iter_days(df, daily):
        o = g["Open"].to_numpy(); h = g["High"].to_numpy()
        l = g["Low"].to_numpy(); c = g["Close"].to_numpy(); t = g["DateTime"].to_numpy()
        adr = float(daily.loc[date, "adr"])
        if adr <= 0:
            continue
        legs = sum(1 for lg in legs_for_day(o, h, l, t, thr) if lg["closed"])
        d_open, d_close = o[0], c[-1]
        d_high, d_low = h.max(), l.min()
        rng = d_high - d_low
        if rng <= 0:
            continue
        up_t, dn_t = d_high - d_open, d_open - d_low
        rls = up_t / (up_t + dn_t) if (up_t + dn_t) > 0 else 0.5
        net = d_close - d_open
        eff = abs(net) / rng
        rows.append({
            "date": date, "net": net, "range_adr": rng / adr, "eff": round(eff, 4),
            "rls": round(rls, 4), "close_loc": round((d_close - d_low) / rng, 4),
            "legs": legs, "type": classify(eff, net),
            "ret": net,  # points; next-day continuation uses sign
        })

    D = pd.DataFrame(rows).reset_index(drop=True)
    D["next_type"] = D["type"].shift(-1)
    D["next_ret"] = D["ret"].shift(-1)
    D.to_csv(OUTDIR / f"leg_day_typing_{RUN}.csv", index=False)

    def p(s=""):
        print(s)

    order = ["Trend-Up", "Channel", "Range", "Trend-Down"]
    p(f"Day-type taxonomy — ES 5M RTH, n={len(D)} days\n")

    # frequency + validation (legs should be fewer on trend days)
    freq = D.groupby("type").agg(
        n=("eff", "size"), pct=("eff", lambda s: 100 * len(s) / len(D)),
        legs=("legs", "mean"), range_adr=("range_adr", "mean"),
        rls=("rls", "mean"), close_loc=("close_loc", "mean"), eff=("eff", "mean"),
    ).reindex(order).round(2)
    p("Frequency + validation (Tim: trend ~12 legs, balanced ~15-16):")
    p(freq.to_string())
    trend_legs = D[D["type"].isin(["Trend-Up", "Trend-Down"])]["legs"].mean()
    range_legs = D[D["type"] == "Range"]["legs"].mean()
    p(f"\n  trend-day legs={trend_legs:.1f}  range-day legs={range_legs:.1f}  "
      f"(validates Tim's inverse leg<->trend relationship: {'YES' if trend_legs < range_legs else 'NO'})")

    # predictiveness: transition matrix P(next | today)
    p("\nTransition matrix  P(tomorrow's type | today's type)  [%]:")
    tm = pd.crosstab(D["type"], D["next_type"], normalize="index").reindex(
        index=order, columns=order) * 100
    p(tm.round(1).to_string())
    base = (D["type"].value_counts(normalize=True) * 100).reindex(order).round(1)
    p("\n  base rate of each type [%]: " + ", ".join(f"{k}={v}" for k, v in base.items()))

    # next-day continuation for trend days (does a trend day lead to more upside/downside?)
    p("\nNext-day mean return (points) by today's type:")
    nd = D.groupby("type").agg(
        n=("next_ret", "size"), next_ret_mean=("next_ret", "mean"),
        next_up_pct=("next_ret", lambda s: 100 * (s > 0).mean()),
    ).reindex(order).round(2)
    p(nd.to_string())

    # volatility clustering: does a big-range day predict a big-range tomorrow?
    D["big_range"] = (D["range_adr"] > D["range_adr"].median()).astype(int)
    D["next_big"] = D["big_range"].shift(-1)
    pbig = D.dropna(subset=["next_big"])
    p_big_given_big = 100 * pbig[pbig["big_range"] == 1]["next_big"].mean()
    p_big_given_small = 100 * pbig[pbig["big_range"] == 0]["next_big"].mean()
    p(f"\nVolatility clustering: P(big-range tomorrow | big today)={p_big_given_big:.1f}%  "
      f"| small today={p_big_given_small:.1f}%  (base 50%)")

    # charts
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.2))
    ax[0].bar(order, freq["pct"], color=["#2b7a3f", "#5a8fc0", "#c08a2b", "#a83b3b"])
    for i, (pc, lg) in enumerate(zip(freq["pct"], freq["legs"])):
        ax[0].text(i, pc + 0.5, f"{pc:.0f}%\n{lg:.0f} legs", ha="center", fontsize=9)
    ax[0].set_ylabel("% of days"); ax[0].set_title("Day-type frequency + legs")
    ax[0].set_ylim(0, max(freq["pct"]) * 1.25)
    im = ax[1].imshow(tm.fillna(0).values, cmap="Blues", vmin=0, vmax=60)
    ax[1].set_xticks(range(4)); ax[1].set_xticklabels(order, rotation=45, ha="right", fontsize=8)
    ax[1].set_yticks(range(4)); ax[1].set_yticklabels(order, fontsize=8)
    for i in range(4):
        for j in range(4):
            v = tm.values[i, j]
            if np.isfinite(v):
                ax[1].text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=9,
                           color="white" if v > 35 else "black")
    ax[1].set_xlabel("tomorrow"); ax[1].set_ylabel("today")
    ax[1].set_title("P(tomorrow | today) %")
    fig.suptitle("LegLab #3 — day-type taxonomy (ES 5M RTH, 2010-2026)")
    fig.tight_layout()
    png = OUTDIR / f"leg_day_typing_{RUN}.png"
    fig.savefig(png, dpi=130)
    p(f"\ncsv -> {OUTDIR / f'leg_day_typing_{RUN}.csv'}")
    p(f"png -> {png}")


if __name__ == "__main__":
    main()
