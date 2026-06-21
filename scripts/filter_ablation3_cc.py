"""Ablation round 3 — per-setup (CC1..CC5) with JUST the chop filter.

For each CC: baseline (no filter) vs chop-filtered (drop ER 0-0.2 'chop' bucket,
i.e. keep ER_intra_6 >= 0.2). NO VA, NO VWAP — isolates the chop filter's effect
per setup. Same engine/window/pins as rounds 1-2 (multileg, 12m/3m, pinned
1.25/-0.25/2.00). Setups with too few signal-days to form >=1 fold are reported
as such.
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
SETUPS = ["CC1", "CC2", "CC3", "CC4", "CC5"]
CHOP_MIN = 0.30  # keep ER >= 0.30


def log(m): print(f"[abl3] {m}", flush=True)


def metrics(run_id):
    oos = store.load_all_oos_trades(run_id, run_id.split("_")[1])
    oos_f = oos[oos["Filled"] == True] if not oos.empty else pd.DataFrame()
    mc = monte_carlo(oos_f["NetPnL"].to_numpy()) if len(oos_f) >= 30 else None
    ps = oos_path_stats(oos_f)
    net = ps["net"] if ps else float("nan")
    dd95 = mc["dd95"] if mc else float("nan")
    return len(oos_f), net, dd95, ps


def main():
    store.init_db()
    sig  = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}
    tagged, bcols = rf.tag_and_bucket(sig, bars)   # tag once on full set
    er = tagged["ER_intra_6"].astype(float)
    sig2 = sig.copy(); sig2["_rf_id"] = np.arange(len(sig2))

    # Build all filtered sets first; collect union dates for one tick load.
    jobs, all_dates = [], set()
    for cc in SETUPS:
        cc_rows = tagged["SignalType"] == cc
        for tag, mask in [("base", cc_rows), ("chop", cc_rows & (er >= CHOP_MIN))]:
            kept = set(tagged.loc[mask.fillna(False), "_rf_id"].tolist())
            fs = sig2[sig2["_rf_id"].isin(kept)].drop(columns="_rf_id").copy()
            jobs.append((cc, tag, fs))
            all_dates |= set(fs["Date"].unique())
            log(f"{cc}/{tag}: {len(fs)} signals, {fs['Date'].nunique()} signal-days")

    log(f"loading ticks for {len(all_dates)} union days…")
    ticks_by_date = {}
    for d in sorted(all_dates):
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t
    log(f"ticks loaded {len(ticks_by_date)} days.")

    rows = []
    for cc, tag, fs in jobs:
        n_days = fs["Date"].nunique()
        if n_days < IS_DAYS + OOS_DAYS:
            log(f"SKIP {cc}/{tag}: {n_days} signal-days < {IS_DAYS+OOS_DAYS} needed (0 folds).")
            rows.append(dict(cc=cc, variant=tag, signals=len(fs), folds=0,
                             oos_trades=0, net=float("nan"), prom=float("nan"),
                             pct_green=float("nan"), wfe=float("nan"), mar95=float("nan")))
            continue
        run_id = f"abl3_{cc}_{tag}"
        store.delete_run(run_id)
        store.create_run(run_id, cc, "multileg", BASE, f"abl3 {cc} {tag}")
        log(f"WFA {cc}/{tag}…")
        folds = wfa.run_wfa(run_id, cc, fs, ticks_by_date, bars_by_date,
                            BASE, "multileg", is_days=IS_DAYS, oos_days=OOS_DAYS,
                            n_param_sets=3, **PINS)
        agg = wfa._aggregate_grid_cell(folds)
        oos = store.load_all_oos_trades(run_id, cc)
        oos_f = oos[oos["Filled"] == True] if not oos.empty else pd.DataFrame()
        mc = monte_carlo(oos_f["NetPnL"].to_numpy()) if len(oos_f) >= 30 else None
        ps = oos_path_stats(oos_f)
        net = ps["net"] if ps else float("nan")
        dd95 = mc["dd95"] if mc else float("nan")
        rows.append(dict(cc=cc, variant=tag, signals=len(fs), folds=agg["n_folds"],
            oos_trades=len(oos_f), net=net, prom=agg["mean_oos_prom"],
            pct_green=agg["pct_oos_prof"], wfe=agg["mean_wfe"],
            mar95=(net/abs(dd95)) if (dd95 and not np.isnan(dd95) and dd95 < 0) else float("nan")))
        r = rows[-1]
        log(f"DONE {cc}/{tag}: folds={r['folds']} net=${net:,.0f} PROM={r['prom']:.2f} MAR95={r['mar95']:.2f}")

    df = pd.DataFrame(rows)
    print("\n============ ABLATION 3 — PER-CC CHOP FILTER ============")
    print(df.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    df.to_csv(_ROOT / "docs" / "living" / "filter_ablation3_cc_results.csv", index=False)


if __name__ == "__main__":
    main()
