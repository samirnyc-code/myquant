"""balance_deepdive.py — expand the balanced-state finding with hard numbers.

Answers, all in real engine dollars (pinned 1.0R single-leg, the deployed config):

  1. ER30 vs BALANCE — is ER30 the only filter with merit? 2x2 expectancy +
     walk-forward OOS. Does balance ADD to ER30 or is it redundant?
  2. PRIOR-DAY CONTEXT theories — does a balanced-state signal behave differently
     when YESTERDAY was: an inside day / a big ADR-extension (trend) day / closed
     strong (CLV)? Tested within balanced signals and overall.
  3. WFA (walk-forward OOS) config comparison: none / ER30 / balance / ER30+balance
     / ER30+balance+prior-day refinements. Metrics: trades, exp, PF, %green folds,
     pooled OOS net, MAR (net/maxDD). Folds = same is=252/oos=63 signal-day windows
     as the rest of the project; NO optimizer (rules are fixed, every OOS window is a
     genuine test). 2022 broken out.

Run: .venv/Scripts/python.exe scripts/balance_deepdive.py
Out: docs/living/balance_deepdive_<date>.md
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
import regime_filter as rf                                          # noqa: E402
import wfa                                                          # noqa: E402
from simulation_engine import simulate_trades                       # noqa: E402
from scripts.regime_overlay_phaseB import (BASE, CHOP_MIN, tag_states,  # noqa: E402
                                           stats, _SIGNALS, _BARS, _SESS)

_OUT = _ROOT / "docs" / "living"
IS_DAYS, OOS_DAYS = 252, 63


def log(m): print(f"[deep] {datetime.now():%H:%M:%S} {m}", flush=True)


def prior_day_context(sess: pd.DataFrame) -> pd.DataFrame:
    """Per-date features describing YESTERDAY (look-ahead-safe: all shifted)."""
    s = sess.sort_values("Date").reset_index(drop=True).copy()
    H, L, C = s["RTH_High"], s["RTH_Low"], s["RTH_Close"]
    # was YESTERDAY an inside day? (its range inside the day-before's range)
    inside_prev = (H.shift(1) < H.shift(2)) & (L.shift(1) > L.shift(2))
    # yesterday's range / its ADR (extension)
    prev_ext = (s["rng"].shift(1) / s["ADR"].shift(1))
    # yesterday's close location value (0=closed on low, 1=on high)
    prev_clv = ((C.shift(1) - L.shift(1)) / (H.shift(1) - L.shift(1)).replace(0, np.nan))
    out = pd.DataFrame({"Date": s["Date"]})
    out["pd_inside"] = np.where(inside_prev.fillna(False), "inside-day", "normal")
    out["pd_ext"] = pd.cut(prev_ext, [0, 0.8, 1.2, 1.6, np.inf],
                           labels=["compressed<0.8", "normal0.8-1.2", "extended1.2-1.6", "trend>1.6"])
    out["pd_clv"] = pd.cut(prev_clv, [-0.01, 0.33, 0.67, 1.01],
                           labels=["closed-weak", "closed-mid", "closed-strong"])
    return out


def line(label, pnl):
    s = stats(np.asarray(pnl, dtype=float))
    if s["n"] == 0:
        return f"| {label} | 0 | — | — | — |"
    pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    return f"| {label} | {s['n']} | ${s['exp']:.0f} | {s['win']:.0f}% | {pf} |"


def walkforward(df, mask, folds):
    """Pooled OOS metrics for a config (boolean mask over filled df)."""
    sub = df[mask]
    fold_nets, pooled = [], []
    for f in folds:
        oos = set(f["oos_dates"])
        t = sub[sub["Date"].isin(oos)]
        if len(t):
            fold_nets.append(t["NetPnL"].sum())
            pooled.append(t)
    if not pooled:
        return None
    p = pd.concat(pooled).sort_values("DateTime")
    pnl = p["NetPnL"].to_numpy()
    eq = np.cumsum(pnl); dd = (np.maximum.accumulate(eq) - eq).max()
    mar = eq[-1] / dd if dd > 0 else float("inf")
    green = np.mean([x > 0 for x in fold_nets]) * 100
    gw = pnl[pnl > 0].sum(); gl = abs(pnl[pnl < 0].sum())
    e22 = p.loc[p["_year"] == 2022, "NetPnL"]
    return dict(n=len(p), exp=pnl.mean(), pf=(gw / gl if gl else float("inf")),
                green=green, net=eq[-1], mar=mar, folds=len(fold_nets),
                exp22=(e22.mean() if len(e22) else float("nan")), n22=len(e22))


def main() -> int:
    log("load + tag (ER, balance, prior-day)...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    sess = pd.read_parquet(_SESS)
    bars_by_date = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}

    tagged, _ = rf.tag_and_bucket(sig, bars)
    er = tagged["ER_intra_6"].astype(float).fillna(0)
    sigf = sig.reset_index(drop=True).copy()           # ALL signals (no ER filter yet)
    sigf["er"] = er.values
    st = tag_states(sigf, bars, sess)
    sigf = pd.concat([sigf, st], axis=1)
    sigf["balance"] = (sigf["open_loc"] == "inside") & (sigf["disc"] == "rotation")
    pdc = prior_day_context(sess)
    sigf = sigf.merge(pdc, on="Date", how="left")

    log("ticks + simulate ALL signals (pinned 1.0R)...")
    tk = {d: massive.load_continuous_ticks(d) for d in sorted(sigf["Date"].unique())}
    tk = {d: t for d, t in tk.items() if not t.empty}
    res = simulate_trades(signals=sigf, ticks_by_date=tk, bars_by_date=bars_by_date, **BASE)
    f = res[res["Filled"] == True].copy()
    for c in ["er", "balance", "open_loc", "disc", "pd_inside", "pd_ext", "pd_clv"]:
        f[c] = sigf.loc[f.index, c].values
    f["DateTime"] = sigf.loc[f.index, "DateTime"].values
    f["Date"] = sigf.loc[f.index, "Date"].values
    f["_year"] = pd.to_datetime(f["DateTime"]).dt.year
    f["er30"] = f["er"] >= CHOP_MIN
    log(f"filled: {len(f)}")

    md = [f"# Balance deep-dive ({datetime.now():%Y-%m-%d})\n",
          f"Pinned 1.0R single-leg, all setups. {len(f)} filled signals. "
          f"'balance' = opened inside prior range AND still inside at signal.\n"]

    # ── 1. ER30 x BALANCE 2x2 ────────────────────────────────────────────────
    md += ["## 1. ER30 vs Balance — is ER30 the only lever? (whole sample)\n",
           "| cell | n | exp | win% | PF |", "|---|---|---|---|---|"]
    for er_on in [True, False]:
        for bal_on in [True, False]:
            m = (f["er30"] == er_on) & (f["balance"] == bal_on)
            lab = f"ER{'≥' if er_on else '<'}.30 · {'balance' if bal_on else 'non-bal'}"
            md.append(line(lab, f.loc[m, "NetPnL"]))
    md += ["",
           "Reading: compare balance vs non-bal WITHIN each ER row (does balance add to ER?), "
           "and ER≥ vs ER< WITHIN each balance column (does ER add to balance?).\n"]

    # ── 2. Prior-day context (within ER>=0.30) ───────────────────────────────
    fe = f[f["er30"]]
    for col, title in [("pd_inside", "prior day was an INSIDE day"),
                       ("pd_ext", "prior day ADR extension (range/ADR)"),
                       ("pd_clv", "prior day close location (CLV)")]:
        md += [f"## 2. {title} — within ER≥0.30\n",
               "| bucket | n | exp | win% | PF | (balance only) n | exp |",
               "|---|---|---|---|---|---|---|"]
        for b in fe[col].dropna().unique():
            m = fe[col] == b
            s = stats(fe.loc[m, "NetPnL"].to_numpy())
            mb = m & fe["balance"]
            sb = stats(fe.loc[mb, "NetPnL"].to_numpy())
            pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
            bexp = f"${sb['exp']:.0f}" if sb["n"] else "—"
            md.append(f"| {b} | {s['n']} | ${s['exp']:.0f} | {s['win']:.0f}% | {pf} | {sb['n']} | {bexp} |")
        md += [""]

    # ── 3. Walk-forward OOS config comparison ─────────────────────────────────
    folds = wfa.build_folds(sorted(f["Date"].unique()), IS_DAYS, OOS_DAYS)
    configs = {
        "none (all signals)":        pd.Series(True, index=f.index),
        "ER≥0.30":                   f["er30"],
        "balance only":              f["balance"],
        "ER≥0.30 + balance":         f["er30"] & f["balance"],
        "ER≥0.30 + bal + prior-inside": f["er30"] & f["balance"] & (f["pd_inside"] == "inside-day"),
        "ER≥0.30 + bal + prior-trend>1.6": f["er30"] & f["balance"] & (f["pd_ext"] == "trend>1.6"),
    }
    md += ["## 3. Walk-forward OOS (pinned 1.0R, same is=252/oos=63 folds)\n",
           "| config | trades | exp | PF | %green folds | pooled net | MAR | exp 2022 (n) |",
           "|---|---|---|---|---|---|---|---|"]
    for name, mask in configs.items():
        r = walkforward(f, mask, folds)
        if r is None:
            md.append(f"| {name} | 0 | — | — | — | — | — | — |"); continue
        pf = "∞" if r["pf"] == float("inf") else f"{r['pf']:.2f}"
        mar = "∞" if r["mar"] == float("inf") else f"{r['mar']:.1f}"
        e22 = f"${r['exp22']:.0f} ({r['n22']})" if not np.isnan(r["exp22"]) else "—"
        md.append(f"| {name} | {r['n']} | ${r['exp']:.0f} | {pf} | {r['green']:.0f}% "
                  f"| ${r['net']:,.0f} | {mar} | {e22} |")
    md += [""]

    out = _OUT / f"balance_deepdive_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote -> {out}")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("\n" + "\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
