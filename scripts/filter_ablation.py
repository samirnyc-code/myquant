"""Filter ablation — isolate the marginal value of each regime filter.

Runs FOUR WFA configs through the SAME engine, SAME window, SAME pinned params,
differing ONLY in the regime-filter spec, so PROM / MAR95 are head-to-head:

    1. VA-only          (session_va ∈ {below, above})          -> should ≈ run_c484a745
    2. VA + VWAP-σ       (+ |σ| ≥ 1.0 tails)
    3. VA + ER-30m       (+ ER ≥ 0.4 trending)
    4. VA + VWAP + ER    (all three)                            -> should ≈ run_b402f142

Pinned T1=1.25 / PB=-0.25 / T2=2.00 (no grid sweep), 12m IS / 3m OOS (252/63
signal-days), multileg, ALL setups. Reproduces the app path exactly:
apply_regime_filter -> run_wfa. Reuses pipeline's MC / path stats. No auto-tuning.
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
from bar_analysis import _VWAP_LABELS, _ERI_LABELS  # noqa: E402
from scripts.run_setup_pipeline import monte_carlo, oos_path_stats  # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"

# Exact bucket sets, sliced from the canonical label constants (byte-identical to
# what run_b402f142 recorded — VWAP |σ|≥1.0 tails, ER ≥0.4 trending).
VA   = ["below", "above"]
VWAP = _VWAP_LABELS[2:7] + _VWAP_LABELS[11:16]   # -3.5..-1.0σ and +1.0..+3.5σ
ER   = _ERI_LABELS[2:5]                           # 0.4-0.6, 0.6-0.8, 0.8-1.0 trend

CONFIGS = {
    "1_VA_only":      {"session_va": VA},
    "2_VA_VWAP":      {"session_va": VA, "vwap_sigma": VWAP},
    "3_VA_ER":        {"session_va": VA, "eri_30": ER},
    "4_VA_VWAP_ER":   {"session_va": VA, "vwap_sigma": VWAP, "eri_30": ER},
}

# Match run_c484a745 / run_b402f142 params_json exactly.
BASE = dict(entry_slip=0.5, exit_slip=0.5, stop_offset=1, tick_value=12.5,
            contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
            ratchet_r=0.0, pb_round="nearest")
IS_DAYS, OOS_DAYS = 252, 63
PINS = dict(pin_t1=1.25, pin_t2=2.00, pin_pb=-0.25)


def log(m): print(f"[ablation] {m}", flush=True)


def main():
    store.init_db()
    sig  = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}
    log(f"{len(sig)} signals, {sig['Date'].nunique()} signal-days loaded.")

    # Tag ONCE on the full set, then mask per config (mirrors the app's memoized tag).
    tagged, bcols = rf.tag_and_bucket(sig, bars)
    log(f"tagged; bucket cols: {list(bcols)}")

    # Build filtered signal sets + union of dates for a single tick load.
    filt = {}
    all_dates = set()
    for name, spec in CONFIGS.items():
        act = rf.active_spec(tagged, bcols, spec)
        mask = rf.filter_mask(tagged, bcols, act)
        kept = set(tagged.loc[mask, "_rf_id"].tolist())
        s2 = sig.copy(); s2["_rf_id"] = np.arange(len(s2))
        fs = s2[s2["_rf_id"].isin(kept)].drop(columns="_rf_id").copy()
        filt[name] = fs
        all_dates |= set(fs["Date"].unique())
        log(f"{name}: {len(fs)} signals, {fs['Date'].nunique()} signal-days, active={rf.describe_spec(act)}")

    log(f"loading tick cache for {len(all_dates)} union days…")
    ticks_by_date = {}
    for d in sorted(all_dates):
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t
    log(f"ticks loaded for {len(ticks_by_date)} days.")

    results = []
    for name, fs in filt.items():
        run_id = f"abl_{name}"
        store.delete_run(run_id)
        store.create_run(run_id, "ALL", "multileg", BASE, f"ablation {name}")
        log(f"running WFA {name}…")
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
        results.append(dict(
            cfg=name, signals=len(fs), folds=agg["n_folds"],
            oos_trades=len(oos_f), net=net,
            prom=agg["mean_oos_prom"], pct_green=agg["pct_oos_prof"],
            wfe=agg["mean_wfe"], pf=agg["oos_pf_median"],
            maxdd=ps["maxdd"] if ps else float("nan"),
            mar=ps["mar"] if ps else float("nan"),
            dd95=dd95, mar95=(net / abs(dd95)) if (dd95 and not np.isnan(dd95) and dd95 < 0) else float("nan"),
            best_share=ps["best_share"] if ps else float("nan"),
        ))
        r = results[-1]
        log(f"DONE {name}: folds={r['folds']} net=${r['net']:,.0f} PROM={r['prom']:.2f} "
            f"MAR95={r['mar95']:.2f} %green={r['pct_green']:.0f} WFE={r['wfe']:.0f}")

    df = pd.DataFrame(results).set_index("cfg")
    pd.set_option("display.width", 200, "display.max_columns", 20)
    print("\n================ FILTER ABLATION RESULTS ================")
    print(df.to_string(float_format=lambda x: f"{x:,.2f}"))
    out = _ROOT / "docs" / "living" / "filter_ablation_results.csv"
    df.to_csv(out)
    print(f"\nsaved -> {out}")


if __name__ == "__main__":
    main()
