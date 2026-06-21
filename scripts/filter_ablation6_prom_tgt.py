"""Ablation round 6 — PROM vs PROM-target objective, UNPINNED per-CC.

For each CC (CC2-CC5): run WFA with ER>=0.30 chop filter, UNPINNED params
(full T1/T2/PB grid sweep), comparing standard PROM vs PROM-target objective.
Multileg, 12m/3m. This tests whether prom_tgt stops the optimizer from chasing
high-R EOD drift.
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
SETUPS = ["CC2", "CC3", "CC4", "CC5"]
CHOP_MIN = 0.30


def log(m): print(f"[abl6] {m}", flush=True)


def main():
    store.init_db()
    sig  = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}
    tagged, bcols = rf.tag_and_bucket(sig, bars)
    er = tagged["ER_intra_6"].astype(float)
    sig2 = sig.copy(); sig2["_rf_id"] = np.arange(len(sig2))

    jobs, all_dates = [], set()
    for cc in SETUPS:
        cc_mask = (tagged["SignalType"] == cc) & (er >= CHOP_MIN)
        kept = set(tagged.loc[cc_mask.fillna(False), "_rf_id"].tolist())
        fs = sig2[sig2["_rf_id"].isin(kept)].drop(columns="_rf_id").copy()
        jobs.append((cc, fs))
        all_dates |= set(fs["Date"].unique())
        log(f"{cc}: {len(fs)} signals, {fs['Date'].nunique()} signal-days")

    log(f"loading ticks for {len(all_dates)} union days…")
    ticks_by_date = {}
    for d in sorted(all_dates):
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t
    log(f"ticks loaded {len(ticks_by_date)} days.")

    rows = []
    for cc, fs in jobs:
        n_days = fs["Date"].nunique()
        if n_days < IS_DAYS + OOS_DAYS:
            log(f"SKIP {cc}: {n_days} signal-days < {IS_DAYS+OOS_DAYS}")
            for obj in ["prom", "prom_tgt"]:
                rows.append(dict(cc=cc, objective=obj, signals=len(fs), folds=0,
                    oos_trades=0, net=float("nan"), exp=float("nan"),
                    prom=float("nan"), pct_green=float("nan"), mar95=float("nan"),
                    avg_target_r=float("nan"), tgt_hit_pct=float("nan")))
            continue

        for obj in ["prom", "prom_tgt"]:
            run_id = f"abl6_{cc}_{obj}"
            store.delete_run(run_id)
            store.create_run(run_id, cc, "multileg", BASE, f"abl6 {cc} obj={obj}")
            log(f"WFA {cc} objective={obj} (UNPINNED)…")
            folds = wfa.run_wfa(run_id, cc, fs, ticks_by_date, bars_by_date,
                                BASE, "multileg", is_days=IS_DAYS, oos_days=OOS_DAYS,
                                n_param_sets=3, objective=obj)
            agg = wfa._aggregate_grid_cell(folds)
            oos = store.load_all_oos_trades(run_id, cc)
            oos_f = oos[oos["Filled"] == True] if not oos.empty else pd.DataFrame()
            mc = monte_carlo(oos_f["NetPnL"].to_numpy()) if len(oos_f) >= 30 else None
            ps = oos_path_stats(oos_f)
            net = ps["net"] if ps else float("nan")
            dd95 = mc["dd95"] if mc else float("nan")

            # What target did the optimizer pick per fold?
            avg_tgt = float("nan")
            tgt_hit = float("nan")
            if folds:
                tgts = [f.get("oos_params", {}).get("target_r", float("nan")) for f in folds]
                avg_tgt = float(np.nanmean(tgts))
            if len(oos_f):
                _tgt_mask = (oos_f["ExitReason"].str.contains("Target", na=False) |
                             oos_f["ExitReason"].isin(["T1+BE", "T1_only"]))
                tgt_hit = float(_tgt_mask.mean() * 100)

            rows.append(dict(cc=cc, objective=obj, signals=len(fs), folds=agg["n_folds"],
                oos_trades=len(oos_f), net=net,
                exp=oos_f["NetPnL"].mean() if len(oos_f) else float("nan"),
                prom=agg["mean_oos_prom"], pct_green=agg["pct_oos_prof"],
                mar95=(net/abs(dd95)) if (dd95 and not np.isnan(dd95) and dd95 < 0) else float("nan"),
                avg_target_r=avg_tgt, tgt_hit_pct=tgt_hit))
            r = rows[-1]
            log(f"DONE {cc}/{obj}: folds={r['folds']} net=${net:,.0f} PROM={r['prom']:.2f} "
                f"MAR95={r['mar95']:.2f} avg_T={r['avg_target_r']:.2f} tgt_hit={r['tgt_hit_pct']:.0f}%")

    df = pd.DataFrame(rows)
    pd.set_option("display.width", 240, "display.max_columns", 20)
    print("\n============ ABLATION 6 — PROM vs PROM-TARGET (UNPINNED) ============")
    print(df.to_string(index=False, float_format=lambda x: f"{x:,.2f}"))
    df.to_csv(_ROOT / "docs" / "living" / "filter_ablation6_prom_tgt.csv", index=False)


if __name__ == "__main__":
    main()
