"""User-rule + expanded-universe level tests (S54, round 3) — pre-registered:

  U1 'never trade INTO a level': opposing level within 1R of entry → WORSE.
     Tested per level family: MQ main / MQ all / STRUCTURAL / cluster zones.
  U2 break-and-retest (MQ main levels): break (close >=2pts beyond), retest
     (back within 2pts), MC signal in break direction within 0.5xABR → BETTER.
     (+ exploratory structural-level variant, labeled.)
  U3 clusters: >=3 levels chained within 4pts (FULL universe: MQ + structural).
     (a) cluster zones bounce more than isolated levels; (b) into-cluster hurts.
  U4 (user horizon expansion): touch test per level family — do MARKET
     structural levels (prior day H/L/C, prior-day VA, IB H/L, VWAP) show S/R
     where MQ levels didn't? Anchors the interpretation of every null above.

Universe: MQ main (CallRes/PutSup/HVL/GW ±0DTE), MQ other (BL, GEX),
STRUCT: prior-day High/Low/Close, prior-day POC/VAH/VAL (volume profile,
70% VA), IB High/Low (first 12 bars, valid after formation). VWAP handled
separately (dynamic): developing session VWAP at touch/entry time.
Exec: cached S54 sim (3R/BE@1R, slips 1/1/1, comm 4.36). Continuous space.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from menthorq_edge_study import load_mq, WIN_START, WIN_END, BARS_PQ   # noqa: E402
from menthorq_sr_followup import offsets_for                            # noqa: E402
from stack_filter import _abr20                                         # noqa: E402

SIM_PQ = ROOT / "data" / "menthorq" / "_study_sim_results.parquet"
OUT = ROOT / "docs" / "living" / "menthorq_userrules_20260704.md"
MQ_MAIN = ["call_resistance", "call_resistance_0dte", "put_support",
           "put_support_0dte", "high_vol_level", "gamma_wall_0dte"]
MQ_OTHER = [f"bl_{i}" for i in range(1, 11)] + [f"gex_{i}" for i in range(1, 11)]
CLUSTER_GAP, CLUSTER_MIN = 4.0, 3
BREAK_PTS, RETEST_PTS = 2.0, 2.0
H_BARS, THRESH, RETOUCH = 6, 3.0, 5.0
IB_BARS = 12
RNG = np.random.default_rng(42)

L = []
def emit(s=""):
    print(s, flush=True); L.append(s)


def touches(day_bars, levels, start=0):
    """6-bar bounce/break touch outcomes; touches counted from bar `start`."""
    hi = day_bars["High"].to_numpy(); lo = day_bars["Low"].to_numpy()
    cl = day_bars["Close"].to_numpy()
    out = []
    for lev in levels:
        if not np.isfinite(lev): continue
        armed, prev_close = True, None
        for i in range(len(day_bars)):
            if i < max(start, 1):
                prev_close = cl[i]; continue
            if prev_close is not None and armed and lo[i] <= lev <= hi[i]:
                appr = 1.0 if prev_close < lev else -1.0
                j = min(i + H_BARS, len(day_bars) - 1)
                if j > i:
                    fh = hi[i + 1:j + 1].max(); fl = lo[i + 1:j + 1].min()
                    pen = (fh - lev) if appr > 0 else (lev - fl)
                    bnc = (lev - fl) if appr > 0 else (fh - lev)
                    out.append(dict(bounce=bnc >= THRESH and pen < THRESH,
                                    breakthru=pen >= THRESH,
                                    drift=(cl[j] - lev) * appr))
                armed = False
            if not armed and abs(cl[i] - lev) > RETOUCH:
                armed = True
            prev_close = cl[i]
    return out


def volume_profile_va(db: pd.DataFrame):
    """POC/VAH/VAL from a day's 5M bars, volume spread uniformly over bar range."""
    if db.empty: return None
    step = 0.25
    lo = db["Low"].min(); hi = db["High"].max()
    grid = np.arange(lo, hi + step, step)
    vol = np.zeros(len(grid))
    use_vol = "Volume" in db.columns and db["Volume"].sum() > 0
    for _, b in db.iterrows():
        i0 = int((b["Low"] - lo) / step); i1 = max(int((b["High"] - lo) / step), i0)
        v = float(b["Volume"]) if use_vol else 1.0
        vol[i0:i1 + 1] += v / (i1 - i0 + 1)
    poc_i = int(vol.argmax()); total = vol.sum()
    inc = {poc_i}; lo_i = hi_i = poc_i
    while vol[list(inc)].sum() < 0.70 * total and (lo_i > 0 or hi_i < len(grid) - 1):
        up = vol[hi_i + 1] if hi_i < len(grid) - 1 else -1
        dn = vol[lo_i - 1] if lo_i > 0 else -1
        if up >= dn: hi_i += 1; inc.add(hi_i)
        else: lo_i -= 1; inc.add(lo_i)
    return dict(poc=grid[poc_i], vah=grid[hi_i], val=grid[lo_i])


