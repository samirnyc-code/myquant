"""keystone_audit.py — try to BREAK Keystone (look-ahead + robustness), per S39.

Guilty until proven innocent. Keystone = origin (StopPrice/MCX) within 0.10 ADR inside
the same-side IB edge (OR60), 2.0R single-leg. Kill attempts:

  1. OR60 causality — verified in code (indicators.py:263-274): developing running range
     for the first hour, frozen after bar 12. Causal. No as-of-merge entry-bar leak (OR60
     via the S34-fixed chokepoint; StopPrice is a direct CSV column). Reported, not re-tested.
  2. SESSION-TIMING SPLIT — the decisive look-ahead test. Signals AFTER the first hour
     (BarNum > 12) have a fully-formed, unambiguously-PAST OR60. If the edge holds there,
     OR60 cannot be the source of any leak. If the edge lives only in the early (developing
     OR60) window, that is a red flag.
  3. COST REALISM at 2R — we only stress-tested costs at 1R. Bump slip 1/0 -> 2/1 -> 3/2.
  4. StopPrice SANITY — is the origin a plausible PAST extreme (correct side, at/below the
     developing low for longs / at/above developing high for shorts)?

Out: docs/living/keystone_audit_<date>.md
"""
from __future__ import annotations

import sys, gc
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                                                       # noqa: E402
from simulation_engine import simulate_trades                        # noqa: E402
from indicators import tag_signals                                   # noqa: E402
from data_loader import bar_num_from_dt                              # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"
EDGE_MAX = 0.10
BASE = dict(stop_offset=1, tick_value=12.5, contracts=1, contracts_t1=1, contracts_t2=1,
            commission=4.36, ratchet_r=0.0, pb_round="nearest", target_r=2.0,
            multileg=False, threeleg=False, overrides=None)
SLIPS = [("1/0 base", 1, 0), ("2/1 conservative", 2, 1), ("3/2 brutal", 3, 2)]


def log(m): print(f"[aud] {datetime.now():%H:%M:%S} {m}", flush=True)


