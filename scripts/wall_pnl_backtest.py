"""Wall-source 0DTE P&L backtest — replicates the desk's gx_bps+gx_bcs exactly,
swapping ONLY the walls. Priced from ThetaData. See docs/research_notes/
wall_pnl_backtest_spec.md.

STAGE 1 (this file, --stage timestop): entry at the open (touch fill) -> exit at the
14:45 CT time-stop (touch). No intraday management yet (level-acceptance = Stage 2).
Holiday-correct calendar (market_calendar). NO dropped days. Fills = marketable touch.
Real IB fees on entry AND exit.

Sources: gx (gexlog published), td (ThetaData per-side calibration), fx (fixed-offset
baseline, spot±OFFSET). MenthorQ dropped per decision.

Entry time: 08:30 CT (09:30 ET) normal; 09:05 CT (10:05 ET) on WAIT days (playbook_wait
from that day's saved gexlog brief, or a missing/blocked brief). Exit: 14:45 CT (15:45 ET);
12:15 CT (13:15 ET) on early-close days.

Usage:
  python scripts/wall_pnl_backtest.py --stage timestop --verify 2026-06-01   # trace 1 day
  python scripts/wall_pnl_backtest.py --stage timestop                        # full pilot
"""
import argparse
import csv
import glob
import json
import os
import statistics as st
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import market_calendar as MC

RAW = ROOT / "data/gexlog/raw"
SIM = ROOT / "data/options_sim"
OUTCSV = SIM / "wall_pnl_backtest.csv"
OUTHTML = ROOT / "data/gexlog/reports/wall_pnl_backtest.html"
BASE = "http://127.0.0.1:25503/v3"
WING = 25.0
FEE = 1.63
STEP = 5.0
SOURCES = ["gx", "td", "fx"]
LABEL = {"gx": "gexlog", "td": "ThetaData", "fx": "fixed-offset"}
# CT->ET is +1h. Open 08:30 CT = 09:30 ET; use 09:31 for a fresh post-open NBBO.
ENTRY_NORMAL_ET = "09:31:00"
ENTRY_WAIT_ET = "10:06:00"      # 09:05 CT + 1min
TIMESTOP_ET = "15:45:00"        # 14:45 CT
TIMESTOP_EARLY_ET = "13:15:00"  # 12:15 CT (early-close days)


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def g(d, *ks, default=None):
    for k in ks:
        d = d.get(k) if isinstance(d, dict) else None
    return d if d is not None else default


def rnd(x):
    return round(x / STEP) * STEP if x is not None else None


# ---------------------------------------------------------------- TD
def td_get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception:
        return None
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if len(lines) < 2 or lines[0].lstrip().startswith("<"):
        return None
    h = [x.strip().strip('"') for x in lines[0].split(",")]
    return dict(zip(h, [x.strip().strip('"') for x in lines[-1].split(",")]))


_cache = {}


def nbbo(date, strike, right, et):
    """(bid, ask) as-of `et` ET; None if no/crossed quote."""
    key = (date, strike, right, et)
    if key in _cache:
        return _cache[key]
    exp = date.replace("-", "")
    r = td_get(f"/option/at_time/quote?symbol=SPXW&expiration={exp}&strike={strike:.3f}"
               f"&right={right}&start_date={exp}&end_date={exp}&time_of_day={et}&format=csv")
    out = (None, None)
    if r:
        b, a = fnum(r.get("bid")), fnum(r.get("ask"))
        if b is not None and a is not None and a >= b >= 0:
            out = (b, a)
    _cache[key] = out
    return out


# ---------------------------------------------------------------- walls / brief
def gexlog_day(date):
    f = RAW / f"{date}_morning.json"
    if not f.exists():
        return None
    d = json.load(open(f, encoding="utf-8"))
    pb = d.get("playbook") or {}
    wait = any("wait" in ((p.get("trigger") or "") + (p.get("bias") or "")).lower()
               for p in pb.values() if isinstance(p, dict))
    blind = bool(d.get("error"))
    return dict(spot=fnum(g(d, "levels", "current")),
                pw=rnd(fnum(g(d, "levels", "putWall"))), cw=rnd(fnum(g(d, "levels", "callWall"))),
                wait=wait or blind)


def td_walls(date, spot):
    f = SIM / f"td_gex_calib_{date}.csv"
    if not f.exists() or spot is None:
        return None, None
    rows = [dict(K=fnum(r["strike"]), cr=fnum(r["call_raw"]), pr=fnum(r["put_raw"]))
            for r in csv.DictReader(open(f, encoding="utf-8"))]
    above = [r for r in rows if r["K"] and r["cr"] is not None and r["K"] > spot]
    below = [r for r in rows if r["K"] and r["pr"] is not None and r["K"] < spot]
    cw = max(above, key=lambda r: r["cr"])["K"] if above else None
    pw = min(below, key=lambda r: r["pr"])["K"] if below else None
    return pw, cw


