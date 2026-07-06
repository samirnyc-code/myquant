"""RevFT SB-extreme entry vs baseline — full per-setup-type comparison.

Baseline: enter BTC at signal price, exit at original 1R (extreme-offset stop).
New:      limit 1t inside SB extreme (long: SBlow+1t, short: SBhigh-1t); price must
          tick to the SB extreme to fill. Two targets: T1=signal price (scalp),
          T2=original 1R. Stop = CSV extreme offset 1t (same as baseline).

Bar mapping: signal bar = iloc[BarNum-1] (NT 1-indexed; close==signal price/time).
"""
import os, sys
from pathlib import Path
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import massive
massive._TICKS_CONT_DIR = ROOT / "data" / "ticks_continuous"
from menthorq_edge_study import WIN_START, WIN_END, BARS_PQ, parse_signals

TICK = 0.25
PT = 50.0  # ES $/point
REV = Path(os.environ.get("REVFT_SIGNAL_TXT",
    ROOT / "data" / "signals" /
    "MyReversals Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"))
OUT = ROOT / "docs" / "living" / (
    "revft_sb_entry_fulldata_20260706.md" if os.environ.get("FULL") == "1"
    else "revft_sb_entry_full_20260706.md")

L = []
def emit(s=""): print(s, flush=True); L.append(s)
def log(m): print(f"[full] {m}", flush=True)


def metrics(rmults, pnls):
    """(n, expR, ci, PF, win%, net$) from arrays."""
    n = len(rmults)
    if n == 0:
        return 0, np.nan, np.nan, np.nan, np.nan, 0.0
    r = np.asarray(rmults, float); p = np.asarray(pnls, float)
    ci = 1.96 * r.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    gw = p[p > 0].sum(); gl = abs(p[p < 0].sum())
    pf = gw / gl if gl > 0 else np.inf
    win = 100.0 * (p > 0).sum() / n
    return n, r.mean(), ci, pf, win, p.sum()


def row(label, rmults, pnls):
    n, er, ci, pf, win, net = metrics(rmults, pnls)
    if n == 0:
        return f"| {label} | 0 | — | — | — | — |"
    lo, hi = er - ci, er + ci
    mark = " ✅" if lo > 0 else (" ❌" if hi < 0 else "")
    pfs = "inf" if np.isinf(pf) else f"{pf:.2f}"
    return f"| {label} | {n} | {er:+.3f} ±{ci:.3f}{mark} | {pfs} | {win:.1f}% | ${net:,.0f} |"


# ── load ──────────────────────────────────────────────────────────────────────
# FULL=1 runs the entire signal history; otherwise the MenthorQ window.
FULL = os.environ.get("FULL") == "1"
sig = parse_signals(REV)
if FULL:
    win = sig.copy()
else:
    win = sig[(sig["DateTime"] >= WIN_START) & (sig["DateTime"] < WIN_END + pd.Timedelta(days=1))].copy()
bars = pd.read_parquet(BARS_PQ); bars["DateTime"] = pd.to_datetime(bars["DateTime"])
day = bars["DateTime"].dt.normalize()
bbd = {d.date(): g.reset_index(drop=True) for d, g in bars.groupby(day)}
dates = sorted(win["Date"].unique())
log(f"loading ticks for {len(dates)} days")
ticks = {d: massive.load_continuous_ticks(d) for d in dates}
ticks = {d: t for d, t in ticks.items() if t is not None and not t.empty}
log(f"loaded {len(ticks)} days; {len(win)} signals in window")


def first_touch_exit(scan, is_long, stop, target):
    """First of {stop, target} the tick path hits. Returns exit price or None."""
    for p in scan:
        if is_long:
            if p <= stop: return stop
            if p >= target: return target
        else:
            if p >= stop: return stop
            if p <= target: return target
    return None


