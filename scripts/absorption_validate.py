"""absorption_validate.py — does L2 absorption at the PB level predict trade outcome?

The gate before trusting any absorption overlay. Tests TWO families that carry real P&L:

  MC : pullback ENTRIES at the 33 / 50 / 66% retracement of the signal->stop leg
       (SignalPrice -> StopPrice). We measure absorption at EACH fib level price
       actually reached, and correlate with the trade's R_achieved.
  2E : the book's second-entry trades at their `trigger`, correlated with net P&L.

At each level, in a window bracketing the signal, on the CACHED order-book tape:
  against = aggressive vol OPPOSING the trade at the level (sellers for a long, v.v.)
  delta   = with - against;  adverse = ticks price ran past the level against the trade
  held    = price did not run > HOLD_TICKS past the level in the window
Then: do held / high-against levels precede better outcomes? If not -> decoration.

Tape is cached (absorption_engine.tape) so re-runs at new levels are instant.

    python scripts/absorption_validate.py                # all covered days, both families
    python scripts/absorption_validate.py --family mc    # mc only
    python scripts/absorption_validate.py --max 30
Output: data/depth/absorption_validation_<stamp>.csv + printed summary.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import absorption_engine as ae

MC = ae.MAIN / "data" / "regime" / "mc_regime_filter_trades_20260725.parquet"
OUT = ae.MAIN / "data" / "depth"
FIBS = [0.33, 0.50, 0.66]
ABS_TICKS = 3
HOLD_TICKS = 8
PRE_MIN, POST_MIN = 3, 30      # pullback to the fib levels happens AFTER the signal


def _mc():
    df = pd.read_parquet(MC, columns=["Date", "EntryTime", "DateTime", "Direction",
                                      "SignalType", "SignalPrice", "StopPrice",
                                      "Filled", "R_achieved", "NetPnL"])
    df["day"] = pd.to_datetime(df["Date"]).dt.date.astype(str)
    df = df[(df["day"] >= "2026-01-01") & (df["day"] <= "2026-07-30") & (df["Filled"] == True)].copy()
    df["dir"] = np.where(df["Direction"].str.lower().str.startswith("l"), "L", "S")
    df["et"] = pd.to_datetime(df["EntryTime"].fillna(df["DateTime"]))
    return df


def _prep_tape(day):
    src, tp = ae.tape(day)
    if tp is None or tp.empty:
        return None, None
    su = ae._load_setups(day)
    off = ae._basis_offset(tp, su.get("bars_ct")) if su else 0.0
    if off:
        tp = tp.assign(price=tp["price"].astype(float) + off)
    buy = ae._calibrate_buy(tp)
    tp = tp.assign(buy=(tp["side"] == buy),
                   pt=(tp["price"].astype(float) / ae.TICK).round().astype(int))
    return src, tp


def _measure(tp, level, dir_long, t0, t1):
    lp = int(round(level / ae.TICK))
    win = tp[(tp["ts"] >= t0) & (tp["ts"] <= t1)]
    w = win[win["pt"].sub(lp).abs() <= ABS_TICKS]
    if w.empty:
        return None                          # price never reached this level -> not tested
    against = int(w.loc[w["buy"] != dir_long, "size"].sum())
    wth = int(w.loc[w["buy"] == dir_long, "size"].sum())
    adverse = int((lp - win["pt"].min()) if dir_long else (win["pt"].max() - lp))
    return {"against": against, "wth": wth, "delta": wth - against,
            "adverse": adverse, "held": adverse <= HOLD_TICKS}


def _score_day(day, mc, do_mc, do_2e):
    src, tp = _prep_tape(day)
    if tp is None:
        return []
    rows = []
    if do_mc:
        for _, t in mc.iterrows():
            et = t["et"];  et = et.tz_localize(ae.CT) if et.tzinfo is None else et
            t0, t1 = et - pd.Timedelta(minutes=PRE_MIN), et + pd.Timedelta(minutes=POST_MIN)
            long = t["dir"] == "L"
            sig, stop = float(t["SignalPrice"]), float(t["StopPrice"])
            for fb in FIBS:
                lvl = sig - fb * (sig - stop)     # long: sig high -> stop below; short mirrors
                m = _measure(tp, lvl, long, t0, t1)
                if m:
                    rows.append({"fam": "MC", "day": day, "src": src, "sig": t["SignalType"],
                                 "dir": t["dir"], "fib": fb, "level": round(lvl, 2), **m,
                                 "R": float(t["R_achieved"]) if pd.notna(t["R_achieved"]) else np.nan,
                                 "win": (1 if (pd.notna(t["R_achieved"]) and t["R_achieved"] > 0) else 0)})
    if do_2e:
        su = ae._load_setups(day)
        for s in (su.get("setups") if su else []):
            m = _measure(tp, s["level"], s["dir"] == "L",
                         s["t0"] - pd.Timedelta(minutes=PRE_MIN), s["t1"])
            if m and s.get("net") is not None:
                rows.append({"fam": "2E", "day": day, "src": src, "sig": s["setup"],
                             "dir": s["dir"], "fib": np.nan, "level": s["level"], **m,
                             "R": np.nan, "win": (1 if s["net"] > 0 else 0), "net": s["net"]})
    return rows


def _blk(name, sub, lines, val="win"):
    if len(sub) < 15:
        lines.append(f"  {name}: n={len(sub)} (too few)"); return
    r = sub["R"].mean() if "R" in sub and sub["R"].notna().any() else np.nan
    lines.append(f"  {name}: n={len(sub):>4}  win%={sub['win'].mean()*100:5.1f}"
                 + (f"  meanR={r:+.2f}" if not np.isnan(r) else ""))


def _report(df, lines):
    for fam in ["MC", "2E"]:
        f = df[df["fam"] == fam]
        if f.empty:
            continue
        lines.append(f"\n===== {fam}  ({len(f)} level-tests, {f['day'].nunique()} days) =====")
        _blk("ALL", f, lines)
        _blk("HELD", f[f["held"]], lines)
        _blk("SWEPT", f[~f["held"]], lines)
        if fam == "MC":
            for fb in FIBS:
                _blk(f"fib {int(fb*100)}%", f[f["fib"] == fb], lines)
                _blk(f"  fib {int(fb*100)}% + HELD", f[(f["fib"] == fb) & f["held"]], lines)
        lines.append("  by AGAINST-volume quartile:")
        try:
            g = f.assign(q=pd.qcut(f["against"], 4, labels=[1, 2, 3, 4], duplicates="drop"))
            for q, gg in g.groupby("q", observed=True):
                _blk(f"    Q{q}", gg, lines)
        except Exception as e:
            lines.append(f"    (quartiles n/a: {e})")
        strong = f[f["held"] & (f["against"] >= f["against"].median())]
        _blk("STRONG (held & against>=median)", strong, lines)
        _blk("REST", f.drop(strong.index), lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0)
    ap.add_argument("--family", choices=["mc", "2e", "both"], default="both")
    a = ap.parse_args()
    do_mc, do_2e = a.family in ("mc", "both"), a.family in ("2e", "both")
    mc = _mc()
    days = sorted(set(mc["day"]) | ({d for d in _cov_2e()} if do_2e else set()))
    if a.max:
        days = days[:a.max]
    print(f"validation — {len(mc)} MC trades, {len(days)} days, family={a.family}")
    rows = []
    for i, d in enumerate(days):
        try:
            rows += _score_day(d, mc[mc["day"] == d], do_mc, do_2e)
            print(f"  [{i+1}/{len(days)}] {d}", flush=True)
        except Exception as e:
            print(f"  {d}: ERROR {type(e).__name__}: {e}")
    if not rows:
        print("no rows"); return 1
    df = pd.DataFrame(rows)
    stamp = days[-1].replace("-", "")
    df.to_csv(OUT / f"absorption_validation_{stamp}.csv", index=False)
    lines = [f"L2 ABSORPTION vs OUTCOME — {len(df)} level-tests over {len(days)} days",
             f"MC fib pb levels {[int(f*100) for f in FIBS]}% of signal->stop · 2E trigger · "
             f"held=adverse<={HOLD_TICKS}t · window[-{PRE_MIN},+{POST_MIN}]min"]
    _report(df, lines)
    rep = "\n".join(lines)
    print("\n" + rep)
    (OUT / f"absorption_validation_{stamp}.txt").write_text(rep, encoding="utf-8")
    return 0


def _cov_2e():
    import glob
    ds = set()
    for f in glob.glob(str(ae.BOOK / "2026-*.json")):
        d = Path(f).stem
        if "2026-01-01" <= d <= "2026-07-30":
            ds.add(d)
    return ds


if __name__ == "__main__":
    sys.exit(main())
