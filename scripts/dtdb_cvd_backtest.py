"""dtdb_cvd_backtest.py — faithful Python port of nt8/indicators/DtDbScannerV3.cs's
DT/DB detection + its new (2026-10-18) CVD divergence check, run against every ES L1
tape day on disk, so the feature can be eyeballed on real history before trusting it
live. Renders one annotated chart per day (NT8-style: legs, neckline, peak line, CVD
divergence badge, pullback-retest badge) and a CSV log of every confirmed instance.

NOT a backtest (no entries/fills/P&L) and NOT a forward-outcome/edge study — purely a
visual + tabulated replay of what the live indicator would have drawn. Requested
2026-10-18 after the live CVD divergence feature was added to DtDbScannerV3.cs.

CVD here is TRUE tick-classified delta from the L1 tape's own Aggr column (askVol -
bidVol per bar), NOT the bar-proxy close-position-in-range formula the live NT8
indicator uses (L1 tape gives us the real thing; the live indicator uses the proxy
because NT8 doesn't always have tick-replay/L1 available). Both are smoothed the same
way (rolling SUM or EMA over CvdPeriod bars) and compared the same way at the two
peak/trough pivots.

Bars are built from raw trade PRINTS (NT8 "Tick" bars count prints, not contracts),
default 2000 per bar to match this user's standard tick-chart interval across other
indicators (WedgeExporter's 2000t MAE/MFE study, RegimeTrackerBox's 2000t-ETH column).

    python scripts/dtdb_cvd_backtest.py
    python scripts/dtdb_cvd_backtest.py --ticks 2000 --day 2026-10-13
"""
from __future__ import annotations

import argparse
import glob
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT))
from bid_ask_volume_ratio_renko import load_day, rth_only, L1_DIR

OUT = L1_DIR / "_analysis"
TICK = 0.25  # ES

# ---- DtDbScannerV3.cs defaults (2026-10-15 user settings, ABR sizing mode) ----
SWING_STRENGTH = 1
USE_ABR_SIZING = True
ABR_BARS = 8
PEAK_TOL_ABR = 0.5
MIN_VALLEY_DEPTH_ABR = 0.5
PEAK_TOL_TICKS = 6
MIN_VALLEY_DEPTH_TICKS = 5
MIN_BARS_BETWEEN = 2
MAX_BARS_BETWEEN = 50
NECKLINE_BUFFER_TICKS = 0
CONFIRM_WITHIN_BARS = 50
# ---- new CVD divergence defaults (2026-10-18) ----
CVD_PERIOD = 21
CVD_MODE = "periodic"  # or "ema"
PULLBACK_WATCH_BARS = 30
RETEST_TOLERANCE_TICKS = 4


def all_dates() -> list[str]:
    return sorted(set(os.path.basename(f).split("_l1_")[-1].split(".")[0]
                       for f in glob.glob(str(L1_DIR / "ES*_l1_*.*"))))


def build_tick_bars(df: pd.DataFrame, tick_count: int) -> pd.DataFrame:
    """N-tick bars (N trade PRINTS, matching NT8's Tick bar definition) with per-bar
    askVol/bidVol from the tape's own Aggr classification."""
    tape = df[df["Ev"] == "T"].sort_values("Time").reset_index(drop=True)
    tape["Size"] = tape["Size"].astype("int64")
    n = len(tape)
    if n < tick_count * 3:
        raise SystemExit(f"only {n} trade prints, too few for {tick_count}-tick bars")

    grp = np.arange(n) // tick_count
    tape["grp"] = grp
    ask = tape["Aggr"].eq("A") * tape["Size"]
    bid = tape["Aggr"].eq("B") * tape["Size"]
    tape["ask"] = ask
    tape["bid"] = bid

    bars = tape.groupby("grp").agg(
        t=("Time", "last"),
        open=("Price", "first"),
        high=("Price", "max"),
        low=("Price", "min"),
        close=("Price", "last"),
        askVol=("ask", "sum"),
        bidVol=("bid", "sum"),
        openT=("Price", lambda s: s.iloc[0]),
    ).reset_index(drop=True)
    # drop a trailing partial bar (< tick_count prints) so it doesn't masquerade as a full bar
    last_grp_n = (tape["grp"] == grp[-1]).sum()
    if last_grp_n < tick_count:
        bars = bars.iloc[:-1].reset_index(drop=True)
    return bars


