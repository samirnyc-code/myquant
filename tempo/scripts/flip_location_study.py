"""flip_location_study.py — WHERE do the good flips fire + hindsight day-extreme check (S119-tempo).

Trade population (PRECISE): every trade of the current-best config = climax flip +
IBS direction + SAR + EB-scratch + fixed 2R (the flip_trap_mgmt RR2 control, n=2748,
regenerated with features by flip_bucket_study.py). That population MIXES both entry
kinds; here each trade is tagged:
  Basic = opened from flat (incl. first of day / after stop/target/eb_scr)
  SAR   = opened by reversing on an opposite flip signal (prev trade that day ended 'rev';
          by construction the reversal entry is on the SAME bar as that exit)
NOTE: the NT chart currently renders 3R targets; every number here is the 2R sim.

Sections:
  S0 entry-kind split + the two S119 findings (hour-8, beyond-PD) within each kind
  S1 entry location within YESTERDAY's range [LOY..HOY], 6 zones
  S2 yesterday's VALUE AREA zones + reversion-toward-POC vs away
  S3 today's INITIAL BALANCE (60-min) zones, entries after IB only
  S4 hindsight: did the flip's trap extreme end up as the day's final HOD/LOD?
     (the user's failed-BO-of-PD-extreme intuition; NOT tradeable at entry)

    python tempo/scripts/flip_location_study.py
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "tempo" / "outputs" / "flip_bucket_trades_2026-09-12.csv"
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
LV = ROOT / "tempo" / "outputs" / "levels_by_day.json"
OUT = ROOT / "tempo" / "outputs"
PT_USD = 50.0


def stats(t, label):
    pnl = t["pnl"]
    gp = pnl[pnl > 0].sum(); gl = -pnl[pnl < 0].sum()
    return {"group": label, "n": len(t),
            "win%": round(100 * (pnl > 0).mean(), 1) if len(t) else np.nan,
            "PF": round(gp / gl, 2) if gl > 0 else np.inf,
            "tot_pts": round(pnl.sum(), 1),
            "$/trade": round(pnl.mean() * PT_USD, 1) if len(t) else np.nan}


def show(title, rows):
    print(f"\n=== {title} ===")
    print(pd.DataFrame(rows).to_string(index=False))
    return rows


def main():
    today = dt.date.today().isoformat()
    t = pd.read_csv(SRC)
    levels = json.loads(LV.read_text(encoding="utf-8"))
    df = pd.read_parquet(ENG)
    df = df[df["state"] >= 0].sort_values(["date", "bar"]).reset_index(drop=True)
    byday = {d: g.reset_index(drop=True) for d, g in df.groupby("date")}

    t["kind"] = np.where(t["prev_res_day"] == "rev", "SAR", "Basic")
    for c in ("hoy", "loy", "coy"):
        t[c] = t["date"].map(lambda d, c=c: levels.get(d, {}).get(c, np.nan))
    t["val_y"] = t["date"].map(lambda d: (levels.get(d, {}).get("vay") or [np.nan] * 3)[0])
    t["poc_y"] = t["date"].map(lambda d: (levels.get(d, {}).get("vay") or [np.nan] * 3)[1])
    t["vah_y"] = t["date"].map(lambda d: (levels.get(d, {}).get("vay") or [np.nan] * 3)[2])
    t["ib_lo"] = t["date"].map(lambda d: (levels.get(d, {}).get("ib") or [np.nan] * 2)[0])
    t["ib_hi"] = t["date"].map(lambda d: (levels.get(d, {}).get("ib") or [np.nan] * 2)[1])

    # trap extreme + hindsight day-extreme flag from the day's bars
    trap_ext = np.full(len(t), np.nan); held = np.zeros(len(t), bool)
    for r in t.itertuples():
        g = byday.get(r.date)
        if g is None:
            continue
        h = g["high"].to_numpy(); l = g["low"].to_numpy()
        i = int(r.i)
        if r.side == "short":
            ext = max(h[i - 1], h[i])
            trap_ext[t.index.get_loc(r.Index)] = ext
            held[t.index.get_loc(r.Index)] = ext >= h.max()
        else:
            ext = min(l[i - 1], l[i])
            trap_ext[t.index.get_loc(r.Index)] = ext
            held[t.index.get_loc(r.Index)] = ext <= l.min()
    t["trap_ext"] = trap_ext
    t["made_day_extreme"] = held

    tr = t[t["year"] <= 2024]; te = t[t["year"] >= 2025]
    allrows = {}

    # --- S0 ---
    r0 = []
    for k in ("Basic", "SAR"):
        r0 += [stats(tr[tr["kind"] == k], f"{k}, 21-24"),
               stats(te[te["kind"] == k], f"{k}, 25-26")]
    for k in ("Basic", "SAR"):
        for name, sub in (("21-24", tr), ("25-26", te)):
            s = sub[sub["kind"] == k]
            r0.append(stats(s[s["hour_ct"] == 8], f"{k} hour-8, {name}"))
            r0.append(stats(s[s["beyond_pd"]], f"{k} beyondPD, {name}"))
    allrows["s0_kind"] = show("S0 entry kind (Basic=from flat, SAR=reversal entry) + findings within kind", r0)

    # --- S1 location within yesterday's range ---
    rngy = t["hoy"] - t["loy"]
    t["pos_pd"] = (t["en"] - t["loy"]) / rngy
    zones = [(-np.inf, 0, "below LOY"), (0, .25, "LOY..25%"), (.25, .5, "25..50%"),
             (.5, .75, "50..75%"), (.75, 1, "75%..HOY"), (1, np.inf, "above HOY")]
    r1 = []
    for name, sub in (("21-24", tr), ("25-26", te)):
        p = (sub["en"] - sub["loy"]) / (sub["hoy"] - sub["loy"])
        for a, b, z in zones:
            r1.append(stats(sub[(p > a) & (p <= b)], f"{z}, {name}"))
        r1.append(stats(sub[p.isna()], f"no levels, {name}"))
    allrows["s1_pdzone"] = show("S1 entry location in yesterday's range", r1)

    # --- S2 value area yesterday ---
    r2 = []
    for name, sub in (("21-24", tr), ("25-26", te)):
        r2 += [stats(sub[sub["en"] > sub["vah_y"]], f"above VAH-Y, {name}"),
               stats(sub[(sub["en"] <= sub["vah_y"]) & (sub["en"] >= sub["val_y"])],
                     f"inside VA-Y, {name}"),
               stats(sub[sub["en"] < sub["val_y"]], f"below VAL-Y, {name}")]
    for name, sub in (("21-24", tr), ("25-26", te)):
        toward = ((sub["side"] == "short") & (sub["en"] > sub["poc_y"])) | \
                 ((sub["side"] == "long") & (sub["en"] < sub["poc_y"]))
        ok = sub["poc_y"].notna()
        r2 += [stats(sub[toward & ok], f"flip TOWARD POC-Y, {name}"),
               stats(sub[~toward & ok], f"flip AWAY from POC-Y, {name}")]
    allrows["s2_va"] = show("S2 yesterday's value area", r2)

    # --- S3 initial balance (today, first 60 min); entries after IB only ---
    r3 = []
    for name, sub in (("21-24", tr), ("25-26", te)):
        s = sub[(sub["session_min"] > 60) & sub["ib_hi"].notna()]
        r3 += [stats(s[s["en"] > s["ib_hi"]], f"above IB-high, {name}"),
               stats(s[(s["en"] <= s["ib_hi"]) & (s["en"] >= s["ib_lo"])], f"inside IB, {name}"),
               stats(s[s["en"] < s["ib_lo"]], f"below IB-low, {name}")]
    allrows["s3_ib"] = show("S3 today's initial balance (entries after minute 60 only)", r3)

    # --- S4 hindsight day-extreme ---
    r4 = []
    for name, sub in (("21-24", tr), ("25-26", te), ("full", t)):
        bp = sub[sub["beyond_pd"]]
        r4 += [stats(bp[bp["made_day_extreme"]], f"beyondPD + trap WAS day extreme, {name}"),
               stats(bp[~bp["made_day_extreme"]], f"beyondPD + it was not, {name}")]
    r4 += [stats(t[t["made_day_extreme"]], "ALL trades where trap = day extreme, full"),
           stats(t[~t["made_day_extreme"]], "ALL others, full")]
    allrows["s4_hindsight"] = show("S4 HINDSIGHT (not tradeable): trap extreme ended as final HOD/LOD?", r4)
    bp = t[t["beyond_pd"]]
    w = bp[bp["pnl"] > 0]
    print(f"\nbeyond-PD winners: n={len(w)} of {len(bp)}; of those winners "
          f"{(w['made_day_extreme']).sum()} ({(w['made_day_extreme']).mean():.0%}) "
          f"had trap = final day extreme")

    for name, rows in allrows.items():
        pd.DataFrame(rows).to_csv(OUT / f"flip_loc_{name}_{today}.csv", index=False)


if __name__ == "__main__":
    main()
