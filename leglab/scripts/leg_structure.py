"""
Idea #6 — breakout-of-structure (BOS) vs inside legs. The test of whether leg
STRUCTURE (not count/size) carries DIRECTIONAL edge — count/size/day-type all
came up null on direction.

For each RTH day, walk the closed legs in order. A leg ends at a new pivot (an
up leg ends at a swing HIGH, a down leg ends at a swing LOW). Tag each leg by
whether its pivot BREAKS structure:
  Up leg   -> BOS if its high > the last confirmed swing HIGH (higher-high);
              else INSIDE (lower-high, stays under prior swing).
  Down leg -> BOS if its low  < the last confirmed swing LOW  (lower-low);
              else INSIDE (higher-low).
This is the classic HH/HL/LH/LL swing read built from our validated pivots.

Questions:
  1. Base rates: what % of legs are BOS vs inside? by direction?
  2. CONTINUATION edge: after a BOS leg, does the NEXT leg tend to extend the
     same direction (trend) or reverse? vs after an inside leg?  -> the tradeable
     bit: does "structure broke" predict the next leg?
  3. Consecutive INSIDE legs (balance) -> does the next leg break out? P(next BOS
     | k consecutive inside).  Balance -> breakout detector.
  4. Does a leg breaking structure travel FURTHER than an inside leg? (size edge)

All measured on legs, then translated to next-leg direction/size (no lookahead:
each leg is classified using only pivots up to and including itself; the outcome
is the leg that follows).

Writes dated CSV (per-leg with structure tags) + summary + chart.
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


def tag_day(legs, adr):
    """Return list of per-leg dicts with structure tags + next-leg outcome."""
    out = []
    last_swing_hi = -np.inf
    last_swing_lo = np.inf
    inside_run = 0
    tags = []
    for lg in legs:
        d = lg["dir"]
        pivot = lg["p1"]
        if d == 1:      # up leg ends at a swing HIGH
            bos = pivot > last_swing_hi
            last_swing_hi = max(last_swing_hi, pivot)
        else:            # down leg ends at a swing LOW
            bos = pivot < last_swing_lo
            last_swing_lo = min(last_swing_lo, pivot)
        inside_run = 0 if bos else inside_run + 1
        tags.append({"dir": d, "bos": int(bos), "size_adr": lg["size"] / adr,
                     "inside_run_before": (inside_run - 1) if not bos else 0})
    # attach next-leg outcome (direction continuation + next size)
    for i in range(len(tags)):
        cur = tags[i]
        nxt = tags[i + 1] if i + 1 < len(tags) else None
        cur["next_same_dir"] = np.nan
        cur["next_bos"] = np.nan
        cur["next_size_adr"] = np.nan
        if nxt is not None:
            # "same direction" = next leg extends current leg's direction.
            # legs alternate by construction, so continuation is measured as:
            # after an UP BOS, does price make a further HIGHER pivot within 2 legs?
            cur["next_same_dir"] = int(np.sign(nxt["dir"]) == np.sign(cur["dir"]))
            cur["next_bos"] = nxt["bos"]
            cur["next_size_adr"] = nxt["size_adr"]
        out.append(cur)
    return out


def main():
    df = load_bars()
    daily = daily_table(df)
    recs = []
    # For the real continuation test we need "does the trend extend?" Because legs
    # strictly alternate, we instead measure: after an up-leg that made a
    # HIGHER-HIGH (BOS up), is the FOLLOWING up-leg ALSO a higher-high? i.e. do
    # breakouts beget breakouts (trend) vs inside legs beget inside (balance)?
    for date, g, thr in iter_days(df, daily):
        o = g["Open"].to_numpy(); h = g["High"].to_numpy()
        l = g["Low"].to_numpy(); t = g["DateTime"].to_numpy()
        adr = float(daily.loc[date, "adr"])
        if adr <= 0:
            continue
        legs = [lg for lg in legs_for_day(o, h, l, t, thr) if lg["closed"]]
        if len(legs) < 4:
            continue
        # per-direction BOS chains: look at up-legs sequence and down-legs sequence
        for d in (1, -1):
            seq = [lg for lg in legs if lg["dir"] == d]
            ext = -np.inf if d == 1 else np.inf
            prev_bos = None
            run_inside = 0
            for k, lg in enumerate(seq):
                piv = lg["p1"]
                bos = (piv > ext) if d == 1 else (piv < ext)
                ext = max(ext, piv) if d == 1 else min(ext, piv)
                nxt_bos = None
                if k + 1 < len(seq):
                    npiv = seq[k + 1]["p1"]
                    nxt_bos = int((npiv > ext) if d == 1 else (npiv < ext))
                recs.append({
                    "date": date, "dir": d, "bos": int(bos),
                    "size_adr": lg["size"] / adr,
                    "inside_run_before": run_inside,
                    "next_bos": nxt_bos,
                })
                run_inside = 0 if bos else run_inside + 1

    R = pd.DataFrame(recs)
    R.to_csv(OUTDIR / f"leg_structure_{RUN}.csv", index=False)

    def p(s=""):
        print(s)

    p(f"Leg structure (BOS vs inside) — ES 5M RTH.  legs analysed={len(R)}\n")

    # 1) base rates
    p("1) BOS base rate by direction:")
    br = R.groupby("dir")["bos"].agg(n="size", bos_pct="mean").round(3)
    br.index = ["down", "up"]
    p(br.to_string())
    p(f"   overall BOS rate = {R['bos'].mean():.3f}")

    # 2) continuation: does a BOS leg beget another BOS (same-dir extension)?
    p("\n2) P(next same-dir leg is ALSO BOS)  — breakouts beget breakouts?")
    cont = R.dropna(subset=["next_bos"]).groupby("bos")["next_bos"].agg(
        n="size", p_next_bos="mean").round(3)
    cont.index = ["after INSIDE", "after BOS"]
    p(cont.to_string())
    base_next = R.dropna(subset=["next_bos"])["next_bos"].mean()
    p(f"   base P(next BOS) = {base_next:.3f}")

    # 3) balance -> breakout: P(next BOS | k consecutive inside legs)
    p("\n3) P(next same-dir leg is BOS | k consecutive INSIDE legs so far):")
    bb = R.dropna(subset=["next_bos"])
    tab = bb.groupby("inside_run_before")["next_bos"].agg(n="size", p_next_bos="mean").round(3)
    p(tab[tab["n"] >= 50].to_string())

    # 4) size: do BOS legs travel further?
    p("\n4) leg size (ADR) by BOS vs inside:")
    sz = R.groupby("bos")["size_adr"].agg(n="size", mean="mean", median="median").round(3)
    sz.index = ["inside", "BOS"]
    p(sz.to_string())

    # chart
    fig, ax = plt.subplots(1, 3, figsize=(16, 4.8))
    ax[0].bar(["after INSIDE", "after BOS"], cont["p_next_bos"], color=["#c08a2b", "#2b7a3f"])
    ax[0].axhline(base_next, color="k", ls="--", lw=1, label=f"base {base_next:.2f}")
    ax[0].set_ylabel("P(next leg BOS)"); ax[0].set_title("2) breakouts beget breakouts?")
    ax[0].legend(); ax[0].grid(axis="y", alpha=0.3)
    t3 = tab[tab["n"] >= 50]
    ax[1].bar(t3.index.astype(int), t3["p_next_bos"], color="#2b5fa8")
    ax[1].axhline(base_next, color="k", ls="--", lw=1)
    ax[1].set_xlabel("consecutive inside legs"); ax[1].set_ylabel("P(next BOS)")
    ax[1].set_title("3) balance -> breakout?"); ax[1].grid(axis="y", alpha=0.3)
    ax[2].bar(["inside", "BOS"], sz["mean"], color=["#c08a2b", "#2b7a3f"])
    ax[2].set_ylabel("mean leg size / ADR"); ax[2].set_title("4) BOS legs travel further?")
    ax[2].grid(axis="y", alpha=0.3)
    fig.suptitle("LegLab #6 — leg structure BOS vs inside (ES 5M RTH, 2010-2026)")
    fig.tight_layout()
    png = OUTDIR / f"leg_structure_{RUN}.png"
    fig.savefig(png, dpi=130)
    p(f"\ncsv -> {OUTDIR / f'leg_structure_{RUN}.csv'}")
    p(f"png -> {png}")


if __name__ == "__main__":
    main()