def build_time_bars(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """N-minute wall-clock bars (standard OHLCV), same per-bar askVol/bidVol from the
    tape's own Aggr classification. Bucketed on RTH-anchored boundaries (08:30 CT start)."""
    tape = df[df["Ev"] == "T"].sort_values("Time").reset_index(drop=True)
    tape["Size"] = tape["Size"].astype("int64")
    n = len(tape)
    if n < 100:
        raise SystemExit(f"only {n} trade prints, too few for {minutes}-minute bars")

    tape["bucket"] = tape["Time"].dt.floor(f"{minutes}min")
    ask = tape["Aggr"].eq("A") * tape["Size"]
    bid = tape["Aggr"].eq("B") * tape["Size"]
    tape["ask"] = ask
    tape["bid"] = bid

    bars = tape.groupby("bucket").agg(
        t=("Time", "last"),
        open=("Price", "first"),
        high=("Price", "max"),
        low=("Price", "min"),
        close=("Price", "last"),
        askVol=("ask", "sum"),
        bidVol=("bid", "sum"),
    ).reset_index(drop=True)
    # drop a trailing partial bar (bucket cut short by RTH close) so it doesn't masquerade as a full bar
    last_bucket_dur = (tape["Time"].iloc[-1] - tape.loc[tape["bucket"] == tape["bucket"].iat[-1], "Time"].iloc[0])
    if last_bucket_dur < pd.Timedelta(minutes=minutes) * 0.5:
        bars = bars.iloc[:-1].reset_index(drop=True)
    return bars


def build_bars(rth: pd.DataFrame, ticks: int | None, minutes: int | None) -> pd.DataFrame:
    if minutes:
        return build_time_bars(rth, minutes)
    return build_tick_bars(rth, ticks or 2000)


def cvd_hist(bars: pd.DataFrame, period: int, mode: str) -> np.ndarray:
    delta = (bars["askVol"] - bars["bidVol"]).astype(float)
    if mode == "periodic":
        return delta.rolling(period, min_periods=1).sum().to_numpy()
    return delta.ewm(span=period, adjust=False).mean().to_numpy()


def avg_bar_range(bars: pd.DataFrame, i: int, abr_bars: int) -> float:
    lo = max(0, i - abr_bars + 1)
    rng = (bars["high"].iloc[lo:i + 1] - bars["low"].iloc[lo:i + 1])
    return float(rng.mean()) if len(rng) else 0.0


def detect_pivots(bars: pd.DataFrame, k: int):
    """NT8 tie rule: candidate must be strictly beyond every EARLIER bar, but a LATER
    bar may equal it (ties resolve to the earlier bar) -- mirrors DetectPivotAt."""
    n = len(bars)
    hi, lo = bars["high"].to_numpy(), bars["low"].to_numpy()
    highs, lows = [], []
    for i in range(k, n - k):
        cand_h, cand_l = hi[i], lo[i]
        is_h = is_l = True
        for j in range(1, k + 1):
            if is_h and hi[i + j] >= cand_h: is_h = False   # later bar, >= blocks
            if is_h and hi[i - j] > cand_h: is_h = False    # earlier bar, > blocks
            if is_l and lo[i + j] <= cand_l: is_l = False
            if is_l and lo[i - j] < cand_l: is_l = False
        if is_h: highs.append((i, cand_h))
        if is_l: lows.append((i, cand_l))
    return highs, lows


def neckline_low(bars: pd.DataFrame, barA: int, barB: int):
    best = None
    for b in range(barA, barB + 1):
        if b == barA and not (bars["close"].iat[b] < bars["open"].iat[b]): continue
        if b == barB and not (bars["close"].iat[b] > bars["open"].iat[b]): continue
        lo = bars["low"].iat[b]
        if best is None or lo < best[1]: best = (b, lo)
    return best


def neckline_high(bars: pd.DataFrame, barA: int, barB: int):
    best = None
    for b in range(barA, barB + 1):
        if b == barA and not (bars["close"].iat[b] > bars["open"].iat[b]): continue
        if b == barB and not (bars["close"].iat[b] < bars["open"].iat[b]): continue
        hi = bars["high"].iat[b]
        if best is None or hi > best[1]: best = (b, hi)
    return best


def effective_sizes(bars: pd.DataFrame, i: int) -> tuple[float, float]:
    if USE_ABR_SIZING:
        abr = avg_bar_range(bars, i, ABR_BARS)
        return PEAK_TOL_ABR * abr, MIN_VALLEY_DEPTH_ABR * abr
    return PEAK_TOL_TICKS * TICK, MIN_VALLEY_DEPTH_TICKS * TICK


@dataclass
class Instance:
    day: str
    kind: str          # "DT" or "DB"
    p1_bar: int; p1_price: float
    p2_bar: int; p2_price: float
    neck_bar: int; neck_price: float
    form_bar: int
    confirm_bar: int | None = None
    cvd1: float = float("nan")
    cvd2: float = float("nan")
    agrees: bool | None = None
    retest_bar: int | None = None
    retest_cvd_delta: float | None = None


def find_confirmed(bars: pd.DataFrame, day: str) -> list[Instance]:
    highs, lows = detect_pivots(bars, SWING_STRENGTH)
    hist = cvd_hist(bars, CVD_PERIOD, CVD_MODE)
    n = len(bars)
    buf = NECKLINE_BUFFER_TICKS * TICK
    tol_rt = RETEST_TOLERANCE_TICKS * TICK

    # a pivot at bar `b` is only KNOWN/confirmed SWING_STRENGTH bars later (DetectPivotAt
    # runs at CurrentBar, testing the candidate SWING_STRENGTH bars back) -- index by the
    # bar it becomes known, not the bar it sits on, or this leaks look-ahead information
    # the live indicator never had at that point in time.
    confirms_high: dict[int, tuple[int, float]] = {b + SWING_STRENGTH: (b, p) for b, p in highs}
    confirms_low: dict[int, tuple[int, float]] = {b + SWING_STRENGTH: (b, p) for b, p in lows}

    pending: list[dict] = []   # structures formed this bar, moved into open_structs below
    confirmed: list[Instance] = []

    def try_pair(p1, p2, extreme, tol, min_depth, is_top: bool):
        # per-candidate reject: a pivot strictly between p1/p2 beyond BOTH of them voids
        # this pair (mirrors TryDoubleTop's own highestBetween/lowestBetween check --
        # distinct from the outer loop's coarser early-break below).
        if is_top and extreme > max(p1[1], p2[1]): return None
        if not is_top and extreme < min(p1[1], p2[1]): return None
        neck = neckline_low(bars, p1[0], p2[0]) if is_top else neckline_high(bars, p1[0], p2[0])
        if neck is None: return None
        diff = abs(p1[1] - p2[1])
        depth = (min(p1[1], p2[1]) - neck[1]) if is_top else (neck[1] - max(p1[1], p2[1]))
        bars_between = p2[0] - p1[0]
        if diff > tol or depth < min_depth: return None
        if bars_between < MIN_BARS_BETWEEN or bars_between > MAX_BARS_BETWEEN: return None
        return dict(p1=p1, p2=p2, neck=neck, is_top=is_top, form_bar=p2[0])

    def check_double(pivots, is_top, confirm_bar):
        if len(pivots) < 2: return
        p2 = pivots[-1]
        tol, min_depth = effective_sizes(bars, confirm_bar)   # ABR ending at the CONFIRM bar, not p2's own bar
        extreme = -1e18 if is_top else 1e18
        for j in range(len(pivots) - 2, -1, -1):
            p1 = pivots[j]
            bars_between = p2[0] - p1[0]
            if bars_between > MAX_BARS_BETWEEN: break
            if is_top and extreme > p2[1] + tol: break     # coarse early-exit (CheckDoubleTop's own break)
            if not is_top and extreme < p2[1] - tol: break
            r = try_pair(p1, p2, extreme, tol, min_depth, is_top)
            if r is not None:
                pending.append(r)
                return
            extreme = max(extreme, p1[1]) if is_top else min(extreme, p1[1])

    seen_highs: list[tuple[int, float]] = []
    seen_lows: list[tuple[int, float]] = []
    open_structs: list[dict] = []   # mirrors openDrawn: watched for confirm/invalidate/expiry
    watching_retest: list[dict] = []

    for i in range(n):
        if i in confirms_high:
            seen_highs.append(confirms_high[i])
            check_double(seen_highs, True, i)
        if i in confirms_low:
            seen_lows.append(confirms_low[i])
            check_double(seen_lows, False, i)

        # move any freshly-formed pending structure into the open/watch list
        while pending:
            p = pending.pop()
            open_structs.append(p)

        # ManagePending + SweepDrawn combined: invalidate / expire / confirm
        still_open = []
        for s in open_structs:
            is_top = s["is_top"]
            invalid = (bars["high"].iat[i] > max(s["p1"][1], s["p2"][1])) if is_top \
                      else (bars["low"].iat[i] < min(s["p1"][1], s["p2"][1]))
            expired = i - s["form_bar"] > CONFIRM_WITHIN_BARS
            neck_px = s["neck"][1]
            conf = (bars["close"].iat[i] < neck_px - buf) if is_top else (bars["close"].iat[i] > neck_px + buf)
            if invalid or expired:
                continue   # dropped, never confirmed
            if conf:
                cvd1, cvd2 = hist[s["p1"][0]], hist[s["p2"][0]]
                agrees = (cvd2 < cvd1) if is_top else (cvd2 > cvd1)
                inst = Instance(day=day, kind="DT" if is_top else "DB",
                                 p1_bar=s["p1"][0], p1_price=s["p1"][1],
                                 p2_bar=s["p2"][0], p2_price=s["p2"][1],
                                 neck_bar=s["neck"][0], neck_price=neck_px,
                                 form_bar=s["form_bar"], confirm_bar=i,
                                 cvd1=cvd1, cvd2=cvd2, agrees=agrees)
                confirmed.append(inst)
                watching_retest.append(dict(inst=inst, is_top=is_top, neck=neck_px,
                                             confirm_bar=i, break_cvd=hist[i]))
                continue   # stop watching this structure, confirmed
            still_open.append(s)
        open_structs = still_open

        # retest watch
        still_watch = []
        for w in watching_retest:
            if i - w["confirm_bar"] > PULLBACK_WATCH_BARS:
                continue
            if i <= w["confirm_bar"]:   # same bug/fix as DtDbScannerV3.cs: skip the confirm bar itself
                still_watch.append(w)
                continue
            is_top = w["is_top"]; neck = w["neck"]
            is_retest = (bars["high"].iat[i] >= neck - tol_rt and bars["close"].iat[i] <= neck) if is_top \
                        else (bars["low"].iat[i] <= neck + tol_rt and bars["close"].iat[i] >= neck)
            if is_retest:
                w["inst"].retest_bar = i
                w["inst"].retest_cvd_delta = float(hist[i] - w["break_cvd"])
                continue
            still_watch.append(w)
        watching_retest = still_watch

    return confirmed


def chart_day(day: str, bars: pd.DataFrame, insts: list[Instance], path: Path, bar_label: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    plt.style.use("dark_background")
    n = len(bars)
    fig, ax = plt.subplots(figsize=(max(20, n * 0.12), 10))
    fig.patch.set_facecolor("black")
    fig.suptitle(f"ES {day} RTH  ·  {len(bars)} x {bar_label} bars  ·  DT/DB CVD divergence "
                 f"({sum(1 for x in insts if x.agrees)}/{len(insts)} agree)", fontsize=13, color="white")

    for i, r in bars.iterrows():
        c = "#2f6fed" if r["close"] >= r["open"] else "#f2f2f2"
        ax.plot([i, i], [r["low"], r["high"]], color=c, lw=0.8, zorder=2)
        blo, bhi = min(r["open"], r["close"]), max(r["open"], r["close"])
        ax.add_patch(Rectangle((i - 0.35, blo), 0.70, max(bhi - blo, 0.01), facecolor=c, edgecolor=c, lw=0.2, zorder=3))

    for inst in insts:
        c = "#e74c3c" if inst.kind == "DT" else "#2ecc71"
        ax.plot([inst.p1_bar, inst.neck_bar, inst.p2_bar],
                [inst.p1_price, inst.neck_price, inst.p2_price], color=c, lw=1.5, zorder=4)
        peak = max(inst.p1_price, inst.p2_price) if inst.kind == "DT" else min(inst.p1_price, inst.p2_price)
        ax.plot([inst.p1_bar, inst.p2_bar], [peak, peak], color="white", lw=2.2, zorder=4)
        y = inst.p2_price + 8 * TICK if inst.kind == "DT" else inst.p2_price - 8 * TICK
        badge_c = "#00e5ff" if inst.agrees else "#888888"
        ax.annotate(f"{inst.kind} CVD{'✓' if inst.agrees else '✗'} {inst.cvd2 - inst.cvd1:+.0f}",
                    (inst.confirm_bar, y), color=badge_c, fontsize=8, ha="center", zorder=5)
        if inst.retest_bar is not None:
            y2 = y + (6 * TICK if inst.kind == "DT" else -6 * TICK)
            ax.annotate(f"retest Δ{inst.retest_cvd_delta:+.0f}", (inst.retest_bar, y2),
                        color="#00e5ff", fontsize=8, ha="center", zorder=5)

    ax.set_xlim(-1, n)
    ax.set_ylabel("ES", color="white", fontsize=12)
    ax.grid(alpha=0.15, color="gray")
    ax.tick_params(colors="white", labelsize=9)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="black")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=2000)
    ap.add_argument("--minutes", type=int, default=None, help="use N-minute time bars instead of tick bars")
    ap.add_argument("--day", default=None, help="single day YYYY-MM-DD; default = every day on disk")
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    bar_label = f"{a.minutes}min" if a.minutes else f"{a.ticks}tick"

    dates = [a.day] if a.day else all_dates()
    outdir = Path(a.out); outdir.mkdir(parents=True, exist_ok=True)

    all_insts: list[Instance] = []
    opened_pngs: list[Path] = []
    for d in dates:
        try:
            df = load_day(d)
            rth = rth_only(df, d)
            bars = build_bars(rth, a.ticks, a.minutes)
        except SystemExit as e:
            print(f"  {d}: skipped ({e})")
            continue
        if len(bars) < 2 * SWING_STRENGTH + 10:
            print(f"  {d}: only {len(bars)} bars, too few -- skipped")
            continue
        insts = find_confirmed(bars, d)
        print(f"  {d}: {len(bars)} bars, {len(insts)} confirmed DT/DB")
        if insts:
            all_insts.extend(insts)
            png = outdir / f"dtdb_cvd_{bar_label}_{d}.png"
            chart_day(d, bars, insts, png, bar_label)
            opened_pngs.append(png)

    if not all_insts:
        print("\nno confirmed DT/DB across any day")
        return 1

    rows = [dict(day=x.day, kind=x.kind, p1_bar=x.p1_bar, p1_price=x.p1_price,
                 p2_bar=x.p2_bar, p2_price=x.p2_price, confirm_bar=x.confirm_bar,
                 cvd1=x.cvd1, cvd2=x.cvd2, cvd_delta=x.cvd2 - x.cvd1, agrees=x.agrees,
                 retest_bar=x.retest_bar, retest_cvd_delta=x.retest_cvd_delta)
            for x in all_insts]
    log = pd.DataFrame(rows)
    csv_out = outdir / f"dtdb_cvd_backtest_{bar_label}_{dates[0]}_{dates[-1]}.csv"
    log.to_csv(csv_out, index=False)

    n = len(log)
    n_dt, n_db = (log["kind"] == "DT").sum(), (log["kind"] == "DB").sum()
    n_agree = log["agrees"].sum()
    n_retest = log["retest_bar"].notna().sum()
    print(f"\n=== {n} confirmed DT/DB across {len(dates)} days ({dates[0]} -> {dates[-1]}) ===")
    print(f"DT {n_dt}  DB {n_db}")
    print(f"CVD agrees: {n_agree}/{n} ({100*n_agree/n:.1f}%)")
    print(f"retest seen within {PULLBACK_WATCH_BARS} bars: {n_retest}/{n} ({100*n_retest/n:.1f}%)")
    print(f"\nsaved: {csv_out}")
    print(f"charts: {len(opened_pngs)} saved to {outdir}")

    try:
        import subprocess
        for p in opened_pngs[:5]:
            subprocess.Popen(["code", "-r", str(p)], shell=True)
        if len(opened_pngs) > 5:
            print(f"(opened first 5 of {len(opened_pngs)} charts in VSCode; rest saved to disk)")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
