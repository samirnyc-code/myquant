"""Explore mq_truth + chain slices structure for GEX formula cracking."""
import pandas as pd

DATA = r"C:\Users\Admin\myquant\data\regime\mq_reveng"

truth = pd.read_csv(f"{DATA}\\mq_truth.csv")
print("truth shape", truth.shape)
print(truth.columns.tolist())
print(truth.head(3).T.to_string())

ch = pd.read_parquet(f"{DATA}\\chain_slices_overlap.parquet")
print("\nchain shape", ch.shape)
print(ch.dtypes)
print(ch.head(5).to_string())
print("\ndte range", ch.dte.min(), ch.dte.max())
print("dates", ch.tradeDate.min(), ch.tradeDate.max(), ch.tradeDate.nunique())
one = ch[ch.tradeDate == ch.tradeDate.max()]
print("one day rows", len(one), "expiries", one.expirDate.nunique(), "strikes", one.strike.nunique())
# sample gex values from truth
cols = [c for c in truth.columns if c.endswith("_gex")]
print("\ngex cols:", cols)
print(truth[cols].describe().T.to_string())
