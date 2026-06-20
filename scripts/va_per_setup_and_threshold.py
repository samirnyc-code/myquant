"""Per-setup VA-imbalance WFA + open-ended VA-threshold framing test.

PART A — run each individual CC setup (CC2..CC5) with the SAME locked session_va
filter ({below, above}, drop inside) and compare OOS to its unfiltered pinned-1.0R
baseline (pin10_ccX_sl). CC1 is excluded — only 129 signal-days, < the 252+63 needed
to form even one fold. The filter is LOCKED before the run; OOS judged once; nothing
is tuned to the result (PROJECT_CHARTER §4).

PART B — test the OPEN-ENDED threshold framing of the hypothesis. session_va's
continuous partner is |vaD_dist| = depth beyond the value-area edge (px−VAH above,
px−VAL below, 0 inside). The {below, above} filter is exactly the floor |vaD_dist|>0.
If "breakouts work in imbalance" is structural, OOS expectancy should rise ~monotonically
as the floor deepens. This is DESCRIPTIVE (describe-don't-fit): we report the trend on
LOCKED OOS trades; we do NOT sweep the floor and crown the best one (that is the
combo-hunting / no-feedback trap the rails forbid).

Usage:  python scripts/va_per_setup_and_threshold.py [--reuse]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive  # noqa: E402
import regime_filter as rf  # noqa: E402
import results_store as store  # noqa: E402
import wfa  # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT = _ROOT / "docs" / "living"

VA_SPEC = {"session_va": ["below", "above"]}
SETUPS = ["CC2", "CC3", "CC4", "CC5"]  # CC1 excluded (too few signal-days for a fold)
BASE_PARAMS = dict(entry_slip=0.5, exit_slip=0.5, stop_offset=1, tick_value=12.5,
                   contracts=1, contracts_t1=1, contracts_t2=1, commission=3.0,
                   ratchet_r=0.0, pb_round="nearest")
IS_DAYS, OOS_DAYS = 252, 63


def _log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def _fmt(v, f=".2f", fb="—"):
    try:
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            return fb
        return f"{v:{f}}"
    except Exception:
        return fb


def _load_bars():
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bbd = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    return bars, bbd


def _ticks_for(dates):
    tbd = {}
    for d in dates:
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            tbd[d] = t
    return tbd


# ── PART A — per-setup filtered WFA ─────────────────────────────────────────────
def run_per_setup(sig_all, bars, bbd):
    rows = []
    for cc in SETUPS:
        sig = sig_all[sig_all["SignalType"] == cc].copy()
        sig_f, info = rf.apply_regime_filter(sig, bars, VA_SPEC)
        n_days_f = sig_f["Date"].nunique()
        drop = (1 - info["n_out"] / info["n_in"]) * 100 if info["n_in"] else 0
        _log(f"{cc}: {info['n_in']}→{info['n_out']} signals (−{drop:.0f}%), {n_days_f} signal-days")
        if n_days_f < IS_DAYS + OOS_DAYS:
            _log(f"  {cc}: only {n_days_f} signal-days after filter (<{IS_DAYS + OOS_DAYS}) — "
                 "may yield 0 folds; running anyway.")
        run_id = f"pin10_{cc.lower()}_va_sl"
        tbd = _ticks_for(sorted(sig_f["Date"].unique()))
        store.delete_run(run_id)
        store.create_run(run_id, cc, "singleleg", BASE_PARAMS,
                         f"pinned 1.0R + LOCKED regime_filter: {rf.describe_spec(info['active'])}")
        wfa.run_wfa(run_id, cc, sig_f, tbd, bbd, BASE_PARAMS, "singleleg",
                    is_days=IS_DAYS, oos_days=OOS_DAYS, n_param_sets=1, pin_t1=1.0,
                    progress_cb=lambda i, t, m: None)
        b = wfa._compare_metrics(f"pin10_{cc.lower()}_sl", cc)
        v = wfa._compare_metrics(run_id, cc)
        rows.append((cc, b, v, drop))
        _log(f"  {cc}: baseline {b['n'] if b else 0} tr → filtered {v['n'] if v else 0} tr")
    return rows


# ── PART B — open-ended threshold monotonicity (descriptive, OOS only) ──────────
def threshold_test(sig_all, bars):
    """Tag the full signal set, attach |vaD_dist| to each setup's LOCKED baseline OOS
    trades, and report OOS expectancy as the open-ended depth floor rises."""
    tagged, _ = rf.tag_and_bucket(sig_all, bars)
    key = ["SignalType", "DateTime", "SignalPrice"]
    tag_small = tagged[key + ["vaD_dist", "vaD_loc"]].drop_duplicates(key)

    frames = []
    for cc in SETUPS:
        oos = store.load_all_oos_trades(f"pin10_{cc.lower()}_sl", cc)
        if oos.empty:
            continue
        f = oos[oos["Filled"] == True].copy()
        frames.append(f)
    if not frames:
        return None
    oos_all = pd.concat(frames, ignore_index=True)
    merged = oos_all.merge(tag_small, on=key, how="left")
    merged["depth"] = merged["vaD_dist"].abs()
    matched = merged["vaD_dist"].notna().mean() * 100

    # Discrete location buckets (inside vs the two open-ended tails).
    out = {"matched_pct": matched, "loc": {}, "floor": []}
    for loc in ["inside", "below", "above"]:
        g = merged[merged["vaD_loc"] == loc]
        if len(g):
            out["loc"][loc] = dict(n=len(g), exp=float(g["NetPnL"].mean()),
                                   win=float((g["NetPnL"] > 0).mean() * 100),
                                   net=float(g["NetPnL"].sum()))

    # Open-ended floor sweep — PRE-SPECIFIED ES-point floors (NOT optimised; we read the
    # trend, we do not select a winner). depth is in ES points.
    floors = [0.0, 2.0, 4.0, 6.0, 8.0, 12.0]
    outside = merged[merged["vaD_loc"] != "inside"]
    for k in floors:
        g = outside[outside["depth"] >= k]
        if len(g):
            out["floor"].append(dict(k=k, n=len(g), exp=float(g["NetPnL"].mean()),
                                     win=float((g["NetPnL"] > 0).mean() * 100),
                                     net=float(g["NetPnL"].sum())))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reuse", action="store_true", help="skip per-setup runs; load existing")
    args = ap.parse_args()
    store.init_db()

    _log("Loading signals + bars…")
    sig_all = pd.read_parquet(_SIGNALS)
    bars, bbd = _load_bars()

    R = ["# Per-setup VA-imbalance WFA + open-ended threshold test",
         f"*Generated {datetime.now():%Y-%m-%d %H:%M} · headless · same engine · "
         "LOCKED filter, no tuning to result (PROJECT_CHARTER §4).*\n"]

    # ── PART A ─────────────────────────────────────────────────────────────────
    if not args.reuse:
        rows = run_per_setup(sig_all, bars, bbd)
    else:
        rows = []
        for cc in SETUPS:
            b = wfa._compare_metrics(f"pin10_{cc.lower()}_sl", cc)
            v = wfa._compare_metrics(f"pin10_{cc.lower()}_va_sl", cc)
            sig = sig_all[sig_all["SignalType"] == cc]
            sig_f, info = rf.apply_regime_filter(sig, bars, VA_SPEC)
            drop = (1 - info["n_out"] / info["n_in"]) * 100
            rows.append((cc, b, v, drop))

    R.append("## Part A — individual CC setups: baseline vs VA-filtered (OOS)")
    R.append("*CC1 excluded: 129 signal-days < the 315 (252 IS + 63 OOS) needed for one fold.*\n")
    R.append("| Setup | Folds B→V | OOS trades B→V (−%) | Expectancy $ B→V | Net $ B→V | "
             "Best-yr% B→V | MAR B→V | Mean PROM B→V | Med WFE% B→V |")
    R.append("|---|---|---|---|---|---|---|---|---|")
    verdicts = []
    for cc, b, v, drop in rows:
        if not b or not v or b.get("n", 0) == 0:
            R.append(f"| {cc} | — | baseline empty | — | — | — | — | — | — |")
            continue
        if v.get("n", 0) == 0 or v.get("n_folds", 0) == 0:
            R.append(f"| {cc} | {b['n_folds']}→0 | {b['n']}→0 | filter left too few signal-days "
                     "for a fold | — | — | — | — |")
            verdicts.append((cc, "no folds after filter"))
            continue
        dn = (1 - v["n"] / b["n"]) * 100
        better_exp = v["exp"] > b["exp"]
        better_prom = v["prom"] >= b["prom"]
        better_share = (np.isnan(v["best_share"]) or v["best_share"] <= b["best_share"] + 5)
        not_attrition = v["net"] >= b["net"]
        score = sum([better_exp, better_prom, better_share])
        verdicts.append((cc, f"exp {'↑' if better_exp else '↓'}, PROM {'↑' if better_prom else '↓'}, "
                         f"best-yr {'↓(better)' if better_share else '↑(worse)'}, "
                         f"net {'↑' if not_attrition else '↓'} → {score}/3 durability dims up"))
        R.append(
            f"| {cc} | {b['n_folds']}→{v['n_folds']} | {b['n']}→{v['n']} (−{dn:.0f}%) | "
            f"${b['exp']:,.0f}→${v['exp']:,.0f} | ${b['net']:,.0f}→${v['net']:,.0f} | "
            f"{_fmt(b['best_share'],'.0f')}→{_fmt(v['best_share'],'.0f')}% | "
            f"{_fmt(b['mar'])}→{_fmt(v['mar'])} | {_fmt(b['prom'])}→{_fmt(v['prom'])} | "
            f"{_fmt(b['wfe'],'.0f')}→{_fmt(v['wfe'],'.0f')}% |")
    R.append("")
    for cc, vd in verdicts:
        R.append(f"- **{cc}:** {vd}")
    R.append("")

    # ── PART B ─────────────────────────────────────────────────────────────────
    _log("Part B — open-ended threshold monotonicity…")
    tt = threshold_test(sig_all, bars)
    R.append("## Part B — open-ended VA-threshold framing (descriptive, OOS only)")
    if tt is None:
        R.append("No OOS trades available.\n")
    else:
        R.append(f"*Pooled LOCKED baseline OOS trades across {', '.join(SETUPS)} "
                 f"({tt['matched_pct']:.0f}% matched to a VA tag). depth = |vaD_dist| in ES points.*\n")
        R.append("**Discrete location (the 3-bucket framing):**\n")
        R.append("| Location | OOS trades | Expectancy $ | Win% | Net $ |")
        R.append("|---|---|---|---|---|")
        for loc in ["inside", "below", "above"]:
            d = tt["loc"].get(loc)
            if d:
                R.append(f"| {loc} | {d['n']} | ${d['exp']:,.1f} | {d['win']:.1f}% | ${d['net']:,.0f} |")
        R.append("\n**Open-ended depth floor `|vaD_dist| ≥ k` (outside-VA trades only):**\n")
        R.append("| Floor k (pts) | OOS trades | Expectancy $ | Win% | Net $ |")
        R.append("|---|---|---|---|---|")
        for d in tt["floor"]:
            R.append(f"| ≥ {d['k']:.0f} | {d['n']} | ${d['exp']:,.1f} | {d['win']:.1f}% | ${d['net']:,.0f} |")
        # Monotonicity read
        exps = [d["exp"] for d in tt["floor"]]
        mono = all(exps[i] <= exps[i + 1] for i in range(len(exps) - 1))
        rising = exps[-1] > exps[0]
        R.append(f"\n- Expectancy as the floor deepens: "
                 f"{' → '.join(f'${e:,.0f}' for e in exps)}.")
        R.append(f"- **{'Monotonic rise' if mono else ('Rises but not strictly monotone' if rising else 'No clear rise')}** "
                 "with depth. " + ("This SUPPORTS the open-ended imbalance hypothesis — deeper "
                 "displacement from value carries a stronger breakout edge."
                 if rising else "This does NOT support a deeper-is-better threshold — the edge "
                 "is in being outside the VA at all, not in how far.") +
                 " *(Descriptive: we report the trend; we do NOT select a k against OOS — that "
                 "would be the no-feedback violation.)*")
        inside = tt["loc"].get("inside")
        out0 = tt["floor"][0] if tt["floor"] else None
        if inside and out0:
            R.append(f"- Inside-VA expectancy **${inside['exp']:,.1f}** vs outside-VA "
                     f"**${out0['exp']:,.1f}** — the {{below, above}} cut "
                     f"{'is justified' if out0['exp'] > inside['exp'] else 'is NOT justified'} "
                     "(it drops the weaker-expectancy bucket).")

    out = _OUT / f"va_per_setup_threshold_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(R), encoding="utf-8")
    print("\n" + "\n".join(R))
    print("\n" + "=" * 70 + f"\nReport → {out}")


if __name__ == "__main__":
    main()
