"""Filter sweep on the v3 IB+OB / EOD-hold set: prior-day trend, don't-fade-the-
day, time-of-day, trendiness (ER), regime age — each with n/avgR/PF/net/DD."""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous.parquet")
b["Date"] = b["DateTime"].dt.date.astype(str)
dl = b.groupby("Date").agg(O=("Open", "first"), H=("High", "max"), L=("Low", "min"), C=("Close", "last"))
dl["rng"] = dl.H - dl.L
dl["adr"] = dl["rng"].rolling(20).mean()
dl["pr_rng_adr"] = (dl["rng"] / dl["adr"]).shift(1)
dl["pr_body_frac"] = ((dl.C - dl.O).abs() / dl["rng"]).shift(1)
dl["strong_prior"] = ((dl["pr_rng_adr"] > 1.1) & (dl["pr_body_frac"] > 0.5)).astype(int)
ctx = dl[["pr_rng_adr", "pr_body_frac", "strong_prior"]].reset_index()

df = pd.read_parquet(ROOT / "docs" / "living" / "brooks_sim_trades_v3.parquet")
df = df.merge(ctx, on="Date", how="left")
E = df[(df.book == "EOD") & (df.setup.isin(["IB", "OB"]))].copy()   # base = IB+OB, EOD hold


def st(sub, lab):
    if len(sub) < 20:
        print(f"  {lab:28s} n={len(sub):5d}  (too few)"); return
    mr = sub["R"].mean(); win = (sub["R"] > 0).mean() * 100
    gp = sub.loc[sub.net > 0, "net"].sum(); gl = -sub.loc[sub.net < 0, "net"].sum()
    pf = gp / gl if gl else np.inf
    dd = 0.0
    if len(sub):
        eq = sub.groupby("Date")["net"].sum().sort_index().cumsum()
        dd = (eq.cummax() - eq).max()
    print(f"  {lab:28s} n={len(sub):5d}  avgR{mr:+.3f}  win{win:4.1f}%  PF{pf:.2f}  "
          f"net${sub['net'].sum():>9,.0f}  DD${dd:>8,.0f}")


print("BASE: IB+OB, EOD hold")
st(E, "all IB+OB")
print("\n-- skip days AFTER a strong trend day --")
st(E[E.strong_prior == 0], "prior NOT strong (take)")
st(E[E.strong_prior == 1], "prior strong (skip these)")
print("\n-- don't fade the day (trade WITH day-so-far) --")
st(E[E.withday == 1], "with day")
st(E[E.withday == 0], "against day (fade)")
print("\n-- time of day (entry bar fraction) --")
st(E[E.frac < 0.33], "morning <1/3")
st(E[(E.frac >= 0.33) & (E.frac < 0.66)], "midday")
st(E[E.frac >= 0.66], "afternoon >2/3")
print("\n-- trendiness at entry (ER12 terciles) --")
q = E["er"].quantile([0.33, 0.66]).values
st(E[E.er <= q[0]], f"low ER (<= {q[0]:.2f})")
st(E[(E.er > q[0]) & (E.er <= q[1])], "mid ER")
st(E[E.er > q[1]], f"high ER (> {q[1]:.2f})")
print("\n-- regime age at entry (bars since regime set) --")
st(E[E.regage <= 3], "early (<=3 bars)")
st(E[(E.regage > 3) & (E.regage <= 10)], "mid (4-10)")
st(E[E.regage > 10], "late (>10)")
print("\n-- promising combos --")
st(E[(E.withday == 1) & (E.strong_prior == 0)], "with-day & prior-not-strong")
st(E[(E.withday == 1) & (E.er > q[1])], "with-day & high-ER")
st(E[(E.withday == 1) & (E["count"] == 1)], "with-day & 1st entry")
st(E[(E.withday == 1) & (E.setup == "IB")], "with-day & IB")
st(E[(E.withday == 1) & (E.regage > 3)], "with-day & regime>3")
