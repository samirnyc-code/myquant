"""Killer-day forensics: 2025-02-28 (Trump-Zelensky Oval Office clash + month-end rip).

Extracts the local evidence used in the S115 killer-day investigation:
  - killer_context.csv rows 2025-02-24 .. 2025-03-04 (lead-in, day, aftermath)
  - rows.csv (method==vix252) trade rows for 2025-02-28 (which side lost, how far ITM)
  - vix_daily.csv OHLC around the date

Outputs (dated):
  data/options_sim/backtest_full/killerday/killerday_2025-02-28_context.csv
  data/options_sim/backtest_full/killerday/killerday_2025-02-28_trades.csv
  data/options_sim/backtest_full/killerday/killerday_2025-02-28_vix.csv

Web-verified narrative (2026-09-09, sources in the killer-day report):
  - Thu 2/27: SPX -1.59% (Nvidia -8.5% post-earnings, Trump confirms 3/4 tariffs on
    Canada/Mexico +10% China). VIX 21.13.
  - Fri 2/28 premarket: futures little changed; Jan PCE 8:30 ET in line
    (core 2.6% y/y); Asia sold off overnight (Nikkei ~-2.9%). Gap -0.08%.
  - Intraday: soft morning (VIX high 22.40), ~1:40 PM ET Trump-Zelensky Oval Office
    blowup -> dip to session low, then massive final-hour month-end rally.
    SPX +1.59% to 5954.50, +92.9 pts vs 78-pt EM -> upper EM breached ~15 pts.
    Call side (short 5940 @ 1.35cr / 5935 @ 2.00cr) settled 14.5/19.5 ITM = IC -2808.
  - Mon 3/3: full snap-back, SPX -1.76% (tariffs go live 3/4, ISM prices-paid spike).
"""
import os
import pandas as pd

ROOT = r"c:\Users\Admin\myquant"
OUTDIR = os.path.join(ROOT, "data", "options_sim", "backtest_full", "killerday")
DATE = "2025-02-28"
WIN_LO, WIN_HI = "2025-02-24", "2025-03-04"


def main():
    os.makedirs(OUTDIR, exist_ok=True)

    ctx = pd.read_csv(os.path.join(ROOT, "data", "options_sim", "backtest_full", "killer_context.csv"))
    ctx_win = ctx[(ctx["date"] >= WIN_LO) & (ctx["date"] <= WIN_HI)]
    ctx_win.to_csv(os.path.join(OUTDIR, f"killerday_{DATE}_context.csv"), index=False)

    rows = pd.read_csv(os.path.join(ROOT, "data", "options_sim", "backtest_full", "rows.csv"))
    tr = rows[(rows["date"] == DATE) & (rows["method"] == "vix252")]
    tr.to_csv(os.path.join(OUTDIR, f"killerday_{DATE}_trades.csv"), index=False)

    vix = pd.read_csv(os.path.join(ROOT, "data", "vix_daily.csv"))
    dcol = vix.columns[0]
    vx = vix[(vix[dcol] >= WIN_LO) & (vix[dcol] <= WIN_HI)]
    vx.to_csv(os.path.join(OUTDIR, f"killerday_{DATE}_vix.csv"), index=False)

    print("context rows:")
    print(ctx_win.to_string(index=False))
    print("\ntrade rows (vix252):")
    print(tr.to_string(index=False))
    print("\nvix window:")
    print(vx.to_string(index=False))


if __name__ == "__main__":
    main()
