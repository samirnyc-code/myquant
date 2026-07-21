"""revft_vwap_slices.py — RevFT vs VWAP deviation, done carefully (the recheck).

User pushback on revft_vwap_va_location.py: "hard to believe reversals don't work
better when VWAP is extended — are you sure, and in 0.5σ slices?" Two ways the first
pass could mislead, both fixed here:

  1) SIGN — drop the combined directional `S`. Slice on RAW `VWAP_dev` =
     (Close-VWAP)/σ, LONG-only and SHORT-only separately. No sign transform to get
     wrong. For a LONG, "fade an extension BELOW VWAP" = VWAP_dev < 0; for a SHORT,
     fade an extension ABOVE VWAP = VWAP_dev > 0. Read it straight off the table.

  2) EXIT — at 1:1 a mean-reversion fade fired 2σ from VWAP has its winner clipped at
     1R long before price reverts. So slice at target_r ∈ {1, 2, 3}. If the extended
     buckets improve at 2-3R, it's an exit problem, not a location dud.

0.5σ slices so the gradient (and the sample thinning past ~2σ) are both visible.
Includes a direction/sign sanity block up top so the convention is auditable.

Run (MAIN venv): C:/Users/Thomas-Code/Projects/myquant/.venv/Scripts/python.exe scripts/revft_vwap_slices.py
Out: docs/living/revft_vwap_slices_<date>.md
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_MAIN = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import massive                                                       # noqa: E402
massive._TICKS_CONT_DIR = _MAIN / "data" / "ticks_continuous"        # noqa: E402
from simulation_engine import simulate_trades                        # noqa: E402
from indicators import tag_signals                                   # noqa: E402
from data_loader import bar_num_from_dt                              # noqa: E402

_SIGNALS = _MAIN / "saved_signals" / "ba_signals_revft.parquet"
_BARS    = _MAIN / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"

BASE = dict(entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5,
            contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
            ratchet_r=0.0, pb_round="nearest",
            multileg=False, threeleg=False, overrides=None)

TARGETS = [1.0, 2.0, 3.0]

# RAW VWAP_dev slice edges (σ). 0.5σ slices, -3.5..+3.5.
EDGES = [-np.inf, -3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.0,
         0.5, 1.0, 1.5, 2.0, 2.5, 3.0, np.inf]


def slice_labels(edges):
    labs = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        lo_s = "-∞" if lo == -np.inf else f"{lo:+.1f}"
        hi_s = "+∞" if hi == np.inf else f"{hi:+.1f}"
        labs.append(f"{lo_s}..{hi_s}")
    return labs


LABELS = slice_labels(EDGES)


def log(m: str) -> None:
    print(f"[vwslice] {datetime.now():%H:%M:%S} {m}", flush=True)


def stats(pnl: np.ndarray, rmult: np.ndarray | None = None) -> dict:
    n = len(pnl)
    if n == 0:
        return dict(n=0, net=0, exp=0, pf=0, wr=0, expR=np.nan, ci=np.nan)
    net = float(pnl.sum())
    gw = float(pnl[pnl > 0].sum()) if (pnl > 0).any() else 0.0
    gl = float(abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else 0.0
    pf = gw / gl if gl > 0 else float("inf")
    wr = float((pnl > 0).sum() / n * 100)
    exp = net / n
    ci = float(1.96 * pnl.std(ddof=1) / np.sqrt(n)) if n > 1 else np.nan
    expR = float(np.nanmean(rmult)) if rmult is not None and len(rmult) else np.nan
    return dict(n=n, net=net, exp=exp, pf=pf, wr=wr, expR=expR, ci=ci)


HDR = "| VWAP_dev (σ) | n | net $ | exp $ | ±95%CI | exp R | ±R CI | PF | win% |"
SEP = "|---|---|---|---|---|---|---|---|---|"


def row(label: str, pnl: np.ndarray, rmult: np.ndarray) -> str:
    s = stats(pnl, rmult)
    if s["n"] == 0:
        return f"| {label} | 0 | — | — | — | — | — | — | — |"
    pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    ci = "—" if np.isnan(s["ci"]) else f"±{s['ci']:.0f}"
    er = "—" if np.isnan(s["expR"]) else f"{s['expR']:+.3f}"
    rci = "—"
    if s["n"] > 1 and rmult is not None and np.isfinite(rmult).any():
        rr = rmult[np.isfinite(rmult)]
        rci = f"±{1.96 * rr.std(ddof=1) / np.sqrt(len(rr)):.3f}"
    return (f"| {label} | {s['n']} | ${s['net']:,.0f} | ${s['exp']:+.0f} | {ci} | "
            f"{er} | {rci} | {pf} | {s['wr']:.1f}% |")


def slice_table(dev: pd.Series, pnl: pd.Series, rmult: pd.Series,
                mask: pd.Series) -> list[str]:
    md = [HDR, SEP]
    d = dev[mask]
    p = pnl[mask].values
    r = rmult[mask].values
    md.append(row("ALL", p, r))
    for lo, hi, lab in zip(EDGES[:-1], EDGES[1:], LABELS):
        b = ((d >= lo) & (d < hi)).values
        md.append(row(lab, p[b], r[b]))
    md.append("")
    return md


def simulate_at(tagged, ticks_by_date, bars_by_date, target_r):
    res = simulate_trades(signals=tagged, ticks_by_date=ticks_by_date,
                          bars_by_date=bars_by_date, target_r=target_r,
                          **BASE).reset_index(drop=True)
    filled = res["Filled"] == True
    rf = res.loc[filled].reset_index(drop=True)
    risk = rf["RiskDollar"] if "RiskDollar" in rf.columns else None
    rmult = (rf["NetPnL"] / risk) if risk is not None else pd.Series(np.nan, index=rf.index)
    return filled.values, rf["NetPnL"], rmult


def main() -> int:
    log("loading signals + bars...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}
    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)

    log("tagging signals (causal VWAP_dev)...")
    tagged = tag_signals(sig, bars).sort_values("DateTime").reset_index(drop=True)
    isL_all = tagged["Direction"].str.lower().str.startswith("l")

    log("loading ticks...")
    dates = sorted(pd.to_datetime(tagged["Date"]).dt.date.unique()) \
        if "Date" in tagged.columns else \
        sorted(tagged["DateTime"].dt.date.unique())
    ticks_by_date = {d: massive.load_continuous_ticks(d) for d in dates}
    ticks_by_date = {d: t for d, t in ticks_by_date.items() if not t.empty}

    md = [f"# RevFT vs VWAP deviation — 0.5σ slices, recheck ({datetime.now():%Y-%m-%d})\n",
          "Raw `VWAP_dev` = (Close − VWAP)/σ at the signal bar (causal). **No directional "
          "transform** — long-only and short-only tables read straight. For a LONG a "
          "mean-reversion fade is BELOW VWAP (VWAP_dev < 0); for a SHORT it is ABOVE "
          "(VWAP_dev > 0). Pinned single-leg, real tick engine, sliced at 1R / 2R / 3R "
          "to see whether a tight exit was hiding a reversion edge.\n"]

    # ── sign / direction sanity block ─────────────────────────────────────────
    dvals = tagged["VWAP_dev"]
    md.append("## Sign / direction sanity check\n")
    md.append(f"- `Direction` values: {sorted(tagged['Direction'].dropna().unique().tolist())}\n")
    md.append(f"- VWAP_dev percentiles (all signals): "
              + ", ".join(f"p{q}={np.nanpercentile(dvals, q):+.2f}"
                          for q in (1, 5, 25, 50, 75, 95, 99)) + "\n")
    md.append(f"- LONG signals: median VWAP_dev = {np.nanmedian(dvals[isL_all]):+.2f}, "
              f"% below VWAP (dev<0) = {100*(dvals[isL_all] < 0).mean():.1f}%\n")
    md.append(f"- SHORT signals: median VWAP_dev = {np.nanmedian(dvals[~isL_all]):+.2f}, "
              f"% above VWAP (dev>0) = {100*(dvals[~isL_all] > 0).mean():.1f}%\n")
    md.append("- _Reversal logic predicts longs skew below VWAP and shorts above. If the "
              "skew is the other way, RevFT fires WITH the move (pullback-in-trend), not "
              "against it — itself the answer to 'why don't extended fades work'._\n")

    # ── slices at each target R ───────────────────────────────────────────────
    for tr in TARGETS:
        log(f"simulating at {tr:.0f}R...")
        filled, pnl, rmult = simulate_at(tagged, ticks_by_date, bars_by_date, tr)
        f = tagged.loc[filled].reset_index(drop=True)
        dev = f["VWAP_dev"].reset_index(drop=True)
        isL = f["Direction"].str.lower().str.startswith("l").reset_index(drop=True)
        log(f"  filled: {int(filled.sum())}")

        md.append(f"\n# Target {tr:.0f}R\n")
        md.append(f"**Baseline (all filled, {tr:.0f}R):** {row('ALL', pnl.values, rmult.values)}\n")
        md.append("### LONG only — mean-reversion fade is the LEFT (VWAP_dev < 0) cells\n")
        md += slice_table(dev, pnl, rmult, isL)
        md.append("### SHORT only — mean-reversion fade is the RIGHT (VWAP_dev > 0) cells\n")
        md += slice_table(dev, pnl, rmult, ~isL)

    out = _OUT / f"revft_vwap_slices_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
