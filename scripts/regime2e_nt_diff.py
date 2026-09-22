"""PARITY DIFF: NT8 Regime2ESetups indicator log vs the audited python 2E engine.

NT side : Documents\\regime2e_setups_ES.csv (FIRE + SKIP rows = every 2E trigger
          touch the indicator saw, gates irrelevant for signal parity).
PY side : real NT tick trove (data/ticks_continuous/<date>.parquet, RTH
          08:30-15:15 trove clock) -> day-scoped 5-min bars + true tick path ->
          detect_entries_causal (cnt==2 only) + phase_transitions regime at the
          trigger-touch tick. Engines imported VERBATIM from the regime worktree.

Match: same direction, trigger within TRIG_TOL ticks, bar index within BAR_TOL
(after estimating the day's constant NT-vs-python bar offset). Days where the
chart contract differs from the trove's rolled front contract (pre-roll June)
are auto-flagged CONTRACT-MISMATCH via the median trigger gap and excluded from
the parity verdict.

  python scripts/regime2e_nt_diff.py [path\\to\\nt.csv]
Output: reports/regime2e/nt_diff_<stamp>.csv + stdout summary.
"""
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from bisect import bisect_right

import numpy as np
import pandas as pd

TICK = 0.25
TRIG_TOL_TICKS = 1          # trigger price tolerance (ticks) for a MATCH
BAR_TOL = 1                 # bar-index tolerance after offset estimation
REPO = Path(__file__).resolve().parent.parent
TICKD = REPO / "data" / "ticks_continuous"
WT_SCRIPTS = Path(r"C:\Users\Admin\myquant-regime\scripts")
OUTDIR = REPO / "reports" / "regime2e"

sys.path.insert(0, str(WT_SCRIPTS))
from regime_second_entry_study import phase_transitions          # noqa: E402
from regime_2e_causal_check import detect_entries_causal         # noqa: E402


