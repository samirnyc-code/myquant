"""confirm_er_lookback.py — WFA OOS confirmation: ER10 vs ER30 at 0.30 threshold.

The er_lookback_study found 10min (2-bar) ER dominates 30min (6-bar) ER on the
full sample ($469k/$107 exp vs $386k/$87). This confirms via walk-forward OOS
folds (IS=252/OOS=63 signal-days) that the advantage holds out-of-sample.

Head-to-head: same fold structure, same sim params, only the ER column differs.
Also tests ER10 at higher thresholds (0.35, 0.40) since the lookback study
showed monotonic improvement.

Run: .venv/Scripts/python.exe scripts/confirm_er_lookback.py
Out: docs/living/confirm_er_lookback_<date>.md
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                                                       # noqa: E402
import wfa                                                           # noqa: E402
from simulation_engine import simulate_trades                        # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"

BASE = dict(entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5,
            contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
            ratchet_r=0.0, pb_round="nearest", target_r=1.0,
            multileg=False, threeleg=False, overrides=None)

IS_DAYS, OOS_DAYS = 252, 63


def log(m: str) -> None:
    print(f"[er_cf] {datetime.now():%H:%M:%S} {m}", flush=True)


def kaufman_er(close: pd.Series, n: int) -> pd.Series:
    step = close.diff().abs()
    direction = (close - close.shift(n)).abs()
    volatility = step.rolling(n).sum().replace(0, np.nan)
    return direction / volatility


def stats(pnl: np.ndarray) -> dict:
    n = len(pnl)
    if n == 0:
        return dict(n=0, net=0, exp=0, pf=0, wr=0)
    net = float(pnl.sum())
    gross_w = float(pnl[pnl > 0].sum()) if (pnl > 0).any() else 0
    gross_l = float(abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else 0
    pf = gross_w / gross_l if gross_l > 0 else float("inf")
    wr = float((pnl > 0).sum() / n * 100)
    return dict(n=n, net=net, exp=net / n, pf=pf, wr=wr)


def pf_str(v: float) -> str:
    return "∞" if v == float("inf") else f"{v:.2f}"


def main() -> int:
    log("loading data...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    # compute ER columns
    log("computing ER variants...")
    df_bars = bars.sort_values("DateTime").reset_index(drop=True)
    er_df = pd.DataFrame({
        "DateTime": df_bars["DateTime"],
        "er_2": kaufman_er(df_bars["Close"], 2).values,   # 10min
        "er_3": kaufman_er(df_bars["Close"], 3).values,   # 15min
        "er_6": kaufman_er(df_bars["Close"], 6).values,   # 30min
    })

    sig["DateTime"] = pd.to_datetime(sig["DateTime"]).dt.as_unit("ns")
    er_df["DateTime"] = pd.to_datetime(er_df["DateTime"]).dt.as_unit("ns")
    sig = pd.merge_asof(
        sig.sort_values("DateTime"),
        er_df.sort_values("DateTime"),
        on="DateTime", direction="backward",
    )

    # load ticks once for all signals
    log("loading ticks...")
    all_dates = sorted(sig["Date"].unique())
    ticks_by_date = {d: massive.load_continuous_ticks(d) for d in all_dates}
    ticks_by_date = {d: t for d, t in ticks_by_date.items() if not t.empty}

    # simulate ALL signals (no filter — slice post-hoc)
    log(f"simulating {len(sig)} signals...")
    res = simulate_trades(signals=sig, ticks_by_date=ticks_by_date,
                          bars_by_date=bars_by_date, **BASE)
    filled_mask = res["Filled"] == True
    sig_f = sig.loc[filled_mask].copy()
    res_f = res.loc[filled_mask].copy()
    sig_f["NetPnL"] = res_f["NetPnL"].values
    log(f"filled: {len(sig_f)}")

    # configs to compare
    configs = [
        ("ER30 >= 0.30", "er_6", 0.30),
        ("ER10 >= 0.30", "er_2", 0.30),
        ("ER10 >= 0.35", "er_2", 0.35),
        ("ER10 >= 0.40", "er_2", 0.40),
        ("ER15 >= 0.30", "er_3", 0.30),
    ]

    # build folds from the broadest signal set (no filter)
    sig_dates = sorted(sig_f["Date"].unique())
    folds = wfa.build_folds(sig_dates, IS_DAYS, OOS_DAYS)
    n_folds = len(folds)
    log(f"built {n_folds} folds")

    md = [f"# Confirm ER Lookback — WFA OOS ({datetime.now():%Y-%m-%d})\n",
          f"Pinned 1.0R single-leg, IS={IS_DAYS}/OOS={OOS_DAYS} signal-day folds. "
          f"{n_folds} folds, {len(sig_f)} filled signals total.\n"]

    # ══════════════════════════════════════════════════════════════════════════
    # PART 1 — per-fold head-to-head
    # ══════════════════════════════════════════════════════════════════════════
    for cfg_name, col, thr in configs:
        md.append(f"\n## {cfg_name}\n")
        md += ["| fold | OOS range | n | net | exp | PF | win% |",
               "|---|---|---|---|---|---|---|"]
        pooled = []
        green = 0
        for fold in folds:
            oos = set(fold["oos_dates"])
            sub = sig_f[sig_f["Date"].isin(oos)]
            gate = sub[col].fillna(0) >= thr
            pnl = sub.loc[gate, "NetPnL"].values
            pooled.append(pnl)
            s = stats(pnl)
            if s["net"] > 0:
                green += 1
            d0, d1 = min(oos), max(oos)
            md.append(f"| {fold['fold_id']} | {d0}→{d1} | {s['n']} | "
                      f"${s['net']:,.0f} | ${s['exp']:.0f} | {pf_str(s['pf'])} | {s['wr']:.1f}% |")

        pooled_pnl = np.concatenate(pooled) if pooled else np.array([])
        ps = stats(pooled_pnl)
        md.append(f"| **POOLED** | | **{ps['n']}** | **${ps['net']:,.0f}** | "
                  f"**${ps['exp']:.0f}** | **{pf_str(ps['pf'])}** | **{ps['wr']:.1f}%** |")
        md.append(f"\n**{green}/{n_folds} folds green ({green/n_folds*100:.0f}%).**\n")

    # ══════════════════════════════════════════════════════════════════════════
    # PART 2 — summary comparison table
    # ══════════════════════════════════════════════════════════════════════════
    md.append("\n## Summary — head-to-head\n")
    md += ["| config | pooled n | pooled net | pooled exp | pooled PF | % green | 2022 exp |",
           "|---|---|---|---|---|---|---|"]

    for cfg_name, col, thr in configs:
        # pooled OOS
        pooled = []
        green = 0
        for fold in folds:
            oos = set(fold["oos_dates"])
            sub = sig_f[sig_f["Date"].isin(oos)]
            gate = sub[col].fillna(0) >= thr
            pnl = sub.loc[gate, "NetPnL"].values
            pooled.append(pnl)
            if pnl.sum() > 0:
                green += 1

        pooled_pnl = np.concatenate(pooled) if pooled else np.array([])
        ps = stats(pooled_pnl)

        # 2022 slice (regime stress test)
        yr_mask = pd.to_datetime(sig_f["DateTime"]).dt.year == 2022
        gate_22 = sig_f[col].fillna(0) >= thr
        pnl_22 = sig_f.loc[yr_mask & gate_22, "NetPnL"].values
        s22 = stats(pnl_22)

        md.append(f"| {cfg_name} | {ps['n']} | ${ps['net']:,.0f} | ${ps['exp']:.0f} | "
                  f"{pf_str(ps['pf'])} | {green}/{n_folds} ({green/n_folds*100:.0f}%) | ${s22['exp']:.0f} |")
    md.append("")

    # ══════════════════════════════════════════════════════════════════════════
    # PART 3 — per-year breakdown for ER10 vs ER30
    # ══════════════════════════════════════════════════════════════════════════
    md.append("\n## Per-year: ER10 >= 0.30 vs ER30 >= 0.30\n")
    md += ["| year | ER30 n | ER30 exp | ER30 PF | ER10 n | ER10 exp | ER10 PF | lift |",
           "|---|---|---|---|---|---|---|---|"]

    years = sorted(pd.to_datetime(sig_f["DateTime"]).dt.year.unique())
    yr_vals = pd.to_datetime(sig_f["DateTime"]).dt.year.values
    for y in years:
        ymask = yr_vals == y
        # ER30
        g30 = sig_f["er_6"].fillna(0) >= 0.30
        p30 = sig_f.loc[ymask & g30, "NetPnL"].values
        s30 = stats(p30)
        # ER10
        g10 = sig_f["er_2"].fillna(0) >= 0.30
        p10 = sig_f.loc[ymask & g10, "NetPnL"].values
        s10 = stats(p10)
        lift = s10["exp"] - s30["exp"]
        md.append(f"| {y} | {s30['n']} | ${s30['exp']:.0f} | {pf_str(s30['pf'])} | "
                  f"{s10['n']} | ${s10['exp']:.0f} | {pf_str(s10['pf'])} | ${lift:+.0f} |")

    # totals
    g30_all = sig_f["er_6"].fillna(0) >= 0.30
    g10_all = sig_f["er_2"].fillna(0) >= 0.30
    s30a = stats(sig_f.loc[g30_all, "NetPnL"].values)
    s10a = stats(sig_f.loc[g10_all, "NetPnL"].values)
    md.append(f"| **ALL** | **{s30a['n']}** | **${s30a['exp']:.0f}** | **{pf_str(s30a['pf'])}** | "
              f"**{s10a['n']}** | **${s10a['exp']:.0f}** | **{pf_str(s10a['pf'])}** | "
              f"**${s10a['exp']-s30a['exp']:+.0f}** |")
    md.append("")

    # write
    out_path = _OUT / f"confirm_er_lookback_{datetime.now():%Y%m%d}.md"
    out_path.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out_path}")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n" + "\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
