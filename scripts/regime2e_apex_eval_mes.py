"""How long to PASS the Apex legacy 150K eval, sized in MES?
Eval = reach +$9,000 in >=7 traded days WITHOUT breaching the intraday $5,000
trailing DD. Sweeps MES size; for every possible start date reports pass-rate
(reached $9k before blowing) and time-to-pass distribution. Cached trades.

  python scripts/regime2e_apex_eval_mes.py
"""
import pickle
from datetime import date
from pathlib import Path
import numpy as np

MES_PT = 5.0; FEE = 1.02 + 1.25; T = 5000.0; GOAL = 9000.0; MIN_DAYS = 7
REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / "reports" / "regime2e" / "apex_mes_trades.pkl"


def d(s):
    return date(*map(int, s.split("-")))


def eval_from(trades, i, size):
    """Return ('pass', calendar_days, traded_days) / ('blow',..) / ('incomplete',..)."""
    realized = 0.0; peak = 0.0; start = d(trades[i]["date"]); traded = 0
    for t in trades[i:]:
        traded += 1
        u = t["sgn"] * (t["seg"] - t["entry"]) * MES_PT * size
        eq = realized + u
        runpk = np.maximum(peak, np.maximum.accumulate(eq))
        floor = np.where(runpk >= T + 100, 100.0, runpk - T)
        if float((eq - floor).min()) <= 0:
            return "blow", (d(t["date"]) - start).days, traded
        peak = float(runpk[-1])
        realized += t["gross_pts"] * MES_PT * size - FEE * size
        if realized >= GOAL and traded >= MIN_DAYS:
            return "pass", (d(t["date"]) - start).days, traded
    return "incomplete", 0, 0


def main():
    trades = pickle.load(open(CACHE, "rb"))
    n = len(trades)
    print(f"Apex legacy 150K EVAL — goal +${GOAL:,.0f}, intraday ${T:,.0f} DD, >={MIN_DAYS} traded days, MES\n")
    print(f"{'size':>5} {'=ES':>4} | {'pass%':>6} {'blow%':>6} | {'median days-to-pass':>20} {'25th':>6} {'75th':>6} {'med traded-days':>15}")
    for size in (5, 7, 8, 10, 15, 20, 30, 40, 50, 70):
        results = [eval_from(trades, i, size) for i in range(n)]
        passes = [r for r in results if r[0] == "pass"]
        blows = [r for r in results if r[0] == "blow"]
        tot = len(results)
        if passes:
            cal = np.array([r[1] for r in passes]); td = np.array([r[2] for r in passes])
            print(f"{size:>5} {size/10:>4.1f} | {100*len(passes)/tot:>5.0f}% {100*len(blows)/tot:>5.0f}% | "
                  f"{int(np.median(cal)):>15}d {int(np.percentile(cal,25)):>5}d {int(np.percentile(cal,75)):>5}d "
                  f"{int(np.median(td)):>13}d  (~{np.median(cal)/30:.1f} mo)")
        else:
            print(f"{size:>5} {size/10:>4.1f} | {100*len(passes)/tot:>5.0f}% {100*len(blows)/tot:>5.0f}% |  (never passes)")


if __name__ == "__main__":
    main()
