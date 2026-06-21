"""Per-setup optimization + portfolio assembly.

Phase A: For each CC2-CC5, run UNPINNED WFA with ER>=0.30 chop filter.
         Extract Kaufman-averaged params per setup.
Phase B: For each CC, run PINNED WFA with that setup's optimal params + ER>=0.30.
         Then combine all setups into one portfolio run with per-setup pinned params.
         Report side-by-side metrics.

Usage:
    python scripts/per_setup_portfolio.py                         # multileg ES (default)
    python scripts/per_setup_portfolio.py --mode singleleg        # singleleg ES
    python scripts/per_setup_portfolio.py --instrument MES --contracts 5  # 5 MES
"""
from __future__ import annotations
import argparse
import sys, time
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                                  # noqa: E402
import wfa                                      # noqa: E402
import regime_filter as rf                      # noqa: E402
import results_store as store                   # noqa: E402
from simulation_engine import simulate_trades, compute_summary, INSTRUMENTS  # noqa: E402
from scripts.run_setup_pipeline import monte_carlo, oos_path_stats  # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"

IS_DAYS, OOS_DAYS = 252, 63
SETUPS = ["CC2", "CC3", "CC4", "CC5"]
CHOP_MIN = 0.30


def log(m):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {m}", flush=True)


def make_base(instrument: str, contracts: int) -> dict:
    inst = INSTRUMENTS[instrument]
    return dict(
        entry_slip=1, exit_slip=0, stop_offset=1,
        tick_value=inst["tick_value"],
        contracts=contracts, contracts_t1=contracts, contracts_t2=contracts,
        commission=inst["default_commission"],
        ratchet_r=0.0, pb_round="nearest",
    )