def stat(pnl, r):
    n = len(pnl)
    if n == 0:
        return dict(n=0, exp=0, expR=np.nan, pf=0, win=0, ciR=np.nan, net=0)
    net = float(pnl.sum())
    gw = float(pnl[pnl > 0].sum()) if (pnl > 0).any() else 0.0
    gl = float(abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else 0.0
    return dict(n=n, net=net, exp=net / n, expR=float(np.nanmean(r)),
                pf=gw / gl if gl > 0 else float("inf"),
                win=float((pnl > 0).mean() * 100),
                ciR=float(1.96 * np.nanstd(r, ddof=1) / np.sqrt(n)) if n > 1 else np.nan)


def line(lbl, pnl, r):
    s = stat(pnl, r)
    if s["n"] == 0:
        return f"| {lbl} | 0 | — | — | — | — |"
    pf = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    cr = "—" if np.isnan(s["ciR"]) else f"±{s['ciR']:.3f}"
    return f"| {lbl} | {s['n']} | ${s['net']:,.0f} | {s['expR']:+.3f} | {cr} | {pf} |"


def main() -> int:
    log("tag + gate...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bbd = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)
    tg = tag_signals(sig, bars).sort_values("DateTime").reset_index(drop=True)
    adr = tg["prior_ATR"].replace(0, np.nan).to_numpy()
    isL = tg["Direction"].str.lower().str.startswith("l").values
    origin = tg["StopPrice"].to_numpy()
    d_edge = np.where(isL, origin - tg["OR60_Low"].to_numpy(),
                            tg["OR60_High"].to_numpy() - origin) / adr
    G = (d_edge >= 0) & (d_edge <= EDGE_MAX)
    gtg = tg.loc[G].reset_index(drop=True)
    gtg["_date"] = pd.to_datetime(gtg["DateTime"]).dt.date

    # StopPrice sanity (causal: origin should be a PAST extreme on the correct side)
    gL = gtg["Direction"].str.lower().str.startswith("l").values
    sp_correct = np.where(gL, gtg["StopPrice"] < gtg["SignalPrice"],
                              gtg["StopPrice"] > gtg["SignalPrice"]).mean() * 100
    past_ext = np.where(gL, gtg["StopPrice"] <= gtg["dev_Low"] + 1e-9,
                            gtg["StopPrice"] >= gtg["dev_High"] - 1e-9).mean() * 100

    log("ticks + sims (3 slip levels)...")
    acc = {s[0]: {"pnl": [], "r": []} for s in SLIPS}
    base_extra = []
    for ci, chunk in enumerate(np.array_split(np.array(sorted(gtg["_date"].unique()), object), 4)):
        sub = gtg[gtg["_date"].isin(set(chunk.tolist()))].reset_index(drop=True)
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        for lbl, es, xs in SLIPS:
            res = simulate_trades(signals=sub, ticks_by_date=tbd, bars_by_date=bbd,
                                  entry_slip=es, exit_slip=xs, **BASE).reset_index(drop=True)
            fl = (res["Filled"] == True).values
            rf = res.loc[fl]
            pnl = rf["NetPnL"].values
            r = pnl / rf["RiskDollar"].replace(0, np.nan).values
            acc[lbl]["pnl"].append(pnl); acc[lbl]["r"].append(r)
            if (es, xs) == (1, 0):
                base_extra.append(pd.DataFrame({
                    "pnl": pnl, "r": r,
                    "BarNum": sub.loc[fl, "BarNum"].values,
                    "isL": sub.loc[fl, "Direction"].str.lower().str.startswith("l").values}))
        del tbd; gc.collect()
        log(f"  chunk {ci+1}/4")

    be = pd.concat(base_extra, ignore_index=True)
    early = be["BarNum"] <= 12
    md = [f"# Keystone — Look-ahead & Robustness Audit ({datetime.now():%Y-%m-%d})\n",
          "Try to BREAK it (guilty until proven innocent). Single-leg 2.0R, gated book.\n",
          "\n## 1. OR60 causality — VERIFIED IN CODE\n",
          "`indicators.py:263-274`: OR60 is the developing running 60-min range for the first "
          "hour (`bar_num < 12`, only bars seen so far) and frozen after. Causal. OR60 reaches "
          "signals via the S34-fixed causal merge; StopPrice is a direct CSV column. No as-of "
          "merge can land on the entry bar → the ER10 leak class is absent. PASS.\n",
          "\n## 2. Session-timing split (the decisive look-ahead test)\n",
          f"_Early (BarNum<=12, OR60 still developing): {int(early.sum())} trades. "
          f"After first hour (BarNum>12, OR60 frozen & unambiguously PAST): {int((~early).sum())}._\n",
          "| subset | n | net $ | exp R | ±CI R | PF |", "|---|---|---|---|---|---|",
          line("ALL gated", be["pnl"].values, be["r"].values),
          line("AFTER first hour (clean OR60)", be.loc[~early, "pnl"].values, be.loc[~early, "r"].values),
          line("DURING first hour (developing)", be.loc[early, "pnl"].values, be.loc[early, "r"].values),
          "\n_If the AFTER-first-hour row holds the edge, OR60 timing is not the source._\n",
          "\n## 3. Cost realism at 2R\n",
          "| slip | n | net $ | exp R | ±CI R | PF |", "|---|---|---|---|---|---|"]
    for lbl, _, _ in SLIPS:
        md.append(line(f"gate @ {lbl}", np.concatenate(acc[lbl]["pnl"]), np.concatenate(acc[lbl]["r"])))
    md += ["\n## 4. StopPrice sanity (causal past-extreme check)\n",
           f"- StopPrice on the correct side of SignalPrice (stop below for longs / above for "
           f"shorts): **{sp_correct:.1f}%**\n",
           f"- StopPrice at/beyond the developing extreme (origin is a PAST swing low/high, not "
           f"inside the formed range): **{past_ext:.1f}%**\n",
           "_Caveat: StopPrice comes from the NT MC indicator export; its internal causality "
           "can't be audited from here. But it's the same stop every MCSignal strategy uses, "
           "and these checks confirm it behaves like a past extreme._\n"]

    out = _OUT / f"keystone_audit_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
