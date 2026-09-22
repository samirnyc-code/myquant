"""Do Blind Spots WORK as reaction zones? ES+NQ, 1-min bars, matched null, confluence split.

For each session's 10 BLs: first same-day touch, then measure over the rest of the session
  reaction    = max move AWAY from the level after touch (rejection), / session range
  penetration = max move THROUGH the level after touch, / session range
  rejected    = reaction > penetration
NULL = matched-band random levels (same per-day offset span). CONFLUENCE = BL within tol of a
same-day gamma level {CR,PS,HVL,Gamma Wall 0DTE}; test if confluent BLs reject harder (MQ's claim).
Honest: first-touch only, no look-ahead, no fills claimed.
"""
import csv, json
from pathlib import Path
import numpy as np, pandas as pd
MQ = Path("data/menthorq")
RNG = np.random.default_rng(7)

INSTR = {"ES1!": ("data/ticks_continuous", 0.10),      # (tick dir, confluence tol as % of price)
         "NQ1!": ("data/ticks_continuous_NQ", 0.10)}
STRUCT = ["Call Resistance", "Put Support", "HVL", "Gamma Wall 0DTE"]


def load_bl(sym):
    d = {}
    for r in csv.DictReader(open(MQ / f"{sym}_mq_blindspots_history.csv")):
        v = [float(r[f"bl_{i}"]) for i in range(1, 11) if r.get(f"bl_{i}")]
        if len(v) == 10:
            d[r["date"]] = v
    return d


def load_gamma(sym):
    f = MQ / f"{sym}_mq_levels_history_raw.jsonl"
    out = {}
    if not f.exists():
        return out
    for ln in open(f, encoding="utf-8"):
        try:
            it = json.loads(ln).get("item", {})
        except Exception:
            continue
        for lv in it.get("levels", []):
            if lv.get("level_type") == "gamma_levels":
                out[it["date"]] = {v["name"]: v["value"] for v in lv["level_values"]}
    return out


def bars(tickdir, date):
    p = Path(tickdir) / f"{date}.parquet"
    if not p.exists():
        return None
    t = pd.read_parquet(p, columns=["DateTime", "Price"]).set_index("DateTime")
    o = t.Price.resample("1min").ohlc().dropna()
    o = o[(o.index.time >= pd.to_datetime("08:30").time()) &
          (o.index.time <= pd.to_datetime("15:00").time())]
    return o if len(o) > 60 else None


W = 20  # post-touch window in minutes (bars) — a reaction zone should bounce SOON


def touches(o, levels, open_px):
    hi, lo = o.high.values, o.low.values
    rng = hi.max() - lo.min()
    if rng <= 0:
        return []
    out = []
    for L in levels:
        above = L > open_px
        idx = np.where(hi >= L)[0] if above else np.where(lo <= L)[0]
        if len(idx) == 0 or idx[0] >= len(o) - 5:
            continue
        i0 = idx[0]
        j = min(i0 + W, len(o))
        h2, l2 = hi[i0:j], lo[i0:j]     # only the W bars AFTER first touch
        react = (L - l2.min()) if above else (h2.max() - L)   # favorable (rejection)
        pen = (h2.max() - L) if above else (L - l2.min())     # adverse (break through)
        out.append((L, react / rng, pen / rng, react > pen))
    return out


def run():
    real, null, conf, iso = [], [], [], []
    sessions = 0
    for sym, (tdir, tolpct) in INSTR.items():
        BL, GAM = load_bl(sym), load_gamma(sym)
        for date, levels in sorted(BL.items()):
            o = bars(tdir, date)
            if o is None:
                continue
            sessions += 1
            open_px = float(o.open.iloc[0])
            tol = open_px * tolpct / 100
            g = GAM.get(date, {})
            glev = [g[k] for k in STRUCT if g.get(k) is not None]
            for L, r, p, rej in touches(o, levels, open_px):
                real.append((r, p, rej))
                is_conf = any(abs(L - gl) <= tol for gl in glev)
                (conf if is_conf else iso).append((r, p, rej))
            # matched-band null: random levels over the same offset span
            offs = [(L - open_px) / open_px for L in levels]
            rnd = [open_px * (1 + o_) for o_ in RNG.uniform(min(offs), max(offs), 40)]
            for L, r, p, rej in touches(o, rnd, open_px):
                null.append((r, p, rej))

    def stat(rows):
        a = np.array([x[0] for x in rows]); pn = np.array([x[1] for x in rows])
        rj = np.array([x[2] for x in rows])
        return len(rows), np.median(a), np.median(pn), rj.mean()

    def z_rate(g1, g2):
        n1, _, _, p1 = stat(g1); n2, _, _, p2 = stat(g2)
        se = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
        return (p1 - p2) / se if se else 0

    print(f"BLIND SPOT EDGE STUDY — ES+NQ, 1-min, {sessions} sessions\n")
    print(f"  {'group':14}{'n':>7}{'med_react':>11}{'med_pen':>10}{'reject%':>10}")
    for name, g in [("BLIND SPOTS", real), ("random null", null),
                    ("BL+gamma(conf)", conf), ("BL isolated", iso)]:
        n, mr, mp, rj = stat(g)
        print(f"  {name:14}{n:>7}{mr:>11.3f}{mp:>10.3f}{rj*100:>9.1f}%")
    print()
    print(f"  BL vs null   — reject-rate z = {z_rate(real, null):+.1f}")
    ra = np.array([x[0] for x in real]); na = np.array([x[0] for x in null])
    ze = (ra.mean() - na.mean()) / np.sqrt(ra.var()/len(ra) + na.var()/len(na))
    print(f"  BL vs null   — reaction-magnitude z = {ze:+.1f}")
    print(f"  confluent vs isolated BL — reject-rate z = {z_rate(conf, iso):+.1f}  "
          f"(MQ's key claim: gamma-stacked BLs react harder)")
    print(f"  confluent BL vs null     — reject-rate z = {z_rate(conf, null):+.1f}")


if __name__ == "__main__":
    run()
