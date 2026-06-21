"""er_slice_breakdown.py — ER10 bucketed into 0.10 slices + cumulative.

Shows each 0.10-wide ER bucket's performance so you can see WHERE the edge
lives, not just "above X is good." Also shows the cumulative (>= threshold)
view WITH trade counts to make the tradeoff visible.

Run: .venv/Scripts/python.exe scripts/er_slice_breakdown.py
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
    print(f"[er_sl] {datetime.now():%H:%M:%S} {m}", flush=True)


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
        "er_2": kaufman_er(df_bars["Close"], 2).values,
        "er_6": kaufman_er(df_bars["Close"], 6).values,
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

    md = [f"# ER Slice Breakdown ({datetime.now():%Y-%m-%d})\n",
          "Pinned 1.0R single-leg, no filters. All filled signals bucketed by ER value.\n"]

    # ── helper for both ER variants ───────────────────────────────────────────
    edges = np.arange(0, 1.01, 0.10)

    for er_name, er_col in [("ER10 (2-bar)", "er_2"), ("ER30 (6-bar)", "er_6")]:
        er = sf[er_col].fillna(-1).values

        md.append(f"\n## {er_name} — 0.10-wide slices\n")
        md += ["| bucket | n | % of total | net | exp | PF | win% |",
               "|---|---|---|---|---|---|---|"]
        # NaN bucket
        nan_mask = sf[er_col].isna()
        if nan_mask.sum() > 0:
            s = stats(sf.loc[nan_mask, "NetPnL"].values)
            pct = s["n"] / len(sf) * 100
            md.append(f"| NaN | {s['n']} | {pct:.1f}% | ${s['net']:,.0f} | "
                      f"${s['exp']:.0f} | {pf_str(s['pf'])} | {s['wr']:.1f}% |")

        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            if i == len(edges) - 2:
                mask = (er >= lo) & (er <= hi)
                label = f"{lo:.1f}–{hi:.1f}"
            else:
                mask = (er >= lo) & (er < hi)
                label = f"{lo:.1f}–{hi:.1f}"
            pnl = sf.loc[mask, "NetPnL"].values
            s = stats(pnl)
            pct = s["n"] / len(sf) * 100
            md.append(f"| {label} | {s['n']} | {pct:.1f}% | ${s['net']:,.0f} | "
                      f"${s['exp']:.0f} | {pf_str(s['pf'])} | {s['wr']:.1f}% |")

        # total row
        s = stats(sf["NetPnL"].values)
        md.append(f"| **ALL** | **{s['n']}** | 100% | **${s['net']:,.0f}** | "
                  f"**${s['exp']:.0f}** | **{pf_str(s['pf'])}** | **{s['wr']:.1f}%** |")
        md.append("")

        # cumulative (>= threshold) table
        md.append(f"\n## {er_name} — cumulative (>= threshold)\n")
        md += ["| >= threshold | n | dropped | net | exp | PF | win% | marginal exp |",
               "|---|---|---|---|---|---|---|---|"]

        thresholds = np.arange(0, 0.81, 0.05)
        prev_n = len(sf)
        for thr in thresholds:
            mask = sf[er_col].fillna(-1) >= thr
            pnl = sf.loc[mask, "NetPnL"].values
            s = stats(pnl)
            dropped = len(sf) - s["n"]
            # marginal: what did the trades between this threshold and the previous one contribute?
            if thr == 0:
                marg = "—"
            else:
                prev_mask = (sf[er_col].fillna(-1) >= (thr - 0.05)) & (sf[er_col].fillna(-1) < thr)
                marg_pnl = sf.loc[prev_mask, "NetPnL"].values
                ms = stats(marg_pnl)
                marg = f"${ms['exp']:.0f} ({ms['n']})" if ms["n"] > 0 else "—"
            md.append(f"| {thr:.2f} | {s['n']} | {dropped} | ${s['net']:,.0f} | "
                      f"${s['exp']:.0f} | {pf_str(s['pf'])} | {s['wr']:.1f}% | {marg} |")
        md.append("")

    out_path = _OUT / f"er_slice_breakdown_{datetime.now():%Y%m%d}.md"
    out_path.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out_path}")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n" + "\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