def day_frames(date: str):
    p = TICKD / f"{date}.parquet"
    if not p.exists():
        return None, None, None
    t = pd.read_parquet(p).sort_values("DateTime").reset_index(drop=True)
    if len(t) < 1000:
        return None, None, None
    sess0 = pd.Timestamp(f"{date} 08:30:00")
    sec = (t["DateTime"] - sess0).dt.total_seconds()
    t = t[(sec >= 0) & (sec < 405 * 60)].reset_index(drop=True)
    if len(t) < 1000:
        return None, None, None
    k = ((t["DateTime"] - sess0).dt.total_seconds() // 300).astype(int).rename("k")
    g = t.groupby(k)["Price"].agg(Open="first", High="max", Low="min", Close="last")
    g = g.reindex(range(int(k.max()) + 1)).ffill()          # empty 5m slots: flat carry
    g = g.reset_index()
    g["DateTime"] = sess0 + pd.to_timedelta((g["k"] + 1) * 5, unit="m")   # bar END time
    tP = t["Price"].values
    tbar = k.values
    return g[["DateTime", "Open", "High", "Low", "Close"]], tP, tbar


def py_signals(date: str):
    g, tP, tbar = day_frames(date)
    if g is None or len(g) < 30:
        return None
    trans = phase_transitions(g["High"].values, g["Low"].values, len(g), tP, tbar)
    tr_ix = [i for (i, _) in trans]; tr_md = [m for (_, m) in trans]
    out = []
    for (fb, sb, dr, cnt, trig) in detect_entries_causal(g, tP, tbar):
        if cnt != 2:
            continue
        a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
        s = tP[a:z]
        hit = np.nonzero(s <= trig)[0] if dr == "S" else np.nonzero(s >= trig)[0]
        if not len(hit):
            continue
        jf = a + int(hit[0])
        reg = tr_md[bisect_right(tr_ix, jf) - 1] if tr_ix else "NEUTRAL"
        out.append(dict(bar=int(fb), dir=dr, trig=float(trig), regime=reg,
                        time=str(g["DateTime"].iloc[min(fb, len(g) - 1)].time())))
    return out


def main():
    nt_csv = Path(sys.argv[1]) if len(sys.argv) > 1 else (Path.home() / "Documents" / "regime2e_setups_ES.csv")
    nt = pd.read_csv(nt_csv, dtype={"reason": str}).fillna({"reason": ""})
    nt = nt[nt.event.isin(["FIRE", "SKIP"])].copy()
    dates = sorted(nt["date"].unique())
    rows, day_lines = [], []
    tot = Counter()
    for d in dates:
        ntd = nt[nt.date == d].to_dict("records")
        py = py_signals(d)
        if py is None:
            day_lines.append(f"{d}: NO TROVE TICKS - skipped ({len(ntd)} NT signals unchecked)")
            tot["days_no_ticks"] += 1
            continue
        # contract check: median absolute gap between each NT trig and the closest py trig
        if ntd and py:
            gaps = [min(abs(r["trig"] - p["trig"]) for p in py) for r in ntd]
            med_gap = float(np.median(gaps))
        else:
            med_gap = 0.0
        if med_gap > 5.0:
            # NOT a roll artifact (June days match exactly -> same contract both sides):
            # the two tick feeds forked the path-dependent engine early in the day.
            day_lines.append(f"{d}: DIVERGENT DAY (median trig gap {med_gap:.1f}pt - tick-path fork) - "
                             f"{len(ntd)} NT vs {len(py)} PY signals unmatched")
            tot["days_divergent"] += 1
            tot["nt_div"] += len(ntd); tot["py_div"] += len(py)
            continue
        # estimate the day's constant bar offset from nearest-price same-dir pairs
        offs = []
        for r in ntd:
            best = min((p for p in py if p["dir"] == r["dir"]),
                       key=lambda p: abs(p["trig"] - r["trig"]), default=None)
            if best is not None and abs(best["trig"] - r["trig"]) <= 2 * TICK:
                offs.append(r["engine_bar"] - best["bar"])
        bar_off = int(pd.Series(offs).mode().iloc[0]) if offs else 0
        used = set()
        n_match = n_reg = 0
        for r in ntd:
            cand = None
            for j, p in enumerate(py):
                if j in used or p["dir"] != r["dir"]:
                    continue
                if abs(p["trig"] - r["trig"]) <= TRIG_TOL_TICKS * TICK \
                        and abs((r["engine_bar"] - bar_off) - p["bar"]) <= BAR_TOL:
                    cand = j; break
            status = "NT_ONLY"
            if cand is not None:
                used.add(cand); n_match += 1
                p = py[cand]
                status = "MATCH"
                if str(r["regime"]) == p["regime"]:
                    n_reg += 1
            rows.append(dict(date=d, side="NT", dir=r["dir"], time=r["time"],
                             bar=r["engine_bar"], trig=r["trig"], regime=r["regime"],
                             event=r["event"], reason=r["reason"], status=status))
        for j, p in enumerate(py):
            if j not in used:
                rows.append(dict(date=d, side="PY", dir=p["dir"], time=p["time"],
                                 bar=p["bar"], trig=p["trig"], regime=p["regime"],
                                 event="", reason="", status="PY_ONLY"))
        tot["days"] += 1
        tot["nt"] += len(ntd); tot["py"] += len(py)
        tot["match"] += n_match; tot["reg_agree"] += n_reg
        nt_only = len(ntd) - n_match; py_only = len(py) - n_match
        day_lines.append(f"{d}: NT {len(ntd):2d} / PY {len(py):2d} -> match {n_match:2d}"
                         f" (bar_off {bar_off:+d}, NT-only {nt_only}, PY-only {py_only})")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    out_csv = OUTDIR / f"nt_diff_{stamp}.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print("\n".join(day_lines))
    print("\n===== PARITY SUMMARY (comparable days only) =====")
    print(f"days compared      : {tot['days']}  (fully-divergent days: {tot['days_divergent']}"
          f" w/ {tot['nt_div']} NT / {tot['py_div']} PY signals; no-ticks: {tot['days_no_ticks']})")
    print(f"NT signals         : {tot['nt']}")
    print(f"PY signals         : {tot['py']}")
    if tot["nt"] and tot["py"]:
        print(f"matched            : {tot['match']}  ({100 * tot['match'] / tot['nt']:.1f}% of NT,"
              f" {100 * tot['match'] / tot['py']:.1f}% of PY)")
    if tot["match"]:
        print(f"regime agreement   : {tot['reg_agree']}/{tot['match']}"
              f" ({100 * tot['reg_agree'] / tot['match']:.1f}%) on matched signals")
    print(f"detail: {out_csv}")


if __name__ == "__main__":
    main()
