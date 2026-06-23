"""profile_node_study.py — do MCs originating at prior-session HVN/LVN/single-prints behave differently?

Builds the profile-node infrastructure deferred in auction_features.py (phase 2:
"HVN/LVN shelves, single/zero prints"). For each RTH session we build a volume-at-price
profile (typical-price-per-1M-bar histogram, 1pt buckets — same methodology as
indicators.value_areas, finer bars) and extract:
  • HVN  — high-volume nodes (local maxima ≥ HVN_FRAC×POC) = acceptance/value shelves
  • LVN  — low-volume nodes (interior valleys between HVNs) = fast-traversal rejection zones
  • single/zero prints — buckets with vol ≤ SINGLE_FRAC×POC inside the range = profile gaps/magnets

Each signal's MC origin (StopPrice = MCX, where the channel formed) is then measured
against the PRIOR completed session's nodes (fully look-ahead-safe — yesterday's profile
is known at today's open). Distance is normalized by ADR (prior_ATR).

Pre-committed hypotheses (structural, not fished):
  H1  origin at a prior LVN  → fast traversal → momentum/continuation edge
  H2  origin at a prior HVN  → acceptance/stall → fade or AVOID (chop)
  H3  origin at a single/zero print → magnet → directional fill

METHODOLOGY CAVEAT: typical-price-per-bar is a PROXY profile (true HVN/LVN want tick
volume-at-price/TPO). Cheap probe first; upgrade to ticks only if signal appears.

Descriptive only — pinned 1.0R single-leg, real tick engine. Judge on coherent gradient
+ sample + (next step) year robustness. Don't bank a lone thin bucket.

Run: .venv/Scripts/python.exe scripts/profile_node_study.py
Out: docs/living/profile_node_study_<date>.md
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
from indicators import tag_signals, _typical, TICK_SIZE             # noqa: E402
from data_loader import bar_num_from_dt                              # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS5M  = _ROOT / "data" / "bars" / "_continuous.parquet"
_BARS1M  = _ROOT / "data" / "bars" / "_continuous_1m.parquet"
_OUT     = _ROOT / "docs" / "living"

BASE = dict(entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5,
            contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
            ratchet_r=0.0, pb_round="nearest", target_r=1.0,
            multileg=False, threeleg=False, overrides=None)

BUCKET_TICKS = 4          # 1 ES point profile buckets (matches value_areas default)
HVN_FRAC     = 0.30       # local max ≥ 30% of POC = a high-volume node
SINGLE_FRAC  = 0.05       # bucket ≤ 5% of POC (inside range) = single/zero print

BANDS = [(0.0, 0.05), (0.05, 0.10), (0.10, 0.20), (0.20, 0.35),
         (0.35, 0.60), (0.60, np.inf)]
BAND_LABELS = ["0..0.05 (AT)", "0.05..0.10", "0.10..0.20",
               "0.20..0.35", "0.35..0.60", "> 0.60"]


def log(m: str) -> None:
    print(f"[node] {datetime.now():%H:%M:%S} {m}", flush=True)


# ── node extraction ───────────────────────────────────────────────────────────

def extract_nodes(prof: pd.Series) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """From a price→volume profile (index=price asc), return (HVN, LVN, single) prices."""
    prices = prof.index.to_numpy(dtype=float)
    v = prof.to_numpy(dtype=float)
    n = len(v)
    if n < 3:
        return np.array([]), np.array([]), prices[v <= SINGLE_FRAC * (v.max() or 1)]
    vs = np.convolve(v, np.array([0.25, 0.5, 0.25]), mode="same")   # light smooth
    poc = vs.max()
    hvn, lvn = [], []
    for i in range(n):
        left = vs[i - 1] if i > 0 else -1.0
        right = vs[i + 1] if i < n - 1 else -1.0
        if vs[i] >= left and vs[i] >= right and vs[i] >= HVN_FRAC * poc:
            hvn.append(prices[i])
        if 0 < i < n - 1 and vs[i] < left and vs[i] < right:        # interior valley
            lvn.append(prices[i])
    single = prices[v <= SINGLE_FRAC * poc]                          # gaps inc. tails
    return np.array(hvn), np.array(lvn), np.array(single)


def build_session_nodes(bars1m: pd.DataFrame) -> dict:
    """date -> (HVN, LVN, single) arrays, from each session's 1M volume profile."""
    bucket = TICK_SIZE * BUCKET_TICKS
    out = {}
    for d, g in bars1m.groupby(bars1m["DateTime"].dt.date):
        tp = _typical(g)
        keys = (tp / bucket).round() * bucket
        prof = g["Volume"].groupby(keys).sum().sort_index()
        if prof.empty or prof.sum() <= 0:
            continue
        out[d] = extract_nodes(prof)
    return out


def nearest(x: float, nodes: np.ndarray) -> float:
    if nodes is None or len(nodes) == 0 or not np.isfinite(x):
        return np.nan
    return float(np.min(np.abs(nodes - x)))


# ── stats (shared shape with origin study) ────────────────────────────────────

def stats(pnl, rmult=None):
    n = len(pnl)
    if n == 0:
        return dict(n=0, net=0, exp=0, pf=0, wr=0, expR=np.nan, ci=np.nan)
    net = float(pnl.sum())
    gw = float(pnl[pnl > 0].sum()) if (pnl > 0).any() else 0.0
    gl = float(abs(pnl[pnl < 0].sum())) if (pnl < 0).any() else 0.0
    pf = gw / gl if gl > 0 else float("inf")
    wr = float((pnl > 0).sum() / n * 100)
    ci = float(1.96 * pnl.std(ddof=1) / np.sqrt(n)) if n > 1 else np.nan
    expR = float(np.nanmean(rmult)) if rmult is not None and len(rmult) else np.nan
    return dict(n=n, net=net, exp=net / n, pf=pf, wr=wr, expR=expR, ci=ci)


