"""Filter ablation, round 2 — find the RIGHT threshold for VWAP-σ and ER-30m.

Round 1 tested only one cut each. Here we vary the threshold, all on top of the
VA filter (established as helpful), same engine/window/pins as round 1.

VWAP: does a GENTLE cut (drop only the dead-center ±0.5σ) help, vs the aggressive
      |σ|≥1.0 that hurt? Tested on raw VWAP_dev.
ER:   where is the edge — keep ≥0.2 (drop chop only), ≥0.32, or ≥0.4? Raw ER_intra_6.
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


def log(m): print(f"[abl2] {m}", flush=True)


def main():
    store.init_db()
    sig  = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}
    tagged, bcols = rf.tag_and_bucket(sig, bars)
    va_mask = rf.filter_mask(tagged, bcols, {"session_va": VA})
    vd = tagged["VWAP_dev"].astype(float)
    er = tagged["ER_intra_6"].astype(float)
    log(f"VWAP_dev non-null {vd.notna().sum()}, ER non-null {er.notna().sum()}")

    # mask builders (all AND with VA). NaN on the active dim is dropped (>= is False for NaN).
    CONFIGS = {
        "VA_only":        va_mask,
        "VA_VWAPgt0.5":   va_mask & (vd.abs() >= 0.5),   # drop only dead-center -0.5..+0.5
        "VA_VWAPgt1.0":   va_mask & (vd.abs() >= 1.0),   # round-1 aggressive (reconfirm)
        "VA_ERgt0.2":     va_mask & (er >= 0.2),         # drop only 0-0.2 chop
        "VA_ERgt0.32":    va_mask & (er >= 0.32),        # finer threshold
        "VA_ERgt0.4":     va_mask & (er >= 0.4),         # round-1 winner (reconfirm)
    }

    filt, all_dates = {}, set()
    for name, mask in CONFIGS.items():
        kept = set(tagged.loc[mask.fillna(False), "_rf_id"].tolist())
        s2 = sig.copy(); s2["_rf_id"] = np.arange(len(s2))
        fs = s2[s2["_rf_id"].isin(kept)].drop(columns="_rf_id").copy()
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
        run_id = f"abl2_{name}"
        store.delete_run(run_id)
        store.create_run(run_id, "ALL", "multileg", BASE, f"abl2 {name}")
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
        rows.append(dict(cfg=name, signals=len(fs), folds=agg["n_folds"],
            oos_trades=len(oos_f), net=net, prom=agg["mean_oos_prom"],
            pct_green=agg["pct_oos_prof"], wfe=agg["mean_wfe"], pf=agg["oos_pf_median"],
            mar=ps["mar"] if ps else float("nan"),
            mar95=(net/abs(dd95)) if (dd95 and not np.isnan(dd95) and dd95 < 0) else float("nan"),
            best_share=ps["best_share"] if ps else float("nan")))
        r = rows[-1]
        log(f"DONE {name}: folds={r['folds']} net=${r['net']:,.0f} PROM={r['prom']:.2f} "
            f"MAR95={r['mar95']:.2f} %green={r['pct_green']:.0f} WFE={r['wfe']:.0f}")

    df = pd.DataFrame(rows).set_index("cfg")
    print("\n============ ABLATION 2 — THRESHOLD SCAN ============")
    print(df.to_string(float_format=lambda x: f"{x:,.2f}"))
    df.to_csv(_ROOT / "docs" / "living" / "filter_ablation2_results.csv")


if __name__ == "__main__":
    main()
