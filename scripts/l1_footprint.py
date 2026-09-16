"""l1_footprint.py — reconstruct footprint + cumulative delta from the L1 tape.

PROVES the L1 recorder (L1TapeRecorderAddOn) captures everything the Wyckoff-2.0 order-flow
TRIGGER lane needs: every trade is aggressor-tagged (A = buy lifting the ask, B = sell hitting
the bid), so per-bar bid/ask volume-at-price (the footprint) and cumulative delta (CVD) rebuild
directly — no L2 DOM, no paid vendor. Same classification that validated exact vs MzPack.

    python scripts/l1_footprint.py                       # latest file in data/l1_tape, 1-min bars
    python scripts/l1_footprint.py --file <csv/parquet> --bar 2000t
    python scripts/l1_footprint.py --bar 1min --out data/l1_tape/_analysis

Outputs (dated): a per-bar CSV (OHLC/vol/buy/sell/delta/CVD), a footprint ladder for the
busiest bar, and a 3-panel PNG (price · CVD · per-bar delta) auto-opened in VSCode.
"""
from __future__ import annotations

import argparse
import datetime as dt
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
L1_DIR = ROOT / "data" / "l1_tape"


def load(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    return df


def bar_key(t: pd.DataFrame, bar: str) -> pd.Series:
    """Assign each tape row to a bar. Time bars ('1min','5min') floor the timestamp;
    tick bars ('2000t') group by running trade count."""
    if bar.endswith("t"):
        n = int(bar[:-1])
        return (pd.RangeIndex(len(t)) // n).astype("int64").to_series(index=t.index)
    return t["Time"].dt.floor(bar.replace("min", "min"))


def reconstruct(df: pd.DataFrame, bar: str):
    tape = df[df["Ev"] == "T"].copy()
    if tape.empty:
        raise SystemExit("no tape (T) rows in this file")
    tape["Size"] = tape["Size"].astype("int64")
    tape["buy"] = tape["Aggr"].astype(str).eq("A") * tape["Size"]   # aggressive buys @ ask
    tape["sell"] = tape["Aggr"].astype(str).eq("B") * tape["Size"]  # aggressive sells @ bid
    tape["bar"] = bar_key(tape, bar)

    # per-bar OHLC (from trades) + effort split + delta
    g = tape.groupby("bar", sort=True)
    bars = pd.DataFrame({
        "t_start": g["Time"].first(),
        "t_end":   g["Time"].last(),
        "open":    g["Price"].first(),
        "high":    g["Price"].max(),
        "low":     g["Price"].min(),
        "close":   g["Price"].last(),
        "vol":     g["Size"].sum(),
        "buy":     g["buy"].sum(),
        "sell":    g["sell"].sum(),
        "trades":  g["Price"].size,
    })
    bars["delta"] = bars["buy"] - bars["sell"]
    bars["cvd"] = bars["delta"].cumsum()
    # per-bar footprint POC = price level with the most total volume
    fp_all = (tape.groupby(["bar", "Price"])
                  .agg(sell=("sell", "sum"), buy=("buy", "sum"), vol=("Size", "sum"))
                  .reset_index())
    poc = fp_all.loc[fp_all.groupby("bar")["vol"].idxmax()].set_index("bar")["Price"]
    bars["poc"] = poc
    return bars.reset_index(drop=True), fp_all, tape


def footprint_ladder(fp_all: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """The bid/ask volume-at-price ladder for the single busiest bar — the footprint you'd
    read at a zone. sell = aggressive sells (bid-hit), buy = aggressive buys (ask-hit)."""
    busiest = bars["vol"].idxmax()
    key = fp_all["bar"].unique()[busiest] if busiest < len(fp_all["bar"].unique()) else fp_all["bar"].iloc[0]
    lad = fp_all[fp_all["bar"] == fp_all["bar"].unique()[busiest]].copy()
    lad = lad.sort_values("Price", ascending=False)
    lad["delta"] = lad["buy"] - lad["sell"]
    return busiest, lad[["Price", "sell", "buy", "delta", "vol"]]


def chart(bars: pd.DataFrame, fp_all: pd.DataFrame, tape: pd.DataFrame, bar: str, path: Path):
    """A REAL footprint chart: each bar is a price-ladder column showing sell×buy at every
    traded level, cell colored by delta (green=buy-heavy, red=sell-heavy), POC outlined,
    close path overlaid. Bottom panel = cumulative delta on the same bars."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    import numpy as np

    keys = list(bars_key_order(fp_all))
    keymap = {k: i for i, k in enumerate(keys)}
    fp = fp_all.copy()
    fp["bi"] = fp["bar"].map(keymap)
    n = len(keys)

    tick = 0.25
    prices = tape["Price"].unique()
    pmin, pmax = float(prices.min()), float(prices.max())
    nlev = int(round((pmax - pmin) / tick)) + 1

    fig_w = max(13, n * 0.78)
    fig_h = max(6.5, nlev * 0.34 + 2)
    fig, (ax, axd) = plt.subplots(2, 1, figsize=(fig_w, fig_h), sharex=True,
                                  gridspec_kw={"height_ratios": [nlev * 0.34, 1.6]})
    fig.suptitle(f"L1 FOOTPRINT — ES  {bars['t_start'].iloc[0]:%Y-%m-%d %H:%M}→{bars['t_end'].iloc[-1]:%H:%M}"
                 f"  ·  {bar} bars  ·  cell = sell×buy (aggr sells @bid × aggr buys @ask)", fontsize=11)

    # per-level footprint cells
    dmax = max(1, int(fp["buy"].sub(fp["sell"]).abs().max()))
    for _, r in fp.iterrows():
        bi, price = int(r["bi"]), float(r["Price"])
        sell, buy = int(r["sell"]), int(r["buy"])
        d = buy - sell
        inten = min(0.85, 0.18 + 0.67 * abs(d) / dmax)
        color = (0.15, 0.6, 0.25, inten) if d > 0 else (0.8, 0.15, 0.15, inten) if d < 0 else (0.5, 0.5, 0.5, 0.25)
        ax.add_patch(Rectangle((bi - 0.46, price - tick / 2), 0.92, tick, color=color, lw=0))
        ax.text(bi, price, f"{sell}×{buy}", ha="center", va="center", fontsize=6.5, color="black")

    # POC per bar (outlined) + close path
    for i, row in bars.reset_index(drop=True).iterrows():
        ax.add_patch(Rectangle((i - 0.46, float(row["poc"]) - tick / 2), 0.92, tick,
                               fill=False, edgecolor="#111", lw=1.6))
    ax.plot(range(n), bars["close"].values, color="#1f77b4", lw=1.1, alpha=0.55, zorder=5, label="close")

    ax.set_ylim(pmin - tick, pmax + tick)
    ax.set_xlim(-0.6, n - 0.4)
    ax.set_yticks(np.arange(pmin, pmax + tick, tick))
    ax.set_ylabel("price"); ax.grid(axis="y", alpha=0.15); ax.legend(loc="upper left", fontsize=8)

    # bottom: cumulative delta
    axd.plot(range(n), bars["cvd"].values, color="#2ca02c", lw=1.6, marker="o", ms=3)
    axd.axhline(0, color="#888", lw=0.7)
    axd.set_ylabel("cum delta"); axd.grid(alpha=0.2)
    axd.set_xticks(range(n))
    axd.set_xticklabels([t.strftime("%H:%M") for t in bars["t_start"]], rotation=90, fontsize=7)

    fig.tight_layout(rect=[0, 0, 1, 0.98])
    fig.savefig(path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def bars_key_order(fp_all: pd.DataFrame):
    """Bar keys in chronological order (groupby sort order)."""
    return list(dict.fromkeys(fp_all["bar"].tolist()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=None, help="L1 csv/parquet (default: latest in data/l1_tape)")
    ap.add_argument("--bar", default="1min", help="bar size: 1min / 5min / 2000t")
    ap.add_argument("--out", default=str(L1_DIR / "_analysis"))
    a = ap.parse_args()

    if a.file:
        path = Path(a.file)
    else:
        cands = sorted(L1_DIR.glob("ES*_l1_*.csv")) + sorted(L1_DIR.glob("ES*_l1_*.parquet"))
        if not cands:
            raise SystemExit("no L1 files in data/l1_tape")
        path = max(cands, key=lambda p: p.stat().st_mtime)
    print(f"reading {path.name}  (bar={a.bar})")

    df = load(path)
    bars, fp_all, tape = reconstruct(df, a.bar)
    busiest, ladder = footprint_ladder(fp_all, bars)

    outdir = Path(a.out); outdir.mkdir(parents=True, exist_ok=True)
    stamp = path.stem
    csv_out = outdir / f"{stamp}_{a.bar}_bars.csv"
    bars.to_csv(csv_out, index=False)
    png_out = outdir / f"{stamp}_{a.bar}_footprint.png"
    chart(bars, fp_all, tape, a.bar, png_out)

    # ---- inline summary (user can't see tool stdout otherwise) ----
    tot_buy, tot_sell = int(tape["buy"].sum()), int(tape["sell"].sum())
    print(f"\ntape prints: {len(tape):,}  |  aggressive buys {tot_buy:,} vs sells {tot_sell:,}  "
          f"|  session delta {tot_buy - tot_sell:+,}  |  final CVD {int(bars['cvd'].iloc[-1]):+,}")
    print(f"\nper-bar ({a.bar}):")
    show = bars.copy()
    show["t"] = show["t_start"].dt.strftime("%H:%M:%S")
    cols = ["t", "open", "high", "low", "close", "vol", "buy", "sell", "delta", "cvd", "poc"]
    with pd.option_context("display.max_rows", 60, "display.width", 160):
        print(show[cols].to_string(index=False))
    print(f"\nfootprint ladder — busiest bar #{busiest} "
          f"({bars.loc[busiest, 't_start']:%H:%M:%S}, vol {int(bars.loc[busiest,'vol']):,}):")
    print("  price     sell(bid)  buy(ask)   delta   vol")
    for _, r in ladder.iterrows():
        print(f"  {r['Price']:>8.2f}  {int(r['sell']):>8}  {int(r['buy']):>8}  {int(r['delta']):>+7}  {int(r['vol']):>5}")

    print(f"\nsaved: {csv_out}")
    print(f"chart: {png_out}")
    try:
        subprocess.Popen(["code", "-r", str(png_out)], shell=True)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
