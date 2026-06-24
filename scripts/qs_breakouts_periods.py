"""QS Breakouts — period breakdowns (Year / Quarter / Month / Week).

Runs the WP setup once (frictionless), then aggregates per-trade results into
time-period tables with the main metrics. Console shows Year + Quarter; Month +
Week saved to CSV under docs/living/qs_periods/.

Config = QSConfig.paper(); subset = FT-only (the WP BO+FT setup, entry bar 2).
Targets 1.0R and 2.0R. Frictionless (no costs).

Run: python scripts/qs_breakouts_periods.py
"""
from __future__ import annotations
import sys, gc
from pathlib import Path
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
import massive                                          # noqa: E402
from simulation_engine import simulate_trades           # noqa: E402
from qs_setups import detect, QSConfig                  # noqa: E402

_BARS = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT = _ROOT / "docs" / "living" / "qs_periods"
BASE = dict(stop_offset=1, tick_value=12.5, contracts=1, commission=0.0,
            multileg=False, threeleg=False, overrides=None, entry_model="market",
            entry_slip=0, exit_slip=0)
N_CHUNKS = 6
PT = 50.0  # $/pt per ES contract (net$ already in $ from engine NetPnL)


def log(m): print(f"[qsper] {m}", flush=True)


def run_trades(sig, target_r) -> pd.DataFrame:
    """Sim the subset frictionless; return per-trade df: dt, r, pnl."""
    sig = sig[sig["FilterStatus"] == "ok"].reset_index(drop=True)
    sig["_date"] = pd.to_datetime(sig["DateTime"]).dt.date
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bbd = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    dates = np.array(sorted(sig["_date"].unique()), object)
    out = []
    for ci, chunk in enumerate(np.array_split(dates, N_CHUNKS)):
        sub = sig[sig["_date"].isin(set(chunk.tolist()))].reset_index(drop=True)
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        res = simulate_trades(signals=sub, ticks_by_date=tbd, bars_by_date=bbd,
                              target_r=target_r, **BASE).reset_index(drop=True)
        fl = (res["Filled"] == True).values
        rf = res.loc[fl]
        out.append(pd.DataFrame({
            "dt": pd.to_datetime(sub.loc[fl, "DateTime"].values),
            "pnl": rf["NetPnL"].values,
            "r": rf["NetPnL"].values / rf["RiskDollar"].replace(0, np.nan).values,
        }))
        del tbd; gc.collect()
        log(f"  target {target_r}R chunk {ci+1}/{N_CHUNKS}")
    return pd.concat(out, ignore_index=True).sort_values("dt").reset_index(drop=True)


def metrics(g: pd.DataFrame) -> pd.Series:
    r = g["r"].to_numpy(float); pnl = g["pnl"].to_numpy(float)
    n = len(r)
    wins = r > 0
    std = np.nanstd(r, ddof=1) if n > 1 else np.nan
    cum = np.cumsum(r)
    dd = (cum - np.maximum.accumulate(cum)).min() if n else np.nan
    gw = pnl[pnl > 0].sum(); gl = abs(pnl[pnl < 0].sum())
    return pd.Series({
        "n": n,
        "win%": round(wins.mean() * 100, 1),
        "expR": round(np.nanmean(r), 3),
        "CIR": round(1.96 * std / np.sqrt(n), 3) if n > 1 else np.nan,
        "PF": round(gw / gl, 2) if gl > 0 else np.inf,
        "SQN": round(np.nanmean(r) / std * np.sqrt(n), 2) if (n > 1 and std > 0) else np.nan,
        "totR": round(r.sum(), 1),
        "net$": round(pnl.sum(), 0),
        "avgW_R": round(r[wins].mean(), 2) if wins.any() else np.nan,
        "avgL_R": round(r[~wins].mean(), 2) if (~wins).any() else np.nan,
        "maxDD_R": round(dd, 1),
    })


def by_period(trades: pd.DataFrame, freq: str) -> pd.DataFrame:
    key = trades["dt"].dt.to_period(freq).astype(str)
    tbl = trades.groupby(key, sort=True).apply(metrics, include_groups=False)
    tbl.index.name = freq
    return tbl


def main():
    _OUT.mkdir(parents=True, exist_ok=True)
    bars = pd.read_parquet(_BARS)
    sig = detect(bars, QSConfig.paper())
    ft = sig[sig["SignalType"] == "BO+FT"]
    log(f"FT-only signals: {len(ft):,}  ({(ft['FilterStatus']=='ok').sum():,} ok)")

    for tr in (1.0, 2.0):
        trades = run_trades(ft, tr)
        tag = f"FTonly_{tr:.0f}R_frictionless"
        log(f"\n################  {tag}  (n={len(trades):,})  ################")
        for freq, name in [("Y", "YEARLY"), ("Q", "QUARTERLY"),
                            ("M", "MONTHLY"), ("W", "WEEKLY")]:
            tbl = by_period(trades, freq)
            tbl.to_csv(_OUT / f"{tag}_{name.lower()}.csv")
            if freq in ("Y", "Q"):
                log(f"\n===== {name} — {tag} =====")
                log(tbl.to_string())
        log(f"\n[saved monthly+weekly CSVs to {_OUT}]")


if __name__ == "__main__":
    main()
