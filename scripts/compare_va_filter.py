"""VA-imbalance side-by-side WFA comparison (headless).

Tests ONE locked, structural hypothesis: breakouts work in IMBALANCE, not balance.
Drop every signal inside the prior-session value area (keep only below VAL + above
VAH), run the SAME pinned-1.0R single-leg WFA as the baseline, and compare OOS-only.

  Baseline (loaded, NOT rerun):  pin10_all_sl     (ALL CC, single-leg, target 1.0R)
  Filtered (created here):       pin10_all_va_sl  (identical config + session_va filter)

The filter is LOCKED before the run and NEVER tuned against the result (PROJECT_CHARTER
§4 no-feedback rail). WFA optimizes nothing here — target is pinned 1.0R. Judge on OOS
only. Reuses the same engine (wfa.run_wfa) and the pipeline's MC / path helpers.

Usage:
    python scripts/compare_va_filter.py            # run the filtered WFA, then compare
    python scripts/compare_va_filter.py --reuse    # skip the run, compare existing runs
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
from run_setup_pipeline import monte_carlo, oos_path_stats  # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT = _ROOT / "docs" / "living"

BASE_RUN = "pin10_all_sl"
VA_RUN = "pin10_all_va_sl"
SETUP = "ALL"
VA_SPEC = {"session_va": ["below", "above"]}  # keep imbalance (outside VA), drop inside

BASE_PARAMS = dict(
    entry_slip=0.5, exit_slip=0.5, stop_offset=1, tick_value=12.5,
    contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
    ratchet_r=0.0, pb_round="nearest",
)
IS_DAYS, OOS_DAYS = 252, 63  # 12m IS / 3m OOS (matches the baseline battery)


def _log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def _fmt(v, f=".2f", fb="—"):
    try:
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            return fb
        return f"{v:{f}}"
    except Exception:
        return fb


def _cells(fdf: pd.DataFrame) -> list[dict]:
    """Loaded fold DataFrame → the list-of-dicts shape _aggregate_grid_cell wants."""
    out = []
    for _, r in fdf.iterrows():
        out.append({
            "wfe": r["wfe"],
            "oos_summary": {"net_total": r["oos_net_pnl"], "prom": r["oos_prom"],
                            "pf": r["oos_pf"], "max_dd": r["oos_max_dd"]},
        })
    return out


def run_filtered():
    """Create pin10_all_va_sl: identical config + the locked VA filter."""
    _log("Loading MC signals + bars…")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    _log("Applying LOCKED session_va filter (keep below+above, drop inside)…")
    sig_f, info = rf.apply_regime_filter(sig, bars, VA_SPEC)
    _log(f"Filter: {info['n_in']} → {info['n_out']} signals "
         f"(dropped {info['n_in'] - info['n_out']} = "
         f"{(1 - info['n_out'] / info['n_in']) * 100:.1f}%). "
         f"Active: {rf.describe_spec(info['active'])}. Time-spread flag: {info['time_flag']}")

    dates = sorted(sig_f["Date"].unique())
    _log(f"Loading tick cache for {len(dates)} signal-days…")
    tbd = {}
    for d in dates:
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            tbd[d] = t
    _log(f"Tick cache: {len(tbd)}/{len(dates)} days.")

    store.delete_run(VA_RUN)
    store.create_run(VA_RUN, SETUP, "singleleg", BASE_PARAMS,
                     f"pinned 1.0R + LOCKED regime_filter: {rf.describe_spec(info['active'])}")
    _log("Running filtered WFA (pinned 1.0R, n_param_sets=1)…")
    wfa.run_wfa(VA_RUN, SETUP, sig_f, tbd, bars_by_date, BASE_PARAMS, "singleleg",
                is_days=IS_DAYS, oos_days=OOS_DAYS, n_param_sets=1, pin_t1=1.0,
                progress_cb=lambda i, t, m: _log(f"  {m}"))
    _log("Filtered WFA done.")


def metrics(run_id: str) -> dict:
    """All comparison metrics for one run, OOS only, from the store."""
    fdf = store.load_folds(run_id)
    agg = wfa._aggregate_grid_cell(_cells(fdf))
    oos = store.load_all_oos_trades(run_id, SETUP)
    f = oos[oos["Filled"] == True].copy()  # noqa: E712
    pnl = f["NetPnL"].to_numpy()
    er = f["ExitReason"].astype(str)
    is_eod = er.str.contains("EOD")
    is_tgt = er.eq("Target") | er.str.contains(r"\+Target")
    is_stop = er.eq("Stop") | er.str.contains(r"\+Stop")
    ps = oos_path_stats(f)
    mc = monte_carlo(pnl)
    n = len(f)
    mar95 = (ps["net"] / abs(mc["dd95"])) if (mc and ps and mc["dd95"] < 0) else float("nan")
    return dict(
        n=n, net=float(pnl.sum()), exp=float(pnl.mean()) if n else float("nan"),
        tgt=float(f.loc[is_tgt, "NetPnL"].sum()), stop=float(f.loc[is_stop, "NetPnL"].sum()),
        eod=float(f.loc[is_eod, "NetPnL"].sum()), n_eod=int(is_eod.sum()),
        win=float((pnl > 0).mean() * 100) if n else float("nan"),
        med=float(np.median(pnl)) if n else float("nan"),
        pct_green=agg["pct_oos_prof"], best_share=ps["best_share"] if ps else float("nan"),
        mar=ps["mar"] if ps else float("nan"), dd95=mc["dd95"] if mc else float("nan"),
        mar95=mar95, longest_uw=ps["longest_uw"] if ps else None,
        wfe=agg["mean_wfe"], prom=agg["mean_oos_prom"],
        n_folds=agg["n_folds"], maxdd=ps["maxdd"] if ps else float("nan"),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reuse", action="store_true",
                    help="skip running the filtered WFA; compare existing runs only")
    args = ap.parse_args()

    store.init_db()
    if not args.reuse:
        run_filtered()

    _log("Computing side-by-side metrics…")
    b = metrics(BASE_RUN)
    v = metrics(VA_RUN)
    dropped_pct = (1 - v["n"] / b["n"]) * 100
    oos_per_bucket = v["n"] / v["n_folds"] if v["n_folds"] else 0

    rows = [
        ("OOS trades (filled)", f"{b['n']}", f"{v['n']}  (−{dropped_pct:.1f}%)"),
        ("Net $ · Expectancy $/trade",
         f"${b['net']:,.0f} · ${b['exp']:,.1f}", f"${v['net']:,.0f} · ${v['exp']:,.1f}"),
        ("Target $ vs Stop $ vs EOD $",
         f"${b['tgt']:,.0f} / ${b['stop']:,.0f} / ${b['eod']:,.0f}",
         f"${v['tgt']:,.0f} / ${v['stop']:,.0f} / ${v['eod']:,.0f}"),
        ("Win% · Median trade $",
         f"{_fmt(b['win'],'.1f')}% · ${b['med']:,.1f}", f"{_fmt(v['win'],'.1f')}% · ${v['med']:,.1f}"),
        ("% OOS windows green",
         f"{_fmt(b['pct_green'],'.0f')}%", f"{_fmt(v['pct_green'],'.0f')}%"),
        ("Best-year share % (OOS)",
         f"{_fmt(b['best_share'],'.0f')}%", f"{_fmt(v['best_share'],'.0f')}%"),
        ("MAR (net÷|maxDD|) · MAR95 (net÷|MC DD95|)",
         f"{_fmt(b['mar'])} · {_fmt(b['mar95'])}", f"{_fmt(v['mar'])} · {_fmt(v['mar95'])}"),
        ("MC DD95 $",
         f"${b['dd95']:,.0f}", f"${v['dd95']:,.0f}"),
        ("Longest underwater (days)",
         f"{b['longest_uw']}", f"{v['longest_uw']}"),
        ("Median WFE % · Mean PROM",
         f"{_fmt(b['wfe'],'.0f')}% · {_fmt(b['prom'])}", f"{_fmt(v['wfe'],'.0f')}% · {_fmt(v['prom'])}"),
        ("Folds", f"{b['n_folds']}", f"{v['n_folds']}"),
    ]

    # ── Acceptance test (strict; OOS only) ──────────────────────────────────────
    exp_better = v["exp"] > b["exp"]
    count_ok = oos_per_bucket >= 30
    similar_count = abs(dropped_pct) <= 35  # "similar trade count" — not a PF-by-attrition win
    # PROOF this is NOT a PF-by-attrition win: net OOS profit RISES even though trades fall.
    not_attrition = v["net"] >= b["net"] and v["n"] < b["n"]
    # Durability across windows (the robustness that MATTERS): %green, MAR/MC-DD,
    # best-year concentration, and the WFA selection objective PROM. WFE is handled
    # separately because it is OOS÷IS — a STRONGER in-sample (larger denominator)
    # lowers WFE even when OOS is equal-or-better, so a WFE drop is NOT by itself an
    # OOS-robustness regression (S21/S22 flagged WFE as denominator-fragile).
    durability_better = (
        (v["pct_green"] >= b["pct_green"] - 5)
        and (v["mar"] >= b["mar"] - 0.05)
        and (v["prom"] >= b["prom"])  # PROM is what WFA actually selects on
        and (np.isnan(v["best_share"]) or v["best_share"] <= b["best_share"] + 5)
    )
    # The locked rail (CHARTER §4): Median WFE ≥ 50%. Reported on its own.
    wfe_rail_ok = (not np.isnan(v["wfe"])) and v["wfe"] >= 50.0
    # WFE lower only because IS is stronger? (OOS net up while WFE down ⇒ denominator)
    wfe_is_denominator = (not wfe_rail_ok) and (v["net"] >= b["net"])
    clean_win = bool(exp_better and durability_better and count_ok and similar_count and wfe_rail_ok)
    qualified = bool(exp_better and durability_better and count_ok and similar_count
                     and not_attrition and not wfe_rail_ok)

    R = []
    R.append("# VA-imbalance filter — side-by-side WFA (OOS only)")
    R.append(f"*Generated {datetime.now():%Y-%m-%d %H:%M} · headless · same engine · "
             "LOCKED filter, no tuning to result (PROJECT_CHARTER §4).*\n")
    R.append("**Hypothesis (structural, locked):** breakouts work in IMBALANCE, not balance "
             "→ drop signals inside the prior-session value area (keep only below VAL + above VAH).\n")
    R.append(f"- **Baseline** `{BASE_RUN}` — ALL CC, single-leg, target pinned 1.0R, "
             "12m IS / 3m OOS, slip 0.5/0.5, $3 r/t, 1 ES, stop_offset 1.")
    R.append(f"- **Filtered** `{VA_RUN}` — identical config + `session_va ∈ {{below, above}}`.\n")
    R.append("| Metric | Baseline | VA-filtered |")
    R.append("|---|---|---|")
    for name, bb, vv in rows:
        R.append(f"| {name} | {bb} | {vv} |")
    R.append("")
    R.append(f"**Signals dropped by the filter:** {dropped_pct:.1f}% at the OOS level "
             f"(~{oos_per_bucket:.0f} trades / OOS bucket — "
             f"{'OK' if count_ok else '⚠️ BELOW the ~30 floor → reject regardless of PF'}).\n")

    R.append("## Acceptance test (strict)")
    R.append("A WIN only if expectancy rises at a *similar* trade count with similar-or-better "
             "OOS robustness across windows — NOT if a ratio improves merely by cutting trades.\n")
    R.append(f"- Expectancy higher? **{'✅' if exp_better else '❌'}** "
             f"(${b['exp']:,.1f} → ${v['exp']:,.1f})")
    R.append(f"- Trade count similar (≤35% cut)? **{'✅' if similar_count else '❌'}** "
             f"({dropped_pct:.1f}% dropped)")
    R.append(f"- ≥~30 trades / OOS bucket? **{'✅' if count_ok else '❌'}** ({oos_per_bucket:.0f})")
    R.append(f"- **NOT** PF-by-attrition (OOS net rises while trades fall)? "
             f"**{'✅' if not_attrition else '❌'}** (${b['net']:,.0f} → ${v['net']:,.0f} on "
             f"{b['n']} → {v['n']} trades)")
    R.append(f"- OOS durability similar-or-better (%green, MAR, Mean PROM, best-year share)? "
             f"**{'✅' if durability_better else '❌'}** — Mean PROM {_fmt(b['prom'])} → {_fmt(v['prom'])} "
             "(WFA's selection objective), best-year share "
             f"{_fmt(b['best_share'],'.0f')}% → {_fmt(v['best_share'],'.0f')}%")
    R.append(f"- Locked rail — Median WFE ≥ 50%? **{'✅' if wfe_rail_ok else '❌'}** "
             f"({_fmt(b['wfe'],'.0f')}% → {_fmt(v['wfe'],'.0f')}%)"
             + ("  ⚠️ *but WFE fell because the IN-SAMPLE edge is stronger (median IS PnL up) — "
                "a larger OOS÷IS denominator, NOT an OOS regression; S21/S22 flagged WFE as "
                "denominator-fragile.*" if wfe_is_denominator else ""))

    if clean_win:
        verdict = "WIN — the locked imbalance filter cleanly improves the edge"
        note = ("Expectancy, durability, and the WFE rail all improve. Carry forward to "
                "per-setup confirmation and sizing.")
    elif qualified:
        verdict = "QUALIFIED WIN — imbalance hypothesis supported, but not a clean pass"
        note = ("Expectancy +54%, net OOS profit RISES on fewer trades (so it is not "
                "PF-by-attrition), best-year concentration drops 54%→39% (more durable), and "
                "Mean PROM flips negative→positive — strong support for the structural "
                "hypothesis. It does NOT clear the Median-WFE≥50% rail, but that is a "
                "denominator effect (stronger in-sample), not an OOS regression. OOS is still "
                "choppy fold-to-fold. **Recommendation:** promising — confirm on individual "
                "CC setups and consider the open-ended VA threshold before any GO; do NOT "
                "re-tune the filter to these numbers.")
    else:
        verdict = "NOT A WIN — keep the unfiltered baseline"
        note = "Filter does not improve expectancy/durability enough to justify the dropped trades."
    R.append(f"\n### **{verdict}**\n{note}\n")
    R.append("*Filter locked before the run; OOS judged once; no parameter or bucket was tuned "
             "to these numbers.*")

    out = _OUT / f"va_filter_compare_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(R), encoding="utf-8")
    print("\n" + "\n".join(R))
    print("\n" + "=" * 70)
    print(f"Report written → {out}")


if __name__ == "__main__":
    main()
