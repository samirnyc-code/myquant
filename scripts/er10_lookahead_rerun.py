"""er10_lookahead_rerun.py — headless reproduction of the ER10 merge_asof look-ahead.

User request (S38): "go back and rerun the data WITH the bug, 1 run, headless, no
code changes." This script makes ZERO changes to production code. It imports the
bug-reproduction helpers that already ship in er_lookahead_tab.py
(`_er10_both_modes`, `_apply_gate`) — those build BOTH the pre-fix look-ahead ER10
(raw backward merge_asof → entry bar, one interval in the future) and the causal
ER10 (signal bar's own value, what the live pipeline now uses) — and drives the
PRODUCTION engine (simulate_trades / compute_summary).

Run config = the original ER10 study's pinned execution (er10_oos_sweep_20260621.md):
  1.0R single-leg, 1 contract, entry_slip=1t, exit_slip=0, stop_offset=1t,
  commission $4.36 RT (ES), ER10 = ER_intra_2 (2-bar / 10-min Kaufman ER).

Signal set : saved_signals/ba_signals_mc.parquet  (the original "too-good ER10" pop.)
Gate       : ER10 >= 0.70
Output     : both modes side-by-side, full metric table + delta.
Ticks are loaded ONCE per date (chunked for memory) and reused for both sims.
Out: docs/living/er10_lookahead_rerun_<date>.md
"""
from __future__ import annotations

import sys, gc
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                                                        # noqa: E402
from simulation_engine import simulate_trades, compute_summary        # noqa: E402
from data_loader import bar_num_from_dt                               # noqa: E402
# bug-reproduction helpers — imported, NOT modified
from er_lookahead_tab import _er10_both_modes, _apply_gate            # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"

GATE       = 0.70
COMMISSION = 4.36
N_CHUNKS   = 4
SIM_KW = dict(target_r=1.0, entry_slip=1, exit_slip=0, stop_offset=1,
              tick_value=12.5, contracts=1, commission=COMMISSION, overrides=None)

# metrics to surface (key, label) — mirrors er_lookahead_tab._METRICS subset
_METRICS = [
    ("n_total", "Signals (total)"), ("n_filtered", "Filtered out (gate)"),
    ("n_trades", "Trades (filled)"), ("win_pct", "Win %"),
    ("net_total", "Net P&L $"), ("exp_dollar", "Expectancy $/trade"),
    ("exp_r", "Expectancy R"), ("pf", "Profit Factor"), ("sqn", "SQN"),
    ("prom", "PROM"), ("max_dd", "Max Drawdown $"), ("avg_win", "Avg Win $"),
    ("avg_loss", "Avg Loss $"), ("wl_ratio", "Win/Loss ratio"),
    ("sharpe", "Sharpe (notional)"), ("cagr", "CAGR (notional) %"),
]


def log(m): print(f"[er10] {datetime.now():%H:%M:%S} {m}", flush=True)


