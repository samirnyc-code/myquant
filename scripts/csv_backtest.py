"""NT MyReversals RTH export -> full setup table + sequential backtest with target sweep.

PART 1: every setup with date/time/b#/dir/type/LMT/stop and bars-to-fill (pure pullback
        fill in isolation: away-move then tick THROUGH the limit; min 2 bars; RTH only).

PART 2: sequential intraday sim (flat by EOD), one position at a time.
  - Entry: pending limit at LMT fills on the pullback tick-through (long Low<LMT / short High>LMT
    after a fresh away-extreme beyond the setup bar). Entry price = LMT. risk = |LMT-stop|.
  - Exit: first of  stop (touch: long Low<=stop / short High>=stop),  target (T*risk, touch),
    EOD (last-bar close).  Intrabar: stop assumed before target.
  - OPPOSITE signal cancels the prior trade: a new signal opposite the open position closes it
    at that setup bar's close; the new signal becomes the pending order. Same-dir signal while
    in a position is ignored. A new signal always replaces a still-pending (unfilled) order.
  - Target sweep: 1,1.5,2,2.5,3,4,5 R and EOD-hold (no target). Frictionless, R-based
    (ES = $50/pt for the $ column; no commission).
Saves dated CSVs.
"""
import json, glob, csv
from pathlib import Path
from datetime import date as _date

WT = Path(__file__).resolve().parent.parent
TLET = {"BO": "B", "Trap": "T", "IB": "I", "OB": "O"}
f = sorted(glob.glob(str(WT / "data/signals/*RTH*Days.txt")))[-1]

sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit():
        continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    d, m, y = dt.split("/")
    num = lambda s: round(float(s.replace(",", "")), 2)
    sigs.append(dict(rt=rt, long=dr.lower().startswith("l"), date=f"{y}-{m}-{d}",
                     time=tm, bn=int(bn), ft=int(bn) - 1, stop=num(stop), lmt=num(lmt)))

cache = {}
def bars(dt):
    if dt not in cache:
        cache[dt] = json.load(open(WT / f"data/annotations/book_review/{dt}.json"))["bars"]
    return cache[dt]

# ---- pure fill (isolated) ----
def fill_bar(s):
    b = bars(s["date"]); n = len(b); ft = s["ft"]; lmt = s["lmt"]; long = s["long"]
    slo, shi = b[ft][4], b[ft][3]; away = False
    for i in range(ft + 1, n):
        hi, lo = b[i][3], b[i][4]
        if long:
            if away and lo < lmt: return i, i - ft
            if hi > shi: away = True
        else:
            if away and hi > lmt: return i, i - ft
            if lo < slo: away = True
    return None, None

# PART 1 table
rows1 = []
for k, s in enumerate(sigs, 1):
    fb, btf = fill_bar(s)
    rows1.append(dict(n=k, date=s["date"], time=s["time"], bar=s["bn"],
                      dir="L" if s["long"] else "S", type=s["rt"], lmt=s["lmt"],
                      stop=s["stop"], risk=round(abs(s["lmt"] - s["stop"]), 2),
                      bars_to_fill=btf if btf is not None else ""))
