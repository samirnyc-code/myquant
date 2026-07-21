"""Stop sweep on the EOD-hold set (reconstruct EOD-with-any-stop from MAE/final):
signal-bar stop vs ABR multiples vs fixed pts, per setup. Plus SB-IBS-direction
filter and the morning cut. avgR/win/PF/net/DD, $5 RT, 1 ES, 1 year."""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent; PT = 50.0; COMM = 5.0
df = pd.read_parquet(ROOT / "docs" / "living" / "brooks_sim_trades_v3.parquet")
E = df[df.book == "EOD"].copy()          # one row per entry, with path summary


def eod_with_stop(sub, stop_dist):
    d = np.maximum(stop_dist, 0.25)
    outcome = np.where(sub["mae"].values >= d, -d, sub["fin"].values)   # pts
    net = outcome * PT - COMM
    R = outcome / d
    return R, net


def rep(sub, stop_dist, lab):
    if len(sub) < 20:
        print(f"  {lab:24s} n={len(sub):5d} (few)"); return
    R, net = eod_with_stop(sub, stop_dist)
    gp = net[net > 0].sum(); gl = -net[net < 0].sum(); pf = gp / gl if gl else np.inf
    tmp = pd.DataFrame({"Date": sub["Date"].values, "net": net})
    eq = tmp.groupby("Date")["net"].sum().sort_index().cumsum()
    dd = (eq.cummax() - eq).max()
    print(f"  {lab:24s} n={len(sub):5d}  avgR{R.mean():+.3f}  win{(R>0).mean()*100:4.1f}%  "
          f"PF{pf:.2f}  net${net.sum():>9,.0f}  DD${dd:>8,.0f}")


def stopmodes(sub, title):
    print(f"\n### {title}  (n={len(sub)})")
    rep(sub, sub["Rpts"].values, "SB stop")
    for m in (0.5, 1.0, 1.5, 2.0):
        rep(sub, m * sub["abr_e"].values, f"ABR x{m}")
    for fx in (5, 8, 12):
        rep(sub, np.full(len(sub), float(fx)), f"fixed {fx}pt")


for st, mask in [("IB+OB", E.setup.isin(["IB", "OB"])), ("IB", E.setup == "IB"),
                 ("OB", E.setup == "OB"), ("N", E.setup == "N")]:
    stopmodes(E[mask], f"setup {st}")

print("\n\n======== SB-IBS-direction filter (setup IB+OB, ABR x1 stop) ========")
base = E[E.setup.isin(["IB", "OB"])]
for thr in (0, 50, 60, 69, 75):
    rep(base[base.sbibs >= thr], 1.0 * base[base.sbibs >= thr]["abr_e"].values, f"SB-IBS >= {thr}")

print("\n======== MORNING (<1/3) x IB+OB, stop modes ========")
stopmodes(E[(E.setup.isin(["IB", "OB"])) & (E.frac < 0.33)], "morning IB+OB")

print("\n======== MORNING x IB+OB x SB-IBS>=60, ABR x1 ========")
m = E[(E.setup.isin(["IB", "OB"])) & (E.frac < 0.33) & (E.sbibs >= 60)]
rep(m, 1.0 * m["abr_e"].values, "morning+IBS60 ABRx1")
rep(m, 1.5 * m["abr_e"].values, "morning+IBS60 ABRx1.5")
