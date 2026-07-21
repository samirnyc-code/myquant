"""revft_continuation_gate.py — pre-registered confirmatory test of the RevFT
continuation tilt discovered in revft_vwap_slices.py.

PRE-REGISTERED GATE (fixed BEFORE this run, from the slice study):
    continuation = (Long  AND VWAP_dev > +0.5σ)   # buy on the far side of VWAP
                OR (Short AND VWAP_dev < -0.5σ)   # sell on the far side of VWAP
The thesis (inverted from the original mean-reversion premise): RevFT is a WITH-TREND
continuation signal whose edge GROWS with a wider target. So we judge in R at 1/2/3R.

Reported alongside:
  • REVERSION complement: (Long & dev<-0.5) OR (Short & dev>+0.5)  — should stay red.
  • NEUTRAL middle: |dev| <= 0.5                                    — the inert band.
  • BASELINE: all filled.
Full-sample CI (must exclude zero in R to be a finding) + year-by-year stability.

Honesty: the +0.5σ threshold was chosen in-sample on this same 5yr set; this is a
selectivity confirmation, NOT out-of-sample. A pass here earns a true OOS test, not belief.

Run (MAIN venv): C:/Users/Thomas-Code/Projects/myquant/.venv/Scripts/python.exe scripts/revft_continuation_gate.py
Out: docs/living/revft_continuation_gate_<date>.md
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
THR = 0.5   # σ threshold, pre-registered from the slice study


def log(m: str) -> None:
    print(f"[contgate] {datetime.now():%H:%M:%S} {m}", flush=True)


def stats(pnl: np.ndarray, rmult: np.ndarray) -> dict:
    n = len(pnl)
    if n == 0:
        return dict(n=0, net=0, exp=0, pf=0, wr=0, expR=np.nan, ci=np.nan, rci=np.nan)
    net = float(pnl.sum())
    gw = float(pnl[pnl > 0].sum()) if (pnl > 0).any() else 0.0
    gl = float(abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else 0.0
    pf = gw / gl if gl > 0 else float("inf")
    wr = float((pnl > 0).sum() / n * 100)
    exp = net / n
    ci = float(1.96 * pnl.std(ddof=1) / np.sqrt(n)) if n > 1 else np.nan
    rr = rmult[np.isfinite(rmult)]
    expR = float(rr.mean()) if len(rr) else np.nan
    rci = float(1.96 * rr.std(ddof=1) / np.sqrt(len(rr))) if len(rr) > 1 else np.nan
    return dict(n=n, net=net, exp=exp, pf=pf, wr=wr, expR=expR, ci=ci, rci=rci)


HDR = "| group | n | net $ | exp $ | exp R | ±R CI | R-95% interval | PF | win% |"
SEP = "|---|---|---|---|---|---|---|---|---|"


def row(label: str, pnl: np.ndarray, rmult: np.ndarray) -> str:
    s = stats(pnl, rmult)
    if s["n"] == 0:
        return f"| {label} | 0 | — | — | — | — | — | — | — |"
    pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    er = "—" if np.isnan(s["expR"]) else f"{s['expR']:+.3f}"
    rci = "—" if np.isnan(s["rci"]) else f"±{s['rci']:.3f}"
    if not np.isnan(s["expR"]) and not np.isnan(s["rci"]):
        lo, hi = s["expR"] - s["rci"], s["expR"] + s["rci"]
        excl = "" if (lo > 0 or hi < 0) else "  (∋0)"
        interval = f"[{lo:+.3f}, {hi:+.3f}]{excl}"
    else:
        interval = "—"
    return (f"| {label} | {s['n']} | ${s['net']:,.0f} | ${s['exp']:+.0f} | "
            f"{er} | {rci} | {interval} | {pf} | {s['wr']:.1f}% |")


def main() -> int:
    log("loading + tagging...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}
    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)
    tagged = tag_signals(sig, bars).sort_values("DateTime").reset_index(drop=True)

    log("loading ticks...")
    dates = sorted(pd.to_datetime(tagged["Date"]).dt.date.unique()) \
        if "Date" in tagged.columns else \
        sorted(tagged["DateTime"].dt.date.unique())
    ticks_by_date = {d: massive.load_continuous_ticks(d) for d in dates}
    ticks_by_date = {d: t for d, t in ticks_by_date.items() if not t.empty}

    md = [f"# RevFT continuation gate — pre-registered confirmatory test ({datetime.now():%Y-%m-%d})\n",
          "**Pre-registered gate** (fixed before this run, from the 0.5σ slice study): "
          "`continuation = (Long & VWAP_dev > +0.5σ) OR (Short & VWAP_dev < -0.5σ)` — RevFT "
          "fired WITH the move, on the far side of developing VWAP. Thesis: with-trend, edge "
          "grows with target → judged in R at 1R/2R/3R.\n",
          "- **REVERSION** = the mean-reversion complement (should stay red). "
          "**NEUTRAL** = `|dev| ≤ 0.5` (inert). **BASELINE** = all filled.\n",
          "- A group is a *finding* only if its R 95%-interval EXCLUDES zero AND it holds "
          "year-by-year. `(∋0)` flags an interval that still contains zero.\n",
          "- **Honesty:** the +0.5σ threshold was chosen in-sample on this same 5yr set. "
          "This is selectivity confirmation, NOT out-of-sample. A pass earns a true OOS run.\n"]

    best_by_year = {}
    for tr in TARGETS:
        log(f"simulating at {tr:.0f}R...")
        res = simulate_trades(signals=tagged, ticks_by_date=ticks_by_date,
                              bars_by_date=bars_by_date, target_r=tr,
                              **BASE).reset_index(drop=True)
        filled = (res["Filled"] == True).values
        f = tagged.loc[filled].reset_index(drop=True)
        rf = res.loc[filled].reset_index(drop=True)
        pnl = rf["NetPnL"].values
        risk = rf["RiskDollar"].values if "RiskDollar" in rf.columns else None
        rmult = (rf["NetPnL"].values / risk) if risk is not None else np.full(len(rf), np.nan)

        isL = f["Direction"].str.lower().str.startswith("l").values
        dev = f["VWAP_dev"].values
        cont = ((isL & (dev > THR)) | (~isL & (dev < -THR)))
        revn = ((isL & (dev < -THR)) | (~isL & (dev > THR)))
        neut = np.abs(dev) <= THR

        md.append(f"\n# Target {tr:.0f}R\n")
        md += [HDR, SEP]
        md.append(row("BASELINE (all)", pnl, rmult))
        md.append(row("CONTINUATION gate", pnl[cont], rmult[cont]))
        md.append(row("  · long leg (dev>+0.5)", pnl[cont & isL], rmult[cont & isL]))
        md.append(row("  · short leg (dev<-0.5)", pnl[cont & ~isL], rmult[cont & ~isL]))
        md.append(row("REVERSION complement", pnl[revn], rmult[revn]))
        md.append(row("NEUTRAL (|dev|<=0.5)", pnl[neut], rmult[neut]))
        md.append("")
        best_by_year[tr] = (f, pnl, rmult, cont)

    # ── year-by-year for the continuation gate at each target ──────────────────
    md.append("\n# Year-by-year — CONTINUATION gate\n")
    for tr in TARGETS:
        f, pnl, rmult, cont = best_by_year[tr]
        yr = pd.to_datetime(f["DateTime"]).dt.year.values
        md.append(f"\n### {tr:.0f}R\n")
        md += [HDR, SEP]
        for y in sorted(np.unique(yr)):
            m = cont & (yr == y)
            md.append(row(str(y), pnl[m], rmult[m]))
        md.append("")

    out = _OUT / f"revft_continuation_gate_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
