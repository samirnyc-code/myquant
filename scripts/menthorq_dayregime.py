"""MenthorQ day-regime study (S54, round 4) — unit of analysis = DAY (n=81).

Pre-registered:
  D1 negative gamma -> realized range / expected move HIGHER (amplification)
  D2 negative gamma -> higher trend efficiency |C-O|/(H-L); positive -> chop
  D3 gamma corridor (CallRes-PutSup)/EM: narrower -> compressed day (range ratio),
     + open position in corridor vs drift direction (open near PutSup -> up drift?)
  D4 expiring GEX share -> afternoon compression (last-2h range share lower)
  D5 book day-P&L (stacked, cached sim) vs D1-D3 regime cuts
Gamma condition tested BOTH as-published and causal prev-day (archive is EOD-stamped).
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(r"c:\Users\Admin\myquant")
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))

from menthorq_edge_study import load_mq, WIN_START, WIN_END, BARS_PQ   # noqa: E402
from menthorq_sr_followup import offsets_for                            # noqa: E402

SIM_PQ = ROOT / "data" / "menthorq" / "_study_sim_results.parquet"
OUT = ROOT / "docs" / "living" / "menthorq_dayregime_20260704.md"
RNG = np.random.default_rng(42)
L = []
def emit(s=""):
    print(s, flush=True); L.append(s)


def boot_diff_mean(a, b, n=2000):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = [np.mean(RNG.choice(a, len(a))) - np.mean(RNG.choice(b, len(b))) for _ in range(n)]
    lo, hi = np.percentile(d, [2.5, 97.5])
    return lo, hi


def grp(label, a, b, unit=""):
    if len(a) < 5 or len(b) < 5:
        return f"| {label} | n={len(a)} vs {len(b)} | insufficient | |"
    lo, hi = boot_diff_mean(a, b)
    sig = " **⇐**" if lo > 0 or hi < 0 else ""
    return (f"| {label} | {np.mean(a):.3f}{unit} (n={len(a)}) vs {np.mean(b):.3f}{unit} (n={len(b)}) "
            f"| {np.mean(a)-np.mean(b):+.3f} | [{lo:+.3f},{hi:+.3f}]{sig} |")


def spear(x, y):
    x, y = pd.Series(x, dtype=float), pd.Series(y, dtype=float)
    ok = x.notna() & y.notna()
    if ok.sum() < 10: return np.nan, 0
    r = x[ok].rank().corr(y[ok].rank())
    return r, int(ok.sum())


def main():
    emit(f"# MenthorQ day-regime study — {datetime.now():%Y-%m-%d %H:%M}\n")
    bars = pd.read_parquet(BARS_PQ)
    bars["DateTime"] = pd.to_datetime(bars["DateTime"])
    day = bars["DateTime"].dt.normalize()
    mq = load_mq(); mq["date"] = mq["date"].dt.normalize()
    mq = mq[(mq["date"] >= WIN_START) & (mq["date"] <= WIN_END)].reset_index(drop=True)
    off = offsets_for(mq, bars)
    mq = mq[mq["date"].isin(off)].reset_index(drop=True)

    rows = []
    prior_close = None
    for i, r in mq.iterrows():
        d = r["date"]; o_ = off[d]
        db = bars[day == d]
        if len(db) < 30: continue
        op = float(db["Open"].iloc[0]); hi = float(db["High"].max())
        lo = float(db["Low"].min()); cl = float(db["Close"].iloc[-1])
        rng_ = hi - lo
        em = r["exp_move_1d_pct"] / 100.0 * (prior_close if prior_close else cl)
        # afternoon share: range of last 24 bars (2h) / day range
        pm = db.iloc[-24:]
        pm_share = (pm["High"].max() - pm["Low"].min()) / rng_ if rng_ > 0 else np.nan
        cr = r["call_resistance"] + o_; ps = r["put_support"] + o_
        corridor = (cr - ps) / em if em > 0 else np.nan
        open_pos = (op - ps) / (cr - ps) if cr > ps else np.nan   # 0=PutSup, 1=CallRes
        rows.append(dict(
            date=d,
            neg=str(r["gamma_condition"]).lower() == "negative",
            neg_prev=str(mq["gamma_condition"].iloc[i - 1]).lower() == "negative" if i > 0 else np.nan,
            vol_prev=pd.to_numeric(mq["volatility_score"].iloc[i - 1], errors="coerce") if i > 0 else np.nan,
            rr=rng_ / em if em > 0 else np.nan,            # realized/implied
            eff=abs(cl - op) / rng_ if rng_ > 0 else np.nan,  # trend efficiency
            drift=(cl - op),
            corridor=corridor, open_pos=open_pos,
            exp_share=abs(r["expiring_gex"]) / abs(r["total_gex"]) if r["total_gex"] else np.nan,
            pm_share=pm_share,
            pc_oi=r["pc_oi"], iv=r["implied_vol_30d"],
        ))
        prior_close = cl
    D = pd.DataFrame(rows)
    emit(f"{len(D)} days. Negative-gamma days: {int(D['neg'].sum())} "
         f"(causal prev: {int(D['neg_prev'].fillna(False).sum())}).\n")

    # book day-PnL (stacked)
    res = pd.read_parquet(SIM_PQ)
    f = res[res["Filled"].astype(bool) & (res["stack_pass"] == True)].copy()  # noqa: E712
    f["DateD"] = pd.to_datetime(f["Date"]).dt.normalize()
    dp = f.groupby("DateD")["NetPnL"].sum()
    D["book"] = D["date"].map(dp)          # NaN = no stacked trades that day
    D["book0"] = D["book"].fillna(0.0)

    emit("## D1/D2 — gamma condition vs day character\n")
    emit("| test (registered direction) | groups | diff | 95% CI |")
    emit("|---|---|---|---|")
    ng, pg = D[D["neg"]], D[~D["neg"]]
    emit(grp("D1 range/EM: NEG vs pos (reg: NEG higher)", ng["rr"].dropna(), pg["rr"].dropna()))
    emit(grp("D2 trend eff: NEG vs pos (reg: NEG higher)", ng["eff"].dropna(), pg["eff"].dropna()))
    m = D.dropna(subset=["neg_prev"])
    ngp, pgp = m[m["neg_prev"] == True], m[m["neg_prev"] == False]  # noqa: E712
    emit(grp("D1 CAUSAL prev-day gamma", ngp["rr"].dropna(), pgp["rr"].dropna()))
    emit(grp("D2 CAUSAL prev-day gamma", ngp["eff"].dropna(), pgp["eff"].dropna()))
    emit(grp("D1 by prev vol_score>=3 (context)", m[m["vol_prev"] >= 3]["rr"].dropna(),
             m[m["vol_prev"] < 3]["rr"].dropna()))
    emit("")

    emit("## D3 — gamma corridor geometry\n")
    emit("| relation | Spearman r | n |")
    emit("|---|---|---|")
    for lab, x, y in [
        ("corridor width vs range/EM (reg: +)", D["corridor"], D["rr"]),
        ("corridor width vs trend eff", D["corridor"], D["eff"]),
        ("open_pos (0=PutSup,1=CallRes) vs signed drift (reg: −)", D["open_pos"], D["drift"]),
        ("D4 expiring-GEX share vs PM range share (reg: −)", D["exp_share"], D["pm_share"]),
        ("IV30 vs range/EM (sanity)", D["iv"], D["rr"]),
    ]:
        r_, n_ = spear(x, y)
        sig = " **⇐**" if abs(r_) > 1.96 / np.sqrt(max(n_, 1)) else ""
        emit(f"| {lab} | {r_:+.3f}{sig} | {n_} |")
    emit("")
    # corridor tertiles detail
    D["corr_t"] = pd.qcut(D["corridor"], 3, labels=["narrow", "mid", "wide"])
    emit("| corridor tertile | days | range/EM | trend eff | book $/day |")
    emit("|---|---|---|---|---|")
    for t in ("narrow", "mid", "wide"):
        g = D[D["corr_t"] == t]
        emit(f"| {t} | {len(g)} | {g['rr'].mean():.2f} | {g['eff'].mean():.2f} | ${g['book0'].mean():,.0f} |")
    emit("")

    emit("## D5 — stacked book day-P&L by regime (n=81 days, day = unit)\n")
    emit("| cut | groups ($/day) | diff | 95% CI |")
    emit("|---|---|---|---|")
    emit(grp("book: NEG vs pos gamma", ng["book0"], pg["book0"], "$"))
    emit(grp("book: CAUSAL prev NEG vs pos", ngp["book0"], pgp["book0"], "$"))
    nb, mb, wb = (D[D["corr_t"] == t]["book0"] for t in ("narrow", "mid", "wide"))
    emit(grp("book: narrow vs wide corridor", nb, wb, "$"))
    hi_rr = D["rr"] >= D["rr"].median()
    emit(grp("book: hi vs lo realized/EM (diagnostic, not causal)",
             D[hi_rr]["book0"], D[~hi_rr]["book0"], "$"))
    emit("")
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"written {OUT}")


if __name__ == "__main__":
    main()
