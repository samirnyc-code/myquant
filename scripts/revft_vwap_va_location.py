"""revft_vwap_va_location.py — best TRADE LOCATION for RevFT via VWAP-dev + value area.

Trade-location hunt #2 for RevFT (MyReversals). The reversal-at-extreme study (S40)
closed the *static* location question (distance to developing HOD/LOD & HOY/LOY = no
edge). This script tests the two location axes the user asked for next:

  A  VWAP DEVIATION — signed sigma-distance of price from the developing session VWAP
     at the signal bar (`VWAP_dev`, causal). Re-expressed DIRECTIONALLY as "stretch
     INTO the fade": S = -VWAP_dev for longs, +VWAP_dev for shorts. S>0 means price is
     extended on the mean-reversion-favorable side (long below VWAP / short above VWAP);
     S<0 means the fade fires on the continuation side (chasing). Hypothesis: a RevFT
     fade has a better edge the deeper the favorable stretch (larger S).

  B  VALUE AREA (prior day) — location of the signal vs the PRIOR completed session's
     value area (`vaD_loc` / `vaD_dist`; look-ahead-safe — yesterday's VA, never today's).
     Directional: long favorable BELOW prior VAL, short favorable ABOVE prior VAH.
     V = (-vaD_dist for long / +vaD_dist for short) / ADR. V>0 = beyond the value edge
     on the responsive-fade side.

  C  2-D CROSS — VWAP-dev band x VA location (above/inside/below). The "best cell" hunt.

Both features come from indicators.tag_signals (the S34 look-ahead-safe chokepoint).

NB (S37): RevFT @1:1 is a firm net loser (net -$187k). This is a SELECTIVITY hunt —
is there a SUBSET whose gross/trade clears the ~$15/trade cost hurdle with a CI that
excludes zero — not a validation of RevFT as-is. Verdict rule: a MONOTONIC gradient
across a real sample (check +-95%CI). One lucky thin bucket != edge.

Worktree note: code + output live in the `docs/revft-tradelocation` worktree, but the
signals/ticks/venv are gitignored and exist only in the MAIN checkout, so data paths
point there. Run with the MAIN venv:
  C:/Users/Thomas-Code/Projects/myquant/.venv/Scripts/python.exe scripts/revft_vwap_va_location.py
Out: docs/living/revft_vwap_va_location_<date>.md
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]          # the worktree (code + output)
_MAIN = Path(__file__).resolve().parent.parent       # gitignored data lives here
sys.path.insert(0, str(_ROOT))

import massive                                                       # noqa: E402
# massive resolves its data dir from its own file location (the worktree, where the
# gitignored tick cache is absent). Point its per-day tick cache at the MAIN checkout.
massive._TICKS_CONT_DIR = _MAIN / "data" / "ticks_continuous"        # noqa: E402
from simulation_engine import simulate_trades                        # noqa: E402
from indicators import tag_signals                                   # noqa: E402
from data_loader import bar_num_from_dt                              # noqa: E402

_SIGNALS = _MAIN / "saved_signals" / "ba_signals_revft.parquet"
_BARS    = _MAIN / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"

BASE = dict(entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5,
            contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
            ratchet_r=0.0, pb_round="nearest", target_r=1.0,
            multileg=False, threeleg=False, overrides=None)

# A — directional VWAP stretch S (sigma units). 0 == at VWAP, >0 == stretched on the
# mean-reversion-favorable side (long below / short above VWAP), <0 == continuation side.
S_BANDS = [(-np.inf, -1.0), (-1.0, -0.25), (-0.25, 0.25), (0.25, 1.0),
           (1.0, 2.0), (2.0, 3.0), (3.0, np.inf)]
S_LABELS = ["< -1.0 (chase)", "-1.0..-0.25", "-0.25..0.25 (at VWAP)", "0.25..1.0",
            "1.0..2.0", "2.0..3.0", "> 3.0 (deep stretch)"]

# B — directional value-area position V (ADR units). 0 == at the favorable VA edge /
# inside, >0 == beyond the edge on the responsive-fade side (long below VAL / short
# above VAH), <0 == beyond the OTHER edge (fading toward value from the far side).
V_BANDS = [(-np.inf, -0.15), (-0.15, 0.0), (0.0, 0.15), (0.15, 0.30),
           (0.30, 0.60), (0.60, np.inf)]
V_LABELS = ["< -0.15 (far side)", "-0.15..0.0", "0.0..0.15", "0.15..0.30",
            "0.30..0.60", "> 0.60 (deep beyond edge)"]


def log(m: str) -> None:
    print(f"[revloc] {datetime.now():%H:%M:%S} {m}", flush=True)


# ── stats ─────────────────────────────────────────────────────────────────────

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


HDR = "| band | n | net $ | exp $ | ±95%CI | exp R | PF | win% |"
SEP = "|---|---|---|---|---|---|---|---|"


def row(label: str, pnl: np.ndarray, rmult: np.ndarray | None) -> str:
    s = stats(pnl, rmult)
    if s["n"] == 0:
        return f"| {label} | 0 | — | — | — | — | — | — |"
    pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    ci = "—" if np.isnan(s["ci"]) else f"±{s['ci']:.0f}"
    er = "—" if np.isnan(s["expR"]) else f"{s['expR']:+.3f}"
    return (f"| {label} | {s['n']} | ${s['net']:,.0f} | ${s['exp']:+.0f} | {ci} | "
            f"{er} | {pf} | {s['wr']:.1f}% |")


def bucket_table(feat: pd.Series, pnl: pd.Series, rmult: pd.Series, mask: pd.Series,
                 bands, labels) -> list[str]:
    md = [HDR, SEP]
    f = feat[mask]
    p = pnl[mask].values
    r = rmult[mask].values
    md.append(row("ALL", p, r))
    for (lo, hi), lab in zip(bands, labels):
        b = (f >= lo) & (f < hi)
        md.append(row(lab, p[b.values], r[b.values]))
    md.append("")
    return md


def loc_table(loc: pd.Series, pnl: pd.Series, rmult: pd.Series,
              mask: pd.Series) -> list[str]:
    """Categorical prior-day VA location (above/inside/below)."""
    md = [HDR, SEP]
    f = loc[mask]
    p = pnl[mask].values
    r = rmult[mask].values
    md.append(row("ALL", p, r))
    for cat in ["above", "inside", "below"]:
        b = (f == cat)
        md.append(row(cat, p[b.values], r[b.values]))
    md.append("")
    return md


def main() -> int:
    log("loading signals + bars...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)

    log("tagging signals (causal VWAP_dev + prior-day value area)...")
    tagged = tag_signals(sig, bars).sort_values("DateTime").reset_index(drop=True)

    sgnL = tagged["Direction"].str.lower().str.startswith("l")        # True = Long
    adr = tagged["prior_ATR"].replace(0, np.nan)

    # A — directional VWAP stretch (sigma). long favorable below VWAP (-dev), short above.
    tagged["S"] = np.where(sgnL, -tagged["VWAP_dev"], tagged["VWAP_dev"])

    # B — directional prior-day VA position (ADR). vaD_dist>0 above VAH, <0 below VAL.
    # long favorable below VAL (-dist), short favorable above VAH (+dist).
    tagged["V"] = np.where(sgnL, -tagged["vaD_dist"], tagged["vaD_dist"]) / adr

    # ── real tick engine (pinned 1.0R single-leg) ─────────────────────────────
    log("loading ticks...")
    dates = sorted(pd.to_datetime(tagged["Date"]).dt.date.unique()) \
        if "Date" in tagged.columns else \
        sorted(tagged["DateTime"].dt.date.unique())
    ticks_by_date = {d: massive.load_continuous_ticks(d) for d in dates}
    ticks_by_date = {d: t for d, t in ticks_by_date.items() if not t.empty}

    log(f"simulating {len(tagged)} signals (pinned 1.0R single-leg)...")
    res = simulate_trades(signals=tagged, ticks_by_date=ticks_by_date,
                          bars_by_date=bars_by_date, **BASE).reset_index(drop=True)
    filled = res["Filled"] == True
    log(f"filled: {int(filled.sum())} / {len(res)}")

    f = tagged.loc[filled].reset_index(drop=True)
    rf = res.loc[filled].reset_index(drop=True)
    pnl = rf["NetPnL"]
    risk = rf["RiskDollar"] if "RiskDollar" in rf.columns else None
    rmult = (rf["NetPnL"] / risk) if risk is not None else pd.Series(np.nan, index=rf.index)
    isL = f["Direction"].str.lower().str.startswith("l")
    allm = pd.Series(True, index=f.index)

    # how many rows have a usable VWAP_dev (NaN in session warmup)
    nS = int(f["S"].notna().sum())
    nV = int(f["V"].notna().sum())

    md = [f"# RevFT Trade-Location — VWAP deviation + value area ({datetime.now():%Y-%m-%d})\n",
          "**Question:** is there a SUBSET of RevFT defined by where the signal sits vs "
          "the developing-session VWAP and the prior-day value area that clears the "
          "~$15/trade cost hurdle? Descriptive only — pinned 1.0R single-leg, real tick "
          "engine, look-ahead-safe features (S34 `tag_signals`).\n",
          f"- Signal set: `ba_signals_revft.parquet` · {len(tagged)} signals · "
          f"filled: {len(rf)} · with VWAP_dev: {nS} · with prior-VA dist: {nV}\n",
          "- **S** = directional VWAP stretch (σ): `-VWAP_dev` long / `+VWAP_dev` short. "
          ">0 = stretched on the mean-reversion-favorable side (long below VWAP / short "
          "above); <0 = fading on the continuation side (chasing).\n",
          "- **V** = directional prior-day VA position (ADR): beyond the responsive-fade "
          "edge (long below prior VAL / short above prior VAH) is >0.\n",
          "- **Verdict rule:** MONOTONIC gradient across a real sample (check ±95%CI). "
          "One lucky thin bucket ≠ edge.\n",
          "- **NB (S37):** RevFT @1:1 is a firm net loser overall — selectivity hunt, not "
          "a validation.\n",
          f"\n**Baseline (ALL filled):** {row('ALL', pnl.values, rmult.values)}\n"]

    # ════ A — VWAP deviation ════════════════════════════════════════════════════
    md.append("\n# A — VWAP deviation (directional stretch S)\n")
    md.append("### Both directions\n");  md += bucket_table(f["S"], pnl, rmult, allm, S_BANDS, S_LABELS)
    md.append("### Long only (fade up — favorable BELOW VWAP)\n"); md += bucket_table(f["S"], pnl, rmult, isL, S_BANDS, S_LABELS)
    md.append("### Short only (fade down — favorable ABOVE VWAP)\n"); md += bucket_table(f["S"], pnl, rmult, ~isL, S_BANDS, S_LABELS)

    # ════ B — value area ════════════════════════════════════════════════════════
    md.append("\n# B — Prior-day value area\n")
    md.append("## B1 — categorical location (signal price vs prior VAH/VAL)\n")
    md.append("### Both directions\n"); md += loc_table(f["vaD_loc"], pnl, rmult, allm)
    md.append("### Long only\n");  md += loc_table(f["vaD_loc"], pnl, rmult, isL)
    md.append("### Short only\n"); md += loc_table(f["vaD_loc"], pnl, rmult, ~isL)
    md.append("## B2 — directional distance V beyond the responsive-fade edge (ADR)\n")
    md.append("### Both directions\n"); md += bucket_table(f["V"], pnl, rmult, allm, V_BANDS, V_LABELS)
    md.append("### Long only\n");  md += bucket_table(f["V"], pnl, rmult, isL, V_BANDS, V_LABELS)
    md.append("### Short only\n"); md += bucket_table(f["V"], pnl, rmult, ~isL, V_BANDS, V_LABELS)

    # ════ C — 2-D cross (S band × VA location) ══════════════════════════════════
    md.append("\n# C — 2-D cross: VWAP stretch S × prior-day VA location\n")
    md.append("_Rows = S bands; within each, split by prior-day VA location._\n")
    md += [HDR, SEP]
    for (lo, hi), lab in zip(S_BANDS, S_LABELS):
        sb = (f["S"] >= lo) & (f["S"] < hi)
        for cat in ["above", "inside", "below"]:
            m = (sb & (f["vaD_loc"] == cat)).values
            md.append(row(f"S {lab} · VA {cat}", pnl[m].values, rmult[m].values))
    md.append("")

    # ── year-by-year stability of the best a-priori responsive cell ─────────────
    # a-priori favorable = stretched fade (S>1) AND beyond the value edge (V>0).
    md.append("\n# Year-by-year — a-priori responsive cell (S > 1.0 AND V > 0)\n")
    md.append("_Defined BEFORE seeing the cross above: a stretched VWAP fade that is also "
              "beyond the prior-day value edge. Stability check, not a tuned cell._\n")
    cell = (f["S"] > 1.0) & (f["V"] > 0)
    yr = pd.to_datetime(f["DateTime"]).dt.year
    md += ["| year | n | net $ | exp $ | ±95%CI | exp R | PF | win% |",
           "|---|---|---|---|---|---|---|---|"]
    for y in sorted(yr.unique()):
        m = (cell & (yr == y)).values
        s = stats(pnl[m].values, rmult[m].values)
        if s["n"] == 0:
            md.append(f"| {y} | 0 | — | — | — | — | — | — |"); continue
        pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
        ci = "—" if np.isnan(s["ci"]) else f"±{s['ci']:.0f}"
        er = "—" if np.isnan(s["expR"]) else f"{s['expR']:+.3f}"
        md.append(f"| {y} | {s['n']} | ${s['net']:,.0f} | ${s['exp']:+.0f} | {ci} | {er} | {pf} | {s['wr']:.1f}% |")
    md.append(f"\n**Full-sample cell:** {row('S>1 & V>0', pnl[cell.values].values, rmult[cell.values].values)}")
    md.append("")

    out = _OUT / f"revft_vwap_va_location_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
