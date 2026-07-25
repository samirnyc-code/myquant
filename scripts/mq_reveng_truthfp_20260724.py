"""Truth-internal fingerprint for MQ CR/PS/0DTE levels.

Uses ONLY mq_truth.csv (MQ's own published levels + their GEX values) to test
structural hypotheses that need no chain data:
  1. Is CR the max-positive-GEX strike among their own top-10 list? PS the min?
  2. How often do the 0DTE levels (cr0/ps0/hvl0/gw0) equal the all-DTE levels
     (cr/ps/hvl), overall and by year/weekday (SPX had M/W/F expiries pre-2022-05)?
  3. Is gw0 = the strike among {cr0,ps0} (or top-10) with max |gex|?
  4. Rounding distributions of cr0/ps0/gw0/hvl0.
  5. rank_of_truth distribution of prior CR/PS misses (from crps_missrank CSV).
Outputs: data/regime/mq_reveng/truthfp_20260724.csv (stat,value rows)
"""
import pandas as pd
import numpy as np

DD = "c:/Users/Admin/myquant/data/regime/mq_reveng"
t = pd.read_csv(f"{DD}/mq_truth.csv", parse_dates=["session_date", "eod_date"])
rows = []


def add(k, v):
    rows.append({"stat": k, "value": v})


gs = [f"gex_{i}" for i in range(1, 11)]
gv = [f"gex_{i}_gex" for i in range(1, 11)]
S = t[gs].to_numpy(float)   # strikes
V = t[gv].to_numpy(float)   # their gex values
n = len(t)
add("n_days", n)

# 1) CR/PS vs their own top-10 ranking
cr = t["cr"].to_numpy(float)
ps = t["ps"].to_numpy(float)
hvl = t["hvl"].to_numpy(float)
in10_cr = (S == cr[:, None]).any(1)
in10_ps = (S == ps[:, None]).any(1)
in10_hvl = (S == hvl[:, None]).any(1)
add("cr_in_top10_frac", in10_cr.mean())
add("ps_in_top10_frac", in10_ps.mean())
add("hvl_in_top10_frac", in10_hvl.mean())
# argmax/argmin of their values
Vm = np.where(np.isnan(V), -np.inf, V)
argmax_strike = S[np.arange(n), Vm.argmax(1)]
Vm2 = np.where(np.isnan(V), np.inf, V)
argmin_strike = S[np.arange(n), Vm2.argmin(1)]
add("cr_eq_top10argmax_frac", (argmax_strike == cr).mean())
add("ps_eq_top10argmin_frac", (argmin_strike == ps).mean())
# does the top-10 contain any value LARGER than cr_gex / smaller than ps_gex?
crg = t["cr_gex"].to_numpy(float)
psg = t["ps_gex"].to_numpy(float)
add("any_top10_gex_gt_crgex_frac", (Vm.max(1) > crg + 1e-6).mean())
add("any_top10_gex_lt_psgex_frac", (Vm2.min(1) < psg - 1e-6).mean())
# is gex_1 the max |gex|? i.e. are the 10 ordered by |value|?
absV = np.abs(np.where(np.isnan(V), 0, V))
add("top10_sorted_by_absgex_frac", (np.diff(absV, axis=1) <= 1e-6).all(1).mean())

# 2) 0DTE == all-DTE equality
t["year"] = t["eod_date"].dt.year
t["dow"] = t["session_date"].dt.dayofweek  # 0=Mon
for a, b in [("cr0", "cr"), ("ps0", "ps"), ("hvl0", "hvl"), ("gw0", "cr"), ("gw0", "ps")]:
    eq = (t[a] == t[b])
    add(f"{a}_eq_{b}_frac", eq.mean())
eqcr = t["cr0"] == t["cr"]
eqg = t["cr0_gex"] == t["cr_gex"]
add("cr0gex_eq_crgex_frac", eqg.mean())
add("cr0gex_eq_crgex_given_strike_eq", eqg[eqcr].mean() if eqcr.any() else np.nan)
for y, grp in t.groupby("year"):
    add(f"cr0_eq_cr_frac_{y}", (grp.cr0 == grp.cr).mean())
    add(f"ps0_eq_ps_frac_{y}", (grp.ps0 == grp.ps).mean())
    add(f"hvl0_eq_hvl_frac_{y}", (grp.hvl0 == grp.hvl).mean())
    add(f"cr0gex_eq_crgex_frac_{y}", (grp.cr0_gex == grp.cr_gex).mean())
pre = t[t.eod_date < "2022-05-01"]
for d, grp in pre.groupby("dow"):
    add(f"pre2205_cr0_eq_cr_frac_dow{d}", (grp.cr0 == grp.cr).mean())

# 3) gw0 identity: max |gex| of cr0/ps0?
c0g = t["cr0_gex"].to_numpy(float)
p0g = t["ps0_gex"].to_numpy(float)
pick = np.where(np.abs(c0g) >= np.abs(p0g), t["cr0"].to_numpy(float), t["ps0"].to_numpy(float))
gw0 = t["gw0"].to_numpy(float)
ok = ~np.isnan(gw0)
add("gw0_eq_maxabs_cr0ps0_frac", (pick[ok] == gw0[ok]).mean())
add("gw0_eq_cr0_frac", (t.gw0 == t.cr0).mean())
add("gw0_eq_hvl0_frac", (t.gw0 == t.hvl0).mean())
# gw0 gex sign
g0g = t["gw0_gex"].to_numpy(float)
add("gw0_gex_pos_frac", (g0g[~np.isnan(g0g)] > 0).mean())
add("cr0_gex_pos_frac", (c0g[~np.isnan(c0g)] > 0).mean())
add("ps0_gex_neg_frac", (p0g[~np.isnan(p0g)] < 0).mean())

# 4) rounding of 0DTE strikes
for col in ["cr0", "ps0", "gw0", "hvl0", "hvl"]:
    x = t[col].dropna().to_numpy(float)
    for m in [5, 10, 25, 50, 100]:
        add(f"{col}_frac_mult{m}", (np.mod(x, m) == 0).mean())

# 5) rank_of_truth distribution from prior missrank file
try:
    mr = pd.read_csv(f"{DD}/crps_missrank_20260724.csv")
    for lev in mr.level.unique():
        sub = mr[mr.level == lev]
        miss = sub[sub.truth != sub.pred]
        add(f"missrank_{lev}_n_miss", len(miss))
        for r in [2, 3]:
            add(f"missrank_{lev}_truthrank{r}_frac", (miss.rank_of_truth == r).mean())
        add(f"missrank_{lev}_truthrank_gt5_frac", (miss.rank_of_truth > 5).mean())
        add(f"missrank_{lev}_truthrank_med", miss.rank_of_truth.median())
except Exception as e:
    add("missrank_error", str(e))

out = pd.DataFrame(rows)
out.to_csv(f"{DD}/truthfp_20260724.csv", index=False)
pd.set_option("display.width", 200)
print(out.to_string(index=False))
