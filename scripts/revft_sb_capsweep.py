"""RevFT SB-extreme entry — bars-to-fill cap sweep, full dataset, year-by-year.

Constant-risk sizing ($500/trade) so R and $ agree. Full target = original 1R.
Records bars-to-fill; sweeps a "cancel entry if unfilled within N bars" cap and
checks year-by-year stability (the real out-of-sample test for the cap idea).

Bar mapping: signal bar = iloc[BarNum-1]. Stop = CSV extreme ∓1t.
Set FULL=1 for entire history; else the MenthorQ window.
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

TICK = 0.25; PT = 50.0; RISK = 500.0; BARSEC = 300
FULL = os.environ.get("FULL") == "1"
REV = ROOT / "data" / "signals" / \
    "MyReversals Signal Export - ES SEP26 - 5 Minute from 02.07.2026 - 1850 Days.txt"
OUT = ROOT / "docs" / "living" / (
    "revft_sb_capsweep_fulldata_20260706.md" if FULL else "revft_sb_capsweep_window_20260706.md")

L = []
def emit(s=""): print(s, flush=True); L.append(s)
def log(m): print(f"[cap] {m}", flush=True)


def fte(scan, is_long, stop, tg):
    for p in scan:
        if is_long:
            if p <= stop: return stop
            if p >= tg: return tg
        else:
            if p >= stop: return stop
            if p <= tg: return tg
    return None


sig = parse_signals(REV)
win = sig.copy() if FULL else \
    sig[(sig["DateTime"] >= WIN_START) & (sig["DateTime"] < WIN_END + pd.Timedelta(days=1))].copy()
bars = pd.read_parquet(BARS_PQ); bars["DateTime"] = pd.to_datetime(bars["DateTime"])
day = bars["DateTime"].dt.normalize()
bbd = {d.date(): g.reset_index(drop=True) for d, g in bars.groupby(day)}
dates = sorted(win["Date"].unique())
log(f"loading ticks for {len(dates)} days")
ticks = {d: massive.load_continuous_ticks(d) for d in dates}
ticks = {d: t for d, t in ticks.items() if t is not None and not t.empty}
log(f"loaded {len(ticks)} days; {len(win)} signals")

rows = []
for _, s in win.iterrows():
    d = s["Date"]; bo = bbd.get(d); tk = ticks.get(d)
    if bo is None or tk is None: continue
    is_long = s["Direction"].upper()[0] == "L"; idx = int(s["BarNum"]) - 1
    if idx < 0 or idx >= len(bo): continue
    sb = bo.iloc[idx]; sb_ext = float(sb["Low"]) if is_long else float(sb["High"])
    sp = float(s["SignalPrice"]); ext = float(s["StopPrice"])
    stop = ext - TICK if is_long else ext + TICK
    orisk = abs(sp - stop)
    if orisk <= 0: continue
    t2 = sp + orisk if is_long else sp - orisk
    ta = tk[tk["DateTime"] > s["DateTime"]]
    if ta.empty: continue
    pr = ta["Price"].to_numpy(); tms = ta["DateTime"].to_numpy()
    limit = sb_ext + TICK if is_long else sb_ext - TICK
    touch = np.where(pr <= sb_ext)[0] if is_long else np.where(pr >= sb_ext)[0]
    if not len(touch): continue
    ti = touch[0]
    fm = np.where(pr[ti:] >= limit)[0] if is_long else np.where(pr[ti:] <= limit)[0]
    if not len(fm): continue
    fi = ti + fm[0]; entry = pr[fi]; arisk = abs(entry - stop)
    if arisk <= 0: continue
    btf = int(np.ceil((pd.Timestamp(tms[fi]) - s["DateTime"]).total_seconds() / BARSEC))
    fx = fte(pr[fi:], is_long, stop, t2)
    if fx is None: continue
    contracts = RISK / (arisk * PT)
    fpnl = ((fx - entry) if is_long else (entry - fx)) * PT * contracts
    rows.append(dict(type=s["SignalType"], year=s["DateTime"].year, btf=btf,
                     R=fpnl / RISK, pnl=fpnl))

df = pd.DataFrame(rows)
log(f"{len(df)} full-resolved filled trades")

_wlo = win["DateTime"].min().date(); _whi = win["DateTime"].max().date()
emit("# RevFT SB-Extreme Entry — Bars-to-Fill Cap Sweep (Full target, constant-risk)\n")
emit(f"**Window:** {_wlo} – {_whi} · **Filled+resolved trades:** {len(df)} · "
     f"**Sizing:** ${RISK:.0f}/trade constant risk\n")

emit("## Bars-to-fill distribution\n")
emit("| pct | bars |")
emit("|---|---|")
for q in [.25, .5, .75, .9, .95, 1.0]:
    emit(f"| {int(q*100)}% | {df['btf'].quantile(q):.0f} |")
emit("")


def mstat(g):
    n = len(g)
    if n == 0: return 0, np.nan, np.nan, np.nan, 0.0
    r = g["R"].to_numpy(); ci = 1.96 * r.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    return n, r.mean(), ci, 100 * (g["pnl"] > 0).mean(), g["pnl"].sum()

emit("## Cap sweep — cancel entry if unfilled within N bars\n")
emit("| Cap | fills | fill% | meanR | 95%CI | Win% | Net$ |")
emit("|---|---|---|---|---|---|---|")
tot = len(df)
for N in [1, 2, 3, 4, 5, 6, 8, 10, 999]:
    g = df[df["btf"] <= N]; n, er, ci, w, net = mstat(g)
    lab = "none" if N == 999 else str(N)
    mark = " ✅" if er - ci > 0 else (" ❌" if er + ci < 0 else "")
    emit(f"| {lab} | {n} | {100*n/tot:.0f}% | {er:+.3f}{mark} | ±{ci:.3f} | {w:.0f}% | ${net:,.0f} |")
emit("")

emit("## Year-by-year — the out-of-sample stability test\n")
emit("Rows = fill-cap; columns = year (meanR). ✅/❌ = 95% CI excludes 0.\n")
years = sorted(df["year"].unique())
emit("| Cap | " + " | ".join(str(y) for y in years) + " | ALL |")
emit("|---|" + "|".join("---" for _ in years) + "|---|")
for N in [1, 2, 3, 4, 6, 999]:
    cells = []
    sub = df[df["btf"] <= N]
    for y in years:
        g = sub[sub["year"] == y]; n, er, ci, w, net = mstat(g)
        if n == 0: cells.append("—"); continue
        mark = "✅" if er - ci > 0 else ("❌" if er + ci < 0 else "")
        cells.append(f"{er:+.3f}{mark}(n{n})")
    n, er, ci, w, net = mstat(sub)
    amark = "✅" if er - ci > 0 else ("❌" if er + ci < 0 else "")
    lab = "none" if N == 999 else f"≤{N}"
    emit(f"| {lab} | " + " | ".join(cells) + f" | {er:+.3f}{amark} |")
emit("")

emit("## Cap ≤1 bar, by setup type (the best-looking cap)\n")
emit("| Setup | n | meanR | 95%CI | Win% | Net$ |")
emit("|---|---|---|---|---|---|")
c1 = df[df["btf"] <= 1]
for t in ["BO", "IB", "OB", "Sneaky", "Trap", "ALL"]:
    g = c1 if t == "ALL" else c1[c1["type"] == t]
    n, er, ci, w, net = mstat(g)
    if n == 0: emit(f"| {t} | 0 | — | — | — | — |"); continue
    mark = " ✅" if er - ci > 0 else (" ❌" if er + ci < 0 else "")
    emit(f"| {'**'+t+'**' if t=='ALL' else t} | {n} | {er:+.3f}{mark} | ±{ci:.3f} | {w:.0f}% | ${net:,.0f} |")
emit("")

OUT.write_text("\n".join(L), encoding="utf-8")
log(f"written {OUT}")
