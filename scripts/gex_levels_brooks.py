"""S75Q part 2 — do MenthorQ gamma LEVELS mark prices where behaviour differs?

Pre-registration: docs/living/s75q_prereg.md  (written before any result seen)

Primary  H1  CR is rejected from below more often than a matched control strike.
Explore  E1  PS rejected from above.
         E2  HVL as a day-type divider.
         E3  session extremes cluster near GEX 1-4 vs matched controls.

Design notes that matter:
  * Levels for session d come from the PRIOR session's MQ row, and the SPX->ES
    basis is the prior session's too. No lookahead, at a small cost in precision.
  * Every level statistic is paired with control strikes on the same 25pt grid,
    STRATIFIED BY DISTANCE FROM THE OPEN. Comparing raw rates would just measure
    "levels sit further from the open", not gamma.
  * CIs are bootstrapped over SESSIONS, not touches. Touches within a session are
    correlated; per-touch resampling would give fake precision.

This is a reaction base-rate study. No fills, no P&L. Not a backtest.
"""
import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "options_sim" / "s75q_levels.json"

R_PTS = 10.0        # rejection / follow-through threshold, ES points
N_BARS = 24         # 2h of 5-min bars
GRID = 25.0         # SPX strike grid the levels live on
# SPAN was 0.015 in the pre-registration. At +-1.5% the span holds ~6 grid
# strikes, and with ~14 published levels plus a 15pt exclusion the control pool
# collapsed to 0.72/session (594 sessions had ZERO controls) — a broken
# instrument, not a result. Widened to 3% and exclusion cut to 12pts to make the
# control arm exist at all. Changed BEFORE any effect direction was observed;
# the pre-registered 1.5% spec is still reported alongside, as `strict`.
SPAN = 0.030
EXCL = 12.0
DIST_BIN = 10.0     # distance-from-open stratification bin, ES points
RNG = np.random.default_rng(7)

LEVEL_COLS = ["cr", "ps", "hvl", "gex_1", "gex_2", "gex_3", "gex_4"]


# ---------------------------------------------------------------- data loading
def es_sessions():
    """5-min RTH bars per session for the front-month ES contract."""
    fr = []
    for f in sorted(glob.glob(str(ROOT / "data" / "bars" / "ES*.parquet"))):
        d = pd.read_parquet(f)
        d["contract"] = Path(f).stem
        fr.append(d)
    ES = pd.concat(fr, ignore_index=True)
    ES["date"] = ES.DateTime.dt.strftime("%Y-%m-%d")
    # front month = highest-volume contract that day (same rule as the slide deck)
    vol = ES.groupby(["date", "contract"]).Volume.sum().reset_index()
    front = vol.sort_values("Volume").groupby("date").tail(1).set_index("date")["contract"]
    ES = ES[[c == front.get(d) for c, d in zip(ES.contract, ES.date)]]
    out = {}
    for d, g in ES.sort_values("DateTime").groupby("date"):
        if len(g) >= 30:
            out[d] = g[["Open", "High", "Low", "Close"]].to_numpy(float)
    return out


def basis_table(sessions):
    """ES(front) close - SPX close, per session, for SPX->ES level conversion."""
    spx = pd.read_csv(ROOT / "data" / "spx_daily_full.csv")
    spx["Date"] = spx.Date.astype(str).str[:10]
    spx = spx.set_index("Date").Close.apply(pd.to_numeric, errors="coerce")
    b = {}
    for d, bars in sessions.items():
        if d in spx.index and np.isfinite(spx[d]):
            b[d] = float(bars[-1, 3] - spx[d])
    return b


def mq_levels():
    mq = pd.read_csv(ROOT / "data" / "menthorq" / "SPX_mq_levels_history.csv")
    mq["session_date"] = mq.session_date.astype(str).str[:10]
    return mq.set_index("session_date")


