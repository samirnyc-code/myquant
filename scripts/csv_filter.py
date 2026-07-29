"""Filter the INDEPENDENT NT-export trades by (a) price vs SMA20-D and (b) phase-machine
regime at the signal bar. Same entry/exit as csv_backtest_indep.py (pullback tick-through,
no opp-cancel, no order-expiry). Reports Total R at 1R and EOD, ALL + by type.

Gates (side = long/short of the signal):
  with-MA   : long only if signal-bar close > SMA20-D ; short only if close < SMA20-D
  against-MA: the opposite
  with-regime: long only in BULL ; short only in BEAR   (skip NEUTRAL / wrong regime)
Frictionless, R-based.
"""
import json, glob
from pathlib import Path
from datetime import date as _date

WT = Path(__file__).resolve().parent.parent
f = sorted(glob.glob(str(WT / "data/signals/*RTH*Days.txt")))[-1]
sigs = []
for ln in open(f, encoding="utf-8"):
    p = ln.split()
    if len(p) != 9 or not p[0].isdigit():
        continue
    _, rt, dr, dt, tm, bn, btc, stop, lmt = p
    dd, mm, yy = dt.split("/")
    num = lambda s: round(float(s.replace(",", "")), 2)
    sigs.append(dict(rt=rt, long=dr.lower().startswith("l"), date=f"{yy}-{mm}-{dd}",
                     ft=int(bn) - 1, stop=num(stop), lmt=num(lmt)))

cache = {}
def day(dt):
    if dt not in cache:
        cache[dt] = json.loads(open(WT / f"data/annotations/book_review/{dt}.json").read())
    return cache[dt]

def regime_at(d, i):
    for s in d.get("regime", []):
        if s["from"] <= i <= s["to"]:
            return s["mode"]
    return None

def trade(s, T):
    d = day(s["date"]); b = d["bars"]; n = len(b); ft = s["ft"]; lmt = s["lmt"]; long = s["long"]; stop = s["stop"]
    slo, shi = b[ft][4], b[ft][3]; away = False; fb = None
    for i in range(ft + 1, n):
        hi, lo = b[i][3], b[i][4]
        if long:
            if away and lo < lmt: fb = i; break
            if hi > shi: away = True
        else:
            if away and hi > lmt: fb = i; break
            if lo < slo: away = True
    if fb is None:
        return None
    entry = lmt; risk = abs(entry - stop)
    tgt = None if T is None else (entry + T * risk if long else entry - T * risk)
    for j in range(fb, n):
        hi, lo = b[j][3], b[j][4]
        if long:
            if lo <= stop: return dict(R=-1.0, rt=s["rt"])
            if tgt is not None and hi >= tgt: return dict(R=T, rt=s["rt"])
        else:
            if hi >= stop: return dict(R=-1.0, rt=s["rt"])
            if tgt is not None and lo <= tgt: return dict(R=T, rt=s["rt"])
    r = (b[n - 1][5] - entry) / risk * (1 if long else -1)
    return dict(R=round(r, 3), rt=s["rt"])

def gate(s, kind):
    d = day(s["date"]); close = d["bars"][s["ft"]][5]; sma = d.get("sma20")
    if kind == "all": return True
    if kind in ("withMA", "againstMA"):
        if sma is None: return False
        w = (close > sma) if s["long"] else (close < sma)
        return w if kind == "withMA" else (not w)
    if kind == "withRegime":
        m = regime_at(d, s["ft"])
        return (m == "BULL") if s["long"] else (m == "BEAR")
    return True

def totrow(kind, T, drop_trap=False):
    trs = []
    for s in sigs:
        if drop_trap and s["rt"] == "Trap": continue
        if not gate(s, kind): continue
        t = trade(s, T)
        if t: trs.append(t)
    n = len(trs); totR = sum(t["R"] for t in trs)
    wins = sum(1 for t in trs if t["R"] > 0)
    tt = lambda rt: round(sum(t["R"] for t in trs if t["rt"] == rt), 1)
    return dict(n=n, win=(round(100*wins/n) if n else 0), totR=round(totR, 1),
                Trap=tt("Trap"), BO=tt("BO"), IB=tt("IB"))

for T, tlab in [(1, "1R"), (None, "EOD")]:
    print(f"\n===== target = {tlab} =====")
    print(f"  {'filter':<14} {'n':>3} {'win%':>4} {'totR':>7} | {'Trap':>6} {'BO':>6} {'IB':>6}")
    for kind, lab in [("all", "no filter"), ("withMA", "with SMA20-D"),
                      ("againstMA", "against SMA20-D"), ("withRegime", "with-regime")]:
        r = totrow(kind, T)
        print(f"  {lab:<14} {r['n']:>3} {r['win']:>4} {r['totR']:>7} | {r['Trap']:>6} {r['BO']:>6} {r['IB']:>6}")
    # best combos: drop Trap + gate
    for kind, lab in [("all", "dropTrap"), ("withMA", "dropTrap+SMA20"), ("withRegime", "dropTrap+regime")]:
        r = totrow(kind, T, drop_trap=True)
        print(f"  {lab:<14} {r['n']:>3} {r['win']:>4} {r['totR']:>7} | {'--':>6} {r['BO']:>6} {r['IB']:>6}")
