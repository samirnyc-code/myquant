"""er_lookback_study.py — is 30min the right ER lookback? Test 5/10/15/30min.

Three questions:
  1. Early-bar penalty: bars 1-5 use prior-session ER (cross-session contamination).
     Are signals in those bars statistically better or worse?
  2. Session-reset ER: compute ER that resets each session (NaN for bars with
     insufficient same-session history). Does it filter better?
  3. Lookback sweep: test ER gate (>=0.30) at 1/2/3/6 bars (5/10/15/30min),
     both cross-session and session-reset variants. Which lookback + variant
     produces the best filter?

Population: ba_signals_mc.parquet, pinned 1.0R single-leg (BASE).

Run: .venv/Scripts/python.exe scripts/er_lookback_study.py
Out: docs/living/er_lookback_study_<date>.md
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
from data_loader import bar_num_from_dt                              # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"

BASE = dict(entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5,
            contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
            ratchet_r=0.0, pb_round="nearest", target_r=1.0,
            multileg=False, threeleg=False, overrides=None)
CHOP_MIN = 0.30
SPANS = [1, 2, 3, 6]          # bars = 5min / 10min / 15min / 30min
SPAN_LABELS = {1: "5min", 2: "10min", 3: "15min", 6: "30min"}


def log(m: str) -> None:
    print(f"[er_lb] {datetime.now():%H:%M:%S} {m}", flush=True)


# ── ER computation ────────────────────────────────────────────────────────────

def kaufman_er(close: pd.Series, n: int) -> pd.Series:
    """Standard (cross-session) Kaufman ER."""
    step = close.diff().abs()
    direction = (close - close.shift(n)).abs()
    volatility = step.rolling(n).sum().replace(0, np.nan)
    return direction / volatility


def kaufman_er_session_reset(bars: pd.DataFrame, n: int) -> pd.Series:
    """Session-reset ER: NaN for bars with < n same-session predecessors."""
    df = bars.sort_values("DateTime").reset_index(drop=True)
    day = df["DateTime"].dt.normalize()
    bar_in_session = df.groupby(day).cumcount()  # 0-indexed

    er = kaufman_er(df["Close"], n)
    # zero out bars that straddle a session boundary
    er = er.where(bar_in_session >= n)
    return er


def compute_all_ers(bars: pd.DataFrame) -> pd.DataFrame:
    """Return a DataFrame aligned to bars with ER columns for all span×variant combos."""
    df = bars.sort_values("DateTime").reset_index(drop=True)
    out = {"DateTime": df["DateTime"]}
    for n in SPANS:
        out[f"er_cross_{n}"] = kaufman_er(df["Close"], n).values
        out[f"er_reset_{n}"] = kaufman_er_session_reset(df, n).values
    return pd.DataFrame(out)


# ── stats helper ──────────────────────────────────────────────────────────────

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


def row(label: str, pnl: np.ndarray) -> str:
    s = stats(pnl)
    if s["n"] == 0:
        return f"| {label} | 0 | — | — | — | — |"
    pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    return f"| {label} | {s['n']} | ${s['net']:,.0f} | ${s['exp']:.0f} | {pf} | {s['wr']:.1f}% |"


HDR = "| slice | n | net | exp | PF | win% |"
SEP = "|---|---|---|---|---|---|"


def main() -> int:
    log("loading data...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}

    # compute bar number for each signal
    sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)

    # compute all ER variants and merge onto signals
    log("computing ER variants (4 spans × 2 variants)...")
    er_df = compute_all_ers(bars)
    sig["DateTime"] = pd.to_datetime(sig["DateTime"]).dt.as_unit("ns")
    er_df["DateTime"] = pd.to_datetime(er_df["DateTime"]).dt.as_unit("ns")
    sig = pd.merge_asof(
        sig.sort_values("DateTime"),
        er_df.sort_values("DateTime"),
        on="DateTime", direction="backward",
    )

    # load ticks + simulate ALL signals (no filter — we'll slice post-hoc)
    log("loading ticks...")
    ticks_by_date = {d: massive.load_continuous_ticks(d) for d in sorted(sig["Date"].unique())}
    ticks_by_date = {d: t for d, t in ticks_by_date.items() if not t.empty}

    log(f"simulating {len(sig)} signals (pinned 1.0R, single-leg)...")
    res = simulate_trades(signals=sig, ticks_by_date=ticks_by_date,
                          bars_by_date=bars_by_date, **BASE)
    filled = res["Filled"] == True
    pnl_all = res.loc[filled, "NetPnL"].values
    sig_filled = sig.loc[filled].copy()
    res_filled = res.loc[filled].copy()
    log(f"filled: {len(res_filled)}")

    md = [f"# ER Lookback Study ({datetime.now():%Y-%m-%d})\n"]

    # ══════════════════════════════════════════════════════════════════════════
    # PART 1 — early-bar performance (using the CURRENT ER_intra_6 cross-session)
    # ══════════════════════════════════════════════════════════════════════════
    md.append("\n## 1. Early-bar performance (current ER30 cross-session)\n")
    md.append("Bars 1-5 (first 25 min) use prior-session ER values — cross-session contamination.\n\n")

    early = sig_filled["BarNum"] <= 5
    er30 = sig_filled["er_cross_6"] >= CHOP_MIN

    md.append("### All signals (no ER filter)\n")
    md += [HDR, SEP,
           row("ALL", pnl_all),
           row("bars 1-5", res_filled.loc[early, "NetPnL"].values),
           row("bars 6+", res_filled.loc[~early, "NetPnL"].values),
           ""]

    md.append("\n### With ER30 >= 0.30 gate\n")
    md += [HDR, SEP,
           row("ER30 all", res_filled.loc[er30, "NetPnL"].values),
           row("ER30 bars 1-5", res_filled.loc[er30 & early, "NetPnL"].values),
           row("ER30 bars 6+", res_filled.loc[er30 & (~early), "NetPnL"].values),
           ""]

    # per-bar breakdown for bars 1-10
    md.append("\n### Per-bar expectancy (bars 1-12, no ER filter)\n")
    md += [HDR, SEP]
    for b in range(1, 13):
        mask = sig_filled["BarNum"] == b
        md.append(row(f"bar {b}", res_filled.loc[mask, "NetPnL"].values))
    md.append("")

    md.append("\n### Per-bar expectancy (bars 1-12, ER30 cross >= 0.30)\n")
    md += [HDR, SEP]
    for b in range(1, 13):
        mask = (sig_filled["BarNum"] == b) & er30
        md.append(row(f"bar {b}", res_filled.loc[mask, "NetPnL"].values))
    md.append("")

    # ══════════════════════════════════════════════════════════════════════════
    # PART 2 — cross-session vs session-reset at each lookback
    # ══════════════════════════════════════════════════════════════════════════
    md.append("\n## 2. ER >= 0.30 gate: cross-session vs session-reset, by lookback\n")
    md.append("Session-reset: NaN (and therefore DROPPED) for bars with < N same-session bars.\n\n")

    md += ["| lookback | variant | passed | dropped | n_filled | net | exp | PF | win% |",
           "|---|---|---|---|---|---|---|---|---|"]

    for n in SPANS:
        lb = SPAN_LABELS[n]
        for variant in ("cross", "reset"):
            col = f"er_{variant}_{n}"
            gate = sig_filled[col] >= CHOP_MIN
            nan_drop = sig_filled[col].isna()
            passed = gate.sum()
            dropped = (~gate & ~nan_drop).sum() + nan_drop.sum()
            pnl = res_filled.loc[gate, "NetPnL"].values
            s = stats(pnl)
            pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
            md.append(f"| {lb} | {variant} | {passed} | {dropped} | {s['n']} | "
                      f"${s['net']:,.0f} | ${s['exp']:.0f} | {pf} | {s['wr']:.1f}% |")
    md.append("")

    # ══════════════════════════════════════════════════════════════════════════
    # PART 3 — what does session-reset do to early bars specifically?
    # ══════════════════════════════════════════════════════════════════════════
    md.append("\n## 3. Early bars: cross vs session-reset (30min / 6-bar lookback)\n")
    md.append("Session-reset drops bars 1-5 entirely (NaN). Cross keeps them with stale ER.\n\n")

    er_cross_gate = sig_filled["er_cross_6"] >= CHOP_MIN
    er_reset_gate = sig_filled["er_reset_6"] >= CHOP_MIN

    md += [HDR, SEP,
           row("cross ER30, bars 1-5", res_filled.loc[er_cross_gate & early, "NetPnL"].values),
           row("cross ER30, bars 6+", res_filled.loc[er_cross_gate & (~early), "NetPnL"].values),
           row("reset ER30, bars 6+", res_filled.loc[er_reset_gate & (~early), "NetPnL"].values),
           ""]

    md.append("(Session-reset has no bars 1-5 by definition for span=6.)\n")

    # ══════════════════════════════════════════════════════════════════════════
    # PART 4 — shorter lookbacks: what do they do to early bars?
    # ══════════════════════════════════════════════════════════════════════════
    md.append("\n## 4. Shorter lookbacks — session-reset keeps more early bars\n")
    md.append("With span=1 (5min), session-reset only drops bar 1. Span=2 drops bars 1-2, etc.\n\n")

    md += ["| lookback | variant | bars 1-5 passed | bars 1-5 exp | bars 6+ passed | bars 6+ exp | total net |",
           "|---|---|---|---|---|---|---|"]

    for n in SPANS:
        lb = SPAN_LABELS[n]
        for variant in ("cross", "reset"):
            col = f"er_{variant}_{n}"
            gate = sig_filled[col] >= CHOP_MIN
            early_gate = gate & early
            late_gate = gate & (~early)
            e_pnl = res_filled.loc[early_gate, "NetPnL"].values
            l_pnl = res_filled.loc[late_gate, "NetPnL"].values
            e_s = stats(e_pnl)
            l_s = stats(l_pnl)
            total = e_s["net"] + l_s["net"]
            md.append(f"| {lb} | {variant} | {e_s['n']} | ${e_s['exp']:.0f} | "
                      f"{l_s['n']} | ${l_s['exp']:.0f} | ${total:,.0f} |")
    md.append("")

    # ══════════════════════════════════════════════════════════════════════════
    # PART 5 — ER threshold sensitivity at each lookback (cross only, quick)
    # ══════════════════════════════════════════════════════════════════════════
    md.append("\n## 5. Threshold sensitivity by lookback (cross-session)\n")
    md.append("Does 0.30 remain the right threshold for shorter lookbacks?\n\n")

    thresholds = [0.20, 0.25, 0.30, 0.35, 0.40, 0.50]
    hdr5 = "| threshold | " + " | ".join(f"{SPAN_LABELS[n]} exp (n)" for n in SPANS) + " |"
    sep5 = "|---" * (len(SPANS) + 1) + "|"
    md += [hdr5, sep5]

    for thr in thresholds:
        cells = []
        for n in SPANS:
            col = f"er_cross_{n}"
            gate = sig_filled[col] >= thr
            pnl = res_filled.loc[gate, "NetPnL"].values
            s = stats(pnl)
            cells.append(f"${s['exp']:.0f} ({s['n']})")
        md.append(f"| {thr:.2f} | " + " | ".join(cells) + " |")
    md.append("")

    # ══════════════════════════════════════════════════════════════════════════
    # PART 6 — yearly stability for the top candidates
    # ══════════════════════════════════════════════════════════════════════════
    md.append("\n## 6. Yearly breakdown — top candidates\n")
    md.append("Checking regime stability across years for each lookback at ER >= 0.30.\n\n")

    sig_filled_year = pd.to_datetime(sig_filled["DateTime"]).dt.year.values
    years = sorted(set(sig_filled_year))

    for n in SPANS:
        lb = SPAN_LABELS[n]
        md.append(f"\n### {lb} cross-session ER >= 0.30\n")
        md += [HDR, SEP]
        col = f"er_cross_{n}"
        gate = sig_filled[col] >= CHOP_MIN
        for y in years:
            ymask = gate & (sig_filled_year == y)
            md.append(row(str(y), res_filled.loc[ymask, "NetPnL"].values))
        md.append(row("ALL", res_filled.loc[gate, "NetPnL"].values))
        md.append("")

    # write
    out_path = _OUT / f"er_lookback_study_{datetime.now():%Y%m%d}.md"
    out_path.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
