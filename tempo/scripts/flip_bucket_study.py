"""flip_bucket_study.py — inside the climax bars: winners vs losers, bucketed (S119-tempo).

Trade generation = FROZEN current-best config (identical to flip_trap_mgmt RR2 control):
climax flip + IBS direction (0.55/0.45, middle = no signal) + SAR on opposite flip
+ EB opposite-IBS scratch + fixed 2R target; stop 1 tick beyond the 2-bar box; one
position; conservative both-in-bar -> stop; session end marked to close.

At ENTRY (close of SB = bar i; pre-SB climax = bar i-1) a feature vector is recorded.
No lookahead: only bars <= i, prior-day levels, and open-of-day. Session hi/lo are
RUNNING values up to bar i (the levels-file hod/lod are full-day -> not used).

Features (abr = ABR(8) recovered from amp_abr8 at the SB):
  climax internals : tpct1 tpct2 tempo_ratio amp1 amp2 amp_sum dur1 dur2 dur_ratio
                     vol_ratio ibs1 ibs2 range1 range2 box_pts box_abr overlap
                     sb_poke_abr rt_depth_abr
  context          : net6_abr net20_abr fade_run20 eff10 t10 ncx20 prev_state
                     sess_net_abr pos_in_day_range dayrange_abr gap_abr
                     new20 new60 newsess beyond_pd room_abr dist_lvl_abr
  time / meta      : session_min hour_ct dow side n_prior_day prev_res_day
Outcome: pnl (pts), R = pnl/risk, win = pnl > 0.

Analysis (printed + dated CSVs in tempo/outputs/):
  A. winners vs losers per feature: median W / median L / AUC (P(feat_W > feat_L))
  B. numeric buckets: quartile edges fit on TRAIN 2021-24 only; per-bucket n/avgR/win%
     for train AND test 2025-26; CONSISTENT flag = Q4-Q1 avgR spread same sign both
     halves and |spread| >= 0.05R in both
  C. categoricals: TOD hour, DOW, side, prev-trade-result, prev_state, flags

    python tempo/scripts/flip_bucket_study.py
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
LV = ROOT / "tempo" / "outputs" / "levels_by_day.json"
OUT = ROOT / "tempo" / "outputs"
TICK = 0.25
PT_USD = 50.0
RR = 2

NUMERIC = ["tpct1", "tpct2", "tempo_ratio", "amp1", "amp2", "amp_sum", "dur1", "dur2",
           "dur_ratio", "vol_ratio", "ibs1", "ibs2", "range1", "range2", "box_pts",
           "box_abr", "overlap", "sb_poke_abr", "rt_depth_abr", "net6_abr", "net20_abr",
           "eff10", "t10", "ncx20", "sess_net_abr", "pos_in_day_range", "dayrange_abr",
           "gap_abr", "room_abr", "dist_lvl_abr", "session_min"]
FLAGS = ["fade_run20", "new20", "new60", "newsess", "beyond_pd"]
CATS = ["hour_ct", "dow", "side", "prev_state", "prev_res_day"]


def bar_dir(h, l, c, i):
    rg = h[i] - l[i]
    if rg < TICK / 2:
        return 0
    ibs = (c[i] - l[i]) / rg
    return 1 if ibs >= 0.55 else (-1 if ibs <= 0.45 else 0)


def features(g, i, lv, n_prior, prev_res):
    h = g["high"].to_numpy(); l = g["low"].to_numpy()
    o = g["open"].to_numpy(); c = g["close"].to_numpy()
    j = i - 1
    r1 = h[j] - l[j]; r2 = h[i] - l[i]
    amp2 = g["amp_abr8"].iat[i]
    abr = 100.0 * r2 / amp2 if amp2 and amp2 > 0 else np.nan
    sig_short = bar_dir(h, l, c, j) == 1
    sgn = -1 if sig_short else 1
    en = c[i]
    hi2, lo2 = max(h[j], h[i]), min(l[j], l[i])

    runmax = h[:i + 1].max(); runmin = l[:i + 1].min()
    k20 = max(0, j - 20); k60 = max(0, j - 60)
    if sig_short:
        new20 = j > k20 and h[j] > h[k20:j].max()
        new60 = j > k60 and h[j] > h[k60:j].max()
        newsess = h[j] >= h[:j].max() if j > 0 else False
        sb_poke = (h[i] - h[j]) / abr if abr > 0 else np.nan
        rt_depth = (o[j] - c[i]) / abr if abr > 0 else np.nan
    else:
        new20 = j > k20 and l[j] < l[k20:j].min()
        new60 = j > k60 and l[j] < l[k60:j].min()
        newsess = l[j] <= l[:j].min() if j > 0 else False
        sb_poke = (l[j] - l[i]) / abr if abr > 0 else np.nan
        rt_depth = (c[i] - o[j]) / abr if abr > 0 else np.nan

    net6 = (c[i] - c[i - 6]) / abr if i >= 6 and abr > 0 else np.nan
    net20 = (c[i] - c[i - 20]) / abr if i >= 20 and abr > 0 else np.nan
    # fading the 20-bar run: run direction opposite to trade direction
    fade = bool(net20 * sgn < 0) if net20 == net20 else False
    cx = g["climax"].to_numpy()
    ncx20 = int(cx[max(0, i - 21):max(0, i - 1)].sum())
    prev_state = int(g["state"].iat[i - 2]) if i >= 2 else -1

    ood = lv.get("ood") if lv else None
    coy = lv.get("coy") if lv else None
    sess_net = (c[i] - ood) / abr if ood and abr > 0 else np.nan
    drange = runmax - runmin
    posdr = (c[i] - runmin) / drange if drange > 0 else np.nan
    gap = (ood - coy) / abr if ood and coy and abr > 0 else np.nan

    lvls = []
    if lv:
        for k in ("hoy", "loy", "coy", "pmid"):
            if lv.get(k):
                lvls.append(lv[k])
        if lv.get("vay"):
            lvls += [x for x in lv["vay"] if x]
    hoy, loy = (lv.get("hoy"), lv.get("loy")) if lv else (None, None)
    beyond_pd = bool((hoy and en > hoy) or (loy and en < loy))
    dist_lvl = min((abs(en - x) for x in lvls), default=np.nan)
    ahead = [x for x in lvls if (x - en) * sgn > 0]
    room = min((abs(x - en) for x in ahead), default=np.nan)

    v = g["vol"].to_numpy(dtype=float)
    d1 = g["duration_s"].iat[j]; d2 = g["duration_s"].iat[i]
    t1 = g["tempo"].iat[j]; t2 = g["tempo"].iat[i]
    start = pd.Timestamp(g["start"].iat[i])
    ib1 = (c[j] - l[j]) / r1 if r1 > 0 else np.nan
    ib2 = (c[i] - l[i]) / r2 if r2 > 0 else np.nan

    return {
        "tpct1": g["tpct"].iat[j], "tpct2": g["tpct"].iat[i],
        "tempo_ratio": t2 / t1 if t1 and t1 > 0 else np.nan,
        "amp1": g["amp_abr8"].iat[j], "amp2": amp2,
        "amp_sum": (g["amp_abr8"].iat[j] or np.nan) + (amp2 or np.nan),
        "dur1": d1, "dur2": d2, "dur_ratio": d2 / d1 if d1 and d1 > 0 else np.nan,
        "vol_ratio": v[i] / v[j] if v[j] > 0 else np.nan,
        "ibs1": ib1, "ibs2": ib2, "range1": r1, "range2": r2,
        "box_pts": hi2 - lo2 + TICK,
        "box_abr": (hi2 - lo2 + TICK) / abr if abr > 0 else np.nan,
        "overlap": (min(h[j], h[i]) - max(l[j], l[i])) / r1 if r1 > 0 else np.nan,
        "sb_poke_abr": sb_poke, "rt_depth_abr": rt_depth,
        "net6_abr": net6, "net20_abr": net20, "fade_run20": fade,
        "eff10": g["eff10"].iat[i], "t10": g["t10"].iat[i], "ncx20": ncx20,
        "prev_state": prev_state, "sess_net_abr": sess_net,
        "pos_in_day_range": posdr, "dayrange_abr": drange / abr if abr > 0 else np.nan,
        "gap_abr": gap, "new20": bool(new20), "new60": bool(new60),
        "newsess": bool(newsess), "beyond_pd": beyond_pd,
        "room_abr": room / abr if abr > 0 else np.nan,
        "dist_lvl_abr": dist_lvl / abr if abr > 0 else np.nan,
        "session_min": g["session_min"].iat[i],
        "hour_ct": int(start.hour), "dow": int(pd.Timestamp(g["date"].iloc[0]).dayofweek),
        "side": "short" if sig_short else "long",
        "n_prior_day": n_prior, "prev_res_day": prev_res,
    }


def sim_day(g, lv):
    """Exact replica of flip_trap_mgmt.sim_day mode=RR2, plus feature capture."""
    h = g["high"].to_numpy(); l = g["low"].to_numpy(); c = g["close"].to_numpy()
    cx = g["climax"].to_numpy()
    n = len(g)
    trades = []
    pos = None
    for i in range(1, n):
        if pos is not None:
            sh = pos["short"]; sgn = -1 if sh else 1
            hs = h[i] >= pos["stop"] if sh else l[i] <= pos["stop"]
            if hs:
                trades.append({**pos, "res": "stop", "pnl": (pos["stop"] - pos["en"]) * sgn})
                pos = None
            else:
                if pos["tg"] is not None and (l[i] <= pos["tg"] if sh else h[i] >= pos["tg"]):
                    trades.append({**pos, "res": "target", "pnl": (pos["tg"] - pos["en"]) * sgn})
                    pos = None
                elif i == pos["i"] + 1:
                    d = bar_dir(h, l, c, i)
                    if (not cx[i]) and ((not sh and d == -1) or (sh and d == 1)):
                        trades.append({**pos, "res": "eb_scr", "pnl": (c[i] - pos["en"]) * sgn})
                        pos = None
        if not (cx[i] and cx[i - 1]):
            continue
        d1, d2 = bar_dir(h, l, c, i - 1), bar_dir(h, l, c, i)
        if d1 == 0 or d2 == 0 or d1 == d2:
            continue
        sig_short = d1 == 1
        if pos is not None:
            if sig_short != pos["short"]:
                sgn = -1 if pos["short"] else 1
                trades.append({**pos, "res": "rev", "pnl": (c[i] - pos["en"]) * sgn})
                pos = None
            else:
                continue
        hi2, lo2 = max(h[i - 1], h[i]), min(l[i - 1], l[i])
        en = c[i]
        st = hi2 + TICK if sig_short else lo2 - TICK
        rk = abs(en - st)
        if rk < TICK:
            continue
        sgn = -1 if sig_short else 1
        prev_res = trades[-1]["res"] if trades else "none"
        f = features(g, i, lv, len(trades), prev_res)
        pos = {"i": i, "short": sig_short, "en": en, "stop": st, "rk": rk,
               "tg": en + sgn * RR * rk, "date": g["date"].iloc[0], **f}
    if pos is not None:
        sgn = -1 if pos["short"] else 1
        trades.append({**pos, "res": "open", "pnl": (c[n - 1] - pos["en"]) * sgn})
    return trades


def auc(a, b):
    """P(sample from a > sample from b), rank-based; a=winners, b=losers."""
    a = a[~np.isnan(a)]; b = b[~np.isnan(b)]
    if len(a) == 0 or len(b) == 0:
        return np.nan
    allv = np.concatenate([a, b])
    r = pd.Series(allv).rank().to_numpy()
    return (r[:len(a)].sum() - len(a) * (len(a) + 1) / 2) / (len(a) * len(b))


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    levels = json.loads(LV.read_text(encoding="utf-8")) if LV.exists() else {}
    trades = []
    for d, g in df.groupby("date"):
        trades += sim_day(g.reset_index(drop=True), levels.get(d))
    t = pd.DataFrame(trades)
    t["R"] = t["pnl"] / t["rk"]
    t["win"] = t["pnl"] > 0
    t["year"] = t["date"].str[:4].astype(int)
    t.to_csv(OUT / f"flip_bucket_trades_{today}.csv", index=False)
    print(f"trades n={len(t)}  avgR {t['R'].mean():+.4f}  "
          f"win% {t['win'].mean():.1%}  (sanity vs flip_trap_mgmt RR2 full)")

    # --- A. winners vs losers ---
    w = t[t["pnl"] > 0]; lo = t[t["pnl"] < 0]
    rows = []
    for f in NUMERIC:
        rows.append({"feature": f, "med_W": w[f].median(), "med_L": lo[f].median(),
                     "AUC_W>L": round(auc(w[f].to_numpy(dtype=float),
                                          lo[f].to_numpy(dtype=float)), 3)})
    wl = pd.DataFrame(rows)
    wl["dev"] = (wl["AUC_W>L"] - 0.5).abs()
    wl = wl.sort_values("dev", ascending=False).drop(columns="dev")
    wl.to_csv(OUT / f"flip_bucket_winloss_{today}.csv", index=False)
    print("\n=== A. winners (n=%d) vs losers (n=%d) — sorted by |AUC-0.5| ===" % (len(w), len(lo)))
    print(wl.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    # --- B. quartile buckets, train edges, train/test ---
    tr = t[t["year"] <= 2024]; te = t[t["year"] >= 2025]
    print(f"\n=== B. quartile buckets (edges fit on TRAIN 21-24 n={len(tr)}; "
          f"test 25-26 n={len(te)}) ===")
    brow = []
    for f in NUMERIC:
        x = tr[f].astype(float)
        try:
            edges = x.quantile([0.25, 0.5, 0.75]).to_numpy()
        except Exception:
            continue
        if len(np.unique(edges)) < 3:
            continue
        def bq(s):
            return pd.cut(s.astype(float), [-np.inf, *edges, np.inf], labels=[1, 2, 3, 4])
        trq, teq = bq(tr[f]), bq(te[f])
        rec = {"feature": f}
        for name, sub, q in (("tr", tr, trq), ("te", te, teq)):
            for b in (1, 2, 3, 4):
                m = sub[q == b]
                rec[f"{name}_R{b}"] = round(m["R"].mean(), 3) if len(m) else np.nan
            rec[f"{name}_n1"] = int((q == 1).sum()); rec[f"{name}_n4"] = int((q == 4).sum())
        sp_tr = rec["tr_R4"] - rec["tr_R1"]; sp_te = rec["te_R4"] - rec["te_R1"]
        rec["spread_tr"] = round(sp_tr, 3); rec["spread_te"] = round(sp_te, 3)
        rec["consistent"] = bool(sp_tr * sp_te > 0 and abs(sp_tr) >= 0.05 and abs(sp_te) >= 0.05)
        brow.append(rec)
    bt = pd.DataFrame(brow)
    bt.to_csv(OUT / f"flip_bucket_quartiles_{today}.csv", index=False)
    cols = ["feature", "tr_R1", "tr_R2", "tr_R3", "tr_R4", "te_R1", "te_R2", "te_R3",
            "te_R4", "spread_tr", "spread_te", "consistent"]
    bt2 = bt[cols].sort_values("consistent", ascending=False)
    print(bt2.to_string(index=False))

    # --- C. categoricals + flags (train | test avgR, n) ---
    print("\n=== C. categorical / flag buckets (avgR train | test) ===")
    crow = []
    for f in FLAGS + CATS:
        for val, gtr in tr.groupby(f):
            gte = te[te[f] == val]
            crow.append({"feature": f, "value": val,
                         "tr_n": len(gtr), "tr_R": round(gtr["R"].mean(), 3),
                         "te_n": len(gte),
                         "te_R": round(gte["R"].mean(), 3) if len(gte) else np.nan})
    ct = pd.DataFrame(crow)
    ct.to_csv(OUT / f"flip_bucket_cats_{today}.csv", index=False)
    print(ct.to_string(index=False))

    # --- D. side-controlled check of the consistent numerics ---
    # ibs1 / sess_net_abr / pos_in_day_range correlate with side (bar1 bull -> short);
    # verify each survivor WITHIN each side: above/below the train median, train | test.
    print("\n=== D. side-controlled: avgR above|below train median, within side ===")
    drow = []
    for f in ["sb_poke_abr", "amp2", "dayrange_abr", "pos_in_day_range",
              "sess_net_abr", "ibs1", "tpct2"]:
        for side in ("long", "short"):
            med = tr[tr["side"] == side][f].median()
            rec = {"feature": f, "side": side, "train_med": round(med, 3)}
            for name, sub in (("tr", tr), ("te", te)):
                s = sub[sub["side"] == side]
                hi = s[s[f] > med]; lo2 = s[s[f] <= med]
                rec[f"{name}_hi_R"] = round(hi["R"].mean(), 3) if len(hi) else np.nan
                rec[f"{name}_lo_R"] = round(lo2["R"].mean(), 3) if len(lo2) else np.nan
                rec[f"{name}_n"] = len(s)
            drow.append(rec)
    dtab = pd.DataFrame(drow)
    dtab.to_csv(OUT / f"flip_bucket_sidectl_{today}.csv", index=False)
    print(dtab.to_string(index=False))


if __name__ == "__main__":
    main()