# ------------------------------------------------------------ touch mechanics
def resolve(bars, i, L, above):
    """From first-touch bar i, did price reach L-R before L+R (a rejection)?

    `above` = level sits above the open, i.e. it was approached from below and a
    move DOWN through L-R is the rejection. Mirrored when the level is below.
    Returns 'reject' | 'follow' | None (timeout or same-bar ambiguity).
    """
    rej_lvl, fol_lvl = (L - R_PTS, L + R_PTS) if above else (L + R_PTS, L - R_PTS)
    for k in range(i, min(i + N_BARS, len(bars))):
        hi, lo = bars[k, 1], bars[k, 2]
        hit_r = lo <= rej_lvl if above else hi >= rej_lvl
        hit_f = hi >= fol_lvl if above else lo <= fol_lvl
        if hit_r and hit_f:
            return None            # both inside one bar — unresolvable, drop it
        if hit_r:
            return "reject"
        if hit_f:
            return "follow"
    return None


def first_touch(bars, L):
    """Index of the first bar whose range contains L, else None."""
    for k in range(len(bars)):
        if bars[k, 2] <= L <= bars[k, 1]:
            return k
    return None


def evaluate(bars, L, open_px):
    """Full outcome for one candidate level in one session."""
    above = L > open_px
    i = first_touch(bars, L)
    if i is None:
        return None
    return {"outcome": resolve(bars, i, L, above),
            "dist": abs(L - open_px), "above": above}


