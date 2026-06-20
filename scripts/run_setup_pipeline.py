"""Drive ONE setup through the entire decision pipeline, headless, and document it.

This is the "master run" from the S22 plan / setup_decision_manual: it executes a
HUMAN-PRE-SPECIFIED config (setup, mode, filter) and *reports*. It NEVER auto-tunes
the regime filter or pins params to results — that is the no-feedback / overfitting
violation the whole project guards against (PROJECT_CHARTER §4).

It reuses the SAME engine the app uses (simulation_engine.simulate_trades, wfa.run_wfa,
wfa.run_window_structures) — no trade logic is reimplemented here.

Usage:
    python scripts/run_setup_pipeline.py --setup CC4 --mode singleleg --filter off

Writes: docs/living/pipeline_<setup>_<mode>_<date>.md  (and prints progress).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive  # noqa: E402
from simulation_engine import simulate_trades, compute_summary, INSTRUMENTS  # noqa: E402
import results_store as store  # noqa: E402
import wfa  # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT_DIR = _ROOT / "docs" / "living"

# Fixed acceptance rails (PROJECT_CHARTER §4 / setup_decision_manual). NOT tuned.
_BASELINE_IS_MO, _BASELINE_OOS_MO = 12, 3
_STRUCTURES = [(3, 1), (6, 1), (6, 3), (12, 3), (12, 1), (24, 6)]  # stability↔adaptivity spread
_MC_ITERS = 5000
_RNG = np.random.default_rng(42)


def _log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def _fmt(v, f=".2f", fb="—"):
    try:
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            return fb
        return f"{v:{f}}"
    except Exception:
        return fb


# ── Data loading ──────────────────────────────────────────────────────────────
def load_inputs(setup: str):
    sig = pd.read_parquet(_SIGNALS)
    sig = sig[sig["SignalType"] == setup].copy()
    if sig.empty:
        raise SystemExit(f"No signals for setup {setup}")

    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    dates = sorted(sig["Date"].unique())
    _log(f"Loading tick cache for {len(dates)} signal-days…")
    ticks_by_date = {}
    for d in dates:
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t
    _log(f"Tick cache loaded for {len(ticks_by_date)}/{len(dates)} days.")
    return sig, bars_by_date, ticks_by_date


def base_params(commission: float) -> dict:
    return dict(
        entry_slip=1.0, exit_slip=1.0, stop_offset=1, tick_value=INSTRUMENTS["ES"]["tick_value"],
        contracts=1, contracts_t1=1, contracts_t2=1, commission=commission,
        ratchet_r=0.0, pb_round="nearest",
    )


# ── Monte Carlo on OOS trades (Phase 4.5) ─────────────────────────────────────
def monte_carlo(oos_pnl: np.ndarray):
    """Bootstrap-reshuffle the realised OOS trades → DD & terminal-PnL distributions."""
    n = len(oos_pnl)
    if n < 30:
        return None
    term, maxdd = np.empty(_MC_ITERS), np.empty(_MC_ITERS)
    for i in range(_MC_ITERS):
        draw = _RNG.choice(oos_pnl, size=n, replace=True)
        eq = np.cumsum(draw)
        term[i] = eq[-1]
        maxdd[i] = (eq - np.maximum.accumulate(eq)).min()
    return dict(
        dd95=float(np.percentile(maxdd, 5)),    # 5th pct of (negative) DD = 95% worst
        dd99=float(np.percentile(maxdd, 1)),
        p_term_loss=float((term < 0).mean() * 100),
        term_med=float(np.median(term)),
        term_lo=float(np.percentile(term, 2.5)),
        term_hi=float(np.percentile(term, 97.5)),
    )


# ── OOS equity PATH / shape (the gate the first version missed) ────────────────
def oos_path_stats(oos_f: pd.DataFrame):
    """Shape of the COMBINED OOS equity curve — aggregate PnL can be positive while
    the path is a regime-dependent disaster. Gates: MAR (net ÷ max DD) and best-year
    profit concentration (>70% of OOS profit from one year = regime-dependent)."""
    if oos_f.empty:
        return None
    f = oos_f.sort_values(["Date", "EntryTime"])
    pnl = f["NetPnL"].to_numpy()
    eq = np.cumsum(pnl)
    dd = eq - np.maximum.accumulate(eq)
    maxdd = float(dd.min())
    net = float(eq[-1])
    yr = pd.to_datetime(f["Date"]).dt.year
    by_year = f.groupby(yr)["NetPnL"].sum()
    best_share = float(by_year.max() / net * 100) if net > 0 else float("nan")
    # longest underwater stretch in calendar days
    dts = pd.to_datetime(f["Date"]).to_numpy()
    longest, start = 0, None
    for i, u in enumerate(dd < 0):
        if u and start is None:
            start = dts[i]
        elif not u and start is not None:
            longest = max(longest, int((dts[i] - start) / np.timedelta64(1, "D")))
            start = None
    if start is not None:
        longest = max(longest, int((dts[-1] - start) / np.timedelta64(1, "D")))
    return dict(net=net, maxdd=maxdd, mar=(net / abs(maxdd) if maxdd < 0 else float("inf")),
                trough=float(eq.min()), best_share=best_share, longest_uw=longest, by_year=by_year)


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", default="CC4")
    ap.add_argument("--mode", default="singleleg", choices=["singleleg", "multileg", "3leg"])
    ap.add_argument("--filter", default="off", choices=["off"])  # locked OFF this run
    args = ap.parse_args()

    setup, mode = args.setup, args.mode
    comm = INSTRUMENTS["ES"]["default_commission"]
    bp = base_params(comm)

    store.init_db()
    sig, bars_by_date, ticks_by_date = load_inputs(setup)
    R = []  # report lines
    R.append(f"# Pipeline Report — {setup} ({mode}, regime filter OFF)")
    R.append(f"*Generated {datetime.now():%Y-%m-%d %H:%M} · headless · same engine as the app · "
             "human-pre-specified config, no auto-tuning (PROJECT_CHARTER §4).*\n")

    # ── Phase 0 — Sanity ───────────────────────────────────────────────────────
    dates = sorted(sig["Date"].unique())
    yrs = (pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days / 365.25
    R.append("## Phase 0 — Sanity")
    R.append(f"- **{len(sig)} {setup} signals** over {dates[0]} → {dates[-1]} (~{yrs:.1f} yr), "
             f"{len(dates)} signal-days.")
    R.append(f"- Tick data present for **{len(ticks_by_date)}/{len(dates)}** days.")
    R.append(f"- Avg **{len(sig)/yrs:.0f} signals/yr** "
             f"({'above' if len(sig)/yrs >= 30 else 'BELOW'} the ~30/yr discard floor).\n")
    _log("Phase 0 done.")

    # ── Phase 1 — Raw edge (baseline single-leg, target 1.0R, no optimisation) ──
    _log("Phase 1 — raw edge sim…")
    raw = simulate_trades(signals=sig, ticks_by_date=ticks_by_date, bars_by_date=bars_by_date,
                          target_r=1.0, multileg=False, threeleg=False, **bp)
    rs = compute_summary(raw, commission=comm, contracts=1)
    R.append("## Phase 1 — Raw edge (baseline 1.0R target, NO optimisation)")
    if rs:
        R.append(f"- Trades **{rs['n_trades']}** · Net **${rs['net_total']:,.0f}** · "
                 f"Expectancy **${rs['exp_dollar']:,.1f}/trade** ({_fmt(rs['exp_r'],'.3f')} R) · "
                 f"PF **{_fmt(rs['pf'])}** · Win% **{_fmt(rs['win_pct'],'.1f')}** · "
                 f"Max DD **${rs['max_dd']:,.0f}** · PnL/DD **{_fmt(rs['pnl_dd'])}**.")
        raw_pos = rs["net_total"] > 0
        R.append(f"- Raw expectancy is **{'POSITIVE' if raw_pos else 'NEGATIVE'}** — "
                 f"{'clears' if raw_pos else 'FAILS'} the Phase-1 gate (an edge must exist "
                 "before optimisation; optimising a non-edge just fits noise).\n")
    else:
        R.append("- No filled trades — cannot assess.\n")
        raw_pos = False

    # ── Phase 2/3c — Profit by year & concentration (from raw filled trades) ────
    fr = raw[raw["Filled"] == True].copy() if not raw.empty else pd.DataFrame()
    R.append("## Phase 2 — Structure: profit by year & concentration")
    if not fr.empty:
        fr["Year"] = pd.to_datetime(fr["Date"]).dt.year
        by_year = fr.groupby("Year")["NetPnL"].sum()
        R.append("| Year | Net PnL |\n|---|---|")
        for y, v in by_year.items():
            R.append(f"| {y} | ${v:,.0f} |")
        tot = fr["NetPnL"].sum()
        best_share = (by_year.max() / tot * 100) if tot > 0 else float("nan")
        gross_win = fr.loc[fr["NetPnL"] > 0, "NetPnL"].sum()
        top10 = fr.nlargest(10, "NetPnL")["NetPnL"].sum()
        top10_share = (top10 / gross_win * 100) if gross_win > 0 else float("nan")
        R.append(f"\n- **Best-year share:** {_fmt(best_share,'.0f')}% of total profit "
                 f"({'⚠️ regime-dependent (>70%)' if best_share > 70 else 'ok'}).")
        R.append(f"- **Top-10-trade share of gross profit:** {_fmt(top10_share,'.0f')}% "
                 f"({'⚠️ concentrated (>25%)' if top10_share > 25 else 'ok'}).\n")

    # ── Phase 3 — Baseline WFA (unpinned, persisted) ───────────────────────────
    run_id = f"pipe_{setup.lower()}_{mode}"
    store.delete_run(run_id)
    store.create_run(run_id, setup, mode, bp, "headless pipeline run (filter OFF)")
    is_days = int(_BASELINE_IS_MO * wfa._TRADING_DAYS_PER_YEAR / 12)
    oos_days = int(_BASELINE_OOS_MO * wfa._TRADING_DAYS_PER_YEAR / 12)
    _log(f"Phase 3 — baseline WFA {_BASELINE_IS_MO}m/{_BASELINE_OOS_MO}m…")
    folds = wfa.run_wfa(run_id, setup, sig, ticks_by_date, bars_by_date, bp, mode,
                        is_days=is_days, oos_days=oos_days, n_param_sets=3,
                        progress_cb=lambda i, t, m: _log(f"  {m}"))
    agg = wfa._aggregate_grid_cell(folds)
    passed, fails = wfa._window_pass(agg)
    R.append(f"## Phase 3 — Walk-Forward Analysis (unpinned, {_BASELINE_IS_MO}m IS / {_BASELINE_OOS_MO}m OOS)")
    R.append(f"- **{agg['n_folds']} folds** · Total OOS PnL **${agg['total_oos_pnl']:,.0f}** · "
             f"Median WFE **{_fmt(agg['mean_wfe'],'.0f')}%** · "
             f"% OOS profitable **{_fmt(agg['pct_oos_prof'],'.0f')}%** · "
             f"Median fold PF **{_fmt(agg['oos_pf_median'])}** · "
             f"Mean PROM **{_fmt(agg['mean_oos_prom'])}** · "
             f"Worst-fold DD **${agg['oos_maxdd_worst']:,.0f}**.")
    R.append(f"- Baseline window **{'PASSES' if passed else 'FAILS'}** the rails"
             + ("" if passed else f" — fails: {'; '.join(fails)}") + ".\n")

    # ── Phase 3a — WF-structure robustness (the architecture question) ─────────
    _log("Phase 3a — window-structure robustness…")
    structs = wfa.run_window_structures(sig, ticks_by_date, bars_by_date, bp, mode,
                                        _STRUCTURES, n_param_sets=3,
                                        progress_cb=lambda i, t, m: _log(f"  struct {i+1}/{t} {m}"))
    R.append("## Phase 3a — Walk-forward STRUCTURE robustness")
    R.append(f"Same setup + params under {len(_STRUCTURES)} IS/OOS architectures. "
             f"Robustness score = independent fixed tests survived (0–{wfa._WIN_N_TESTS}).\n")
    R.append(f"| Architecture | Tests | Folds | OOS PnL | Med PF | Med WFE% | %green | PROM |\n"
             "|---|---|---|---|---|---|---|---|")
    rows = []
    for s in structs:
        a = s["agg"]
        sc = wfa._window_robustness_score(a)
        rows.append((sc, a, s))
        R.append(f"| IS {s['is_months']}m/OOS {s['oos_months']}m | {sc}/{wfa._WIN_N_TESTS} | "
                 f"{a['n_folds']} | ${a['total_oos_pnl']:,.0f} | {_fmt(a['oos_pf_median'])} | "
                 f"{_fmt(a['mean_wfe'],'.0f')} | {_fmt(a['pct_oos_prof'],'.0f')} | {_fmt(a['mean_oos_prom'])} |")
    rows.sort(key=lambda r: r[0], reverse=True)
    n_strong = sum(1 for sc, _, _ in rows if sc >= 5)
    R.append(f"\n- **{n_strong}/{len(rows)} architectures score ≥5/{wfa._WIN_N_TESTS}.** "
             "Robust edges survive *most* structures, not one cherry-picked window.\n")

    # ── Phase 4.5 — Monte Carlo on OOS trades ──────────────────────────────────
    _log("Phase 4.5 — Monte Carlo…")
    oos = store.load_all_oos_trades(run_id, setup)
    oos_f = oos[oos["Filled"] == True] if not oos.empty else pd.DataFrame()
    R.append("## Phase 4.5 — Monte Carlo (baseline OOS trades, 5,000 bootstraps)")
    mc = monte_carlo(oos_f["NetPnL"].to_numpy()) if not oos_f.empty else None
    if mc:
        R.append(f"- **DD95 ${mc['dd95']:,.0f}** · **DD99 ${mc['dd99']:,.0f}** "
                 "(size capital against THIS, not the single realised path).")
        R.append(f"- Terminal OOS PnL: median **${mc['term_med']:,.0f}** "
                 f"(95% CI ${mc['term_lo']:,.0f} … ${mc['term_hi']:,.0f}); "
                 f"**P(OOS loss) = {mc['p_term_loss']:.1f}%**.\n")
    else:
        R.append("- Too few OOS trades for Monte Carlo (<30).\n")

    # ── Phase 4.6 — OOS equity PATH & shape (aggregate PnL hides an ugly path) ──
    ps = oos_path_stats(oos_f)
    R.append("## Phase 4.6 — OOS equity PATH & shape")
    if ps:
        R.append(f"- Combined OOS: Net **${ps['net']:,.0f}** · Max DD **${ps['maxdd']:,.0f}** · "
                 f"**MAR {_fmt(ps['mar'])}** (net ÷ |max DD|) · early trough **${ps['trough']:,.0f}** · "
                 f"longest underwater **{ps['longest_uw']} days**.")
        R.append(f"- **Best-year share: {_fmt(ps['best_share'],'.0f')}% of OOS profit** "
                 f"({'⚠️ regime-dependent (>70%)' if (not np.isnan(ps['best_share']) and ps['best_share'] > 70) else 'ok'}).")
        R.append("\n| Year | OOS Net |\n|---|---|")
        for y, v in ps["by_year"].items():
            R.append(f"| {y} | ${v:,.0f} |")
        R.append("\n*A positive total with one year >70% of profit and a max DD near the total profit "
                 "is a regime-dependent curve, not a durable edge — the shape gates below catch this.*\n")

    # ── Phase 6 / Verdict — Acceptance report card + go/no-go ──────────────────
    raw_ok = raw_pos
    base_ok = passed
    struct_ok = n_strong >= max(1, len(rows) // 2)
    mc_ok = (mc is not None and mc["p_term_loss"] < 35)
    # Shape gates (the blind spot in v1): measured on the COMBINED OOS curve.
    mar_ok  = bool(ps is not None and ps["mar"] >= 1.0)
    conc_ok = bool(ps is not None and not np.isnan(ps["best_share"]) and ps["best_share"] <= 70)

    core = [("Raw edge positive", raw_ok), ("Baseline WFA passes rails", base_ok),
            ("Survives ≥half of structures", struct_ok), ("Monte Carlo P(loss) < 35%", mc_ok)]
    shape = [("OOS max-DD survivable (MAR ≥ 1)", mar_ok),
             ("OOS profit not 1-year (≤70%)", conc_ok)]
    checks = core + shape
    n_ok = sum(c for _, c in checks)
    core_fail  = sum(1 for _, ok in core if not ok)
    shape_fail = sum(1 for _, ok in shape if not ok)

    R.append("## Verdict — Acceptance report card")
    R.append("| Gate | Type | Result |\n|---|---|---|")
    for name, ok in core:
        R.append(f"| {name} | core | {'✅' if ok else '❌'} |")
    for name, ok in shape:
        R.append(f"| {name} | shape | {'✅' if ok else '❌'} |")
    # Shape failures are DECISIVE — a regime-dependent path that can't survive its own
    # drawdown is disqualifying no matter how good the aggregates look (the v1 miss).
    if n_ok == len(checks):
        verdict = "GO — tradeable candidate"
        note = ("Edge is positive raw, survives walk-forward, holds across most window structures, "
                "Monte Carlo risk is acceptable, AND the OOS path is durable. Next: sizing (MES), Q5/Q6, portfolio.")
    elif shape_fail > 0 or core_fail >= 2:
        verdict = "NO-GO — does not clear the rails"
        note = ("Shelve this configuration. " + ("A shape gate failed — the OOS profit is regime-dependent "
                "and/or the drawdown rivals the total profit, so the positive aggregate is not a durable edge. "
                if shape_fail else "") + "Do not trade it as-is.")
    else:
        verdict = "CONDITIONAL — promising but not clean"
        note = "One core gate failed (path is sound); investigate it specifically before risking capital."
    R.append(f"\n### **{verdict}**  ({n_ok}/{len(checks)} gates · {core_fail} core / {shape_fail} shape failed)\n{note}\n")
    R.append("*Rails fixed in advance; this report executes a pre-specified config and never "
             "tuned a parameter or filter to these results.*")

    out = _OUT_DIR / f"pipeline_{setup}_{mode}_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(R), encoding="utf-8")
    _log(f"DONE → {out}")
    print("\n" + "=" * 70)
    print(f"VERDICT: {verdict}  ({n_ok}/{len(checks)} gates)")
    print(f"Report: {out}")


if __name__ == "__main__":
    main()