rows = []  # one dict per signal with baseline + new results
for _, s in win.iterrows():
    d = s["Date"]; bo = bbd.get(d); tk = ticks.get(d)
    if bo is None or tk is None:
        continue
    is_long = s["Direction"].upper()[0] == "L"
    idx = int(s["BarNum"]) - 1
    if idx < 0 or idx >= len(bo):
        continue
    sb = bo.iloc[idx]
    sb_ext = float(sb["Low"]) if is_long else float(sb["High"])
    signal_price = float(s["SignalPrice"])
    extreme = float(s["StopPrice"])
    stop = extreme - TICK if is_long else extreme + TICK
    orisk = abs(signal_price - stop)  # baseline risk (signal → stop)
    if orisk <= 0:
        continue
    t2 = signal_price + orisk if is_long else signal_price - orisk

    ta = tk[tk["DateTime"] > s["DateTime"]]
    if ta.empty:
        continue
    prices = ta["Price"].to_numpy()

    rec = {"SignalType": s["SignalType"], "is_long": is_long}

    # ── baseline: BTC at signal price, exit at original 1R ────────────────────
    bexit = first_touch_exit(prices, is_long, stop, t2)
    if bexit is not None:
        bpnl = (bexit - signal_price) * PT if is_long else (signal_price - bexit) * PT
        rec["base_pnl"] = bpnl
        rec["base_R"] = bpnl / (orisk * PT)

    # ── new entry: must tick to SB extreme, fill at limit 1t inside ───────────
    limit = sb_ext + TICK if is_long else sb_ext - TICK
    if is_long:
        touch = np.where(prices <= sb_ext)[0]
    else:
        touch = np.where(prices >= sb_ext)[0]
    if len(touch):
        ti = touch[0]
        if is_long:
            fm = np.where(prices[ti:] >= limit)[0]
        else:
            fm = np.where(prices[ti:] <= limit)[0]
        if len(fm):
            fi = ti + fm[0]
            entry = prices[fi]
            arisk = abs(entry - stop)
            if arisk > 0:
                scan = prices[fi:]
                # scalp (T1=signal price) and full (T2) independently
                s_exit = first_touch_exit(scan, is_long, stop, signal_price)
                f_exit = first_touch_exit(scan, is_long, stop, t2)
                if s_exit is not None:
                    spnl = (s_exit - entry) * PT if is_long else (entry - s_exit) * PT
                    rec["scalp_pnl"] = spnl; rec["scalp_R"] = spnl / (arisk * PT)
                if f_exit is not None:
                    fpnl = (f_exit - entry) * PT if is_long else (entry - f_exit) * PT
                    rec["full_pnl"] = fpnl; rec["full_R"] = fpnl / (arisk * PT)
    rows.append(rec)

df = pd.DataFrame(rows)
log(f"{len(df)} signals processed")

# ── report ────────────────────────────────────────────────────────────────────
emit("# RevFT SB-Extreme Entry vs Baseline — Per Setup Type\n")
_wlo = win["DateTime"].min().date(); _whi = win["DateTime"].max().date()
emit(f"**Date:** July 6, 2026  ·  **Window:** {_wlo} – {_whi}  ·  "
     f"**Signals:** {len(df)}\n")
emit("- **Baseline:** BTC at signal price → original 1R target")
emit("- **New:** limit 1t inside SB extreme (must tick to SB extreme) → Full = original 1R")
emit("- **Stop:** CSV extreme ∓1t (long −, short +), same for both methods")
emit("- R measured off each method's own entry→stop distance\n")

types = ["BO", "IB", "OB", "Sneaky", "Trap"]

def block(title, base_col, new_col):
    emit(f"## {title}\n")
    emit("| Setup | Baseline n | Base ExpR | Base PF | Base Win% | Base Net$ "
         "| New n | New ExpR | New PF | New Win% | New Net$ |")
    emit("|---|---|---|---|---|---|---|---|---|---|---|")
    for t in types + ["ALL"]:
        sub = df if t == "ALL" else df[df["SignalType"] == t]
        b = sub.dropna(subset=[base_col])
        nw = sub.dropna(subset=[new_col])
        bn, ber, bci, bpf, bwin, bnet = metrics(b[base_col], b[base_col + "_pnl" if False else base_col.replace("_R","_pnl")])
        nn, ner, nci, npf, nwin, nnet = metrics(nw[new_col], nw[new_col.replace("_R","_pnl")])
        bpfs = "inf" if np.isinf(bpf) else (f"{bpf:.2f}" if bn else "—")
        npfs = "inf" if np.isinf(npf) else (f"{npf:.2f}" if nn else "—")
        bmark = "" if bn == 0 else (" ✅" if ber - bci > 0 else (" ❌" if ber + bci < 0 else ""))
        nmark = "" if nn == 0 else (" ✅" if ner - nci > 0 else (" ❌" if ner + nci < 0 else ""))
        lab = "**ALL**" if t == "ALL" else t
        emit(f"| {lab} | {bn} | {ber:+.3f}{bmark} | {bpfs} | {bwin:.0f}% | ${bnet:,.0f} "
             f"| {nn} | {ner:+.3f}{nmark} | {npfs} | {nwin:.0f}% | ${nnet:,.0f} |")
    emit("")

block("Full target (original 1R): Baseline vs New Entry", "base_R", "full_R")

# scalp-only table
emit("## New Entry — Scalp target (→ signal price)\n")
emit("| Setup | n | ExpR | PF | Win% | Net$ |")
emit("|---|---|---|---|---|---|")
for t in types + ["ALL"]:
    sub = df if t == "ALL" else df[df["SignalType"] == t]
    sc = sub.dropna(subset=["scalp_R"])
    lab = "**ALL**" if t == "ALL" else t
    emit(row(lab, sc["scalp_R"], sc["scalp_pnl"]))
emit("")

OUT.write_text("\n".join(L), encoding="utf-8")
log(f"written {OUT}")
