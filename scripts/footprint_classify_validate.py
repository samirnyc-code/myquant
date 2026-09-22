"""footprint_classify_validate.py — Stage-1 trust gate for the NT footprint build.

The NT footprint indicator (NTLFootprintOF) will classify each trade's aggressor with
NTLCore.IsAskTrade(price, bid, ask, lastPrice):
    trade >= ask -> aggressive BUY (ask)
    trade <= bid -> aggressive SELL (bid)
    else          -> uptick rule (>= last trade price -> buy)

Our L1 tape already carries the recorder's own aggressor tag (Aggr A/B) AND the raw
bid/ask quote stream (Ev B / A). This replays the quote stream, applies the SAME IsAskTrade
rule NT will use, and compares to the recorded tag. High agreement => NT's live footprint
reproduces our validated (vs MzPack) footprint, so the on-chart markers are trustworthy.

    python scripts/footprint_classify_validate.py --day 2026-09-16
Outputs a dated report CSV + prints the agreement rate.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
L1 = ROOT / "data" / "l1_tape"
OUT = L1 / "_analysis"


def is_ask_trade(price: float, bid: float, ask: float, last: float) -> bool:
    """Exact port of NTLCore.IsAskTrade."""
    if ask > 0 and price >= ask:
        return True
    if bid > 0 and price <= bid:
        return False
    return math.isnan(last) or price >= last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", default="2026-09-16")
    ap.add_argument("--rth", action="store_true", help="restrict to RTH 08:30-15:15 CT")
    a = ap.parse_args()

    cand = list(L1.glob(f"ES_*_l1_{a.day}.parquet")) + list(L1.glob(f"ES_*_l1_{a.day}.csv"))
    if not cand:
        raise SystemExit(f"no L1 file for {a.day}")
    path = max(cand, key=lambda p: p.stat().st_size)
    df = (pd.read_parquet(path) if path.suffix == ".parquet"
          else pd.read_csv(path, low_memory=False, usecols=["Time", "Ev", "Price", "Size", "Aggr"]))
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    # DO NOT sort — the file is already in capture order; sorting reorders same-ms
    # quote/trade events and stales the reconstructed top-of-book.
    df = df.dropna(subset=["Time"]).reset_index(drop=True)
    if a.rth:
        df = df[(df["Time"].dt.time >= pd.Timestamp("08:30").time())
                & (df["Time"].dt.time <= pd.Timestamp("15:15").time())]
    print(f"[load] {path.name}  rows={len(df):,}")

    ev = df["Ev"].to_numpy()
    price = pd.to_numeric(df["Price"], errors="coerce").to_numpy()
    aggr = df["Aggr"].astype(str).to_numpy()

    cur_bid = 0.0
    cur_ask = 0.0
    last_trade = float("nan")
    n = agree = disagree = skipped_noquote = 0
    rows = []
    for i in range(len(df)):
        e = ev[i]
        if e == "B":
            cur_bid = price[i]
        elif e == "A":
            cur_ask = price[i]
        elif e == "T":
            p = price[i]
            tag = aggr[i]
            if tag not in ("A", "B"):
                continue
            if cur_bid <= 0 or cur_ask <= 0:
                skipped_noquote += 1
                last_trade = p
                continue
            pred = "A" if is_ask_trade(p, cur_bid, cur_ask, last_trade) else "B"
            n += 1
            if pred == tag:
                agree += 1
            else:
                disagree += 1
                if len(rows) < 500:
                    rows.append({"Time": df["Time"].iloc[i], "price": p, "bid": cur_bid,
                                 "ask": cur_ask, "recorder": tag, "isasktrade": pred})
            last_trade = p

    rate = 100.0 * agree / n if n else 0.0
    print(f"\n=== aggressor classification agreement ({a.day}{' RTH' if a.rth else ''}) ===")
    print(f"  trades compared : {n:,}")
    print(f"  agree           : {agree:,} ({rate:.3f}%)")
    print(f"  disagree        : {disagree:,} ({100 - rate:.3f}%)")
    print(f"  skipped (no quote yet): {skipped_noquote:,}")

    # where do disagreements land? (usually price strictly between bid/ask -> uptick fallback)
    if rows:
        d = pd.DataFrame(rows)
        d["at_bid"] = d["price"] <= d["bid"]
        d["at_ask"] = d["price"] >= d["ask"]
        d["inside"] = (~d["at_bid"]) & (~d["at_ask"])
        print(f"  of disagreements: inside-spread={int(d['inside'].sum())} "
              f"at/thru bid={int(d['at_bid'].sum())} at/thru ask={int(d['at_ask'].sum())}")
        OUT.mkdir(parents=True, exist_ok=True)
        rp = OUT / f"footprint_classify_disagree_{a.day}.csv"
        d.to_csv(rp, index=False)
        print(f"  disagreement sample -> {rp}")

    verdict = ("TRUST: NT footprint will match our recorded footprint"
               if rate >= 99 else
               "CHECK: >1% disagreement — inspect before trusting NT markers")
    print(f"\n  VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
