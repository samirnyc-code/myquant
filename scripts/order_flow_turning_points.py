"""order_flow_turning_points.py — scan every ES L1 day on disk, build Flex Renko bricks
(16-8-4, same convention as the NT8 FlexRenkoBarsType port / bid_ask_volume_ratio_renko.py),
compute per-brick Ask/Bid volume, detect swing highs/lows, and flag three order-flow
patterns at each swing. Then FORWARD-CHECKS whether price actually reversed, so this
produces a real hit-rate, not just annotated pictures.

  DIVERGENCE  — price makes a new extreme (higher high / lower low vs the prior same-type
                swing) but the leg's net Delta (sum of AskVol-BidVol over the bricks since
                the prior opposite-type swing) is SMALLER than the prior same-type leg's
                Delta -- momentum not confirming price.
  ABSORPTION  — the pivot brick's total volume is >= `--abs-vol-mult` x the trailing
                median brick volume, while its own body is <= `--abs-body-mult` x the
                trailing median body -- heavy effort, little net result.
  REJECTION   — the pivot brick's true wick (flex_renko's wlo/whi, beyond the box body) is
                >= `--rej-wick-mult` x its own body on the side of the extreme.

FORWARD CHECK: within `--horizon` bricks after the pivot, did price move >= `--confirm-pts`
points in the REVERSAL direction before moving that far in the continuation direction
(first-touch)? That outcome is what "hit rate" means below -- it is NOT a backtest (no
entries, fills, or costs), it is a frequency check of whether the pattern precedes a real
directional turn more often than not.

RTH only, ES 16-8-4. Skips stub days automatically (prints which were skipped and why).

    python scripts/order_flow_turning_points.py
    python scripts/order_flow_turning_points.py --swing 3 --horizon 15 --confirm-pts 4
"""
from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
from bid_ask_volume_ratio_renko import load_day, rth_only, build, L1_DIR

OUT = L1_DIR / "_analysis"


def all_dates() -> list[str]:
    return sorted(set(os.path.basename(f).split("_l1_")[-1].split(".")[0]
                       for f in glob.glob(str(L1_DIR / "ES*_l1_*.*"))))


def swings(R: pd.DataFrame, k: int):
    """K-brick fractal: index i is a swing high if high[i] is the strict max over
    [i-k, i+k]; swing low mirrors on low. Returns two bool arrays."""
    n = len(R)
    hi, lo = R["high"].to_numpy(), R["low"].to_numpy()
    is_high = np.zeros(n, dtype=bool)
    is_low = np.zeros(n, dtype=bool)
    for i in range(k, n - k):
        window_h = hi[i - k:i + k + 1]
        window_l = lo[i - k:i + k + 1]
        if hi[i] == window_h.max() and (window_h == hi[i]).sum() == 1:
            is_high[i] = True
        if lo[i] == window_l.min() and (window_l == lo[i]).sum() == 1:
            is_low[i] = True
    return is_high, is_low


def leg_delta(R: pd.DataFrame, a: int, b: int) -> float:
    delta = (R["askVol"] - R["bidVol"]).to_numpy()
    return float(delta[a:b + 1].sum())


def forward_outcome(R: pd.DataFrame, i: int, is_high: bool, horizon: int, confirm_pts: float) -> str:
    """First-touch outcome. BUG FIX: a single brick (body+wick) can easily span MORE than
    confirm_pts in BOTH directions at once if confirm_pts is smaller than ~1 box -- that
    made every pivot read 100% 'reversed' (first-checked branch always won the tie), which
    is how the original run was caught as broken (100% hit rate incl. the no-signal
    baseline is not a real result). A same-brick double-hit is now 'ambiguous', not an
    automatic win, and the default confirm_pts is large enough (caller-side) to make this
    rare rather than the common case."""
    n = len(R)
    piv = R["high"].iat[i] if is_high else R["low"].iat[i]
    for j in range(i + 1, min(n, i + 1 + horizon)):
        hit_rev  = (R["low"].iat[j]  <= piv - confirm_pts) if is_high else (R["high"].iat[j] >= piv + confirm_pts)
        hit_cont = (R["high"].iat[j] >= piv + confirm_pts) if is_high else (R["low"].iat[j]  <= piv - confirm_pts)
        if hit_rev and hit_cont:
            return "ambiguous"
        if hit_rev:
            return "reversed"
        if hit_cont:
            return "continued"
    return "neither"


