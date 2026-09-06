"""
Stress-test #6 — is the BOS-persistence (48% vs 14%) REAL edge, or just the
mechanical fact that after a BOS you sit near the extreme so a new extreme is
cheap, while after an inside leg the old extreme is far away?

Control = GAP-TO-BEAT: for each same-direction leg k+1, how far (in ADR) it must
travel from its start (the pullback pivot) to exceed the running extreme:
   up:   gap = running_extreme_high - start_price_of_leg_{k+1}
   down: gap = start_price_of_leg_{k+1} - running_extreme_low
Then WITHIN gap-to-beat bins, compare P(next leg BOS) for prior-BOS vs prior-inside.
If the gap closes the difference -> mechanical (no edge). If a spread survives at
equal gap-to-beat -> real regime persistence.

Also reports: does prior-BOS systematically mean a smaller gap (the mechanism)?

Reads via leg_engine. Writes dated CSV + summary + chart.
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
    rows = []
    for date, g, thr in iter_days(df, daily):
        o = g["Open"].to_numpy(); h = g["High"].to_numpy()
        l = g["Low"].to_numpy(); t = g["DateTime"].to_numpy()
        adr = float(daily.loc[date, "adr"])
        if adr <= 0:
            continue
        legs = [lg for lg in legs_for_day(o, h, l, t, thr) if lg["closed"]]
        for d in (1, -1):
            seq = [lg for lg in legs if lg["dir"] == d]
            if len(seq) < 2:
                continue
            ext = seq[0]["p1"]           # running extreme after leg 0
            prior_bos = 1                # leg 0 makes the first extreme -> counts as BOS
            for k in range(1, len(seq)):
                lg = seq[k]
                start = lg["p0"]         # pullback pivot where this leg begins
                if d == 1:
                    gap = ext - start
                    bos = int(lg["p1"] > ext)
                    ext = max(ext, lg["p1"])
                else:
                    gap = start - ext
                    bos = int(lg["p1"] < ext)
                    ext = min(ext, lg["p1"])
                rows.append({
                    "date": date, "dir": d, "prior_bos": prior_bos,
                    "gap_adr": gap / adr, "next_bos": bos,
                    "size_adr": lg["size"] / adr,
                })
                prior_bos = bos

    R = pd.DataFrame(rows)
    R = R[R["gap_adr"] >= 0]   # gap can be tiny; drop rare negatives from rounding
    R.to_csv(OUTDIR / f"leg_structure_stresstest_{RUN}.csv", index=False)

    def p(s=""):
        print(s)

    p(f"Stress-test #6 — BOS persistence vs gap-to-beat.  transitions={len(R)}\n")

    # 0) replicate the raw effect
    raw = R.groupby("prior_bos")["next_bos"].agg(n="size", p="mean").round(3)
    raw.index = ["prior INSIDE", "prior BOS"]
    p("Raw (uncontrolled) P(next BOS):")
    p(raw.to_string())

    # 1) the mechanism: is gap smaller after BOS?
    gm = R.groupby("prior_bos")["gap_adr"].agg(n="size", mean="mean", median="median").round(3)
    gm.index = ["prior INSIDE", "prior BOS"]
    p("\nMechanism check — gap-to-beat (ADR) by prior state:")
    p(gm.to_string())

    # 2) THE TEST: within gap-to-beat quintiles, compare prior-BOS vs prior-inside
    R["gap_q"] = pd.qcut(R["gap_adr"], 5, labels=False, duplicates="drop")
    piv = R.pivot_table(index="gap_q", columns="prior_bos", values="next_bos", aggfunc="mean")
    cnt = R.pivot_table(index="gap_q", columns="prior_bos", values="next_bos", aggfunc="size")
    band = R.groupby("gap_q")["gap_adr"].agg(["min", "max"]).round(3)
    tbl = pd.DataFrame({
        "gap_lo": band["min"], "gap_hi": band["max"],
        "n_inside": cnt.get(0), "n_bos": cnt.get(1),
        "P_next|inside": piv.get(0).round(3), "P_next|bos": piv.get(1).round(3),
    })
    tbl["diff"] = (tbl["P_next|bos"] - tbl["P_next|inside"]).round(3)
    p("\nCONTROLLED — P(next BOS) within gap-to-beat quintiles:")
    p(tbl.to_string())
    # weighted mean surviving difference
    w = tbl[["n_inside", "n_bos"]].min(axis=1)
    surv = (tbl["diff"] * w).sum() / w.sum()
    p(f"\nGap-controlled mean (BOS - inside) P(next BOS) = {surv:+.3f}")
    p("  ~0 => mechanical (proximity to extreme explains it, no edge)")
    p("  >0 => real regime persistence beyond positioning")

    # chart
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.2))
    x = tbl.index.astype(int)
    ax[0].plot(x, tbl["P_next|bos"], "o-", color="#2b7a3f", label="prior BOS")
    ax[0].plot(x, tbl["P_next|inside"], "o-", color="#c08a2b", label="prior inside")
    ax[0].set_xlabel("gap-to-beat quintile (low→high)"); ax[0].set_ylabel("P(next leg BOS)")
    ax[0].set_title("Controlled: does the spread survive?"); ax[0].legend(); ax[0].grid(alpha=0.3)
    ax[1].bar(["prior inside", "prior BOS"], raw["p"], color=["#c08a2b", "#2b7a3f"])
    ax[1].set_title(f"Raw effect (surviving diff after control = {surv:+.3f})")
    ax[1].set_ylabel("P(next BOS)"); ax[1].grid(axis="y", alpha=0.3)
    fig.suptitle("LegLab #6 stress-test — mechanical vs real (ES 5M RTH)")
    fig.tight_layout()
    png = OUTDIR / f"leg_structure_stresstest_{RUN}.png"
    fig.savefig(png, dpi=130)
    p(f"\ncsv -> {OUTDIR / f'leg_structure_stresstest_{RUN}.csv'}")
    p(f"png -> {png}")


if __name__ == "__main__":
    main()
