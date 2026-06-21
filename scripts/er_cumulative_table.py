"""er_cumulative_table.py — side-by-side "drop everything below X" for ER10 vs ER60.

Run: .venv/Scripts/python.exe scripts/er_cumulative_table.py
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
from simulation_engine import simulate_trades                        # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"

BASE = dict(entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5,
            contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
            ratchet_r=0.0, pb_round="nearest", target_r=1.0,
            multileg=False, threeleg=False, overrides=None)


def log(m: str) -> None:
    print(f"[er_ct] {datetime.now():%H:%M:%S} {m}", flush=True)


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
    log("loading + simulating...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    df_bars = bars.sort_values("DateTime").reset_index(drop=True)
    er_df = pd.DataFrame({
        "DateTime": df_bars["DateTime"],
        "er_2":  kaufman_er(df_bars["Close"], 2).values,   # 10min
        "er_12": kaufman_er(df_bars["Close"], 12).values,  # 60min
    })
    sig["DateTime"] = pd.to_datetime(sig["DateTime"]).dt.as_unit("ns")
    er_df["DateTime"] = pd.to_datetime(er_df["DateTime"]).dt.as_unit("ns")
    sig = pd.merge_asof(sig.sort_values("DateTime"),
                        er_df.sort_values("DateTime"),
                        on="DateTime", direction="backward")

    ticks_by_date = {d: massive.load_continuous_ticks(d) for d in sorted(sig["Date"].unique())}
    ticks_by_date = {d: t for d, t in ticks_by_date.items() if not t.empty}

    res = simulate_trades(signals=sig, ticks_by_date=ticks_by_date,
                          bars_by_date=bars_by_date, **BASE)
    filled = res["Filled"] == True
    sf = sig.loc[filled].copy()
    sf["NetPnL"] = res.loc[filled, "NetPnL"].values
    log(f"filled: {len(sf)}")

    md = [f"# ER Cumulative Filter Table ({datetime.now():%Y-%m-%d})\n",
          "Pinned 1.0R single-leg, no filters. 'Drop below X' = keep signals with ER >= X.\n"]

    thresholds = np.arange(0, 1.01, 0.10)

    md.append("\n## Side-by-side: ER10 (2-bar / 10min) vs ER60 (12-bar / 60min)\n")
    md += ["| drop below | ER10 n | ER10 net | ER10 exp | ER10 PF | ER10 win% | | ER60 n | ER60 net | ER60 exp | ER60 PF | ER60 win% |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]

    for thr in thresholds:
        # ER10
        m10 = sf["er_2"].fillna(-1) >= thr
        s10 = stats(sf.loc[m10, "NetPnL"].values)
        # ER60
        m60 = sf["er_12"].fillna(-1) >= thr
        s60 = stats(sf.loc[m60, "NetPnL"].values)

        md.append(f"| {thr:.1f} | {s10['n']} | ${s10['net']:,.0f} | ${s10['exp']:.0f} | "
                  f"{pf_str(s10['pf'])} | {s10['wr']:.1f}% | | "
                  f"{s60['n']} | ${s60['net']:,.0f} | ${s60['exp']:.0f} | "
                  f"{pf_str(s60['pf'])} | {s60['wr']:.1f}% |")

    md.append("")

    out_path = _OUT / f"er_cumulative_table_{datetime.now():%Y%m%d}.md"
    out_path.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out_path}")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n" + "\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