def scan_day(day: str, box: int, trend: int, rev: int, k: int, horizon: int, confirm_pts: float,
             abs_vol_mult: float, abs_body_mult: float, rej_wick_mult: float) -> pd.DataFrame:
    df = load_day(day)
    rth = rth_only(df, day)
    R = build(rth, box, trend, rev, length=1, ma="simple", sign=1)
    n = len(R)
    if n < 2 * k + 5:
        print(f"  {day}: only {n} bricks, too few for swing={k} -- skipped")
        return pd.DataFrame()

    is_high, is_low = swings(R, k)
    body = (R["close"] - R["open"]).abs().to_numpy()
    vol = (R["askVol"] + R["bidVol"]).to_numpy()
    med_vol = pd.Series(vol).rolling(20, min_periods=5).median().to_numpy()
    med_body = pd.Series(body).rolling(20, min_periods=5).median().to_numpy()
    wick_up = (R["high"] - np.maximum(R["open"], R["close"])).to_numpy()
    wick_dn = (np.minimum(R["open"], R["close"]) - R["low"]).to_numpy()

    rows = []
    last_high_i, last_low_i = None, None
    for i in range(n):
        if not (is_high[i] or is_low[i]):
            continue
        kind = "high" if is_high[i] else "low"
        price = R["high"].iat[i] if kind == "high" else R["low"].iat[i]

        # --- divergence vs the prior swing of the SAME kind ---
        divergence = False
        prior_i = last_high_i if kind == "high" else last_low_i
        anchor_i = last_low_i if kind == "high" else last_high_i   # leg starts at the last OPPOSITE swing
        if prior_i is not None and anchor_i is not None:
            this_leg = leg_delta(R, anchor_i, i)
            prior_anchor = last_low_i if kind == "high" else last_high_i  # same formula, prior leg uses the leg before `prior_i`
            # leg into the PRIOR same-kind swing: from the opposite swing before it to it
            # (approximate: walk back to find the opposite-kind swing before prior_i)
            prev_opp = None
            for j in range(prior_i - 1, -1, -1):
                if (kind == "high" and is_low[j]) or (kind == "low" and is_high[j]):
                    prev_opp = j
                    break
            if prev_opp is not None:
                prior_leg = leg_delta(R, prev_opp, prior_i)
                price_new_extreme = price > R["high"].iat[prior_i] if kind == "high" else price < R["low"].iat[prior_i]
                if price_new_extreme and abs(this_leg) < abs(prior_leg):
                    divergence = True

        # --- absorption: high volume, small body, at the pivot brick ---
        absorption = (not np.isnan(med_vol[i]) and not np.isnan(med_body[i])
                      and med_vol[i] > 0 and vol[i] >= abs_vol_mult * med_vol[i]
                      and body[i] <= abs_body_mult * max(med_body[i], 1e-9))

        # --- rejection: wick on the extreme side >= rej_wick_mult x own body ---
        b = max(body[i], 1e-9)
        rejection = (wick_up[i] >= rej_wick_mult * b) if kind == "high" else (wick_dn[i] >= rej_wick_mult * b)

        # record EVERY swing (not just flagged ones) so we have a true no-signal baseline
        outcome = forward_outcome(R, i, kind == "high", horizon, confirm_pts)
        rows.append(dict(day=day, i=i, t=R["t"].iat[i], kind=kind, price=price,
                          divergence=divergence, absorption=absorption, rejection=rejection,
                          outcome=outcome))

        if kind == "high": last_high_i = i
        else: last_low_i = i

    return pd.DataFrame(rows)