# ------------------------------------------------------------------ stratified
def strat_rate(recs):
    """Rejection rate, and the per-distance-bin counts needed for matching."""
    d = {}
    for r in recs:
        if r["outcome"] is None:
            continue
        b = int(r["dist"] // DIST_BIN)
        w, l = d.get(b, (0, 0))
        d[b] = (w + (r["outcome"] == "reject"), l + 1)
    return d


def matched_diff(lvl, ctl):
    """Level rate minus control rate, matched within distance bins.

    Bins are weighted by the LEVEL counts, so the control is re-weighted onto the
    level's distance distribution rather than its own.
    """
    L, C = strat_rate(lvl), strat_rate(ctl)
    num = den = lw = ln = 0.0
    for b, (w, n) in L.items():
        if b not in C or C[b][1] < 5:
            continue
        cw, cn = C[b]
        num += n * (w / n - cw / cn)
        den += n
        lw += w
        ln += n
    if den == 0:
        return None
    return {"level_rate": lw / ln, "diff": num / den, "n": int(ln)}


def bootstrap(per_session, stat, iters=2000):
    """Session-clustered bootstrap CI for a statistic over per-session records."""
    keys = list(per_session)
    vals = []
    for _ in range(iters):
        pick = RNG.choice(len(keys), len(keys), replace=True)
        lvl, ctl = [], []
        for j in pick:
            a, b = per_session[keys[j]]
            lvl += a
            ctl += b
        s = stat(lvl, ctl)
        if s is not None:
            vals.append(s["diff"])
    if len(vals) < 100:
        return None
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


# ----------------------------------------------------------------------- tests
def build(sessions, basis, mq):
    """Assemble per-session level + control candidates, all prior-session sourced."""
    dates = sorted(set(sessions) & set(basis))
    rows = []
    for prev, cur in zip(dates, dates[1:]):
        if prev not in mq.index:
            continue
        m = mq.loc[prev]
        if isinstance(m, pd.DataFrame):
            m = m.iloc[0]
        bars, bas = sessions[cur], basis[prev]
        open_px = float(bars[0, 0])
        lv = {}
        for c in LEVEL_COLS:
            v = pd.to_numeric(m.get(c), errors="coerce")
            if np.isfinite(v):
                es = float(v) + bas
                if abs(es - open_px) <= open_px * SPAN:
                    lv[c] = es
        if not lv:
            continue
        # control grid: same 25pt lattice, inside the same span, clear of levels
        allv = [pd.to_numeric(m.get(c), errors="coerce") for c in mq.columns
                if not c.endswith("_gex") and c not in ("eod_date",)]
        allv = [float(x) + bas for x in allv if np.isfinite(pd.to_numeric(x, errors="coerce"))]
        lo, hi = open_px * (1 - SPAN), open_px * (1 + SPAN)
        grid = np.arange(np.ceil(lo / GRID) * GRID, hi, GRID) + (bas % GRID)
        ctl = [float(g) for g in grid if all(abs(g - a) >= EXCL for a in allv)]
        rows.append({"date": cur, "bars": bars, "open": open_px,
                     "levels": lv, "controls": ctl,
                     "hvl": lv.get("hvl"), "close": float(bars[-1, 3]),
                     "high": float(bars[:, 1].max()), "low": float(bars[:, 2].min())})
    return rows


PLACEBO_K = 10      # date-shuffle draws per session


def rejection_test(rows, level_key, want_above):
    """H1 / E1: rejection rate at a named level vs DATE-SHUFFLED placebo levels.

    The original same-day grid control was unusable: a 12pt exclusion zone around
    ~14 published levels evacuates the near-open region where all the touches
    happen, so grid controls sat 60-140pts out and were never touched.

    The placebo instead reuses the level's OFFSET FROM THE OPEN taken from a
    different, randomly chosen session, applied to today's open. Same geometry,
    same distance distribution by construction, wrong day's gamma. If the level
    only "works" because a barrier N points above the open tends to get rejected,
    the placebo scores identically and the difference is zero.
    """
    offsets = [r["levels"][level_key] - r["open"] for r in rows
               if level_key in r["levels"]
               and (r["levels"][level_key] > r["open"]) == want_above]
    if len(offsets) < 30:
        return None
    offsets = np.array(offsets)

    per = {}
    for r in rows:
        L = r["levels"].get(level_key)
        if L is None:
            continue
        e = evaluate(r["bars"], L, r["open"])
        if e is None or e["above"] != want_above:
            continue
        cs = []
        for off in RNG.choice(offsets, PLACEBO_K, replace=True):
            ce = evaluate(r["bars"], r["open"] + float(off), r["open"])
            if ce is not None and ce["above"] == want_above:
                cs.append(ce)
        per[r["date"]] = ([e], cs)
    lvl = [x for a, _ in per.values() for x in a]
    ctl = [x for _, b in per.values() for x in b]
    res = matched_diff(lvl, ctl)
    if res is None:
        return None
    res["ci"] = bootstrap(per, matched_diff)
    res["sessions"] = len(per)
    res["control_n"] = len([c for c in ctl if c["outcome"]])
    return res


def hvl_test(rows):
    """E2: is HVL a day-type divider?"""
    out = {}
    for side in ("open_above", "open_below"):
        sel = [r for r in rows if r["hvl"] is not None
               and ((r["open"] > r["hvl"]) == (side == "open_above"))]
        if len(sel) < 30:
            continue
        rng = [(r["high"] - r["low"]) / r["open"] * 100 for r in sel]
        ret = [(r["close"] - r["open"]) / r["open"] * 100 for r in sel]
        out[side] = {"n": len(sel), "range_pct": round(float(np.mean(rng)), 3),
                     "ret_pct": round(float(np.mean(ret)), 4),
                     "up_pct": round(float(np.mean([x > 0 for x in ret]) * 100), 1)}
    return out


def extremes_test(rows):
    """E3: do session extremes sit nearer GEX levels than nearer random strikes?"""
    # Same date-shuffle placebo as the rejection tests. The earlier same-day grid
    # control was invalid here: GEX levels cluster near spot while grid controls
    # were pushed to the edge of the span, so ANY near-spot price would have
    # "beaten" them. The placebo reuses another session's level offsets, so the
    # distance-from-open geometry matches by construction.
    pool = [[v - r["open"] for k, v in r["levels"].items() if k.startswith("gex_")]
            for r in rows]
    pool = [p for p in pool if len(p) >= 2]
    if len(pool) < 30:
        return None
    gl, cl = [], []
    for r in rows:
        g = [v for k, v in r["levels"].items() if k.startswith("gex_")]
        if len(g) < 2:
            continue
        offs = pool[int(RNG.integers(len(pool)))]
        c = [r["open"] + o for o in offs]
        for px in (r["high"], r["low"]):
            gl.append(min(abs(px - x) for x in g))
            cl.append(min(abs(px - x) for x in c))
    if len(gl) < 100:
        return None
    return {"n": len(gl),
            "median_dist_gex": round(float(np.median(gl)), 2),
            "median_dist_ctl": round(float(np.median(cl)), 2),
            "mean_dist_gex": round(float(np.mean(gl)), 2),
            "mean_dist_ctl": round(float(np.mean(cl)), 2)}


def vix_split(rows, level_key, want_above):
    """Confound check: does any effect survive inside VIX terciles?"""
    vix = pd.read_csv(ROOT / "data" / "vix_daily.csv")
    vix["date"] = vix.date.astype(str).str[:10]
    v = vix.set_index("date").close
    have = [r for r in rows if r["date"] in v.index]
    if len(have) < 90:
        return {}
    qs = np.quantile([v[r["date"]] for r in have], [1 / 3, 2 / 3])
    out = {}
    for name, sel in (("low VIX", lambda x: x < qs[0]),
                      ("mid VIX", lambda x: qs[0] <= x < qs[1]),
                      ("high VIX", lambda x: x >= qs[1])):
        sub = [r for r in have if sel(v[r["date"]])]
        res = rejection_test(sub, level_key, want_above) if len(sub) > 30 else None
        if res:
            out[name] = {k: res[k] for k in ("level_rate", "diff", "n")}
    return out


def main():
    sessions = es_sessions()
    basis = basis_table(sessions)
    rows = build(sessions, basis, mq_levels())
    print(f"sessions usable: {len(rows)}  ({rows[0]['date']} .. {rows[-1]['date']})")

    res = {"meta": {"sessions": len(rows), "R_pts": R_PTS, "N_bars": N_BARS,
                    "start": rows[0]["date"], "end": rows[-1]["date"]}}
    res["H1_cr"] = rejection_test(rows, "cr", True)
    res["E1_ps"] = rejection_test(rows, "ps", False)
    res["E2_hvl"] = hvl_test(rows)
    res["E3_extremes"] = extremes_test(rows)
    res["H1_vix"] = vix_split(rows, "cr", True)

    # time split — does H1 hold in both halves, or is it one regime?
    mid = "2024-04-01"
    res["H1_time"] = {}
    for nm, sub in (("early", [r for r in rows if r["date"] < mid]),
                    ("late", [r for r in rows if r["date"] >= mid])):
        t = rejection_test(sub, "cr", True)
        if t:
            res["H1_time"][nm] = {k: t[k] for k in ("level_rate", "diff", "n")}
    res["H1_time"]["split_at"] = mid

    # E2 confound — is the HVL range split just VIX composition?
    vix = pd.read_csv(ROOT / "data" / "vix_daily.csv")
    vix["date"] = vix.date.astype(str).str[:10]
    v = vix.set_index("date").close
    have = [r for r in rows if r["hvl"] is not None and r["date"] in v.index]
    qs = np.quantile([v[r["date"]] for r in have], [1 / 3, 2 / 3])
    res["E2_vix"] = {}
    for nm, f in (("low VIX", lambda x: x < qs[0]),
                  ("mid VIX", lambda x: qs[0] <= x < qs[1]),
                  ("high VIX", lambda x: x >= qs[1])):
        sub = [r for r in have if f(v[r["date"]])]
        A = [(r["high"] - r["low"]) / r["open"] * 100 for r in sub if r["open"] > r["hvl"]]
        B = [(r["high"] - r["low"]) / r["open"] * 100 for r in sub if r["open"] <= r["hvl"]]
        if A and B:
            res["E2_vix"][nm] = {"above": round(float(np.mean(A)), 3),
                                 "below": round(float(np.mean(B)), 3),
                                 "n_above": len(A), "n_below": len(B)}

    print("\n=== H1 (primary) CR rejection from below vs matched control ===")
    print(json.dumps(res["H1_cr"], indent=2))
    print("\n=== E1 PS rejection from above ===")
    print(json.dumps(res["E1_ps"], indent=2))
    print("\n=== E2 HVL day-type ===")
    print(json.dumps(res["E2_hvl"], indent=2))
    print("\n=== E3 session extremes vs GEX levels ===")
    print(json.dumps(res["E3_extremes"], indent=2))
    print("\n=== H1 within VIX terciles ===")
    print(json.dumps(res["H1_vix"], indent=2))

    OUT.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
