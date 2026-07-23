"""Build a per-SESSION 24h ES tick cache from the NT exports — S83-ETH stage 1.

Source: MAIN repo data/nt_import/ES_MAS *.Last.txt (tick-level, 17:00 session open,
validated tick-for-tick vs eth_levels in S82). Panama-stitched with the repo roll
table (contracts.py + rolls.json), same as the validated 24h 1m builder.

Session convention: the ETH session belongs to the RTH date it leads into —
ticks with machine-time >= 17:00 roll to the NEXT calendar date; 16:00-17:00
maintenance ticks dropped. So session "2024-03-14" = 2024-03-13 17:00 -> 2024-03-14 16:00.

Output (gitignored, ~6GB):
  data/regime_eth/ticks/<session-date>.parquet   (DateTime, Price, Volume)
  data/regime_eth/_eth_5m.parquet                (5m bars, all sessions, committed)

  python scripts/eth_build_tick_cache.py
"""
import glob, json, os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.csv as pv

WT_ROOT = Path(__file__).resolve().parent.parent
MAIN = Path(r"C:/Users/Admin/myquant")
sys.path.insert(0, str(WT_ROOT))
from contracts import get_contract_windows, CATALOG  # noqa: E402

OUTD = WT_ROOT / "data" / "regime_eth"
TICKD = OUTD / "ticks"
MCODE = {"03": "H", "06": "M", "09": "U", "12": "Z"}


def fname_to_ticker(f):
    stem = os.path.basename(f).replace("ES_MAS ", "").replace(".Last.txt", "")
    mm, yy = stem.split("-")
    return f"ES{MCODE[mm]}{yy[-1]}"


def main():
    t0 = time.time()
    TICKD.mkdir(parents=True, exist_ok=True)
    rolls = json.load(open(WT_ROOT / "rolls.json"))
    windows = get_contract_windows([c.ticker for c in CATALOG], rolls)
    win = {w["ticker"]: w for w in windows}
    files = sorted(glob.glob(str(MAIN / "data" / "nt_import" / "ES_MAS *.Last.txt")))
    bar_parts = []
    for i, f in enumerate(files, 1):
        tk = fname_to_ticker(f)
        w = win.get(tk)
        if w is None:
            print(f"[{i}/{len(files)}] {tk}: NO window, skip", flush=True); continue
        t = pv.read_csv(f, read_options=pv.ReadOptions(column_names=["ts", "price", "vol"]),
                        parse_options=pv.ParseOptions(delimiter=";")).to_pandas()
        t["dt"] = pd.to_datetime(t["ts"], format="%Y%m%d %H%M%S")
        t = t.drop(columns=["ts"]).sort_values("dt", kind="stable")
        start = pd.Timestamp(w["start"])
        end = pd.Timestamp(w["end"]) if w["end"] else t["dt"].max() + pd.Timedelta(days=1)
        t = t[(t.dt >= start) & (t.dt < end)]
        if t.empty:
            print(f"[{i}/{len(files)}] {tk}: 0 active ticks", flush=True); continue
        t["price"] = t["price"] + float(w["cum_offset"])
        hr = t.dt.dt.hour
        t = t[(hr < 16) | (hr >= 17)]                       # drop maintenance
        sess = (t.dt + pd.Timedelta(hours=7)).dt.date.astype(str)   # >=17:00 -> next day
        t = t.assign(session=sess)
        ndays = 0
        for dstr, g in t.groupby("session", sort=True):
            g = g[["dt", "price", "vol"]].rename(
                columns={"dt": "DateTime", "price": "Price", "vol": "Volume"})
            p = TICKD / f"{dstr}.parquet"
            if p.exists():                                   # roll-boundary session: merge
                old = pd.read_parquet(p)
                g = pd.concat([old, g]).sort_values("DateTime", kind="stable")
            g.to_parquet(p, index=False)
            ndays += 1
        # 5m bars for this contract slice
        px = t.set_index("dt")["price"]
        gg = px.resample("5min")
        b = pd.DataFrame({"Open": gg.first(), "High": gg.max(), "Low": gg.min(),
                          "Close": gg.last(),
                          "Volume": t.set_index("dt")["vol"].resample("5min").sum()}
                         ).dropna(subset=["Open"])
        b = b[b["Volume"] > 0]
        bar_parts.append(b)
        print(f"[{i}/{len(files)}] {tk}: {len(t):,} ticks -> {ndays} sessions "
              f"({time.time()-t0:.0f}s)", flush=True)
        del t, px, b
    bars = pd.concat(bar_parts).sort_index()
    bars = bars[~bars.index.duplicated(keep="last")].reset_index().rename(
        columns={"index": "DateTime", "dt": "DateTime"})
    bars.columns = ["DateTime", "Open", "High", "Low", "Close", "Volume"]
    bars["Session"] = (bars.DateTime + pd.Timedelta(hours=7)).dt.date.astype(str)
    bars.to_parquet(OUTD / "_eth_5m.parquet", index=False)
    ndays = len(list(TICKD.glob("*.parquet")))
    print(f"\nDONE {(time.time()-t0)/60:.1f} min  sessions={ndays}  "
          f"5m bars={len(bars):,} -> {OUTD/'_eth_5m.parquet'}", flush=True)


if __name__ == "__main__":
    main()
