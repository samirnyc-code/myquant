"""flip_why_no_short.py — per-bar diagnostic: why did/didn't a flip fire (S119).

Prints, for each 2000t bar in a date+time window, the exact quantities the DEPLOYED
signal rule uses, so we can say precisely why a short/long did or did not trigger:
  climax flag, tempo pctile, IBS, body(ticks), color, and the pair verdict vs the
  prior bar (needs: both climax, adjacent, bar1 color != SB dir, SB IBS 0.55/0.45,
  SB body >= 4t, bar1 non-doji).

    python tempo/scripts/flip_why_no_short.py 2026-09-14 09:55 10:10
"""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ENG = ROOT / "tempo" / "outputs" / "tempo_engine_bars.parquet"
TICK = 0.25
MINBODY = 4


def ibs(r):
    rg = r.high - r.low
    return (r.close - r.low) / rg if rg > TICK / 2 else 0.5


def sbdir(r):
    x = ibs(r)
    return 1 if x >= 0.55 else (-1 if x <= 0.45 else 0)   # 1 bull, -1 bear, 0 dead


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else "2026-09-14"
    t0 = sys.argv[2] if len(sys.argv) > 2 else "09:55"
    t1 = sys.argv[3] if len(sys.argv) > 3 else "10:10"
    df = pd.read_parquet(ENG)
    d = df[df["date"] == date].sort_values("bar").reset_index(drop=True)
    d["hhmm"] = pd.to_datetime(d["start"]).dt.strftime("%H:%M:%S")
    w = d[(d["hhmm"] >= t0) & (d["hhmm"] <= t1 + ":99")].copy()
    if w.empty:
        print(f"no bars for {date} in {t0}..{t1}"); return
    print(f"{date}  bars {t0}..{t1}  (climax share needs tempo pctile >= climactic pct)")
    print(f"{'bar':>4} {'time':>8} {'O':>8} {'H':>8} {'L':>8} {'C':>8} "
          f"{'tpct':>5} {'CLMX':>4} {'IBS':>5} {'body_t':>6} {'color':>5} {'SBdir':>5}")
    for r in w.itertuples():
        body_t = round(abs(r.close - r.open) / TICK, 1)
        color = "bull" if r.close >= r.open else "bear"
        sd = {1: "bull", -1: "bear", 0: "dead"}[sbdir(r)]
        print(f"{r.bar:>4} {r.hhmm:>8} {r.open:>8.2f} {r.high:>8.2f} {r.low:>8.2f} "
              f"{r.close:>8.2f} {r.tpct:>5.0f} {'YES' if r.climax else '-':>4} "
              f"{ibs(r):>5.2f} {body_t:>6.1f} {color:>5} {sd:>5}")

    # evaluate every adjacent pair in the window as a flip
    print("\npair verdicts (bar_i-1 -> bar_i):")
    ws = w.reset_index(drop=True)
    for i in range(1, len(ws)):
        a, b = ws.iloc[i - 1], ws.iloc[i]
        reasons = []
        if not (a.climax and b.climax):
            reasons.append(f"not both climax (bar1 {'Y' if a.climax else 'N'}/SB {'Y' if b.climax else 'N'})")
        if abs(a.close - a.open) < TICK / 2:
            reasons.append("bar1 doji")
        d2 = sbdir(b)
        if d2 == 0:
            reasons.append(f"SB IBS dead-zone ({ibs(b):.2f}, needs>=.55 or <=.45)")
        if abs(b.close - b.open) / TICK < MINBODY:
            reasons.append(f"SB body {abs(b.close-b.open)/TICK:.1f}t < {MINBODY}t")
        d1 = 1 if a.close >= a.open else -1
        if d2 != 0 and d1 == d2:
            reasons.append("bar1 color == SB dir (same direction, not a flip)")
        if not reasons:
            side = "SHORT" if d1 == 1 else "LONG"
            print(f"  {a.hhmm}->{b.hhmm}: *** {side} FIRES ***")
        else:
            print(f"  {a.hhmm}->{b.hhmm}: no signal - " + "; ".join(reasons))


if __name__ == "__main__":
    main()
