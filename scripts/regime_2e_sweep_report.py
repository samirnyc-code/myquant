"""P0 report over the sweeps output: stop/target matrix, regime variants, TOD, features.

Reads:
  data/regime/second_entries_stop_target_sweep_20260723.csv
  data/regime/second_entries_features_20260723.csv
  data/regime/brooks_filters_2e_20260723.csv   (SB anatomy -> Brooks cell mask)
Writes:
  data/regime/sweep_report_tables_20260723.csv (all table rows, long format)
Prints: the key matrices.

  python scripts/regime_2e_sweep_report.py
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "data" / "regime"

sw = pd.read_csv(R / "second_entries_stop_target_sweep_20260723.csv")
ft = pd.read_csv(R / "second_entries_features_20260723.csv")
bk = pd.read_csv(R / "brooks_filters_2e_20260723.csv")

sw2 = sw[sw["count"] == 2].copy()
ft2 = ft[ft["count"] == 2].copy()
bk["entry_id"] = bk.Date + "_" + bk.fire_bar.astype(str) + bk["dir"] + "2"
bk2 = bk[bk.book == "T2"][["entry_id", "sb_ibs_o", "sb_body", "sb_dirok", "sb_rngx",
                           "ema_dist", "ema_side_ok", "ema_touch", "warm"]].drop_duplicates("entry_id")

f = ft2.merge(bk2, on="entry_id", how="left")
wt_ids = set(f[((f.reg_base == "BULL") & (f.dir == "L")) |
               ((f.reg_base == "BEAR") & (f.dir == "S"))].entry_id)
brooks_ids = set(f[(((f.reg_base == "BULL") & (f.dir == "L")) |
                    ((f.reg_base == "BEAR") & (f.dir == "S"))) &
                   (f.sb_ibs_o >= 0.7) & f.sb_dirok.fillna(False) &
                   (f.sb_rngx >= 1.0) & f.ema_side_ok.fillna(False) &
                   f.warm.fillna(False)].entry_id)


def pf(s):
    gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return gp / gl if gl > 0 else float("inf")


out_rows = []


def matrix(scope, ids=None):
    d = sw2 if ids is None else sw2[sw2.entry_id.isin(ids)]
    print(f"\n================ STOP x TARGET  ({scope})  n_entries={d.entry_id.nunique()} ================")
    for metric in ("net", "PF"):
        t = d.pivot_table(index="stop", columns="target", values="net",
                          aggfunc=(lambda s: round(pf(s), 2)) if metric == "PF" else "sum")
        cols = [c for c in ["r05", "r10", "r15", "r20", "r30", "r40",
                            "f2p", "f4p", "f6p", "eod"] if c in t.columns]
        t = t[cols]
        if metric == "net":
            t = t.round(0)
        print(f"-- {metric} --"); print(t.to_string())
        for stop_ in t.index:
            for tgt_ in cols:
                out_rows.append((scope, metric, stop_, tgt_, t.loc[stop_, tgt_]))


matrix("ALL 2E")
matrix("WITH-TREND", wt_ids)
matrix("BROOKS CELL (WT+SBstrong+EMAside)", brooks_ids)

# ---- regime-variant comparison on the base geometry (netT2 from features CSV) ----
print("\n================ REGIME VARIANTS (base geometry, T2 net) ================")
for col in ("reg_base", "reg_sticky", "reg_closec"):
    w = ((f[col] == "BULL") & (f.dir == "L")) | ((f[col] == "BEAR") & (f.dir == "S"))
    for scope, m in (("with-trend", w), ("all-nonneutral", f[col] != "NEUTRAL")):
        d = f[m]
        row = (col, scope, len(d), round(d.netT2.mean(), 1), round(d.netT2.sum()),
               round(pf(d.netT2), 3))
        out_rows.append(("variants", col, scope, "", row[5]))
        print(f"{col:12s} {scope:14s} n={row[2]:5d}  $/tr={row[3]:7.1f}  net={row[4]:8d}  PF={row[5]}")

# ---- TOD ----
print("\n================ TIME OF DAY (machine-tz bar time, T2 net) ================")
f["hh"] = f.bar_time.str[:2]
t = f.groupby("hh").agg(n=("netT2", "size"), net=("netT2", "sum"),
                        PF=("netT2", pf), per_tr=("netT2", "mean")).round(2)
print(t.to_string())
for hh, r_ in t.iterrows():
    out_rows.append(("tod", hh, "", "", r_.PF))

# ---- feature scans (T2 net, quartiles) ----
print("\n================ FEATURE SCANS (T2 net, quartiles or cats) ================")
NUMS = ["ema20_atr", "er10", "adx14", "stochK", "zl_osc", "vix", "gap_pct",
        "prev_rng_pct", "adr10_pct", "sb_ibs_o", "sb_rngx", "ema_dist"]
for c in NUMS:
    if c not in f.columns:
        continue
    x = f.dropna(subset=[c]).copy()
    if len(x) < 400:
        continue
    try:
        x["q"] = pd.qcut(x[c], 4, duplicates="drop")
    except Exception:
        continue
    t = x.groupby("q", observed=True).agg(n=("netT2", "size"), net=("netT2", "sum"),
                                          PF=("netT2", pf)).round(2)
    print(f"\n-- {c} --"); print(t.to_string())
    for qv, r_ in t.iterrows():
        out_rows.append(("feat", c, str(qv), "", r_.PF))
for c in ["ib_pos", "va_pos", "eth_pos", "zl_sign"]:
    if c not in f.columns:
        continue
    t = f.groupby(c, dropna=True).agg(n=("netT2", "size"), net=("netT2", "sum"),
                                      PF=("netT2", pf)).round(2)
    t = t[t.n >= 60]
    print(f"\n-- {c} --"); print(t.to_string())
    for v, r_ in t.iterrows():
        out_rows.append(("feat", c, str(v), "", r_.PF))

pd.DataFrame(out_rows, columns=["table", "a", "b", "c", "value"]).to_csv(
    R / "sweep_report_tables_20260723.csv", index=False)
print("\nsaved ->", R / "sweep_report_tables_20260723.csv")
