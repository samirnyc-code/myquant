"""Killer-day forensics: 2022-11-08 (US midterm Election Day / FTX-Binance LOI whipsaw).

Reads local CSVs only (NO ThetaData). Assembles the per-day forensic record:
- context row from killer_context.csv
- trade rows (IC vix252 + fly) from rows.csv / fly_rows.csv
- SPX OHLC window Nov 3-11 from spx_daily_ohlc.csv
- computed whipsaw metrics (range vs EM, excursion through fly center both directions)

Web-research narrative (sources in killerday CSV output):
- Day: US midterm elections (all-day; results overnight). Morning drift up on
  divided-government optimism; session high 3859.40 (+1.38% vs prior close).
- ~11:00-12:00 ET: CZ/Binance announce non-binding LOI to acquire FTX after FTX
  halted withdrawals that morning -> confirms FTX insolvency; BTC -11% to $17.3k,
  ETH -16%. Equities pared: SPX slid to 3786.28 (-0.54%) in the afternoon,
  bounced to close 3828.11 (+0.56%).
- Next day Nov 9: Binance walks away from deal, indecisive midterms -> SPX -2.08%.
- Nov 10: soft CPI -> SPX +5.54%.

Output: data/options_sim/backtest_full/killerday/2022-11-08_forensics.csv
"""
import csv
import os

REPO = r"C:\Users\Admin\myquant"
BASE = os.path.join(REPO, "data", "options_sim", "backtest_full")
OUTDIR = os.path.join(BASE, "killerday")
DATE = "2022-11-08"


def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main():
    os.makedirs(OUTDIR, exist_ok=True)

    ctx = {r["date"]: r for r in read_csv(os.path.join(BASE, "killer_context.csv"))}
    ohlc = {r["date"]: r for r in read_csv(os.path.join(BASE, "spx_daily_ohlc.csv"))}
    rows = [r for r in read_csv(os.path.join(BASE, "rows.csv"))
            if r["date"] == DATE and r["method"] == "vix252"]
    fly = [r for r in read_csv(os.path.join(BASE, "fly_rows.csv")) if r["date"] == DATE]

    c = ctx[DATE]
    o = ohlc[DATE]
    prior_close = float(ohlc["2022-11-07"]["close"])
    hi, lo, cl, op = (float(o[k]) for k in ("high", "low", "close", "open"))
    em = float(c["em_pts"])
    fly_center = 3805.0

    facts = [
        ("date", DATE),
        ("weekday", "Tuesday"),
        ("scheduled_event", "US midterm elections (all-day; results overnight); NFIB small-biz index; NOT in econ_calendar (event col empty)"),
        ("gap_pct", c["gap_pct"]),
        ("prior_ret", c["prior_ret"]),
        ("prior2_ret", c["prior2_ret"]),
        ("vix_prior", c["vix_prior"]),
        ("vix_chg", c["vix_chg"]),
        ("em_pts", em),
        ("spx_open", op),
        ("spx_high", hi),
        ("spx_low", lo),
        ("spx_close", cl),
        ("high_vs_priorclose_pct", round((hi / prior_close - 1) * 100, 2)),
        ("low_vs_priorclose_pct", round((lo / prior_close - 1) * 100, 2)),
        ("close_vs_priorclose_pct", round((cl / prior_close - 1) * 100, 2)),
        ("day_range_pts", round(hi - lo, 2)),
        ("day_range_pct", round((hi - lo) / prior_close * 100, 2)),
        ("range_vs_em", round((hi - lo) / em, 2)),
        ("fly_center", fly_center),
        ("excursion_above_center_pts", round(hi - fly_center, 2)),
        ("excursion_below_center_pts", round(fly_center - lo, 2)),
        ("ic_pnl_vix252_sum", round(sum(float(r["pnl"]) for r in rows), 2)),
        ("fly_pnl_sum", round(sum(float(r["pnl"]) for r in fly), 2)),
        ("fly_stops", "; ".join(f"{r['strat']} short{r['short_k']} cr{r['credit']} {r['exit_kind']}@{r['exit_val']} pnl{r['pnl']}" for r in fly)),
        ("cause", "Midterm Election Day morning drift-up (+1.4% to 3859) reversed hard early afternoon when Binance's non-binding LOI to acquire FTX (~11-12 ET, after FTX halted withdrawals that morning) confirmed FTX insolvency; BTC -11% to $17.3k, ETH -16%; SPX slid to 3786 (-0.5%) then bounced to close +0.56%. Both fly halves (short 3805) stopped by the up-then-down sweep."),
        ("overnight", "Quiet: futures modestly higher (SPX +0.36% premkt), Nikkei +1.3% (BOJ hold), Shanghai/HangSeng ~flat, Europe muted; gap only +0.27%. FTT token crashing and FTX withdrawal-halt reports were in crypto headlines premarket."),
        ("prior_days", "3-day equity rally into midterms (Nov 4 +1.36% post-NFP, Nov 7 +0.96%), VIX drifting down 24s. Crypto tension building publicly: Nov 2 CoinDesk Alameda balance-sheet story, Nov 6 CZ announces FTT dump, Nov 7-8 FTT collapse - visible in crypto, absent from equity vol."),
        ("aftermath", "Nov 9: Binance walks away, FTX insolvent, indecisive midterms -> SPX -2.08% (VIX +1.19 to 25.54). Nov 10: soft CPI -> SPX +5.54%. No multi-day premium-killer; the whipsaw was event-driven and resolved."),
        ("detectable_by_0830ct", "NO (mechanically). Gap +0.27%, VIX 24.35 falling, 3-day up tape, credits normal-thin (eodic 0.9c/0.65p on EM 58.4 - low but above gate). Soft flags only: (1) midterm Election Day missing from event calendar - election days carry known afternoon/overnight repositioning risk; (2) FTX withdrawal halt + FTT crash in premarket headlines - crypto-contagion tail risk not priced in VIX."),
        ("verdict", "Genuine intraday ambush with a quiet open: scheduled-political-event drift up, then an unscheduled credit-event headline (FTX-Binance LOI) mid-session produced a 1.9% up-then-down sweep (1.25x EM) through the ATM strike, stopping all four fly halves. IC vix252 (wings at EM) survived and settled positive (+217)."),
        ("sources", "cnbc.com 2022/11/08 markets wrap; coindesk.com FTX-Binance LOI 2022-11-08 + collapse timeline; schaeffersresearch.com premarket 2022-11-08; malaymail/Reuters wrap 2022-11-09; cointelegraph Binance LOI; local spx_daily_ohlc.csv"),
    ]

    out = os.path.join(OUTDIR, f"{DATE}_forensics.csv")
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["field", "value"])
        w.writerows(facts)
    print("wrote", out)
    for k, v in facts:
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
