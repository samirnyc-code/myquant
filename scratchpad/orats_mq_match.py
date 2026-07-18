"""Full-history validation: reproduce ALL MenthorQ SPX levels from pulled ORATS
chains, score strike-match + magnitude error across every overlap day.

Rules (reverse-engineered + validated on 2026-07-15):
  cr  = argmax per-strike NetGEX (dte>1)         ps  = argmin
  hvl = argmin cumulative NetGEX near spot        (gamma flip)
  d1_min/max = spot +/- spot*IV30*sqrt(1/252)
  cr0 = gw0 = cr ;  ps0 = hvl0 = 0DTE cumsum-min
  gex_1..10 = top-10 |NetGEX| walls within +/-1.5% of spot
NetGEX_strike = gamma*(callOI-putOI)*100*spot ; dealers long-call/short-put.
"""
import sys, glob
import pandas as pd, numpy as np
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ORATS = ROOT / "data" / "orats" / "SPX"
MQ = pd.read_csv(ROOT / "data" / "menthorq" / "SPX_mq_levels_history.csv")
MQ = MQ.set_index("session_date")

def day_levels(d):
    """d: DataFrame of one tradeDate's chain. Returns dict of computed levels."""
    for c in ["strike","gamma","callOpenInterest","putOpenInterest","dte",
              "callMidIv","putMidIv","spotPrice"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    spot = d["spotPrice"].median()
    if not np.isfinite(spot) or spot <= 0:
        return None
    main = d[d.dte > 1].copy()
    main["n"] = main.gamma*(main.callOpenInterest-main.putOpenInterest)*100*spot
    p = main.groupby("strike")["n"].sum().sort_index()/1e6
    if p.empty: return None
    band = p[(p.index >= spot*0.985) & (p.index <= spot*1.015)]
    flipband = p[(p.index >= spot*0.90) & (p.index <= spot*1.10)]
    out = {"spot": spot, "cr": p.idxmax(), "ps": p.idxmin(),
           "hvl": flipband.cumsum().idxmin() if not flipband.empty else np.nan}
    # top-10 walls near spot excluding cr
    walls = band.reindex(band.abs().sort_values(ascending=False).index)
    out["walls"] = [k for k in walls.index if k != out["cr"]][:10]
    # d1 expected move via IV30
    atm = {}
    for dte, s in d.groupby("dte"):
        a = s.iloc[(s.strike-spot).abs().argsort()[:2]]
        iv = pd.concat([a.callMidIv, a.putMidIv]).mean()
        if np.isfinite(iv): atm[int(dte)] = iv
    if len(atm) >= 2:
        xs = sorted(atm); iv30 = np.interp(31, xs, [atm[x] for x in xs])
        mv = spot*iv30*np.sqrt(1/252)
        out["d1_min"], out["d1_max"] = spot-mv, spot+mv
    # 0DTE — only meaningful once DAILY 0DTE existed (Tue/Thu added ~May 2022);
    # liquid/dominant only 2023+. Skip earlier: no same-day chain most days.
    z = d[(d.dte == 1)].copy()
    if len(z) and str(d.tradeDate.iloc[0] if "tradeDate" in d else "") >= "2022-05-01":
        z["n"] = z.gamma*(z.callOpenInterest-z.putOpenInterest)*100*spot
        pz = z.groupby("strike")["n"].sum().sort_index()/1e6
        fb = pz[(pz.index>=spot*0.97)&(pz.index<=spot*1.03)]
        out["ps0"] = fb.cumsum().idxmin() if not fb.empty else np.nan
    return out

def main():
    files = sorted(glob.glob(str(ORATS / "SPX_*.parquet")))
    if not files:
        sys.exit("no ORATS SPX parquet yet")
    res = []
    for f in files:
        yr = pd.read_parquet(f)
        for d, grp in yr.groupby("tradeDate"):
            d = str(d)
            if d not in MQ.index: continue
            L = day_levels(grp.copy())
            if L is None: continue
            m = MQ.loc[d]
            row = {"date": d}
            for k in ["cr","ps","hvl"]:
                row[k+"_err"] = abs(L[k]-m[k]) if pd.notna(m.get(k)) and pd.notna(L.get(k)) else np.nan
            for k in ["d1_min","d1_max"]:
                row[k+"_err"] = abs(L[k]-m[k]) if (k in L and pd.notna(m.get(k))) else np.nan
            if pd.notna(m.get("ps0")) and "ps0" in L and pd.notna(L["ps0"]):
                row["ps0_err"] = abs(L["ps0"]-m["ps0"])
            mqw = {m.get(f"gex_{i}") for i in range(1,11) if pd.notna(m.get(f"gex_{i}"))}
            if mqw and L.get("walls"):
                myw = set(L["walls"])
                row["wall_ov"] = len(myw & mqw)
                # strong walls = MQ's top-7 by |gex|
                mgex = sorted(((m.get(f"gex_{i}"), abs(m.get(f"gex_{i}_gex",0)))
                               for i in range(1,11) if pd.notna(m.get(f"gex_{i}"))),
                              key=lambda t:-t[1])
                strong = {k for k,_ in mgex[:7]}
                row["strong_ov"] = len(myw & strong)
            res.append(row)
    R = pd.DataFrame(res)
    R["year"] = R.date.str[:4]
    n = len(R)
    print(f"\n===== SPX MenthorQ level reproduction — {n} overlap days =====")

    def stat(col, unit="pts", exact_thresh=0.01):
        s = R[col].dropna()
        if s.empty: return
        exact = (s <= exact_thresh).mean()*100
        w1 = (s <= 5.001).mean()*100
        print(f"  {col:12}: exact {exact:5.1f}% | within 1 strike {w1:5.1f}% | "
              f"median {s.median():6.2f} {unit} | p90 {s.quantile(.9):7.2f} (n={len(s)})")
    print("\n-- OVERALL --")
    for c in ["cr_err","ps_err","hvl_err","ps0_err"]:
        if c in R: stat(c)
    for c in ["d1_min_err","d1_max_err"]:
        if c in R:
            s=R[c].dropna(); print(f"  {c:12}: median {s.median():.2f} pts | p90 {s.quantile(.9):.2f} pts (n={len(s)})")
    if "wall_ov" in R:
        print(f"  gex walls   : mean {R.wall_ov.mean():.1f}/10 | strong(top7) "
              f"{R.strong_ov.mean():.1f}/7 | days {R.wall_ov.notna().sum()}")

    # ---- BY YEAR: the regime-dependence story ----
    print("\n-- BY YEAR (cr/ps/hvl exact% | d1 median-err | walls mean/10 | strong/7) --")
    print(f"  {'yr':5}{'n':>5}  {'cr%':>6}{'ps%':>6}{'hvl%':>6}  {'d1err':>7}  {'walls':>6}{'strong':>7}")
    for yr, g in R.groupby("year"):
        def ex(c):
            s=g[c].dropna(); return (s<=0.01).mean()*100 if len(s) else float("nan")
        d1=pd.concat([g.d1_min_err,g.d1_max_err]).dropna()
        print(f"  {yr:5}{len(g):>5}  {ex('cr_err'):>6.0f}{ex('ps_err'):>6.0f}{ex('hvl_err'):>6.0f}  "
              f"{d1.median() if len(d1) else float('nan'):>7.1f}  "
              f"{g.wall_ov.mean():>6.1f}{g.strong_ov.mean():>7.1f}")

    R.to_csv(ROOT/"scratchpad"/"orats_mq_match_results.csv", index=False)
    print(f"\n  per-day results -> scratchpad/orats_mq_match_results.csv")

if __name__ == "__main__":
    main()
