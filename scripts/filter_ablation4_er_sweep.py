"""Ablation round 4 — fine ER threshold sweep from 0.20 to 0.40.

Maps the full curve at 0.02 increments to find the real optimum. All on top of
VA filter, same engine/window/pins as prior rounds.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                                  # noqa: E402
import wfa                                      # noqa: E402
import regime_filter as rf                      # noqa: E402
import results_store as store                   # noqa: E402
from scripts.run_setup_pipeline import monte_carlo, oos_path_stats  # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"

BASE = dict(entry_slip=0.5, exit_slip=0.5, stop_offset=1, tick_value=12.5,
            contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
            ratchet_r=0.0, pb_round="nearest")
IS_DAYS, OOS_DAYS = 252, 63
PINS = dict(pin_t1=1.25, pin_t2=2.00, pin_pb=-0.25)
VA = ["below", "above"]

ER_THRESHOLDS = [round(0.20 + i * 0.02, 2) for i in range(11)]  # 0.20 .. 0.40


def log(m): print(f"[abl4] {m}", flush=True)


def main():
    store.init_db()
    sig  = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}
    tagged, bcols = rf.tag_and_bucket(sig, bars)
    va_mask = rf.filter_mask(tagged, bcols, {"session_va": VA})
    er = tagged["ER_intra_6"].astype(float)
    sig2 = sig.copy(); sig2["_rf_id"] = np.arange(len(sig2))

    filt, all_dates = {}, set()
    for thr in ER_THRESHOLDS:
        name = f"ER_{thr:.2f}"
        mask = va_mask & (er >= thr)
        kept = set(tagged.loc[mask.fillna(False), "_rf_id"].tolist())
        fs = sig2[sig2["_rf_id"].isin(kept)].drop(columns="_rf_id").copy()
        filt[name] = fs
        all_dates |= set(fs["Date"].unique())
        log(f"{name}: {len(fs)} signals, {fs['Date'].nunique()} signal-days")

    log(f"loading ticks for {len(all_dates)} union days…")
    ticks_by_date = {}
    for d in sorted(all_dates):
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t
    log(f"ticks loaded {len(ticks_by_date)} days.")

    rows = []
    for name, fs in filt.items():
        run_id = f"abl4_{name}"
        store.delete_run(run_id)
        store.create_run(run_id, "ALL", "multileg", BASE, f"abl4 {name}")
        log(f"WFA {name}…")
        folds = wfa.run_wfa(run_id, "ALL", fs, ticks_by_date, bars_by_date,
                            BASE, "multileg", is_days=IS_DAYS, oos_days=OOS_DAYS,
                            n_param_sets=3, **PINS)
        agg = wfa._aggregate_grid_cell(folds)
        oos = store.load_all_oos_trades(run_id, "ALL")
        oos_f = oos[oos["Filled"] == True] if not oos.empty else pd.DataFrame()
        mc = monte_carlo(oos_f["NetPnL"].to_numpy()) if len(oos_f) >= 30 else None
        ps = oos_path_stats(oos_f)
        net = ps["net"] if ps else float("nan")
        dd95 = mc["dd95"] if mc else float("nan")
        exp = oos_f["NetPnL"].mean() if len(oos_f) else float("nan")
        med = oos_f["NetPnL"].median() if len(oos_f) else float("nan")
        win = (oos_f["NetPnL"] > 0).mean() * 100 if len(oos_f) else float("nan")
        rows.append(dict(
            er_min=float(name.split("_")[1]), signals=len(fs), folds=agg["n_folds"],
            oos_trades=len(oos_f), net=net, exp=exp, median=med, win_pct=win,
            prom=agg["mean_oos_prom"], pct_green=agg["pct_oos_prof"],
            wfe=agg["mean_wfe"], pf=agg["oos_pf_median"],
            maxdd=ps["maxdd"] if ps else float("nan"),
            mar=ps["mar"] if ps else float("nan"),
            dd95=dd95,
            mar95=(net / abs(dd95)) if (dd95 and not np.isnan(dd95) and dd95 < 0) else float("nan"),
            best_share=ps["best_share"] if ps else float("nan")))
        r = rows[-1]
        log(f"DONE {name}: folds={r['folds']} net=${r['net']:,.0f} exp=${r['exp']:.1f} "
            f"PROM={r['prom']:.2f} MAR95={r['mar95']:.2f} %green={r['pct_green']:.0f}")

    df = pd.DataFrame(rows)
    pd.set_option("display.width", 240, "display.max_columns", 25)
    print("\n============ ABLATION 4 — ER THRESHOLD SWEEP (0.20–0.40) ============")
    print(df.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    df.to_csv(_ROOT / "docs" / "living" / "filter_ablation4_er_sweep.csv", index=False)


if __name__ == "__main__":
    main()
