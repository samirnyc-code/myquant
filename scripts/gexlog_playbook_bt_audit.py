"""Audit the playbook-only backtest rows: extreme days, entry counts per
scenario kind, and missing-quote coverage. Companion to gexlog_playbook_bt.py."""
from pathlib import Path

import pandas as pd

ROWS = Path(r"c:\Users\Admin\myquant\data\options_sim\backtest_full\playbook_bt_rows.csv")

r = pd.read_csv(ROWS)
t = r[r["pnl"].notna()].copy()
gd = t.groupby(["variant", "date"])["pnl"].sum().reset_index()

print("--- worst 5 days per variant ---")
for v, g in gd.groupby("variant"):
    print(g.nsmallest(5, "pnl").to_string(index=False))
print("\n--- best 5 days per variant ---")
for v, g in gd.groupby("variant"):
    print(g.nlargest(5, "pnl").to_string(index=False))

wd = gd[gd["variant"] == "hold15"].nsmallest(1, "pnl").iloc[0]["date"]
print(f"\n--- all rows of worst hold15 day ({wd}) ---")
cols = ["date", "variant", "scenario", "structure", "trig_kind", "entry_et",
        "right", "long_k", "short_k", "net", "exit_val", "close", "pnl", "note"]
print(r[r["date"] == wd][cols].to_string(index=False))

print("\n--- entry minute distribution (hold15 breakouts) ---")
h = t[(t["variant"] == "hold15") & (t["trig_kind"].isin(["above", "below"]))]
print(h["entry_et"].str[:2].value_counts().sort_index().to_string())

print("\n--- non-priced rows (notes) ---")
print(r[r["pnl"].isna()]["note"].value_counts().to_string())

print("\n--- days with any entry, by variant ---")
print(gd.groupby("variant")["date"].count().to_string())
