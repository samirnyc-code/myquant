"""Full viability audit of the vol-stop EOD books: slippage-adjusted stats, CIs,
losing streaks, R-multiple DD + graphics (equity/underwater PNG, sensitivity PNG).

Slippage model: entry is a LIMIT (strict through-fill -> no entry slip by
construction). EVERY exit is a stop-market or market-at-close -> 1 tick adverse
slip per trade ($12.50 ES / $1.25 MES) NOT in the base numbers; applied here.

  python scripts/regime_2e_viability_full.py
"""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
d = pd.read_csv(ROOT / "data" / "regime" / "volstops_20260724.csv")
YEARS = 5.06
SLIP_ES = 12.5
LEAD = ["adr.30", "abr3.0", "abr1.5", "fx4p"]
rng = np.random.default_rng(83)


def pf(s):
    gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return gp / gl if gl > 0 else float("inf")


def boot_pf_ci(net, n_boot=2000):
    vals = net.values
    out = []
    for _ in range(n_boot):
        s = pd.Series(rng.choice(vals, size=len(vals), replace=True))
        out.append(pf(s))
    return np.percentile(out, [2.5, 97.5])


print("book     n   | GROSS-slipless: $/tr  PF   | NET incl 1t exit slip: $/tr   PF   PF 95% CI    | tr-CI95 $/tr")
books = {}
for sid in LEAD:
    x = d[(d["stop"] == sid) & (d.target == "eod")].sort_values("Date").reset_index(drop=True)
    net = x.net - SLIP_ES                      # 1 tick on the exit, every trade
    books[sid] = (x, net)
    lo, hi = boot_pf_ci(net)
    ci = 1.96 * net.std() / np.sqrt(len(net))
    print(f"{sid:7s} {len(x):4d} |  {x.net.mean():+7.1f}  {pf(x.net):5.2f} | "
          f"{net.mean():+7.1f}  {pf(net):5.2f}  [{lo:.2f},{hi:.2f}] | +/-{ci:.1f}")

print("\nbook     maxDD$(net)  DD in R(avgLoss)  maxConsecLosses  longestUW(tr/days)  worstTrade")
for sid in LEAD:
    x, net = books[sid]
    eq = net.cumsum(); ddser = eq - eq.cummax()
    maxdd = float(ddser.min())
    avg_loss = net[net <= 0].mean()
    streak = mx = 0
    for v in net.values:
        streak = streak + 1 if v <= 0 else 0
        mx = max(mx, streak)
    uw = 0; mxuw = 0; start_i = None; mx_days = 0
    for i, v in enumerate(ddser.values):
        if v < -1e-9:
            if start_i is None:
                start_i = i
            uw += 1; mxuw = max(mxuw, uw)
            mx_days = max(mx_days, (pd.Timestamp(x.Date.iloc[i]) -
                                    pd.Timestamp(x.Date.iloc[start_i])).days)
        else:
            uw = 0; start_i = None
    print(f"{sid:7s}  {maxdd:+10,.0f}   {maxdd/avg_loss:6.1f}R          {mx:3d}              "
          f"{mxuw}/{mx_days}          {net.min():+7.0f}")

print("\nMES per contract (gross/10, then commission + 1t MES exit slip $1.25):")
print("book     @$5RT: $/tr   $/yr    PF  |  @$2.50RT: $/tr   $/yr    PF")
for sid in LEAD:
    x, _ = books[sid]
    gross = (x.net + 5.0) / 10.0
    for line in [None]:
        m5 = gross - 5.0 - 1.25
        m25 = gross - 2.5 - 1.25
        print(f"{sid:7s}  {m5.mean():+6.2f}  {m5.sum()/YEARS:+7.0f}  {pf(m5):5.2f} |  "
              f"{m25.mean():+6.2f}  {m25.sum()/YEARS:+7.0f}  {pf(m25):5.2f}")

# ---- graphics ----
COLS = {"adr.30": "#2a78d6", "abr3.0": "#eb6834", "abr1.5": "#1baf7a", "fx4p": "#8b8f96"}
fig, (a1, a2) = plt.subplots(2, 1, figsize=(13, 8), dpi=115, sharex=True,
                             gridspec_kw=dict(height_ratios=[2, 1], hspace=0.08))
for sid in LEAD:
    x, net = books[sid]
    eq = net.cumsum()
    a1.plot(range(len(eq)), eq.values, lw=2 if sid != "fx4p" else 1.3, color=COLS[sid],
            label=f"{sid} net-of-slip ({eq.iloc[-1]:+,.0f}$)")
    a2.plot(range(len(eq)), (eq - eq.cummax()).values, lw=1.5, color=COLS[sid])
x0, _ = books["fx4p"]
yrs = x0.Date.str[:4].values
for i in range(1, len(yrs)):
    if yrs[i] != yrs[i - 1]:
        for ax in (a1, a2):
            ax.axvline(i, color="#e3e2dc", lw=0.8)
        a2.text(i, a2.get_ylim()[0], yrs[i], fontsize=9, color="#8b8f96")
a1.axhline(0, color="#c3c2b7", lw=1); a1.legend(frameon=False)
a1.set_ylabel("closed equity $ (incl. exit slip)"); a2.set_ylabel("underwater $")
a1.set_title("Vol-stop EOD books — equity and drawdown, NET of $5 RT + 1-tick exit slip (1 ES)",
             fontweight="bold")
for ax in (a1, a2):
    ax.grid(axis="y", color="#eceeed", lw=0.7)
    for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
fig.tight_layout()
p1 = ROOT / "docs" / "living" / "viability_equity_dd_20260724.png"
fig.savefig(p1, facecolor="white"); plt.close(fig)

fig, ax = plt.subplots(figsize=(11, 5), dpi=115)
labels = []; v_gross = []; v_slip = []; v_mes5 = []; v_mes25 = []
for sid in LEAD:
    x, net = books[sid]
    labels.append(sid)
    v_gross.append(x.net.mean()); v_slip.append(net.mean())
    g = (x.net + 5.0) / 10.0
    v_mes5.append((g - 6.25).mean() * 10)      # x10 to same scale for comparability
    v_mes25.append((g - 3.75).mean() * 10)
w = 0.2; xs = np.arange(len(labels))
ax.bar(xs - 1.5 * w, v_gross, w, color="#2a78d6", label="ES $/tr (no slip)")
ax.bar(xs - 0.5 * w, v_slip, w, color="#1baf7a", label="ES $/tr net of exit slip")
ax.bar(xs + 0.5 * w, v_mes5, w, color="#eb6834", label="MES @$5RT+slip (x10 scale)")
ax.bar(xs + 1.5 * w, v_mes25, w, color="#eda100", label="MES @$2.50RT+slip (x10)")
ax.axhline(0, color="#c3c2b7", lw=1)
ax.set_xticks(xs, labels); ax.set_ylabel("expectancy $/trade")
ax.legend(frameon=False, fontsize=9)
ax.set_title("Cost sensitivity: what commissions + 1-tick exit slip do to the edge",
             fontweight="bold")
ax.grid(axis="y", color="#eceeed", lw=0.7)
for s_ in ("top", "right"): ax.spines[s_].set_visible(False)
fig.tight_layout()
p2 = ROOT / "docs" / "living" / "viability_costs_20260724.png"
fig.savefig(p2, facecolor="white"); plt.close(fig)
print(f"\nsaved {p1}\nsaved {p2}")
