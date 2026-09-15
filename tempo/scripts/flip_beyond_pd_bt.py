"""flip_beyond_pd_bt.py — backtest the WHOLE-CHART beyond-prior-day spring/upthrust
detector (feature #2 in TempoSpeedometer.cs) with the same train/test discipline as
the climax-flip Wyckoff study.

Event (matches the indicator exactly):
  Spring   = Low < PDL and Close >= PDL and prior-bar Low >= PDL   -> LONG
  Upthrust = High > PDH and Close <= PDH and prior-bar High <= PDH -> SHORT
  (PDH/PDL = prior session high/low; only the FIRST breach bar counts)

Wyckoff type (Event 5, three factors combined — matches the indicator):
  intensity = (depth + volume + range) / 3, each vs the prior-8-bar average;
  <=0.85 = #3 (slight/low/narrow, best) .. >=1.50 = #1 Terminal Shakeout (deep/high/wide).
  Pre-registered: #3 (low intensity) should beat #1 (high intensity).

Mechanics (frozen, mirror the flip harness): enter at the breach-bar CLOSE, stop 1t
beyond the poke extreme, RR2 target, one position at a time per session, conservative
both-in-bar -> stop, session-end close.

Questions answered:
  A) does the beyond-PD event have ANY edge (spring / upthrust / combined)?
  B) does the low-vol tier beat the high-vol tier, TRAIN and TEST? (validate the tiers)

    python tempo/scripts/flip_beyond_pd_bt.py
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
OUT = ROOT / "tempo" / "outputs"
TICK = 0.25
PT_USD = 50.0
RR = 2
TRAIN_MAX = 2022
LOW_INT, HIGH_INT = 0.85, 1.50      # shipped indicator defaults (Shakeout intensity cutoffs)


def sessions(df):
    """yield (date, year, arrays...) with prior-session H/L attached."""
    days = sorted(df["date"].unique())
    prev_hi = prev_lo = np.nan
    for d in days:
        g = df[df.date == d].reset_index(drop=True)
        yield {
            "date": d, "year": int(str(d)[:4]),
            "o": g["open"].to_numpy(), "h": g["high"].to_numpy(),
            "l": g["low"].to_numpy(), "c": g["close"].to_numpy(),
            "v": g["vol"].to_numpy(dtype=float), "n": len(g),
            "pdh": prev_hi, "pdl": prev_lo,
        }
        prev_hi, prev_lo = g["high"].max(), g["low"].min()


def detect(s):
    """return list of events: dict(i, short, tier, ratio). ratio = combined intensity."""
    h, l, c, v, n = s["h"], s["l"], s["c"], s["v"], s["n"]
    rng = h - l
    pdh, pdl = s["pdh"], s["pdl"]
    ev = []
    for i in range(1, n):
        ut = not np.isnan(pdh) and h[i] > pdh and c[i] <= pdh and h[i - 1] <= pdh
        sp = not np.isnan(pdl) and l[i] < pdl and c[i] >= pdl and l[i - 1] >= pdl
        if not (ut or sp):
            continue
        avR = rng[max(0, i - 8):i].mean() if i > 0 else rng[i]
        avV = v[max(0, i - 8):i].mean() if i > 0 else v[i]
        pen = (h[i] - pdh) if ut else (pdl - l[i])
        pen_f = pen / avR if avR > 0 else 1.0
        vol_r = v[i] / avV if avV > 0 else 1.0
        rng_r = rng[i] / avR if avR > 0 else 1.0
        inten = (pen_f + vol_r + rng_r) / 3.0                 # Wyckoff 3 factors combined
        tier = 0 if inten <= LOW_INT else (2 if inten >= HIGH_INT else 1)  # 0 #3 best .. 2 #1 terminal
        ev.append({"i": i, "short": ut, "tier": tier, "ratio": inten})
    return ev


def sim(s):
    """one-at-a-time; enter breach close, stop beyond poke, RR2. returns trades."""
    h, l, c, n = s["h"], s["l"], s["c"], s["n"]
    ev = {e["i"]: e for e in detect(s)}
    trades = []
    pos = None      # (short, en, st, tg, rk, ev)
    for i in range(1, n):
        if pos is not None:
            short, en, st, tg, rk, e = pos
            if (h[i] >= st) if short else (l[i] <= st):
                trades.append({**e, "pnl": -rk, "res": "stop"}); pos = None
            elif (l[i] <= tg) if short else (h[i] >= tg):
                trades.append({**e, "pnl": RR * rk, "res": "target"}); pos = None
        if pos is not None:
            continue
        if i in ev:
            e = ev[i]; short = e["short"]
            en = c[i]
            st = (h[i] + TICK) if short else (l[i] - TICK)
            rk = abs(en - st)
            if rk < TICK:
                continue
            sg = -1 if short else 1
            pos = (short, en, st, en + sg * RR * rk, rk, e)
    if pos is not None:
        short, en, e = pos[0], pos[1], pos[5]
        trades.append({**e, "pnl": (c[n - 1] - en) * (-1 if short else 1), "res": "eod"})
    return trades


def pf(p):
    p = np.asarray(p, float); gp = p[p > 0].sum(); gl = -p[p < 0].sum()
    return (gp / gl) if gl > 0 else np.inf


def blk(df, label):
    if len(df) == 0:
        return {"split": label, "n": 0, "win%": np.nan, "PF": np.nan, "$/tr": np.nan, "tot_$": 0.0}
    p = df["pnl"].to_numpy(float)
    return {"split": label, "n": len(p), "win%": round(100 * (p > 0).mean(), 1),
            "PF": round(pf(p), 2), "$/tr": round(p.mean() * PT_USD, 1),
            "tot_$": round(p.sum() * PT_USD, 0)}


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    trades = []
    for s in sessions(df):
        for t in sim(s):
            t["year"] = s["year"]; trades.append(t)
    tr = pd.DataFrame(trades)
    tr.to_csv(OUT / f"flip_beyond_pd_trades_{today}.csv", index=False)
    train = tr[tr.year <= TRAIN_MAX]; test = tr[tr.year > TRAIN_MAX]
    print(f"beyond-PD events: {len(tr)} trades {tr.year.min()}-{tr.year.max()} "
          f"(springs {int((~tr.short).sum())} / upthrusts {int(tr.short.sum())})")

    print("\n=== A) RAW EDGE (any edge at all?) ===")
    rows = [blk(tr, "ALL"), blk(tr[~tr.short], "springs (LONG)"), blk(tr[tr.short], "upthrusts (SHORT)"),
            blk(train, "TRAIN 21-22"), blk(test, "TEST 23-26")]
    a = pd.DataFrame(rows); print(a.to_string(index=False))

    print("\n=== B) BY VOLUME TIER (pre-registered: low #3 > high #1) ===")
    rows = []
    for tag, name in [(0, "#3 low-vol (best?)"), (1, "#2 mid"), (2, "#1 high-vol (terminal?)")]:
        rows.append({"tier": name,
                     **{k: v for k, v in blk(tr[tr.tier == tag], "").items() if k != "split"}})
    b_all = pd.DataFrame(rows); print("ALL:"); print(b_all.to_string(index=False))
    for period, sub in [("TRAIN 21-22", train), ("TEST 23-26", test)]:
        rows = []
        for tag, name in [(0, "#3 low"), (1, "#2 mid"), (2, "#1 high")]:
            rows.append({"tier": name,
                         **{k: v for k, v in blk(sub[sub.tier == tag], "").items() if k != "split"}})
        print(f"\n{period}:"); print(pd.DataFrame(rows).to_string(index=False))

    # continuous monotonicity check (train terciles applied to test)
    print("\n=== B') continuous ratio terciles (train cuts -> test), sign stability ===")
    q1, q2 = train["ratio"].quantile([1 / 3, 2 / 3])
    def terc(sub):
        return [round(sub[sub.ratio <= q1].pnl.mean() * PT_USD, 1),
                round(sub[(sub.ratio > q1) & (sub.ratio <= q2)].pnl.mean() * PT_USD, 1),
                round(sub[sub.ratio > q2].pnl.mean() * PT_USD, 1)]
    print(f"cuts @ {q1:.2f}, {q2:.2f}")
    print(f"  TRAIN T1/T2/T3 $/tr = {terc(train)}")
    print(f"  TEST  T1/T2/T3 $/tr = {terc(test)}")
    lo_t, hi_t = terc(train), terc(test)
    verdict = "TIERS VALID" if (lo_t[0] > lo_t[2] and hi_t[0] > hi_t[2]) else "tiers NOT confirmed"
    print(f"  low-vol beats high-vol both periods? -> {verdict}")

    a.to_csv(OUT / f"flip_beyond_pd_raw_{today}.csv", index=False)
    b_all.to_csv(OUT / f"flip_beyond_pd_tiers_{today}.csv", index=False)


if __name__ == "__main__":
    main()
