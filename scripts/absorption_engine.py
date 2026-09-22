"""absorption_engine.py — precompute L2 ABSORPTION at each setup's pullback level.

For every book setup (2E families + rev + BO) on a day we have order-book data for, this
measures — right at the setup's `trigger` (second-entry / pullback) price, during the
pullback window — whether aggression AGAINST the trade was absorbed and the level held.
That is the order-flow tell the 2E/reversal book can't see from price alone.

SOURCES (one metric, two decoders):
  - Databento MBO (L3) for 2026-01-01..2026-07-20  (data/databento/GLBX-*/*.mbo.dbn.zst)
  - NT AddOn depth  for 2026-07-21..now            (data/depth/addon_test/*.parquet)

AGGRESSOR is AUTO-CALIBRATED, not assumed: over the day, we pick the side->buy/sell
mapping whose signed volume best tracks price change. (NT depth already labels A=buy;
Databento's trade `side` convention is confirmed per-day this way, then applied.)

OUTPUT (small, read by book_review's `absorb` toggle):
  <regime>/data/annotations/absorption/<date>.json
    { date, source, setups: [ {key, setup, dir, level, t0, t1,
        against, wth, delta, held, swept, absorbed, score,
        ladder: [ {px, buy, sell, net} ... ] } ] }

    python scripts/absorption_engine.py 2026-01-02            # one day
    python scripts/absorption_engine.py 2026-01-02 2026-07-24 # several
    python scripts/absorption_engine.py --all                 # every covered day
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

CT = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")
MAIN = Path(__file__).resolve().parents[1]
REGIME = MAIN.parent / "myquant-regime"
BOOK = REGIME / "data" / "annotations" / "book_review"
OUT = REGIME / "data" / "annotations" / "absorption"
DEPTH = MAIN / "data" / "depth" / "addon_test"
DBN = MAIN / "data" / "databento"

TICK = 0.25
ABS_TICKS = 3          # +/- ticks around the level counted as "at the level"
LADDER_TICKS = 8       # +/- ticks captured for the depth strip
POST_MIN = 10          # minutes after entry_bar to keep watching the level
HOLD_TICKS = 4         # a break of > this many ticks through the level = swept


# --------------------------------------------------------------- setups + times
def _load_setups(date: str):
    f = BOOK / f"{date}.json"
    if not f.exists():
        return None
    d = json.loads(f.read_text())
    bars = d.get("bars") or []
    if not bars:
        return None
    # bar = [i, "HH:MM", O,H,L,C,EMA] in CT; map bar index -> CT datetime
    def bar_ct(i):
        i = max(0, min(len(bars) - 1, int(i)))
        hh, mm = bars[i][1].split(":")
        return dt.datetime.fromisoformat(f"{date}T{hh}:{mm}:00").replace(tzinfo=CT)
    bars_ct = [(bar_ct(i), float(bars[i][5])) for i in range(len(bars))]  # (t, close) for basis
    out = []
    for k, t in enumerate(d.get("trades") or []):
        lvl = t.get("trigger") if t.get("trigger") is not None else t.get("entry_px")
        if lvl is None or t.get("dir") not in ("L", "S"):
            continue
        sig = t.get("sig_bar", t.get("entry_bar"))
        t0 = bar_ct(sig)
        t1 = bar_ct(t.get("entry_bar", sig)) + dt.timedelta(minutes=POST_MIN)
        out.append({"key": f"{t.get('setup','?')}#{k}", "setup": t.get("setup", "?"),
                    "dir": t["dir"], "level": float(lvl),
                    "stop": (float(t["stop"]) if t.get("stop") is not None else None),
                    "net": t.get("net"), "t0": t0, "t1": t1})
    return {"date": date, "setups": out, "bars_ct": bars_ct}


def _basis_offset(trades: pd.DataFrame, bars_ct) -> float:
    """The book uses a back-adjusted CONTINUOUS series; raw MBO is the front CONTRACT.
    Align them: per 5M book bar, offset = book_close - median(source price in that bar).
    Return the median offset (points) to add to source prices so they match book levels.
    ~0 for NT-depth days (same basis); ~roll gap for older MBO days."""
    if trades is None or trades.empty or not bars_ct:
        return 0.0
    tt = trades["ts"].dt.tz_convert(UTC).dt.tz_localize(None).to_numpy()   # once
    px = trades["price"].astype(float).to_numpy()
    offs = []
    for t, close in bars_ct:
        t0 = np.datetime64(t.astimezone(UTC).replace(tzinfo=None))
        t1 = t0 + np.timedelta64(5, "m")
        m = (tt >= t0) & (tt < t1)
        if m.any():
            offs.append(close - float(np.median(px[m])))
    if not offs:
        return 0.0
    return float(round(np.median(offs) / TICK) * TICK)


# --------------------------------------------------------------- decoders -> trades
def _mbo_file(date: str):
    tag = date.replace("-", "")
    hits = glob.glob(str(DBN / "GLBX-*" / "**" / f"glbx-mdp3-{tag}.mbo.dbn.zst"),
                     recursive=True)
    return hits[0] if hits else None


def _trades_mbo(path: str):
    """Return trade DataFrame [ts(CT), price, size, side] for the front-month OUTRIGHT."""
    import databento as db
    df = db.DBNStore.from_file(path).to_df()
    df = df[df["action"] == "T"]
    if df.empty:
        return df
    # outright front month = highest-volume symbol with no '-' (spreads excluded)
    outs = df[~df["symbol"].str.contains("-", na=False)]
    if outs.empty:
        return outs
    sym = outs.groupby("symbol")["size"].sum().idxmax()
    df = outs[outs["symbol"] == sym].copy()
    ts = df.index if df.index.name in ("ts_recv", "ts_event") else df["ts_event"]
    df["ts"] = pd.to_datetime(ts, utc=True).tz_convert(CT)
    return df[["ts", "price", "size", "side"]].reset_index(drop=True)


TAPE_CACHE = MAIN / "data" / "depth" / "tape_cache"


def tape(date: str):
    """Normalized trade tape [ts(CT), price, size, side] for a date, CACHED to parquet
    so the ~50s MBO decode runs once. Source: NT depth (>=07-21) else Databento MBO."""
    TAPE_CACHE.mkdir(parents=True, exist_ok=True)
    cf = TAPE_CACHE / f"{date}.parquet"
    if cf.exists():
        df = pd.read_parquet(cf)
        return df.attrs.get("source", "cache"), df
    if (DEPTH / f"ES_09-26_depth_{date}.parquet").exists():
        src, df = "nt_depth", _trades_depth(date)
    else:
        mf = _mbo_file(date)
        if not mf:
            return None, None
        src, df = "mbo", _trades_mbo(mf)
    if df is None or df.empty:
        return src, df
    df = df.copy()
    df["source"] = src
    df.to_parquet(cf, index=False)
    return src, df


def _trades_depth(date: str):
    """NT AddOn depth: T rows only. Our recorder writes Side='A' for BUY aggressor."""
    f = DEPTH / f"ES_09-26_depth_{date}.parquet"
    if not f.exists():
        return None
    df = pd.read_parquet(f, columns=["Time", "Ev", "Side", "Price", "Size"])
    df = df[df["Ev"] == "T"].copy()
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["Time"]).dt.tz_localize(CT)
    df["price"] = df["Price"]; df["size"] = df["Size"]; df["side"] = df["Side"]
    return df[["ts", "price", "size", "side"]].reset_index(drop=True)


def _calibrate_buy(df: pd.DataFrame) -> str:
    """Pick which `side` value means BUY-aggressor by whichever choice makes signed
    volume track price change over the day. Returns the side-string that == buy."""
    if df.empty:
        return "A"
    d = df.copy()
    d["m"] = d["price"].astype(float)
    # 1-min signed-volume vs price change, for each hypothesis (buy=='A' vs buy=='B')
    g = d.set_index("ts")
    best, best_corr = "A", -9
    for buy_side in sorted(d["side"].dropna().unique()):
        sgn = np.where(d["side"] == buy_side, 1, -1) * d["size"].astype(float)
        sv = pd.Series(sgn.values, index=g.index).resample("1min").sum()
        pc = g["m"].resample("1min").last().diff()
        c = sv.corr(pc)
        if pd.notna(c) and c > best_corr:
            best_corr, best = c, buy_side
    return best


# --------------------------------------------------------------- metric
def _absorb(setups, trades: pd.DataFrame, buy_side: str, source: str):
    out = []
    if trades is None or trades.empty:
        return out
    tr = trades.copy()
    tr["buy"] = tr["side"] == buy_side
    tr["pt"] = (tr["price"].astype(float) / TICK).round().astype(int)
    for s in setups:
        lp = int(round(s["level"] / TICK))
        win = tr[(tr["ts"] >= s["t0"]) & (tr["ts"] <= s["t1"])]   # ALL window trades
        w = win[win["pt"].sub(lp).abs() <= ABS_TICKS]             # only those AT the level
        if w.empty:
            out.append({**_meta(s), "n": 0, "note": "no trades at level in window"})
            continue
        long = s["dir"] == "L"
        # aggression AGAINST the trade = selling for a long (into support), buying for a short
        against = int(w.loc[w["buy"] != long, "size"].sum())
        wth = int(w.loc[w["buy"] == long, "size"].sum())
        # SWEPT = price reached the setup's own STOP within the window (decisive failure,
        # anchored to the trade's invalidation — not an arbitrary buffer). A winner that
        # only wicks a tick past the level but never hits stop stays HELD.
        stop = s.get("stop")
        sp = int(round(stop / TICK)) if stop is not None else (
            lp - HOLD_TICKS if long else lp + HOLD_TICKS)
        if long:
            swept = bool((win["pt"] <= sp).any())
            adverse = int(lp - win["pt"].min())          # ticks below the level
        else:
            swept = bool((win["pt"] >= sp).any())
            adverse = int(win["pt"].max() - lp)          # ticks above the level
        held = not swept
        absorbed = against if held else 0
        score = round(absorbed / max(wth, 1), 2)          # against-vol absorbed per with-vol
        # ladder for the depth strip: buy/sell vol per tick around the level
        lad = []
        for pt in range(lp - LADDER_TICKS, lp + LADDER_TICKS + 1):
            ww = w[w["pt"] == pt]
            b = int(ww.loc[ww["buy"], "size"].sum())
            se = int(ww.loc[~ww["buy"], "size"].sum())
            if b or se:
                lad.append({"px": round(pt * TICK, 2), "buy": b, "sell": se, "net": b - se})
        out.append({**_meta(s), "n": int(len(w)), "against": against, "wth": wth,
                    "delta": wth - against, "held": held, "swept": swept,
                    "adverse_ticks": adverse, "absorbed": absorbed, "score": score,
                    "net": s.get("net"), "ladder": lad})
    return out


def _meta(s):
    return {"key": s["key"], "setup": s["setup"], "dir": s["dir"],
            "level": s["level"], "t0": s["t0"].strftime("%H:%M"),
            "t1": s["t1"].strftime("%H:%M")}


# --------------------------------------------------------------- driver
def run_day(date: str) -> dict | None:
    su = _load_setups(date)
    if not su:
        print(f"  {date}: no book day / no bars — skip"); return None
    if not su["setups"]:
        print(f"  {date}: 0 setups — skip"); return None
    depth = DEPTH / f"ES_09-26_depth_{date}.parquet"
    if depth.exists():
        source, trades = "nt_depth", _trades_depth(date)
    else:
        mf = _mbo_file(date)
        if not mf:
            print(f"  {date}: no MBO and no NT depth — skip"); return None
        source, trades = "mbo", _trades_mbo(mf)
    if trades is None or trades.empty:
        print(f"  {date}: source {source} had no trades — skip"); return None
    offset = _basis_offset(trades, su.get("bars_ct"))
    if offset:
        trades = trades.assign(price=trades["price"].astype(float) + offset)
    buy_side = _calibrate_buy(trades)
    res = _absorb(su["setups"], trades, buy_side, source)
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"date": date, "source": source, "buy_side": buy_side,
               "basis_offset": offset, "n_setups": len(res), "setups": res}
    (OUT / f"{date}.json").write_text(json.dumps(payload, indent=1))
    hit = [r for r in res if r.get("n")]
    print(f"  {date}: [{source}] buy_side={buy_side} · {len(res)} setups, "
          f"{len(hit)} with trades at level")
    for r in hit:
        nt = r.get("net")
        print(f"      {r['setup']:>5} {r['dir']} @ {r['level']:.2f}  "
              f"against={r['against']:>5} wth={r['wth']:>5} adv={r.get('adverse_ticks'):>3}t "
              f"{'HELD ' if r['held'] else 'SWEPT'} score={r['score']:<4} "
              f"trade_net={'' if nt is None else nt}")
    return payload


def _all_days():
    days = set()
    for f in glob.glob(str(DBN / "GLBX-*" / "**" / "glbx-mdp3-*.mbo.dbn.zst"),
                       recursive=True):
        tag = Path(f).name.split("glbx-mdp3-")[1][:8]
        days.add(f"{tag[:4]}-{tag[4:6]}-{tag[6:]}")
    for f in glob.glob(str(DEPTH / "ES_09-26_depth_*.parquet")):
        days.add(Path(f).stem.split("_depth_")[1])
    return sorted(d for d in days if (BOOK / f"{d}.json").exists())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dates", nargs="*", help="YYYY-MM-DD (one or more)")
    ap.add_argument("--all", action="store_true", help="every covered book day")
    a = ap.parse_args()
    dates = _all_days() if a.all else a.dates
    if not dates:
        print("give dates or --all"); return 1
    print(f"absorption engine — {len(dates)} day(s)")
    for d in dates:
        try:
            run_day(d)
        except Exception as e:
            print(f"  {d}: ERROR {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