def boot_diff(a, b, n=1000):
    d = [np.mean(RNG.choice(a, len(a))) - np.mean(RNG.choice(b, len(b))) for _ in range(n)]
    return np.percentile(d, [2.5, 97.5])


def rrow(label, g):
    n = len(g)
    if n == 0: return f"| {label} | 0 | — | — | — | — |"
    r = g["Rmult"].to_numpy()
    ci = 1.96 * r.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    pnl = g["PnL"].to_numpy()
    gw = pnl[pnl > 0].sum(); gl = abs(pnl[pnl < 0].sum())
    pf = gw / gl if gl > 0 else np.inf
    lo, hi = r.mean() - ci, r.mean() + ci
    mark = " ✅" if lo > 0 else (" ❌" if hi < 0 else "")
    return (f"| {label} | {n} | {r.mean():+.3f} ±{ci:.3f}{mark} | [{lo:+.3f},{hi:+.3f}] "
            f"| {pf:.2f} | ${pnl.sum():,.0f} |")


def main():
    emit(f"# Level-universe & user-rule tests — {datetime.now():%Y-%m-%d %H:%M}\n")
    bars = pd.read_parquet(BARS_PQ)
    bars["DateTime"] = pd.to_datetime(bars["DateTime"])
    day = bars["DateTime"].dt.normalize()
    mq = load_mq(); mq["date"] = mq["date"].dt.normalize()
    mq = mq[(mq["date"] >= WIN_START) & (mq["date"] <= WIN_END)].reset_index(drop=True)
    off = offsets_for(mq, bars)
    mq = mq[mq["date"].isin(off)].reset_index(drop=True)
    abr = _abr20(bars)
    dates = list(mq["date"])
    bars_by = {d: bars[day == d].reset_index(drop=True) for d in dates}
    has_vol = "Volume" in bars.columns and bars["Volume"].sum() > 0
    emit(f"{len(dates)} days; volume data: {has_vol}\n")

    # ── per-day level maps ────────────────────────────────────────────────────
    fam = {}   # date -> {family: {name: price}}, plus 'ib_start'
    prior = None
    for _, r in mq.iterrows():
        d = r["date"]; o = off[d]; db = bars_by[d]
        m = {}
        m["mq_main"] = {c: r[c] + o for c in MQ_MAIN if pd.notna(r[c])}
        m["mq_other"] = {c: r[c] + o for c in MQ_OTHER if pd.notna(r[c])}
        st = {}
        if prior is not None:
            pdb = bars_by[prior]
            st["pdH"] = pdb["High"].max(); st["pdL"] = pdb["Low"].min()
            st["pdC"] = pdb["Close"].iloc[-1]
            va = volume_profile_va(pdb)
            if va: st["POC"] = va["poc"]; st["VAH"] = va["vah"]; st["VAL"] = va["val"]
        m["struct"] = st
        m["ib"] = {"ibH": db["High"].iloc[:IB_BARS].max(),
                   "ibL": db["Low"].iloc[:IB_BARS].min()} if len(db) > IB_BARS else {}
        fam[d] = m
        prior = d

    # ── U4: touch test per family (+ VWAP) + random controls ────────────────
    emit("## U4 — 6-bar touch test by level family (MQ vs market-structure)\n")
    groups = {"MQ main": [], "MQ other (BL+GEX)": [], "Prior day H/L/C": [],
              "Prior day VA (POC/VAH/VAL)": [], "IB high/low (post-IB)": [],
              "VWAP (developing)": [], "random control": []}
    for d in dates:
        db = bars_by[d]
        if len(db) < 20: continue
        m = fam[d]
        groups["MQ main"] += touches(db, list(m["mq_main"].values()))
        groups["MQ other (BL+GEX)"] += touches(db, list(m["mq_other"].values()))
        st = m["struct"]
        groups["Prior day H/L/C"] += touches(db, [st.get(k) for k in ("pdH", "pdL", "pdC") if k in st])
        groups["Prior day VA (POC/VAH/VAL)"] += touches(db, [st.get(k) for k in ("POC", "VAH", "VAL") if k in st])
        groups["IB high/low (post-IB)"] += touches(db, list(m["ib"].values()), start=IB_BARS)
        # VWAP: developing; touch when bar range crosses current vwap
        if has_vol:
            hlc3 = (db["High"] + db["Low"] + db["Close"]) / 3
            vw = (hlc3 * db["Volume"]).cumsum() / db["Volume"].cumsum()
            hi_ = db["High"].to_numpy(); lo_ = db["Low"].to_numpy(); cl_ = db["Close"].to_numpy()
            vwv = vw.to_numpy()
            armed = True
            for i in range(2, len(db)):
                if armed and lo_[i] <= vwv[i - 1] <= hi_[i]:
                    appr = 1.0 if cl_[i - 1] < vwv[i - 1] else -1.0
                    j = min(i + H_BARS, len(db) - 1)
                    if j > i:
                        lev = vwv[i - 1]
                        pen = (hi_[i + 1:j + 1].max() - lev) if appr > 0 else (lev - lo_[i + 1:j + 1].min())
                        bnc = (lev - lo_[i + 1:j + 1].min()) if appr > 0 else (hi_[i + 1:j + 1].max() - lev)
                        groups["VWAP (developing)"].append(dict(
                            bounce=bnc >= THRESH and pen < THRESH,
                            breakthru=pen >= THRESH, drift=(cl_[j] - lev) * appr))
                    armed = False
                if not armed and abs(cl_[i] - vwv[i]) > RETOUCH:
                    armed = True
        # controls
        all_real = ([v for g in ("mq_main", "mq_other", "struct", "ib") for v in m[g].values()])
        dlo, dhi = db["Low"].min(), db["High"].max()
        ctrl, tries = [], 0
        while len(ctrl) < 12 and tries < 300:
            x = RNG.uniform(dlo, dhi); tries += 1
            if all(abs(x - rl) >= 5 for rl in all_real): ctrl.append(x)
        groups["random control"] += touches(db, ctrl)

    emit("| family | touches | bounce% | break% | drift pts | bounce diff vs ctrl (95% CI) |")
    emit("|---|---|---|---|---|---|")
    cg = pd.DataFrame(groups["random control"])
    for nm, tt in groups.items():
        t = pd.DataFrame(tt)
        if t.empty: emit(f"| {nm} | 0 | — | — | — | — |"); continue
        if nm == "random control":
            emit(f"| {nm} | {len(t)} | {t['bounce'].mean()*100:.1f}% | {t['breakthru'].mean()*100:.1f}% | {t['drift'].mean():+.2f} | — |")
            continue
        lo, hi = boot_diff(t["bounce"].to_numpy().astype(float), cg["bounce"].to_numpy().astype(float))
        sig = " **⇐**" if lo > 0 or hi < 0 else ""
        emit(f"| {nm} | {len(t)} | {t['bounce'].mean()*100:.1f}% | {t['breakthru'].mean()*100:.1f}% "
             f"| {t['drift'].mean():+.2f} | [{lo*100:+.1f}pp, {hi*100:+.1f}pp]{sig} |")
    emit("")

    # ── clusters over FULL universe ──────────────────────────────────────────
    emit("## U3a — cluster zones (≥3 of ANY level within 4-pt chain) vs isolated\n")
    clusters = {}
    for d in dates:
        m = fam[d]
        la = sorted([v for g in ("mq_main", "mq_other", "struct") for v in m[g].values()])
        cl, cur = [], [la[0]] if la else []
        for x in la[1:]:
            if x - cur[-1] <= CLUSTER_GAP: cur.append(x)
            else: cl.append(cur); cur = [x]
        if cur: cl.append(cur)
        clusters[d] = {"cluster": [float(np.mean(g)) for g in cl if len(g) >= CLUSTER_MIN],
                       "isolated": [g[0] for g in cl if len(g) == 1]}
    tc, ti = [], []
    ncl = 0
    for d in dates:
        db = bars_by[d]
        if len(db) < 20: continue
        ncl += len(clusters[d]["cluster"])
        tc += touches(db, clusters[d]["cluster"])
        ti += touches(db, clusters[d]["isolated"])
    tc, ti = pd.DataFrame(tc), pd.DataFrame(ti)
    emit(f"{ncl} cluster zones / {len(dates)} days.\n")
    emit("| zone | touches | bounce% | break% | drift |")
    emit("|---|---|---|---|---|")
    for nm, t in (("CLUSTER ≥3", tc), ("isolated", ti)):
        if t.empty: emit(f"| {nm} | 0 | — | — | — |"); continue
        emit(f"| {nm} | {len(t)} | {t['bounce'].mean()*100:.1f}% | {t['breakthru'].mean()*100:.1f}% | {t['drift'].mean():+.2f} |")
    if not tc.empty and not ti.empty:
        lo, hi = boot_diff(tc["bounce"].to_numpy().astype(float), ti["bounce"].to_numpy().astype(float))
        emit(f"\nBounce diff (cluster − isolated) 95% CI: [{lo*100:+.1f}pp, {hi*100:+.1f}pp]"
             + (" **⇐**" if lo > 0 or hi < 0 else ""))
    emit("")

    # ── trade-level tests ─────────────────────────────────────────────────────
    res = pd.read_parquet(SIM_PQ)
    f = res[res["Filled"].astype(bool)].copy()
    f["PnL"] = f["NetPnL"].astype(float)
    f["Rmult"] = f["PnL"] / f["RiskDollar"].replace(0, np.nan)
    f["DateD"] = pd.to_datetime(f["Date"]).dt.normalize()
    f = f[f["DateD"].isin(off)].reset_index(drop=True)
    f["abr"] = f["DateD"].map(abr)
    s = np.where(f["Direction"].astype(str).str.upper().str.startswith("L"), 1.0, -1.0)
    entry = f["SignalPrice"].astype(float).to_numpy()
    riskp = (f["SignalPrice"] - f["StopPrice"]).abs().to_numpy()

    def into_flag(get_levels):
        flag = np.zeros(len(f), dtype=bool)
        for i in range(len(f)):
            lv = np.array(get_levels(f["DateD"].iloc[i]), dtype=float)
            lv = lv[np.isfinite(lv)]
            ahead = lv[(lv - entry[i]) * s[i] > 0]
            if len(ahead): flag[i] = np.abs(ahead - entry[i]).min() <= riskp[i]
        return flag

    f["into_mq_main"] = into_flag(lambda d: list(fam[d]["mq_main"].values()))
    f["into_struct"] = into_flag(lambda d: list(fam[d]["struct"].values()) + list(fam[d]["ib"].values()))
    f["into_cluster"] = into_flag(lambda d: clusters[d]["cluster"])
    f["into_any"] = f["into_mq_main"] | f["into_struct"]

    # U2 break-and-retest (MQ main registered; struct exploratory)
    def bretest_flag(levels_of):
        win = {}
        for d in dates:
            db = bars_by[d]
            if len(db) < 20: win[d] = []; continue
            cl_ = db["Close"].to_numpy(); hi_ = db["High"].to_numpy(); lo_ = db["Low"].to_numpy()
            dt_ = db["DateTime"].to_numpy()
            ev = []
            for lev in set(levels_of(d)):
                if not np.isfinite(lev): continue
                up = np.where(cl_ >= lev + BREAK_PTS)[0]
                dn = np.where(cl_ <= lev - BREAK_PTS)[0]
                fu = up[0] if len(up) else 10**9
                fd = dn[0] if len(dn) else 10**9
                if fu == fd: continue
                ib_, dirb = (fu, 1) if fu < fd else (fd, -1)
                for j in range(ib_ + 1, len(db)):
                    near = (lo_[j] <= lev + RETEST_PTS) if dirb == 1 else (hi_[j] >= lev - RETEST_PTS)
                    if near: ev.append((dt_[j], dirb, lev)); break
            win[d] = ev
        flag = np.zeros(len(f), dtype=bool)
        for i in range(len(f)):
            t = np.datetime64(f["DateTime"].iloc[i])
            for (tr, dirb, lev) in win.get(f["DateD"].iloc[i], []):
                if (t >= tr and s[i] == dirb and abs(entry[i] - lev) <= 0.5 * f["abr"].iloc[i]):
                    flag[i] = True; break
        return flag

    f["u2_mq"] = bretest_flag(lambda d: fam[d]["mq_main"].values())
    f["u2_struct"] = bretest_flag(lambda d: list(fam[d]["struct"].values()) + list(fam[d]["ib"].values()))

    hdr = "| cut | n | ExpR ±CI | 95% interval | PF | net$ |"
    sep = "|---|---|---|---|---|---|"
    for scope, sub in (("ALL MC signals", f),
                       ("STACK v2 subset", f[f["stack_pass"] == True])):  # noqa: E712
        emit(f"## {scope}\n")
        emit(hdr); emit(sep)
        emit(rrow("baseline", sub))
        emit(rrow("U1 INTO MQ main (≤1R) [reg: worse]", sub[sub["into_mq_main"]]))
        emit(rrow("U1 not into MQ main", sub[~sub["into_mq_main"]]))
        emit(rrow("U1 INTO structural (pdHLC/VA/IB, ≤1R)", sub[sub["into_struct"]]))
        emit(rrow("U1 not into structural", sub[~sub["into_struct"]]))
        emit(rrow("U1 INTO any (MQ main ∪ struct)", sub[sub["into_any"]]))
        emit(rrow("U1 clear of all (≥1R air)", sub[~sub["into_any"]]))
        emit(rrow("U3b INTO cluster zone (≤1R) [reg: worse]", sub[sub["into_cluster"]]))
        emit(rrow("U3b not into cluster", sub[~sub["into_cluster"]]))
        emit(rrow("U2 break-retest MQ main [reg: better]", sub[sub["u2_mq"]]))
        emit(rrow("U2 rest (MQ)", sub[~sub["u2_mq"]]))
        emit(rrow("U2 break-retest STRUCT (exploratory)", sub[sub["u2_struct"]]))
        emit(rrow("U2 rest (struct)", sub[~sub["u2_struct"]]))
        emit("")

    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"written {OUT}")


if __name__ == "__main__":
    main()
