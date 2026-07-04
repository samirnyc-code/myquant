"""MenthorQ S/R follow-up (S54) — user challenge: 'the MAIN levels act as S/R'.

Pre-registered before outcomes:
  T-A containment: P(day high <= CallRes) / P(day low >= PutSup) vs a
      distance-matched empirical benchmark (distance from RTH open in
      expected-move units, CDF built from the 82 days' realized excursions).
      Registered direction: real levels contain MORE than benchmark.
  T-B first-touch, EOD horizon: first touch of CallRes from below / PutSup
      from above / HVL either side. Outcomes: close-beyond rate and max
      rejection depth (pts) by EOD, vs pseudo-levels at the SAME distance
      from open (z shuffled across days, seed 42, 5x).
  T-C decomposition of the original 6-bar bounce test per individual level
      type with directional approach (diagnostic for the pooled null).
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

from menthorq_edge_study import (load_mq, CONTRACT_FILE, WIN_START, WIN_END,  # noqa: E402
                                 touches_for_levels, BARS_PQ)

RNG = np.random.default_rng(42)
OUT = ROOT / "docs" / "living" / "menthorq_sr_followup_20260704.md"
L = []
def emit(s=""):
    print(s, flush=True); L.append(s)


def offsets_for(mq, bars):
    day = bars["DateTime"].dt.normalize()
    cache, out = {}, {}
    for _, r in mq.iterrows():
        d = r["date"]; code = CONTRACT_FILE.get(str(r["contract"]))
        if code is None: continue
        if code not in cache:
            p = ROOT / "data" / "bars" / f"{code}.parquet"
            cache[code] = pd.read_parquet(p) if p.exists() else None
        cb = cache[code]
        if cb is None: continue
        cd = cb[cb["DateTime"].dt.normalize() == d]
        bd = bars[day == d]
        if cd.empty or bd.empty: continue
        m = bd.merge(cd[["DateTime", "Close"]].rename(columns={"Close": "ct"}), on="DateTime")
        if m.empty: continue
        out[d] = float((m["Close"] - m["ct"]).median())
    return out


def main():
    emit(f"# MenthorQ main-level S/R follow-up — {datetime.now():%Y-%m-%d %H:%M}\n")
    bars = pd.read_parquet(BARS_PQ)
    bars["DateTime"] = pd.to_datetime(bars["DateTime"])
    day = bars["DateTime"].dt.normalize()
    mq = load_mq()
    mq["date"] = mq["date"].dt.normalize()
    mq = mq[(mq["date"] >= WIN_START) & (mq["date"] <= WIN_END)].reset_index(drop=True)
    off = offsets_for(mq, bars)

    # per-day frame: open/high/low/close + levels in continuous space + EM pts
    rows = []
    prior_close = None
    for _, r in mq.iterrows():
        d = r["date"]
        if d not in off: continue
        db = bars[day == d]
        if len(db) < 20: continue
        o = float(db["Open"].iloc[0]); h = float(db["High"].max())
        lo = float(db["Low"].min()); c = float(db["Close"].iloc[-1])
        em = r["exp_move_1d_pct"] / 100.0 * (prior_close if prior_close else c)
        rows.append(dict(date=d, o=o, h=h, l=lo, c=c, em=em,
                         cr=r["call_resistance"] + off[d],
                         cr0=r["call_resistance_0dte"] + off[d],
                         ps=r["put_support"] + off[d],
                         ps0=r["put_support_0dte"] + off[d],
                         hvl=r["high_vol_level"] + off[d],
                         gw=(r["gamma_wall_0dte"] + off[d]) if pd.notna(r["gamma_wall_0dte"]) else np.nan,
                         mx=r["1d_max"] + off[d], mn=r["1d_min"] + off[d]))
        prior_close = c
    D = pd.DataFrame(rows)
    emit(f"{len(D)} days.\n")

    # ── T-A containment vs distance-matched benchmark ────────────────────────
    emit("## T-A — day-range containment vs distance-matched benchmark\n")
    emit("Benchmark = empirical CDF of the day's (high−open)/EM (resp. (open−low)/EM)")
    emit("over all days, evaluated at each level's z = (level−open)/EM. 'Excess' >0 means")
    emit("the level contains the extreme MORE often than any price that far away would.\n")
    up_exc = np.sort(((D["h"] - D["o"]) / D["em"]).to_numpy())
    dn_exc = np.sort(((D["o"] - D["l"]) / D["em"]).to_numpy())
    emit("| level | days usable | contained | benchmark | excess | boot 95% CI |")
    emit("|---|---|---|---|---|---|")
    for name, col, side in [("Call Resistance", "cr", "up"), ("Call Res 0DTE", "cr0", "up"),
                            ("1d_max (IV band, ref)", "mx", "up"),
                            ("Put Support", "ps", "dn"), ("Put Sup 0DTE", "ps0", "dn"),
                            ("1d_min (IV band, ref)", "mn", "dn")]:
        if side == "up":
            m = D[D[col] > D["o"]]
            cont = (m["h"] <= m[col]).to_numpy()
            z = ((m[col] - m["o"]) / m["em"]).to_numpy()
            bench = np.searchsorted(up_exc, z, side="left") / len(up_exc)
        else:
            m = D[D[col] < D["o"]]
            cont = (m["l"] >= m[col]).to_numpy()
            z = ((m["o"] - m[col]) / m["em"]).to_numpy()
            bench = np.searchsorted(dn_exc, z, side="left") / len(dn_exc)
        if len(m) < 10:
            emit(f"| {name} | {len(m)} | — | — | — | — |"); continue
        exc = cont.mean() - bench.mean()
        boots = []
        for _ in range(2000):
            i = RNG.integers(0, len(cont), len(cont))
            boots.append(cont[i].mean() - bench[i].mean())
        lo_, hi_ = np.percentile(boots, [2.5, 97.5])
        sig = " **⇐**" if lo_ > 0 else ""
        emit(f"| {name} | {len(m)} | {cont.mean()*100:.0f}% | {bench.mean()*100:.0f}% "
             f"| {exc*100:+.1f}pp | [{lo_*100:+.1f}, {hi_*100:+.1f}]{sig} |")
    emit("")

    # ── T-B first directional touch, EOD horizon ─────────────────────────────
    emit("## T-B — first directional touch → EOD outcome vs matched pseudo-levels\n")
    emit("Pseudo-levels: same z-distance distribution (shuffled across days, 5x, seed 42).\n")

    def first_touch_stats(frame, lev_col=None, z_arr=None, side="up"):
        """Returns per-day dicts: touched, close_beyond, reject_depth."""
        out = []
        for k, (_, r) in enumerate(frame.iterrows()):
            db = bars[day == r["date"]].reset_index(drop=True)
            if z_arr is not None:
                lev = r["o"] + z_arr[k] * r["em"] * (1 if side == "up" else -1)
            else:
                lev = r[lev_col]
            if pd.isna(lev): continue
            if side == "up" and lev <= r["o"]: continue
            if side == "dn" and lev >= r["o"]: continue
            hi = db["High"].to_numpy(); lo_a = db["Low"].to_numpy(); cl = db["Close"].to_numpy()
            hit = np.where((hi >= lev) & (lo_a <= lev))[0]
            # approach must be from the registered side at first hit
            if len(hit) == 0:
                out.append(dict(touched=False)); continue
            i = hit[0]
            after_lo = lo_a[i:].min(); after_hi = hi[i:].max()
            if side == "up":
                depth = lev - after_lo  # rejection = how far it falls back
                beyond = cl[-1] > lev
            else:
                depth = after_hi - lev
                beyond = cl[-1] < lev
            out.append(dict(touched=True, depth=depth, beyond=beyond))
        return pd.DataFrame(out)

    emit("| level | touched days | close-beyond% | median reject depth | ctrl beyond% | ctrl depth | depth diff CI |")
    emit("|---|---|---|---|---|---|---|")
    for name, col, side in [("Call Resistance", "cr", "up"), ("Gamma Wall 0DTE", "gw", "up"),
                            ("HVL from below", "hvl", "up"),
                            ("Put Support", "ps", "dn"), ("HVL from above", "hvl", "dn")]:
        real = first_touch_stats(D, lev_col=col, side=side)
        rt = real[real["touched"] == True]  # noqa: E712
        # controls: z of this level type shuffled across days, 5 draws
        if side == "up":
            z_real = ((D[col] - D["o"]) / D["em"]).to_numpy()
        else:
            z_real = ((D["o"] - D[col]) / D["em"]).to_numpy()
        z_real = z_real[np.isfinite(z_real) & (z_real > 0)]
        ct_frames = []
        for _ in range(5):
            z_s = RNG.permutation(z_real)
            n = min(len(z_s), len(D))
            ct = first_touch_stats(D.iloc[:n], z_arr=z_s[:n], side=side)
            ct_frames.append(ct)
        ctrl = pd.concat(ct_frames, ignore_index=True)
        ct = ctrl[ctrl["touched"] == True]  # noqa: E712
        if len(rt) < 8 or len(ct) < 8:
            emit(f"| {name} | {len(rt)} | insufficient | | | | |"); continue
        boots = []
        rd = rt["depth"].to_numpy(); cd_ = ct["depth"].to_numpy()
        for _ in range(2000):
            boots.append(np.median(RNG.choice(rd, len(rd))) - np.median(RNG.choice(cd_, len(cd_))))
        lo_, hi_ = np.percentile(boots, [2.5, 97.5])
        sig = " **⇐**" if lo_ > 0 else ""
        emit(f"| {name} | {len(rt)} | {rt['beyond'].mean()*100:.0f}% | {rt['depth'].median():.1f} pts "
             f"| {ct['beyond'].mean()*100:.0f}% | {np.median(cd_):.1f} pts "
             f"| [{lo_:+.1f}, {hi_:+.1f}]{sig} |")
    emit("")

    # ── T-C per-type decomposition of the original 6-bar bounce test ─────────
    emit("## T-C — original 6-bar bounce test, per level type (diagnostic)\n")
    emit("| level | touches | bounce% | break% | mean drift (pts, along approach) |")
    emit("|---|---|---|---|---|")
    for name, col in [("Call Resistance", "cr"), ("Call Res 0DTE", "cr0"),
                      ("Put Support", "ps"), ("Put Sup 0DTE", "ps0"),
                      ("HVL", "hvl"), ("Gamma Wall 0DTE", "gw"),
                      ("1d_max", "mx"), ("1d_min", "mn")]:
        tt = []
        for _, r in D.iterrows():
            if pd.isna(r[col]): continue
            db = bars[day == r["date"]].reset_index(drop=True)
            tt += touches_for_levels(db, [r[col]])
        t = pd.DataFrame(tt)
        if t.empty:
            emit(f"| {name} | 0 | — | — | — |"); continue
        emit(f"| {name} | {len(t)} | {t['bounce'].mean()*100:.1f}% | {t['breakthru'].mean()*100:.1f}% "
             f"| {t['drift'].mean():+.2f} |")
    emit("")
    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"written {OUT}")


if __name__ == "__main__":
    main()