def main() -> int:
    log("load signals + bars ...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bbd = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)

    log("tag ER10 both modes (look-ahead + causal) ...")
    tagged = _er10_both_modes(sig, bars)            # adds ER10_current, ER10_causal
    tagged.to_parquet(_OUT / "er10_lookahead_tagged.parquet")   # reusable per-signal frame
    g_cur = _apply_gate(tagged, "ER10_current", GATE)   # pre-fix look-ahead gate
    g_cau = _apply_gate(tagged, "ER10_causal",  GATE)   # causal (now-live) gate
    for g in (g_cur, g_cau):
        g["_date"] = pd.to_datetime(g["DateTime"]).dt.date

    # gate-flip diagnostics on rows with a defined causal value
    valid = tagged.dropna(subset=["ER10_causal"])
    cur_pass = valid["ER10_current"] >= GATE
    cau_pass = valid["ER10_causal"] >= GATE
    diag = dict(n=int(len(valid)), pass_cur=int(cur_pass.sum()), pass_cau=int(cau_pass.sum()),
                flips=int((cur_pass != cau_pass).sum()),
                phantom_pass=int((cur_pass & ~cau_pass).sum()),
                phantom_block=int((~cur_pass & cau_pass).sum()))

    res_cur, res_cau = [], []
    dates = sorted(g_cur["_date"].unique())
    for ci, chunk in enumerate(np.array_split(np.array(dates, object), N_CHUNKS)):
        cset = set(chunk.tolist())
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        sub_cur = g_cur[g_cur["_date"].isin(cset)].drop(columns="_date").reset_index(drop=True)
        sub_cau = g_cau[g_cau["_date"].isin(cset)].drop(columns="_date").reset_index(drop=True)
        res_cur.append(simulate_trades(sub_cur, ticks_by_date=tbd, bars_by_date=bbd, **SIM_KW))
        res_cau.append(simulate_trades(sub_cau, ticks_by_date=tbd, bars_by_date=bbd, **SIM_KW))
        del tbd; gc.collect()
        log(f"  chunk {ci+1}/{N_CHUNKS} done")

    sum_cur = compute_summary(pd.concat(res_cur, ignore_index=True), COMMISSION, contracts=1)
    sum_cau = compute_summary(pd.concat(res_cau, ignore_index=True), COMMISSION, contracts=1)

    # ── markdown report ──────────────────────────────────────────────────────
    def f(d, k):
        v = d.get(k)
        if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
            return "—"
        if k in ("net_total", "max_dd", "avg_win", "avg_loss"): return f"${v:,.0f}"
        if k == "exp_dollar": return f"${v:,.2f}"
        if k in ("win_pct", "cagr"): return f"{v:.1f}%"
        if k in ("n_total", "n_filtered", "n_trades"): return f"{v:,.0f}"
        if k in ("exp_r",): return f"{v:.3f}"
        return f"{v:.2f}"

    md = [f"# ER10 look-ahead — headless rerun WITH the bug ({datetime.now():%Y-%m-%d})\n",
          "> ⚠️ This DELIBERATELY reproduces the pre-S34 `merge_asof` look-ahead to show its "
          "inflation. The live pipeline is fixed (causal); nothing here changes production code "
          "— it imports the reproduction helpers from `er_lookahead_tab.py` and drives the "
          "production engine.\n",
          f"**Signal set:** `ba_signals_mc.parquet` ({len(tagged):,} signals)  "
          f"**Gate:** ER10 ≥ {GATE:.2f}  "
          "**Exec:** 1.0R single-leg, 1c, entry_slip=1t, exit_slip=0, stop_offset=1t, "
          f"comm ${COMMISSION:.2f} RT.\n",
          "## Gate decision impact (rows with a defined causal ER10)\n",
          f"- valid: **{diag['n']:,}** — pre-fix gate passes **{diag['pass_cur']:,}**, "
          f"causal passes **{diag['pass_cau']:,}**.",
          f"- decisions FLIPPED by the look-ahead: **{diag['flips']:,}** "
          f"({diag['flips']/diag['n']*100:.1f}%) — phantom PASS (chop snuck in) "
          f"**{diag['phantom_pass']:,}**, phantom BLOCK (good signal tossed) "
          f"**{diag['phantom_block']:,}**.\n",
          "## Metrics — Pre-fix (look-ahead) vs Causal (now live)\n",
          "| Metric | Pre-fix (look-ahead) | Causal (live) |",
          "|---|---|---|"]
    for k, label in _METRICS:
        md.append(f"| {label} | {f(sum_cur, k)} | {f(sum_cau, k)} |")
    nd = sum_cau.get("net_total", 0) - sum_cur.get("net_total", 0)
    ed = sum_cau.get("exp_dollar", 0) - sum_cur.get("exp_dollar", 0)
    md += ["",
           f"**Net P&L:** causal − pre-fix = **${nd:,.0f}**  |  "
           f"**Expectancy/trade:** **${ed:,.2f}**.  The pre-fix column is the inflated "
           "look-ahead result; the gap is the bug.\n"]

    out = _OUT / f"er10_lookahead_rerun_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    # console headline
    log(f"PRE-FIX  net=${sum_cur.get('net_total',0):,.0f} exp=${sum_cur.get('exp_dollar',0):.2f} "
        f"win={sum_cur.get('win_pct',0):.1f}% n={sum_cur.get('n_trades',0)} PF={sum_cur.get('pf',0):.2f}")
    log(f"CAUSAL   net=${sum_cau.get('net_total',0):,.0f} exp=${sum_cau.get('exp_dollar',0):.2f} "
        f"win={sum_cau.get('win_pct',0):.1f}% n={sum_cau.get('n_trades',0)} PF={sum_cau.get('pf',0):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