HDR = "| band (ADR) | n | net $ | exp $ | ±95%CI | exp R | PF | win% |"
SEP = "|---|---|---|---|---|---|---|---|"


def row(label, pnl, rmult):
    s = stats(pnl, rmult)
    if s["n"] == 0:
        return f"| {label} | 0 | — | — | — | — | — | — |"
    pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    ci = "—" if np.isnan(s["ci"]) else f"±{s['ci']:.0f}"
    er = "—" if np.isnan(s["expR"]) else f"{s['expR']:+.3f}"
    return (f"| {label} | {s['n']} | ${s['net']:,.0f} | ${s['exp']:+.0f} | {ci} | "
            f"{er} | {pf} | {s['wr']:.1f}% |")


def bucket_table(feat, pnl, rmult, mask):
    md = [HDR, SEP]
    f = feat[mask]; p = pnl[mask].values; r = rmult[mask].values
    md.append(row("ALL (has node)", p[np.isfinite(f.values)], r[np.isfinite(f.values)]))
    for (lo, hi), lab in zip(BANDS, BAND_LABELS):
        b = (f >= lo) & (f < hi)
        md.append(row(lab, p[b.values], r[b.values]))
    md.append("")
    return md


def main() -> int:
    log("loading signals + bars (5M sim, 1M profile)...")
    sig = pd.read_parquet(_SIGNALS)
    bars5 = pd.read_parquet(_BARS5M).drop(columns=["Contract"], errors="ignore")
    bars1 = pd.read_parquet(_BARS1M).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars5.groupby(bars5["DateTime"].dt.date)}
    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)

    log("tagging signals (prior_ATR for ADR)...")
    tagged = tag_signals(sig, bars5).sort_values("DateTime").reset_index(drop=True)
    adr = tagged["prior_ATR"].replace(0, np.nan)

    log("building per-session profile nodes (1M)...")
    nodes = build_session_nodes(bars1)
    prof_dates = sorted(nodes.keys())
    log(f"sessions with a profile: {len(prof_dates)}")

    # map each signal date -> most recent PRIOR session's nodes (look-ahead-safe)
    pidx = pd.Index(prof_dates)
    sig_dates = pd.to_datetime(tagged["DateTime"]).dt.date
    d_lvn = np.full(len(tagged), np.nan)
    d_hvn = np.full(len(tagged), np.nan)
    d_sgl = np.full(len(tagged), np.nan)
    for i, (d, sp) in enumerate(zip(sig_dates, tagged["StopPrice"].to_numpy(float))):
        pos = pidx.searchsorted(d, side="left") - 1     # strictly-prior session
        if pos < 0:
            continue
        hvn, lvn, single = nodes[prof_dates[pos]]
        d_hvn[i] = nearest(sp, hvn)
        d_lvn[i] = nearest(sp, lvn)
        d_sgl[i] = nearest(sp, single)

    tagged["d_lvn"] = d_lvn / adr.to_numpy()
    tagged["d_hvn"] = d_hvn / adr.to_numpy()
    tagged["d_single"] = d_sgl / adr.to_numpy()

    log("loading ticks...")
    dates = sorted(sig_dates.unique())
    ticks_by_date = {d: massive.load_continuous_ticks(d) for d in dates}
    ticks_by_date = {d: t for d, t in ticks_by_date.items() if not t.empty}

    log(f"simulating {len(tagged)} signals...")
    res = simulate_trades(signals=tagged, ticks_by_date=ticks_by_date,
                          bars_by_date=bars_by_date, **BASE).reset_index(drop=True)
    filled = res["Filled"] == True
    log(f"filled: {int(filled.sum())}")

    f = tagged.loc[filled].reset_index(drop=True)
    rf = res.loc[filled].reset_index(drop=True)
    pnl = rf["NetPnL"]
    risk = rf["RiskDollar"] if "RiskDollar" in rf.columns else None
    rmult = (rf["NetPnL"] / risk) if risk is not None else pd.Series(np.nan, index=rf.index)
    isL = f["Direction"].str.lower().str.startswith("l")

    md = [f"# Profile-Node Origin Study ({datetime.now():%Y-%m-%d})\n",
          "**Q:** do MCs whose origin (MCX/StopPrice) sits at a PRIOR-session HVN / LVN / "
          "single-print behave differently? Look-ahead-safe (yesterday's profile), pinned "
          "1.0R single-leg, real tick engine. Distance = ADR units to nearest node.\n",
          f"- filled: {len(rf)} · sessions w/ profile: {len(prof_dates)}\n",
          "- **PROXY profile** (typical-price-per-1M-bar). Upgrade to tick VAP only if signal.\n",
          f"\n**Baseline (ALL filled):** {row('ALL', pnl.values, rmult.values)}\n"]

    for col, title, hyp in [
        ("d_lvn", "Distance to nearest prior LVN", "H1: origin AT an LVN → fast traversal/momentum"),
        ("d_hvn", "Distance to nearest prior HVN", "H2: origin AT an HVN → stall → fade/avoid"),
        ("d_single", "Distance to nearest prior single/zero print", "H3: origin AT a gap → magnet/fill")]:
        md.append(f"\n## {title}\n_{hyp}_\n")
        md.append("### Both directions\n")
        md += bucket_table(f[col], pnl, rmult, pd.Series(True, index=f.index))
        md.append("### Long only\n")
        md += bucket_table(f[col], pnl, rmult, isL)
        md.append("### Short only\n")
        md += bucket_table(f[col], pnl, rmult, ~isL)

    out = _OUT / f"profile_node_study_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
