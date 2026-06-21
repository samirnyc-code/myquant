"""er_open_endpoint.py — ER computed with Open[T] instead of Close[T].

Removes signal-bar circularity: ER measures trend into the bar, not including
the breakout move itself. Compares Open-endpoint ER vs standard Close-endpoint
ER at multiple lookbacks and thresholds.

Run: .venv/Scripts/python.exe scripts/er_open_endpoint.py
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
    print(f"[er_op] {datetime.now():%H:%M:%S} {m}", flush=True)


def er_close(close: pd.Series, n: int) -> pd.Series:
    """Standard ER: endpoint = Close[T]."""
    step = close.diff().abs()
    direction = (close - close.shift(n)).abs()
    volatility = step.rolling(n).sum().replace(0, np.nan)
    return direction / volatility


def er_open(bars_df: pd.DataFrame, n: int) -> pd.Series:
    """Open-endpoint ER: endpoint = Open[T] instead of Close[T].

    direction = |Open[T] - Close[T-n]|
    volatility = |Open[T] - Close[T-1]| + |Close[T-1] - Close[T-2]| + ... + |Close[T-n+1] - Close[T-n]|

    This gives the ER reading at the instant bar T opens, before the signal
    bar's price action happens.
    """
    c = bars_df["Close"]
    o = bars_df["Open"]
    step_close = c.diff().abs()

    direction = (o - c.shift(n)).abs()

    # volatility: last step is |Open[T] - Close[T-1]|, rest are |Close[i] - Close[i-1]|
    vol_interior = step_close.rolling(n - 1).sum() if n > 1 else 0
    step_open = (o - c.shift(1)).abs()
    volatility = (vol_interior + step_open).replace(0, np.nan)

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

    df_bars = bars.sort_values("DateTime").reset_index(drop=True)

    spans = [2, 3, 6, 12]  # 10min, 15min, 30min, 60min
    span_labels = {2: "10min", 3: "15min", 6: "30min", 12: "60min"}

    log("computing ER variants (close vs open endpoint)...")
    er_df = {"DateTime": df_bars["DateTime"]}
    for n in spans:
        er_df[f"er_close_{n}"] = er_close(df_bars["Close"], n).values
        er_df[f"er_open_{n}"] = er_open(df_bars, n).values
    er_df = pd.DataFrame(er_df)

    sig["DateTime"] = pd.to_datetime(sig["DateTime"]).dt.as_unit("ns")
    er_df["DateTime"] = pd.to_datetime(er_df["DateTime"]).dt.as_unit("ns")
    sig = pd.merge_asof(sig.sort_values("DateTime"),
                        er_df.sort_values("DateTime"),
                        on="DateTime", direction="backward")

    log("loading ticks...")
    ticks_by_date = {d: massive.load_continuous_ticks(d) for d in sorted(sig["Date"].unique())}
    ticks_by_date = {d: t for d, t in ticks_by_date.items() if not t.empty}

    log(f"simulating {len(sig)} signals...")
    res = simulate_trades(signals=sig, ticks_by_date=ticks_by_date,
                          bars_by_date=bars_by_date, **BASE)
    filled = res["Filled"] == True
    sf = sig.loc[filled].copy()
    sf["NetPnL"] = res.loc[filled, "NetPnL"].values
    log(f"filled: {len(sf)}")

    md = [f"# ER Open-Endpoint Study ({datetime.now():%Y-%m-%d})\n",
          "Open[T] endpoint removes signal-bar circularity. "
          "Compares Close[T] (standard) vs Open[T] (independent of signal bar).\n"]

    # ══════════════════════════════════════════════════════════════════════════
    # TABLE 1 — 0.10 slices for ER10 close vs open
    # ══════════════════════════════════════════════════════════════════════════
    edges = np.arange(0, 1.01, 0.10)

    for variant, col in [("ER10 Close[T]", "er_close_2"), ("ER10 Open[T]", "er_open_2")]:
        md.append(f"\n## {variant} — 0.10 slices\n")
        md += ["| bucket | n | % | net | exp | PF | win% |",
               "|---|---|---|---|---|---|---|"]
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            if i == len(edges) - 2:
                mask = (sf[col].fillna(-1) >= lo) & (sf[col].fillna(-1) <= hi)
            else:
                mask = (sf[col].fillna(-1) >= lo) & (sf[col].fillna(-1) < hi)
            pnl = sf.loc[mask, "NetPnL"].values
            s = stats(pnl)
            pct = s["n"] / len(sf) * 100
            md.append(f"| {lo:.1f}–{hi:.1f} | {s['n']} | {pct:.1f}% | "
                      f"${s['net']:,.0f} | ${s['exp']:.0f} | {pf_str(s['pf'])} | {s['wr']:.1f}% |")
        s = stats(sf["NetPnL"].values)
        md.append(f"| **ALL** | **{s['n']}** | 100% | **${s['net']:,.0f}** | "
                  f"**${s['exp']:.0f}** | **{pf_str(s['pf'])}** | **{s['wr']:.1f}%** |")
        md.append("")

    # ══════════════════════════════════════════════════════════════════════════
    # TABLE 2 — cumulative (>= X) side by side, all lookbacks, both endpoints
    # ══════════════════════════════════════════════════════════════════════════
    md.append("\n## Cumulative (drop below X) — Close[T] vs Open[T] by lookback\n")

    thresholds = np.arange(0, 1.01, 0.10)
    for n in spans:
        lb = span_labels[n]
        md.append(f"\n### {lb} (n={n})\n")
        md += ["| drop below | Close n | Close net | Close exp | Close PF | | Open n | Open net | Open exp | Open PF |",
               "|---|---|---|---|---|---|---|---|---|---|"]
        for thr in thresholds:
            mc = sf[f"er_close_{n}"].fillna(-1) >= thr
            sc = stats(sf.loc[mc, "NetPnL"].values)
            mo = sf[f"er_open_{n}"].fillna(-1) >= thr
            so = stats(sf.loc[mo, "NetPnL"].values)
            md.append(f"| {thr:.1f} | {sc['n']} | ${sc['net']:,.0f} | ${sc['exp']:.0f} | "
                      f"{pf_str(sc['pf'])} | | {so['n']} | ${so['net']:,.0f} | ${so['exp']:.0f} | "
                      f"{pf_str(so['pf'])} |")
        md.append("")

    # ══════════════════════════════════════════════════════════════════════════
    # TABLE 3 — yearly stability for best candidates
    # ══════════════════════════════════════════════════════════════════════════
    md.append("\n## Yearly breakdown — ER10 Open[T] >= 0.30\n")
    md += ["| year | n | net | exp | PF | win% |",
           "|---|---|---|---|---|---|"]
    yr = pd.to_datetime(sf["DateTime"]).dt.year.values
    gate = sf["er_open_2"].fillna(-1) >= 0.30
    for y in sorted(set(yr)):
        pnl = sf.loc[gate & (yr == y), "NetPnL"].values
        s = stats(pnl)
        md.append(f"| {y} | {s['n']} | ${s['net']:,.0f} | ${s['exp']:.0f} | "
                  f"{pf_str(s['pf'])} | {s['wr']:.1f}% |")
    s = stats(sf.loc[gate, "NetPnL"].values)
    md.append(f"| **ALL** | **{s['n']}** | **${s['net']:,.0f}** | **${s['exp']:.0f}** | "
              f"**{pf_str(s['pf'])}** | **{s['wr']:.1f}%** |")
    md.append("")

    # same for 0.40
    md.append("\n## Yearly breakdown — ER10 Open[T] >= 0.40\n")
    md += ["| year | n | net | exp | PF | win% |",
           "|---|---|---|---|---|---|"]
    gate40 = sf["er_open_2"].fillna(-1) >= 0.40
    for y in sorted(set(yr)):
        pnl = sf.loc[gate40 & (yr == y), "NetPnL"].values
        s = stats(pnl)
        md.append(f"| {y} | {s['n']} | ${s['net']:,.0f} | ${s['exp']:.0f} | "
                  f"{pf_str(s['pf'])} | {s['wr']:.1f}% |")
    s = stats(sf.loc[gate40, "NetPnL"].values)
    md.append(f"| **ALL** | **{s['n']}** | **${s['net']:,.0f}** | **${s['exp']:.0f}** | "
              f"**{pf_str(s['pf'])}** | **{s['wr']:.1f}%** |")
    md.append("")

    out_path = _OUT / f"er_open_endpoint_{datetime.now():%Y%m%d}.md"
    out_path.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out_path}")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n" + "\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
