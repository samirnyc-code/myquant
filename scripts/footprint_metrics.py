"""Recreate MzPack's footprint analytics from our validated raw ladder (S75).

Input: data/footprint/ES_footprint.csv  (BarIdx,BarTime,Price,BidVol,AskVol) — proven
exact vs MzPack (delta/buy%/sell%/POC match to the contract). From that ladder we derive
the full per-bar field set: volume/delta/%s, POC & value area, per-price delta, diagonal
imbalances (+counts), a volume-absorption proxy, cumulative delta (CVD), HVN/LVN, and
character flags. Fields that need intrabar TICK ORDER (MinDelta/MaxDelta/Open/Close/COT)
are NOT derivable from the aggregated ladder — those get added to the exporter itself.

  .venv/Scripts/python.exe scripts/footprint_metrics.py [YYYY-MM-DD]
"""
import sys
from pathlib import Path

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "footprint" / "ES_footprint.csv"
IMB_RATIO = 3.0      # diagonal imbalance threshold (MzPack default ~300%)
IMB_MIN = 20         # min volume for an imbalance to count
TICK = 0.25


def bar_metrics(g):
    """g = the ladder rows for one bar (Price, BidVol, AskVol), sorted by price."""
    g = g.sort_values("Price")
    price = g.Price.values
    bid = g.BidVol.values          # aggressive sells
    ask = g.AskVol.values          # aggressive buys
    tot = bid + ask
    vol = int(tot.sum())
    buy, sell = int(ask.sum()), int(bid.sum())
    delta = buy - sell
    poc_i = tot.argmax()
    # value area: expand from POC until 70% of volume
    order = tot.argsort()[::-1]
    cum, va = 0, set()
    for i in order:
        va.add(i); cum += tot[i]
        if cum >= 0.70 * vol:
            break
    va_prices = price[list(va)]
    # diagonal imbalance: ask[p] vs bid[p-1 tick]  (buy imb) ; bid[p] vs ask[p+1] (sell imb)
    bmap = {round(p, 2): (bid[i], ask[i]) for i, p in enumerate(price)}
    buy_imb = sell_imb = 0
    imb_cells = []
    for i, p in enumerate(price):
        below = bmap.get(round(p - TICK, 2))
        above = bmap.get(round(p + TICK, 2))
        if below and ask[i] >= IMB_MIN and below[0] > 0 and ask[i] >= IMB_RATIO * below[0]:
            buy_imb += 1; imb_cells.append((p, "buy", int(ask[i]), int(below[0])))
        if above and bid[i] >= IMB_MIN and above[1] > 0 and bid[i] >= IMB_RATIO * above[1]:
            sell_imb += 1; imb_cells.append((p, "sell", int(bid[i]), int(above[1])))
    # HVN/LVN: prices whose volume is >>/<< the bar mean
    mean_v = tot.mean()
    hvn = [float(price[i]) for i in range(len(price)) if tot[i] >= 2 * mean_v]
    lvn = [float(price[i]) for i in range(len(price)) if tot[i] <= 0.25 * mean_v and tot[i] > 0]
    return dict(
        vol=vol, buy=buy, sell=sell, delta=delta,
        buy_pct=round(buy / vol * 100, 2) if vol else 0,
        sell_pct=round(sell / vol * 100, 2) if vol else 0,
        poc=float(price[poc_i]), poc_vol=int(tot[poc_i]),
        vah=float(va_prices.max()), val=float(va_prices.min()),
        high=float(price[-1]), low=float(price[0]), ncells=len(price),
        buy_imb=buy_imb, sell_imb=sell_imb, imb_cells=imb_cells,
        hvn=hvn, lvn=lvn,
        is_bull=delta > 0, is_bear=delta < 0,
    )


def resolve_ladder_path(series=None):
    """S75V: FootprintExporter now writes ONE date-stamped file per chart load, tagged with
    the bar series so 1Min/5Min/6500V charts can record simultaneously without colliding:
        ES_5Min_footprint_20260719_170000.csv
    Default to the newest file; pass series="5Min" (or "6500V", ...) to pick a chart.
    Never pool files here — BarIdx is CurrentBar and restarts at 0 on every load, so
    concatenating would fuse unrelated bars inside the groupby."""
    pat = f"*_{series}_footprint_*.csv" if series else "*_footprint_*.csv"
    stamped = sorted(CSV.parent.glob(pat))
    if not stamped and series:
        raise SystemExit(f"no footprint file for series {series!r} in {CSV.parent}")
    return stamped[-1] if stamped else CSV


def load_ladder(path=None):
    """Load the raw ladder, deduped. Within one file a re-written final partial bar can
    duplicate rows; the LAST write is the complete one — keep='last'."""
    path = Path(path) if path else resolve_ladder_path()
    print(f"ladder: {path.name}")
    d = pd.read_csv(path)
    if "BarIdx" not in d.columns:
        raise SystemExit("CSV missing BarIdx — re-run the fixed FootprintExporter")
    n = len(d)
    d = d[~d.duplicated(subset=["BarIdx", "BarTime", "Price"], keep="last")]
    if len(d) < n:
        print(f"ladder: dropped {n - len(d)} duplicate rows (exporter re-run appends)")
    return d


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else None
    d = load_ladder()
    if day:
        d = d[d.BarTime.str.startswith(day)]
    rows = []
    for bidx, g in d.groupby("BarIdx"):
        m = bar_metrics(g)
        m["BarIdx"] = bidx
        m["BarTime"] = g.BarTime.iloc[0]
        rows.append(m)
    bars = pd.DataFrame(rows).sort_values("BarIdx").reset_index(drop=True)
    bars["cvd"] = bars.delta.cumsum()   # cumulative delta across bars

    out = ROOT / "data" / "footprint" / "ES_metrics.csv"
    bars.drop(columns=["imb_cells", "hvn", "lvn"]).to_csv(out, index=False)

    # show the validated run (14:38–14:44) with the FULL recreated field set
    v = bars[bars.BarTime.str.contains("14:3|14:4")].head(7)
    print(f"=== recreated footprint metrics — {len(bars)} bars"
          + (f" on {day}" if day else "") + " ===\n")
    for _, r in v.iterrows():
        print(f"{r.BarTime}  Δ{r.delta:+5}  buy%{r.buy_pct:5}  sell%{r.sell_pct:5}  "
              f"POC {r.poc:.2f}(vol {r.poc_vol})  VA {r.val:.2f}-{r.vah:.2f}  "
              f"imb: {r.buy_imb}buy/{r.sell_imb}sell  CVD {r.cvd:+}")
        if r.imb_cells:
            cells = "  ".join(f"{p:.2f}:{side}({v}v{n})" for p, side, v, n in r.imb_cells[:6])
            print(f"        imbalance cells -> {cells}")
    print(f"\nwrote {out}  (per-bar; {len(bars.columns)-3} metric columns)")


if __name__ == "__main__":
    main()