# ---------------------------------------------------------------- P&L
def vertical(date, short_k, right, entry_et, exit_et, trace=None):
    """Touch-fill credit spread: enter (sell) short_bid-long_ask; exit (buy) short_ask-long_bid.
    Returns dict with credit/debit/pnl/legs, or None if any leg unquoted."""
    long_k = short_k - WING if right == "P" else short_k + WING
    opt = "put" if right == "P" else "call"
    sb, sa = nbbo(date, short_k, opt, entry_et)
    lb, la = nbbo(date, long_k, opt, entry_et)
    if None in (sb, sa, lb, la):
        return None
    credit = sb - la                       # sell short @bid, buy long @ask (marketable)
    xsb, xsa = nbbo(date, short_k, opt, exit_et)
    xlb, xla = nbbo(date, long_k, opt, exit_et)
    if None in (xsb, xsa, xlb, xla):
        return None
    debit = xsa - xlb                      # buy short @ask, sell long @bid (marketable close)
    pnl = (credit - debit) * 100 - 8 * FEE  # 4 legs entry + 4 legs exit
    if trace is not None:
        trace.append(f"    {opt} {short_k:.0f}/{long_k:.0f}: enter {sb:.2f}-{la:.2f}={credit:+.2f} "
                     f"exit {xsa:.2f}-{xlb:.2f}={debit:+.2f}  P&L ${pnl:,.2f}")
    return dict(credit=credit, debit=debit, pnl=pnl)


def run_day(date, offset, trace=None):
    gx = gexlog_day(date)
    if not gx or gx["spot"] is None:
        return None
    spot = gx["spot"]
    entry_et = ENTRY_WAIT_ET if gx["wait"] else ENTRY_NORMAL_ET
    dd = datetime.strptime(date, "%Y-%m-%d").date()
    exit_et = TIMESTOP_EARLY_ET if MC.day_type(dd)[0] == "early" else TIMESTOP_ET
    walls = {"gx": (gx["pw"], gx["cw"]),
             "td": td_walls(date, spot),
             "fx": (rnd(spot - offset), rnd(spot + offset))}
    if trace is not None:
        trace.append(f"  spot {spot:.1f} | entry {entry_et}{' (WAIT)' if gx['wait'] else ''} "
                     f"| exit {exit_et}")
    row = {"date": date, "spot": spot, "entry_et": entry_et, "exit_et": exit_et, "wait": gx["wait"]}
    for s in SOURCES:
        pw, cw = walls[s]
        row[f"{s}_pw"], row[f"{s}_cw"] = pw, cw
        if pw is None or cw is None or not (pw < spot < cw):
            row[f"{s}_bps"] = row[f"{s}_bcs"] = row[f"{s}_pnl"] = None
            row[f"{s}_note"] = "no OTM condor" if (pw and cw) else "no wall"
            continue
        if trace is not None:
            trace.append(f"  [{LABEL[s]}] put {pw:.0f} / call {cw:.0f}")
        bps = vertical(date, pw, "P", entry_et, exit_et, trace)
        bcs = vertical(date, cw, "C", entry_et, exit_et, trace)
        row[f"{s}_bps"] = bps["pnl"] if bps else None
        row[f"{s}_bcs"] = bcs["pnl"] if bcs else None
        row[f"{s}_pnl"] = (bps["pnl"] + bcs["pnl"]) if (bps and bcs) else None
        row[f"{s}_note"] = "" if (bps and bcs) else "leg unquoted"
    return row


def pilot_dates():
    return sorted(os.path.basename(f)[:10] for f in glob.glob(str(SIM / "td_gex_calib_2026-*.csv")))


def summarize(rows):
    agg = {}
    for s in SOURCES:
        p = [r[f"{s}_pnl"] for r in rows if r.get(f"{s}_pnl") is not None]
        agg[s] = dict(n=len(p), total=sum(p), wins=sum(1 for x in p if x > 0),
                      avg=(sum(p) / len(p) if p else 0),
                      worst=min(p) if p else 0, best=max(p) if p else 0)
    return agg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="timestop", choices=["timestop"])
    ap.add_argument("--offset", type=float, default=35.0)
    ap.add_argument("--verify", help="trace a single date and exit")
    a = ap.parse_args()

    if a.verify:
        tr = [f"===== VERIFY {a.verify} (stage={a.stage}) ====="]
        row = run_day(a.verify, a.offset, trace=tr)
        print("\n".join(tr))
        if row:
            for s in SOURCES:
                print(f"  {LABEL[s]:>12}: bps {row.get(f'{s}_bps')}  bcs {row.get(f'{s}_bcs')}  "
                      f"total {row.get(f'{s}_pnl')}  {row.get(f'{s}_note','')}")
        return

    dates = pilot_dates()
    print(f"pilot: {len(dates)} days ({dates[0]}..{dates[-1]}), stage={a.stage}")
    rows = []
    for i, dt in enumerate(dates):
        r = run_day(dt, a.offset)
        if r:
            rows.append(r)
        if i % 10 == 0:
            print(f"  {i}/{len(dates)} {dt}")
    cols = sorted({k for r in rows for k in r}, key=lambda c: (c != "date", c))
    with open(OUTCSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    agg = summarize(rows)
    print(f"\n{'source':>12} {'total$':>10} {'n':>4} {'win%':>6} {'avg$':>7} {'best$':>8} {'worst$':>9}")
    for s in SOURCES:
        x = agg[s]
        wr = 100 * x['wins'] / x['n'] if x['n'] else 0
        print(f"{LABEL[s]:>12} {x['total']:>10,.0f} {x['n']:>4} {wr:>5.0f}% {x['avg']:>7,.0f} "
              f"{x['best']:>8,.0f} {x['worst']:>9,.0f}")
    print(f"  gexlog−TD: {agg['gx']['total']-agg['td']['total']:+,.0f}   "
          f"gexlog−baseline: {agg['gx']['total']-agg['fx']['total']:+,.0f}")
    print(f"-> {OUTCSV}")


if __name__ == "__main__":
    main()
