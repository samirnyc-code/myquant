"""Build a 24-hour (ETH+RTH) continuous 1-minute ES series from the NT tick
exports in data/nt_import/ES_MAS *.Last.txt — validated tick-for-tick against
eth_levels.parquet. Panama-stitched with the repo roll table (contracts.py).
Output: data/bars/_continuous_1m_24h.parquet  (DateTime, Open, High, Low, Close, Volume)
"""
import glob, json, os, time
from pathlib import Path
import pandas as pd, numpy as np
import pyarrow.csv as pv

ROOT = Path(r"c:\Users\Admin\myquant")
os.chdir(ROOT)
import sys; sys.path.insert(0, str(ROOT))
from contracts import get_contract_windows, CATALOG

MCODE = {"03": "H", "06": "M", "09": "U", "12": "Z"}


def fname_to_ticker(f):
    # "ES_MAS 06-26.Last.txt" -> ESM6
    stem = os.path.basename(f).replace("ES_MAS ", "").replace(".Last.txt", "")
    mm, yy = stem.split("-")
    return f"ES{MCODE[mm]}{yy[-1]}"


def main():
    t0 = time.time()
    rolls = json.load(open("rolls.json"))
    windows = get_contract_windows([c.ticker for c in CATALOG], rolls)
    win = {w["ticker"]: w for w in windows}
    files = sorted(glob.glob("data/nt_import/ES_MAS *.Last.txt"))
    parts = []
    for i, f in enumerate(files, 1):
        tk = fname_to_ticker(f)
        w = win.get(tk)
        if w is None:
            print(f"[{i}/{len(files)}] {tk}: NO window, skip", flush=True); continue
        t = pv.read_csv(f, read_options=pv.ReadOptions(column_names=["ts", "price", "vol"]),
                        parse_options=pv.ParseOptions(delimiter=";")).to_pandas()
        t["dt"] = pd.to_datetime(t["ts"], format="%Y%m%d %H%M%S")
        t = t.set_index("dt").sort_index()
        # active window [start, end)
        start = pd.Timestamp(w["start"]); end = pd.Timestamp(w["end"]) if w["end"] else t.index.max() + pd.Timedelta(days=1)
        t = t[(t.index >= start) & (t.index < end)]
        if t.empty:
            print(f"[{i}/{len(files)}] {tk}: 0 active ticks", flush=True); continue
        off = float(w["cum_offset"])
        p = t["price"].values + off
        px = pd.Series(p, index=t.index)
        g = px.resample("1min")
        b = pd.DataFrame({"Open": g.first(), "High": g.max(), "Low": g.min(), "Close": g.last(),
                          "Volume": t["vol"].resample("1min").sum()}).dropna(subset=["Open"])
        b = b[b["Volume"] > 0]
        parts.append(b)
        print(f"[{i}/{len(files)}] {tk}: {len(t):,} ticks -> {len(b):,} 1m bars "
              f"[{b.index.min()} .. {b.index.max()}] off={off:+.2f}  {time.time()-t0:.0f}s", flush=True)
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    out = out.reset_index().rename(columns={"index": "DateTime"})
    dst = "data/bars/_continuous_1m_24h.parquet"
    out.to_parquet(dst, index=False)
    # coverage report
    hrs = out["DateTime"].dt.hour.value_counts().sort_index()
    print(f"\nWROTE {dst}: {len(out):,} bars  [{out.DateTime.min()} .. {out.DateTime.max()}]", flush=True)
    print("hours present:", sorted(out['DateTime'].dt.hour.unique()), flush=True)
    print(f"done in {(time.time()-t0)/60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