def extract_metrics(folds, run_id, setup_id):
    agg = wfa._aggregate_grid_cell(folds)
    oos = store.load_all_oos_trades(run_id, setup_id)
    oos_f = oos[oos["Filled"] == True] if not oos.empty else pd.DataFrame()
    mc = monte_carlo(oos_f["NetPnL"].to_numpy()) if len(oos_f) >= 30 else None
    ps = oos_path_stats(oos_f)
    net = ps["net"] if ps else float("nan")
    dd95 = mc["dd95"] if mc else float("nan")
    mar95 = (net / abs(dd95)) if (mc and dd95 < 0) else float("nan")
    exp = float(oos_f["NetPnL"].mean()) if len(oos_f) else float("nan")
    med = float(oos_f["NetPnL"].median()) if len(oos_f) else float("nan")

    tgt_hit = float("nan")
    if len(oos_f):
        _tgt_mask = (oos_f["ExitReason"].str.contains("Target", na=False) |
                     oos_f["ExitReason"].isin(["T1+BE", "T1_only"]))
        tgt_hit = float(_tgt_mask.mean() * 100)

    best_yr = ps.get("best_year_share", float("nan")) if ps else float("nan")
    uw_days = ps.get("max_uw_days", float("nan")) if ps else float("nan")

    return dict(
        folds=agg["n_folds"], oos_trades=len(oos_f),
        net=net, exp=exp, median=med, prom=agg["mean_oos_prom"],
        pct_green=agg["pct_oos_prof"], median_wfe=agg["mean_wfe"],
        mar95=mar95, dd95=dd95, tgt_hit_pct=tgt_hit,
        best_yr_pct=best_yr, uw_days=uw_days,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["multileg", "singleleg"], default="multileg")
    parser.add_argument("--instrument", choices=["ES", "MES"], default="ES")
    parser.add_argument("--contracts", type=int, default=None)
    args = parser.parse_args()

    mode = args.mode
    instrument = args.instrument
    contracts = args.contracts or (1 if instrument == "ES" else 5)
    base_params = make_base(instrument, contracts)
    tag = f"{mode}_{instrument}{contracts}"

    log(f"Config: mode={mode}, instrument={instrument}, contracts={contracts}")

    t_start = time.perf_counter()
    store.init_db()

    log("Loading signals + bars...")
    sig  = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    log("Tagging signals for regime filter...")
    tagged, bcols = rf.tag_and_bucket(sig, bars)
    er = tagged["ER_intra_6"].astype(float)
    sig2 = sig.copy()
    sig2["_rf_id"] = np.arange(len(sig2))

    cc_signals = {}
    all_dates = set()
    for cc in SETUPS:
        cc_mask = (tagged["SignalType"] == cc) & (er >= CHOP_MIN)
        kept = set(tagged.loc[cc_mask.fillna(False), "_rf_id"].tolist())
        fs = sig2[sig2["_rf_id"].isin(kept)].drop(columns="_rf_id").copy()
        cc_signals[cc] = fs
        all_dates |= set(fs["Date"].unique())
        log(f"  {cc}: {len(fs)} signals, {fs['Date'].nunique()} signal-days")

    log(f"Loading ticks for {len(all_dates)} union days...")
    ticks_by_date = {}
    for d in sorted(all_dates):
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t
    log(f"Ticks loaded: {len(ticks_by_date)} days")

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE A — Unpinned per-CC WFA
    # ══════════════════════════════════════════════════════════════════════════
    log("=" * 60)
    log(f"PHASE A: Unpinned per-CC WFA ({mode}, {instrument}x{contracts}, ER>=0.30)")
    log("=" * 60)

    optimal_params = {}
    phase_a_rows = []

    for cc in SETUPS:
        fs = cc_signals[cc]
        n_days = fs["Date"].nunique()
        if n_days < IS_DAYS + OOS_DAYS:
            log(f"SKIP {cc}: {n_days} signal-days < {IS_DAYS + OOS_DAYS}")
            continue

        run_id = f"opt_A_{cc}_{tag}"
        store.delete_run(run_id)
        store.create_run(run_id, cc, mode, base_params,
                         f"Phase A: {cc} unpinned {tag} ER>=0.30")
        log(f"  {cc}: running unpinned {mode} WFA...")
        t0 = time.perf_counter()

        folds = wfa.run_wfa(run_id, cc, fs, ticks_by_date, bars_by_date,
                            base_params, mode, is_days=IS_DAYS, oos_days=OOS_DAYS,
                            n_param_sets=3, objective="prom")
        elapsed = time.perf_counter() - t0

        if not folds:
            log(f"  {cc}: NO FOLDS")
            continue

        fold_params = [f["avg_params"] for f in folds]
        if mode == "multileg":
            avg_t1 = float(np.mean([p.get("t1_r", 1.0) for p in fold_params]))
            avg_t2 = float(np.mean([p.get("target_r", 1.0) for p in fold_params]))
            avg_pb = float(np.mean([p.get("ml_pb_r", -0.50) for p in fold_params]))
            optimal_params[cc] = {"t1_r": avg_t1, "target_r": avg_t2, "ml_pb_r": avg_pb}
            param_str = f"T1={avg_t1:.2f} T2={avg_t2:.2f} PB={avg_pb:.2f}"
        else:
            avg_tgt = float(np.mean([p.get("target_r", 1.0) for p in fold_params]))
            optimal_params[cc] = {"target_r": avg_tgt}
            param_str = f"T={avg_tgt:.2f}"

        metrics = extract_metrics(folds, run_id, cc)
        phase_a_rows.append({"cc": cc, **optimal_params[cc], **metrics})
        log(f"  {cc} DONE ({elapsed:.0f}s): {param_str} | "
            f"net=${metrics['net']:,.0f} PROM={metrics['prom']:.2f} MAR95={metrics['mar95']:.2f}")

    log("")
    log("PHASE A SUMMARY:")
    for cc, p in optimal_params.items():
        log(f"  {cc}: {p}")

    if not optimal_params:
        log("No setups produced results. Aborting.")
        return

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE B — Pinned per-CC WFA + portfolio
    # ══════════════════════════════════════════════════════════════════════════
    log("")
    log("=" * 60)
    log(f"PHASE B: Pinned per-CC WFA + portfolio ({tag})")
    log("=" * 60)

    phase_b_rows = []
    all_portfolio_oos = []

    for cc in SETUPS:
        if cc not in optimal_params:
            continue
        fs = cc_signals[cc]
        p = optimal_params[cc]

        run_id = f"opt_B_{cc}_{tag}"
        store.delete_run(run_id)
        store.create_run(run_id, cc, mode, base_params,
                         f"Phase B: {cc} pinned {tag} {p}")
        log(f"  {cc}: pinned WFA ({p})...")
        t0 = time.perf_counter()

        if mode == "multileg":
            folds = wfa.run_wfa(run_id, cc, fs, ticks_by_date, bars_by_date,
                                base_params, mode, is_days=IS_DAYS, oos_days=OOS_DAYS,
                                n_param_sets=3, objective="prom",
                                pin_t1=p["t1_r"], pin_t2=p["target_r"], pin_pb=p["ml_pb_r"])
        else:
            folds = wfa.run_wfa(run_id, cc, fs, ticks_by_date, bars_by_date,
                                base_params, mode, is_days=IS_DAYS, oos_days=OOS_DAYS,
                                n_param_sets=3, objective="prom",
                                pin_t1=p["target_r"])
        elapsed = time.perf_counter() - t0

        if not folds:
            log(f"  {cc}: NO FOLDS")
            continue

        metrics = extract_metrics(folds, run_id, cc)
        phase_b_rows.append({"cc": cc, **p, **metrics})

        oos = store.load_all_oos_trades(run_id, cc)
        if not oos.empty:
            oos_f = oos[oos["Filled"] == True].copy()
            oos_f["setup"] = cc
            all_portfolio_oos.append(oos_f)

        log(f"  {cc} DONE ({elapsed:.0f}s): net=${metrics['net']:,.0f} exp=${metrics['exp']:.0f} "
            f"PROM={metrics['prom']:.2f} MAR95={metrics['mar95']:.2f}")

    # ── Portfolio ──────────────────────────────────────────────────────────────
    log("")
    log("-" * 40)
    log(f"PORTFOLIO ({tag})")
    log("-" * 40)

    port_stats = {}
    by_year = pd.Series(dtype=float)
    if all_portfolio_oos:
        port = pd.concat(all_portfolio_oos, ignore_index=True).sort_values(["Date", "EntryTime"])
        pnl = port["NetPnL"].to_numpy()
        eq = np.cumsum(pnl)
        net = float(eq[-1])
        dd = eq - np.maximum.accumulate(eq)
        maxdd = float(dd.min())
        mc = monte_carlo(pnl) if len(pnl) >= 30 else None
        dd95 = mc["dd95"] if mc else maxdd
        mar95 = (net / abs(dd95)) if dd95 < 0 else float("nan")
        exp = float(pnl.mean())
        med = float(np.median(pnl))
        win_pct = float((pnl > 0).mean() * 100)
        pf = float(pnl[pnl > 0].sum() / abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else float("nan")

        yr = pd.to_datetime(port["Date"]).dt.year
        by_year = port.groupby(yr)["NetPnL"].sum()
        best_yr_pct = float(by_year.max() / net * 100) if net > 0 else float("nan")
        port_stats = dict(trades=len(port), net=net, exp=exp, med=med,
                          win_pct=win_pct, pf=pf, maxdd=maxdd, dd95=dd95,
                          mar95=mar95, best_yr_pct=best_yr_pct)

        log(f"  Trades: {len(port)}")
        log(f"  Net: ${net:,.0f}")
        log(f"  Exp: ${exp:.0f}  Median: ${med:.0f}")
        log(f"  Win%: {win_pct:.1f}%  PF: {pf:.2f}")
        log(f"  MaxDD: ${maxdd:,.0f}  MC DD95: ${dd95:,.0f}")
        log(f"  MAR95: {mar95:.2f}")
        log(f"  Best-year share: {best_yr_pct:.0f}%")
        log(f"  Per-year PnL:")
        for y, v in by_year.items():
            log(f"    {y}: ${v:,.0f}")
    else:
        log("  No OOS trades to combine.")

    # ── Save ───────────────────────────────────────────────────────────────────
    elapsed_total = time.perf_counter() - t_start
    log(f"\nTotal runtime: {elapsed_total/60:.1f} min")

    df_a = pd.DataFrame(phase_a_rows) if phase_a_rows else pd.DataFrame()
    df_b = pd.DataFrame(phase_b_rows) if phase_b_rows else pd.DataFrame()

    out_file = _OUT / f"per_setup_{tag}_{datetime.now().strftime('%Y%m%d')}.md"
    with open(out_file, "w") as f:
        f.write(f"# Per-Setup Optimization: {tag}\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**Runtime:** {elapsed_total/60:.1f} min\n")
        f.write(f"**Config:** {mode}, {instrument} x{contracts}, ER>=0.30, {IS_DAYS}d IS / {OOS_DAYS}d OOS\n\n")

        f.write("## Phase A: Unpinned WFA (optimal params per setup)\n\n")
        if not df_a.empty:
            f.write(df_a.to_markdown(index=False, floatfmt=".2f"))
        f.write("\n\n## Optimal params:\n\n")
        for cc, p in optimal_params.items():
            f.write(f"- **{cc}:** {p}\n")

        f.write("\n\n## Phase B: Pinned WFA (per-setup optimal params)\n\n")
        if not df_b.empty:
            f.write(df_b.to_markdown(index=False, floatfmt=".2f"))

        if port_stats:
            f.write(f"\n\n## Portfolio (combined CC2-CC5)\n\n")
            for k, v in port_stats.items():
                f.write(f"- {k}: {v:,.2f}\n" if isinstance(v, float) else f"- {k}: {v}\n")
            f.write("\n### Per-year PnL\n\n")
            for y, v in by_year.items():
                f.write(f"- {y}: ${v:,.0f}\n")

    log(f"Report saved: {out_file}")

    csv_tag = tag
    if not df_a.empty:
        df_a.to_csv(_OUT / f"per_setup_phase_a_{csv_tag}.csv", index=False)
    if not df_b.empty:
        df_b.to_csv(_OUT / f"per_setup_phase_b_{csv_tag}.csv", index=False)
    log("CSVs saved.")


if __name__ == "__main__":
    main()
