"""S75R — 1-minute BidAsk footprint engine for ES, 2026-07-17.

Source: data/depth/ES_depth_2026-07-17.csv — every print tagged Side=A (traded at
the ask, i.e. a buy) or Side=B (traded at the bid, a sell). That is a true BidAsk
footprint, the same calc mode as the 5M b1 slide.

NOTE ON COVERAGE: the recording starts 08:44:16, so the RTH open (08:30) is NOT in
this file. First complete 1M bar is 08:45. Anything claiming to show the open from
this source would be fabricated.

Window: bars 1-37 (08:45 -> 09:21) = two complete swings, both reversals:
    08:45 L 7475.00 -> 09:10 H 7533.75 -> 09:14 L 7525.00 -> 09:17 H 7539.00
    -> 09:21 L 7527.75

Metrics per bar:
  delta            ask - bid (whole bar)
  poc              price with the most total volume
  diagonal imbalances   ask[P] vs bid[P-tick] >= RATIO  -> buy imbalance
                        bid[P] vs ask[P+tick] >= RATIO  -> sell imbalance
                        3+ consecutive = "stacked"
  absorption       heavy volume at an extreme that price fails to extend through
  close location   where the close sits in the bar range (1.0 = on the high)
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "depth" / "ES_depth_2026-07-17.csv"
OUT = ROOT / "data" / "footprint" / "ES_1m_20260717.json"

TICK = 0.25
START = "2026-07-17 08:45"
N_BARS = 37
RATIO = 3.0          # diagonal imbalance ratio
STACK = 3            # consecutive imbalances to call it "stacked"


def load():
    d = pd.read_csv(SRC, parse_dates=["Time"])
    d["m"] = d.Time.dt.floor("min")
    d = d[d.m >= pd.Timestamp(START)]
    keep = sorted(d.m.unique())[:N_BARS]
    return d[d.m.isin(keep)]


def build():
    d = load()
    bars = []
    for i, (m, x) in enumerate(d.groupby("m"), start=1):
        lad = x.groupby(["Price", "Side"]).Size.sum().unstack(fill_value=0)
        for c in ("A", "B"):
            if c not in lad:
                lad[c] = 0
        lad = lad.sort_index(ascending=False)
        lad.columns.name = None
        lad = lad.rename(columns={"A": "ask", "B": "bid"})
        lad["delta"] = lad.ask - lad.bid
        lad["vol"] = lad.ask + lad.bid

        o, c = float(x.Price.iloc[0]), float(x.Price.iloc[-1])
        hi, lo = float(lad.index.max()), float(lad.index.min())
        delta = int(lad.delta.sum())
        vol = int(lad.vol.sum())

        # --- diagonal imbalances (the real footprint definition) -------------
        buy_imb, sell_imb = [], []
        px = list(lad.index)
        for p in px:
            below = round(p - TICK, 2)
            above = round(p + TICK, 2)
            if below in lad.index:
                a, b = lad.ask[p], lad.bid[below]
                if a >= RATIO * max(b, 1) and a >= 20:
                    buy_imb.append(p)
            if above in lad.index:
                b2, a2 = lad.bid[p], lad.ask[above]
                if b2 >= RATIO * max(a2, 1) and b2 >= 20:
                    sell_imb.append(p)

        # Full detail for every imbalance, including the cell it was compared
        # against. `thin` marks the case where the diagonal denominator is ~empty:
        # the ratio is then meaningless (48 vs 0 is not "48x buying"), and it is how
        # you end up with a BUY imbalance sitting on a NEGATIVE-delta row. Those are
        # edge-of-bar noise, not conviction, and the chart says so.
        detail = []
        for p in buy_imb:
            below = round(p - TICK, 2)
            a, bd = int(lad.ask[p]), int(lad.bid[below])
            detail.append({"kind": "buy", "price": float(p), "here": a,
                           "other": bd, "other_price": float(below),
                           "ratio": (a / bd) if bd else None,
                           "thin": bd < 20, "row_delta": int(lad.delta[p])})
        for p in sell_imb:
            above = round(p + TICK, 2)
            bd, a = int(lad.bid[p]), int(lad.ask[above])
            detail.append({"kind": "sell", "price": float(p), "here": bd,
                           "other": a, "other_price": float(above),
                           "ratio": (bd / a) if a else None,
                           "thin": a < 20, "row_delta": int(lad.delta[p])})

        def stacks(lst):
            """consecutive runs of >=STACK ticks"""
            out, run = [], []
            for p in sorted(lst, reverse=True):
                if run and abs(run[-1] - p - TICK) < 1e-6:
                    run.append(p)
                else:
                    if len(run) >= STACK:
                        out.append((run[0], run[-1]))
                    run = [p]
            if len(run) >= STACK:
                out.append((run[0], run[-1]))
            return out

        poc = float(lad.vol.idxmax())
        rng = max(hi - lo, TICK)

        # actual intrabar price path (we have every print, so this is real, not a
        # sketch): normalised time 0-1 within the minute, subsampled to ~140 pts
        t0 = x.Time.iloc[0]
        secs = (x.Time - t0).dt.total_seconds().to_numpy()
        span = max(secs[-1], 1e-6)
        step = max(1, len(x) // 140)
        prices = x.Price.to_numpy()
        keep = set(range(0, len(x), step)) | {0, len(x) - 1}
        # force the exact high and low prints in: subsampling was dropping the
        # extreme tick, so a swing labelled "up to 7486.00" when the bar high was
        # 7486.25 — wrong by a tick on the one number that matters most
        keep |= {int(prices.argmax()), int(prices.argmin())}
        path = [[round(float(secs[j] / span), 4), float(prices[j])]
                for j in sorted(keep)]
        # first touch time of each price, for anchoring the numbered markers
        ft = {}
        for s, p in zip(secs, x.Price.to_numpy()):
            ft.setdefault(float(p), round(float(s / span), 4))
        # ---- internals -------------------------------------------------------
        body = abs(c - o)
        ibs = (c - lo) / rng                              # internal bar strength
        top_v = float(lad.vol.iloc[0])
        bot_v = float(lad.vol.iloc[-1])
        dom = max(lad.delta.abs())

        bars.append({
            "i": i, "time": pd.Timestamp(m).strftime("%H:%M"),
            "o": o, "h": hi, "l": lo, "c": c,
            "delta": delta, "vol": vol, "poc": poc,
            "close_loc": round(ibs, 2),
            "ibs": round(ibs, 3),
            "body_pct": round(body / rng * 100, 1),
            "uw_pct": round((hi - max(o, c)) / rng * 100, 1),   # upper wick
            "lw_pct": round((min(o, c) - lo) / rng * 100, 1),   # lower wick
            "poc_loc": round((poc - lo) / rng, 2),
            "tail_top": round(top_v / vol * 100, 1),      # % of vol at the top tick
            "tail_bot": round(bot_v / vol * 100, 1),
            "dom_share": round(dom / vol * 100, 1),       # biggest print vs bar vol
            "n_imb": len(buy_imb) + len(sell_imb),
            "divergence": bool((delta > 0) != (c > o)) if abs(c - o) > 1e-9 else False,
            "range": round(hi - lo, 2),
            "eff": round(delta / vol * 100, 1),          # delta as % of volume
            "buy_imb": buy_imb, "sell_imb": sell_imb, "imb": detail,
            "n_imb_thin": sum(1 for q in detail if q["thin"]),
            "buy_stack": stacks(buy_imb), "sell_stack": stacks(sell_imb),
            "top_vol": float(lad.vol.iloc[0]), "bot_vol": float(lad.vol.iloc[-1]),
            "top_delta": int(lad.delta.iloc[0]), "bot_delta": int(lad.delta.iloc[-1]),
            "path": path, "first_touch": ft,
            "ladder": [[float(p), int(r.bid), int(r.ask), int(r.delta)]
                       for p, r in lad.iterrows()],
        })
    return bars


def sr_levels():
    """Support/resistance that is knowable in advance, not drawn after the fact."""
    mq = pd.read_csv(ROOT / "data" / "menthorq" / "ES1!_mq_levels_history.csv")
    mq["session_date"] = mq.session_date.astype(str).str[:10]
    row = mq[mq.session_date == "2026-07-17"]
    out = []
    if len(row):
        r = row.iloc[0]
        for col, lab in (("ps", "MQ Put Support"), ("cr", "MQ Call Resist"),
                         ("hvl", "MQ HVL"), ("d1_min", "MQ d1 min"),
                         ("d1_max", "MQ d1 max"), ("gex_1", "MQ GEX-1")):
            v = pd.to_numeric(r.get(col), errors="coerce")
            if np.isfinite(v):
                out.append({"price": float(v), "label": lab, "kind": "mq"})
    # prior session (7/16) reference — 7/17 gapped well below all of it
    pb = pd.read_csv(ROOT / "data" / "footprint" / "ES_bars.csv", parse_dates=["BarTime"])
    d = pb[pb.BarTime.dt.date.astype(str) == "2026-07-16"]
    if len(d):
        out += [{"price": float(d.High.max()), "label": "prior day HIGH", "kind": "pd"},
                {"price": float(d.Low.min()), "label": "prior day LOW", "kind": "pd"},
                {"price": float(d.Close.iloc[-1]), "label": "prior day CLOSE", "kind": "pd"}]
    return out


def enrich(bars):
    """Relative measures that need neighbours: ABR(8), RVOL(8), session VWAP, tag.

    ABR/RVOL use the PRIOR 8 bars only — never the current one — so a bar is
    measured against what came before it, not against itself.
    """
    for k, b in enumerate(bars):
        prev = bars[max(0, k - 8):k]
        abr = sum(p["range"] for p in prev) / len(prev) if prev else None
        avol = sum(p["vol"] for p in prev) / len(prev) if prev else None
        b["abr8"] = round(abr, 2) if abr else None
        b["rng_vs_abr"] = round(b["range"] / abr * 100) if abr else None
        b["rvol8"] = round(b["vol"] / avol, 2) if avol else None

        # heuristic descriptors — vocabulary for sorting bars later, NOT signals.
        # Nothing here is validated; it is a labelling aid on one session.
        t = []
        if b["rng_vs_abr"] and b["rng_vs_abr"] >= 170 and (b["rvol8"] or 0) >= 1.4:
            t.append("climax/expansion")
        if b["body_pct"] >= 60:
            t.append("trend bar")
        elif b["body_pct"] <= 25:
            t.append("doji/balance")
        if b["ibs"] >= 0.70 and b["delta"] < 0:
            t.append("absorption-low (buyers)")
        if b["ibs"] <= 0.30 and b["delta"] > 0:
            t.append("absorption-high (sellers)")
        if b["divergence"]:
            t.append("delta divergence")
        if b["tail_top"] >= 8:
            t.append("heavy at the high")
        if b["tail_bot"] >= 8:
            t.append("heavy at the low")
        if b["dom_share"] >= 12:
            t.append("single-print dominated")
        b["tags"] = t
    return bars


def main():
    bars = enrich(build())
    # cumulative session VWAP, from the ticks, as at each bar's close
    cum_pv = cum_v = 0.0
    for b in bars:
        for p, bid, ask, _d in b["ladder"]:
            v = bid + ask
            cum_pv += p * v
            cum_v += v
        b["vwap"] = round(cum_pv / cum_v, 2) if cum_v else None
    SR = sr_levels()
    (ROOT / "data" / "footprint" / "ES_1m_sr.json").write_text(
        json.dumps(SR, indent=1), encoding="utf-8")
    print("S/R levels:", ", ".join(f"{s['label']} {s['price']:.2f}" for s in SR))
    OUT.write_text(json.dumps(bars, indent=1), encoding="utf-8")
    print(f"wrote {OUT}  ({len(bars)} bars)\n")
    print(f"{'#':>3} {'time':>5} {'open':>8} {'high':>8} {'low':>8} {'close':>8} "
          f"{'delta':>7} {'vol':>7} {'eff%':>6} {'cl':>5} {'poc':>8}  imbalance stacks")
    for b in bars:
        st = []
        for a, z in b["buy_stack"]:
            st.append(f"BUY {z:.2f}-{a:.2f}")
        for a, z in b["sell_stack"]:
            st.append(f"SELL {z:.2f}-{a:.2f}")
        print(f"{b['i']:>3} {b['time']:>5} {b['o']:>8.2f} {b['h']:>8.2f} {b['l']:>8.2f} "
              f"{b['c']:>8.2f} {b['delta']:>7d} {b['vol']:>7d} {b['eff']:>6.1f} "
              f"{b['close_loc']:>5.2f} {b['poc']:>8.2f}  {'; '.join(st) if st else '-'}")


if __name__ == "__main__":
    main()