with open(WT / f"data/signals/csv_setups_table_{_date.today()}.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows1[0])); w.writeheader(); w.writerows(rows1)

print(f"PART 1 - ALL {len(rows1)} SETUPS  (bars_to_fill = pure pullback fill, blank = never filled in session)\n")
print(f"{'#':>3} {'date':<10} {'time':<8} {'b#':>3} {'d':<1} {'type':<4} {'LMT':>9} {'stop':>9} {'risk':>5} {'fill(bars)':>10}")
for r in rows1:
    print(f"{r['n']:>3} {r['date']:<10} {r['time']:<8} {r['bar']:>3} {r['dir']:<1} {r['type']:<4} "
          f"{r['lmt']:>9} {r['stop']:>9} {r['risk']:>5} {str(r['bars_to_fill']):>10}")

# ---- PART 2 sequential sim ----
by_day = {}
for s in sigs:
    by_day.setdefault(s["date"], []).append(s)
for d in by_day:
    by_day[d].sort(key=lambda x: x["ft"])

def simulate(T):
    """T = R-multiple target, or None for EOD-hold. Returns list of closed trades."""
    trades = []
    for d, day_sigs in by_day.items():
        b = bars(d); n = len(b)
        sig_at = {}
        for s in day_sigs:
            sig_at.setdefault(s["ft"], []).append(s)
        pos = 0; entry = stop = tgt = risk = 0.0; pdir = 0; ptype = None; entry_bar = 0
        pend = None  # dict: long,lmt,stop,sig_bar,away,rt
        for i in range(n):
            hi, lo, cl = b[i][3], b[i][4], b[i][5]
            # 1) exit open position on stop/target (stop priority)
            if pos != 0:
                exit_r = None; why = None
                if pos == 1:
                    if lo <= stop: exit_r, why = -1.0, "stop"
                    elif tgt is not None and hi >= tgt: exit_r, why = T, "target"
                else:
                    if hi >= stop: exit_r, why = -1.0, "stop"
                    elif tgt is not None and lo <= tgt: exit_r, why = T, "target"
                if exit_r is not None:
                    trades.append(dict(date=d, dir="L" if pos == 1 else "S", type=ptype,
                                       entry=entry, risk=risk, R=exit_r, why=why, bars=i - entry_bar))
                    pos = 0
            # 2) try to fill pending (needs away established on an earlier bar)
            if pend is not None and i > pend["sig_bar"]:
                lmt = pend["lmt"]
                if pend["long"]:
                    if pend["away"] and lo < lmt:
                        pos = 1; entry = lmt; stop = pend["stop"]; risk = abs(entry - stop)
                        tgt = None if T is None else entry + T * risk; pdir = 1; ptype = pend["rt"]; entry_bar = i; pend = None
                    elif hi > b[pend["sig_bar"]][3]: pend["away"] = True
                elif pend is not None:
                    if pend["away"] and hi > lmt:
                        pos = -1; entry = lmt; stop = pend["stop"]; risk = abs(entry - stop)
                        tgt = None if T is None else entry - T * risk; pdir = -1; ptype = pend["rt"]; entry_bar = i; pend = None
                    elif lo < b[pend["sig_bar"]][4]: pend["away"] = True
            # 3) new signal(s) firing at this bar close -> opposite-cancel + set pending
            for s in sig_at.get(i, []):
                nd = 1 if s["long"] else -1
                if pos != 0 and nd != pos:                       # opposite cancels open trade at this close
                    exit_r = (cl - entry) / risk * pos
                    trades.append(dict(date=d, dir="L" if pos == 1 else "S", type=ptype,
                                       entry=entry, risk=risk, R=round(exit_r, 3), why="opp-cxl", bars=i - entry_bar))
                    pos = 0
                if pos == 0:                                     # (flat) newest signal becomes the pending order
                    pend = dict(long=s["long"], lmt=s["lmt"], stop=s["stop"], sig_bar=s["ft"], away=False, rt=s["rt"])
                # if same-dir while in a position: ignored
        # EOD: close any open position at last close
        if pos != 0:
            exit_r = (b[n - 1][5] - entry) / risk * pos
            trades.append(dict(date=d, dir="L" if pos == 1 else "S", type=ptype,
                               entry=entry, risk=risk, R=round(exit_r, 3), why="eod", bars=n - 1 - entry_bar))
    return trades

TARGETS = [1, 1.5, 2, 2.5, 3, 4, 5, None]
print("\n\nPART 2 - TARGET SWEEP (sequential, opposite-signal cancels prior trade; frictionless, R-based)\n")
print(f"{'target':>7} {'trades':>6} {'win%':>5} {'avgR':>6} {'totR':>7} {'$/ES':>9} | {'stop%':>5} {'tgt%':>5} {'opp%':>5} {'eod%':>5}")
sweep_rows = []
for T in TARGETS:
    tr = simulate(T)
    nt = len(tr)
    if nt == 0: continue
    wins = [t for t in tr if t["R"] > 0]
    totR = sum(t["R"] for t in tr)
    usd = sum(t["R"] * t["risk"] * 50 for t in tr)   # ES $50/pt, R*risk = points
    br = lambda w: 100 * sum(1 for t in tr if t["why"] == w) / nt
    lab = "EOD" if T is None else f"{T}R"
    print(f"{lab:>7} {nt:>6} {100*len(wins)/nt:>5.0f} {totR/nt:>6.2f} {totR:>7.1f} {usd:>9,.0f} | "
          f"{br('stop'):>5.0f} {br('target'):>5.0f} {br('opp-cxl'):>5.0f} {br('eod'):>5.0f}")
    sweep_rows.append(dict(target=lab, trades=nt, win_pct=round(100*len(wins)/nt, 1),
                           avg_R=round(totR/nt, 3), tot_R=round(totR, 2), usd_ES=round(usd, 0),
                           stop_pct=round(br("stop"), 1), tgt_pct=round(br("target"), 1),
                           opp_pct=round(br("opp-cxl"), 1), eod_pct=round(br("eod"), 1)))
with open(WT / f"data/signals/csv_target_sweep_{_date.today()}.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(sweep_rows[0])); w.writeheader(); w.writerows(sweep_rows)
print(f"\nsaved csv_setups_table_{_date.today()}.csv + csv_target_sweep_{_date.today()}.csv")