def chart_day(day: str, R: pd.DataFrame, ev: pd.DataFrame, box: int, trend: int, rev: int, path: Path):
    """Price bricks with every flagged pivot marked: which signal(s) fired, and whether it
    actually reversed, continued, or did neither -- so the logic can be checked by eye,
    not just trusted from a summary number."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    plt.style.use("dark_background")
    n = len(R)
    fig, ax = plt.subplots(figsize=(max(20, n * 0.30), 10))
    fig.patch.set_facecolor("black")
    fig.suptitle(f"ES {day} RTH  ·  Flex Renko {box}-{trend}-{rev}  ·  flagged pivots "
                 f"(D=divergence R=rejection A=absorption; color = outcome)", fontsize=13, color="white")

    up_c, dn_c = "#2f6fed", "#f2f2f2"
    for i, r in R.iterrows():
        c = up_c if r["dir"] == "up" else dn_c
        ax.plot([i, i], [r["low"], r["high"]], color=c, lw=1.0, zorder=2)
        blo, bhi = min(r["open"], r["close"]), max(r["open"], r["close"])
        ax.add_patch(Rectangle((i - 0.40, blo), 0.80, max(bhi - blo, 0.01),
                                facecolor=c, edgecolor=c, lw=0.3, zorder=3))

    outcome_c = {"reversed": "#2ecc71", "continued": "#e74c3c", "neither": "#999999", "ambiguous": "#f1c40f"}
    for _, e in ev.iterrows():
        i = int(e["i"])
        y = e["price"] + (6 if e["kind"] == "high" else -6)
        tags = "".join([t for t, flag in [("D", e["divergence"]), ("R", e["rejection"]), ("A", e["absorption"])] if flag])
        ax.annotate(tags, (i, y), color=outcome_c.get(e["outcome"], "white"), fontsize=11,
                    ha="center", fontweight="bold", zorder=5)
        ax.scatter([i], [e["price"]], color=outcome_c.get(e["outcome"], "white"), s=40, zorder=6,
                   marker="v" if e["kind"] == "high" else "^")

    ax.set_xlim(-1, n)
    ax.set_ylabel("ES", color="white", fontsize=12)
    ax.grid(alpha=0.15, color="gray")
    ax.tick_params(colors="white", labelsize=10)
    step = max(1, n // 40)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([R["t"].iloc[i].strftime("%H:%M") for i in ticks], rotation=90, fontsize=8, color="white")

    handles = [plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=c, markersize=8, linestyle="")
               for c in outcome_c.values()]
    ax.legend(handles, outcome_c.keys(), loc="upper left", fontsize=9, facecolor="black", labelcolor="white")

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="black")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--box", type=int, default=16)
    ap.add_argument("--trend", type=int, default=8)
    ap.add_argument("--rev", type=int, default=4)
    ap.add_argument("--swing", type=int, default=2, help="bricks each side for a swing pivot")
    ap.add_argument("--horizon", type=int, default=10, help="bricks to look forward for the outcome")
    ap.add_argument("--confirm-pts", type=float, default=8.0,
                     help="points of move to call reversed/continued (default 8pt = 2x the 4pt box, so one brick can't trivially satisfy both directions)")
    ap.add_argument("--chart-day", default=None, help="YYYY-MM-DD -- render an annotated chart of this day's flagged pivots")
    ap.add_argument("--abs-vol-mult", type=float, default=2.0)
    ap.add_argument("--abs-body-mult", type=float, default=0.5)
    ap.add_argument("--rej-wick-mult", type=float, default=1.0)
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()

    dates = all_dates()
    print(f"{len(dates)} candidate days: {dates[0]} .. {dates[-1]}\n")

    all_events = []
    for d in dates:
        try:
            ev = scan_day(d, a.box, a.trend, a.rev, a.swing, a.horizon, a.confirm_pts,
                          a.abs_vol_mult, a.abs_body_mult, a.rej_wick_mult)
            if not ev.empty:
                all_events.append(ev)
                print(f"  {d}: {len(ev)} flagged pivots")
        except SystemExit as e:
            print(f"  {d}: skipped ({e})")

    if not all_events:
        print("\nno events flagged across any day")
        return 1
    events = pd.concat(all_events, ignore_index=True)

    outdir = Path(a.out); outdir.mkdir(parents=True, exist_ok=True)
    csv_out = outdir / f"order_flow_turning_points_{dates[0]}_{dates[-1]}.csv"
    events.to_csv(csv_out, index=False)

    print(f"\n=== {len(events)} flagged pivots across {len(all_events)} days ({dates[0]} -> {dates[-1]}) ===")
    print(f"confirm={a.confirm_pts}pt within {a.horizon} bricks (first-touch; 'neither' = no {a.confirm_pts}pt move either way in time)\n")

    for sig in ["divergence", "absorption", "rejection"]:
        sub = events[events[sig]]
        if sub.empty:
            print(f"{sig:>10}: 0 flagged")
            continue
        n = len(sub)
        rev_n = (sub["outcome"] == "reversed").sum()
        cont_n = (sub["outcome"] == "continued").sum()
        neith_n = (sub["outcome"] == "neither").sum()
        amb_n = (sub["outcome"] == "ambiguous").sum()
        print(f"{sig:>10}: {n:>4} flagged  |  reversed {rev_n:>4} ({100*rev_n/n:5.1f}%)  "
              f"continued {cont_n:>4} ({100*cont_n/n:5.1f}%)  neither {neith_n:>4} ({100*neith_n/n:5.1f}%)  "
              f"ambiguous {amb_n:>4} ({100*amb_n/n:5.1f}%)")

    # any single pivot can carry multiple flags -- also report "all signals combined" (OR)
    # and "2+ signals agree" (AND-ish confluence) since confluence is usually the real claim
    n_any = len(events)
    rev_any = (events["outcome"] == "reversed").sum()
    print(f"\n{'any signal':>10}: {n_any:>4} flagged  |  reversed {rev_any:>4} ({100*rev_any/n_any:5.1f}%)")

    events["n_signals"] = events[["divergence", "absorption", "rejection"]].sum(axis=1)
    conf = events[events["n_signals"] >= 2]
    if not conf.empty:
        rev_c = (conf["outcome"] == "reversed").sum()
        print(f"{'2+ signals':>10}: {len(conf):>4} flagged  |  reversed {rev_c:>4} ({100*rev_c/len(conf):5.1f}%)")
    else:
        print(f"{'2+ signals':>10}: 0 flagged")

    # BASELINE: reversal rate of swing pivots with NO signal flagged at all -- this is the
    # number every signal above has to beat, or it's not adding anything over a random local
    # extreme in a choppy market.
    base = events[events["n_signals"] == 0]
    print(f"\n{'total swings':>10}: {len(events)}  (includes unflagged)")
    if not base.empty:
        rev_b = (base["outcome"] == "reversed").sum()
        print(f"{'baseline':>10}: {len(base):>4} (no signal)  |  reversed {rev_b:>4} ({100*rev_b/len(base):5.1f}%)  <- compare every rate above to THIS, not to 50%")
    else:
        print(f"{'baseline':>10}: 0 unflagged swings (every swing had >=1 signal -- thresholds too loose)")

    print(f"\nsaved: {csv_out}")

    if a.chart_day:
        ev_day = events[(events["day"] == a.chart_day) & (events["n_signals"] >= 1)]
        if ev_day.empty:
            print(f"\n--chart-day {a.chart_day}: no flagged pivots that day, nothing to draw")
        else:
            df = load_day(a.chart_day)
            rth = rth_only(df, a.chart_day)
            R = build(rth, a.box, a.trend, a.rev, length=1, ma="simple", sign=1)
            png_out = outdir / f"order_flow_turning_points_{a.chart_day}.png"
            chart_day(a.chart_day, R, ev_day, a.box, a.trend, a.rev, png_out)
            print(f"chart: {png_out}")
            try:
                import subprocess
                subprocess.Popen(["code", "-r", str(png_out)], shell=True)
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
