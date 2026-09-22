"""Killer-day forensics: 2025-03-26 (Wed) — auto-tariff ambush day.

Extracts the morning-context row + all backtest trade rows for 2025-03-26
(and the +/-2 day window) and writes a dated findings CSV that pairs the
mechanical context with the researched narrative.

Backtest day P&L (vix252 IC streams): IC put side stopped both books,
call side (credit 0.10) settled worthless. Damage was a downside afternoon
grind: SPX -1.12% close 5712.20, through the 5715 short put.

Researched cause (web, 2026-09-10):
- Midday/afternoon: White House said Trump would unveil 25% auto-import
  tariffs at a 4pm ET press conference; stocks hit session lows on that
  headline. Trump signed the proclamation at 4pm ET (tariffs effective
  4/3 cars, 5/3 parts). S&P -1.12% to 5712.20, Nasdaq -2.04%, Dow -0.31%.
- Nvidia -6% on an FT report (out before/around the US open) that China's
  energy-efficiency rules for data-center chips exclude the H20, threatening
  ~$17B (13%) of revenue. Meta/Amazon -2%+, Alphabet -3%.
- Overnight/premarket: futures little changed after a 3-day win streak;
  8:30 ET (7:30 CT) Feb durable goods +0.9% vs -1.0% expected (benign beat).
  Gap at open -0.09%. VIX prior close 17.15, falling.
- Prior days: Mon 3/24 +1.76% relief rally (reports April-2 reciprocal
  tariffs would be narrower/targeted); Tue 3/25 +0.16%. Risk-on tape,
  IV compressing (thin 0.10 call credit on 3/26 = crushed upside premium).
- After: Thu 3/27 -0.33% (GM slumped, tariff digestion); Fri 3/28 -1.97%
  (hot Feb core PCE +0.4% m/m / 2.8% y/y, UMich sentiment 57.0 with highest
  long-run inflation expectations since 1993). Continuation into the
  April 2 "Liberation Day" crash. No snap-back.

Verdict: genuine intraday ambush with a quiet open. Nothing in VIX (17,
falling), gap (-0.09%), scheduled calendar (no Tier-1 event; durable goods
beat), or put credit (0.85, normal) warned by 08:30 CT. The only morning
tells were headline-based: Bloomberg/press reports that auto tariffs could
come "as soon as Wednesday" and the premarket FT Nvidia/China story —
invisible to a purely mechanical gate. Thin 0.10 call credit flagged
low-IV complacency after the 3-day rally but points the wrong direction.
"""
import csv
import os

BASE = r"C:\Users\Admin\myquant\data\options_sim\backtest_full"
OUT_DIR = os.path.join(BASE, "killerday")
DAY = "2025-03-26"
WINDOW = ["2025-03-24", "2025-03-25", "2025-03-26", "2025-03-27", "2025-03-28"]


def rows_from(path, datecol="date", dates=WINDOW, extra=None):
    out = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r[datecol] in dates and (extra is None or extra(r)):
                out.append(r)
    return out


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    ctx = rows_from(os.path.join(BASE, "killer_context.csv"))
    ic = rows_from(os.path.join(BASE, "rows.csv"), dates=[DAY],
                   extra=lambda r: r["method"] == "vix252")
    fly = rows_from(os.path.join(BASE, "fly_rows.csv"), dates=[DAY])

    out = os.path.join(OUT_DIR, f"{DAY}_investigation.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["section", "detail"])
        w.writerow(["cause", "White House announced midday that Trump would unveil 25% auto-import tariffs at 4pm ET; signed same day, effective 4/3. Afternoon grind lower: SPX -1.12% to 5712.20, Nasdaq -2.04%. NVDA -6% on FT China energy-efficiency-rules story (premarket). Close went through the 5715 short put."])
        w.writerow(["overnight", "Futures little changed after 3-day win streak; gap -0.09%. 7:30 CT Feb durable goods +0.9% vs -1.0% exp (benign). No premarket selloff."])
        w.writerow(["prior_days", "3/24 +1.76% relief rally on 'targeted' reciprocal-tariff reports; 3/25 +0.16%. Risk-on, VIX down to 17.15, IV compressed (0.10 call credit)."])
        w.writerow(["aftermath", "3/27 -0.33%; 3/28 -1.97% (hot core PCE + UMich inflation expectations); continuation into 4/2 Liberation Day. No snap-back."])
        w.writerow(["detectable_0830ct", "NO by mechanical signals (VIX 17 falling, flat gap, no Tier-1 event, normal 0.85 put credit). Headline-only tells: auto tariffs expected 'as soon as Wednesday' (Bloomberg), FT NVDA/China story premarket. Thin 0.10 call credit = complacency flag, wrong side."])
        w.writerow(["", ""])
        w.writerow(["context_rows", "date,dow,event,gap_pct,prior_ret,prior_range,prior2_ret,vix_prior,vix_chg,em_pts,cr_eodic_c,cr_eodic_p,ic_pnl,fly_pnl,puts_band_pnl,next_ret"])
        for r in ctx:
            w.writerow(["ctx", ",".join(r.values())])
        w.writerow(["ic_rows_vix252", "date,strat,method,center,em,short_k,long_k,credit,exit_kind,exit_val,pnl"])
        for r in ic:
            w.writerow(["ic", ",".join(v for v in r.values() if v is not None)])
        w.writerow(["fly_rows", "date,strat,center,short_k,long_k,credit,exit_kind,exit_val,pnl"])
        for r in fly:
            w.writerow(["fly", ",".join(v for v in r.values() if v is not None)])
    print("wrote", out)


if __name__ == "__main__":
    main()
