"""
Killer-day forensics: 2022-05-20 (Fri) - monthly OpEx bear-market-touch whipsaw.

Extracts the morning-context row + surrounding days from killer_context.csv and
the day's trade rows (rows.csv vix252 + fly_rows.csv), and writes a dated
findings CSV under data/options_sim/backtest_full/killerday/.

Web-verified narrative (2026-09-10):
- Overnight: China cut the 5-yr Loan Prime Rate 15bp (bigger than expected);
  Asia rallied (HSI +2%), Europe up, US futures up -> SPX gapped UP +0.69%.
- Intraday: no US data print. Monthly OpEx (~$1.9T notional per Goldman/Bloomberg).
  SPX sold off from open 3927.76 to 3810.32 (-2.3% intraday, -20.9% below the
  Jan-3 record close = intraday bear-market touch), then an "incredible
  late-session rally" back to close 3901.36, essentially flat (+0.01%).
  ~3.4% high-to-low round-trip range with a quiet green open. Classic
  OpEx-pin/gamma whipsaw, no headline catalyst intraday.
- Prior days: brutal week. 5/17 Powell "won't hesitate past neutral"; 5/18
  Target -25% earnings shock, SPX -4.04% (worst day since Jun-2020); 5/19
  more retail damage (Kohl's), SPX -0.58%. 7th straight weekly SPX loss
  (longest since 2001); Dow 8th (longest in 90 years).
- Aftermath: SNAP-BACK. Mon 5/23 +1.86%; week of 5/23 rallied ~+6.6%.
Sources:
  https://www.aljazeera.com/economy/2022/5/20/markets-us-stocks-rise-as-china-lifts-sentiment
  https://www.bloomberg.com/news/articles/2022-05-19/battered-stock-traders-get-ready-for-1-9-trillion-option-expiry
  https://www.malaymail.com/news/money/2022/05/20/asian-shares-jump-as-china-cuts-key-lending-benchmark/7808
  https://www.business-standard.com/article/international/s-p-500-falls-20-from-record-close-on-pace-to-confirm-bear-market-122052001750_1.html
  https://www.cnbc.com/2022/05/17/stock-market-news-open-to-close.html
"""
import pandas as pd
from pathlib import Path

ROOT = Path(r"c:/Users/Admin/myquant")
BT = ROOT / "data/options_sim/backtest_full"
OUT = BT / "killerday"
OUT.mkdir(parents=True, exist_ok=True)

DAY = "2022-05-20"
WINDOW = ["2022-05-17", "2022-05-18", "2022-05-19", "2022-05-20", "2022-05-23"]

ctx = pd.read_csv(BT / "killer_context.csv")
ctx_win = ctx[ctx["date"].isin(WINDOW)].copy()
ctx_win.to_csv(OUT / f"context_window_{DAY}.csv", index=False)

rows = pd.read_csv(BT / "rows.csv")
ic = rows[(rows["date"] == DAY) & (rows["method"] == "vix252")].copy()
fly = pd.read_csv(BT / "fly_rows.csv")
fly_d = fly[fly["date"] == DAY].copy()
trades = pd.concat([ic, fly_d], ignore_index=True)
trades.to_csv(OUT / f"trades_{DAY}.csv", index=False)

findings = pd.DataFrame([
    dict(key="cause", value="Monthly OpEx (~$1.9T) whipsaw: gap-up open on China 5y-LPR cut, "
         "then no-catalyst intraday slide from 3927.76 open to 3810.32 (-2.3%, intraday bear-market "
         "touch at -20.9% off Jan-3 record), late-session V-rally to close 3901.36 flat (+0.01%)."),
    dict(key="mechanics", value="Put spreads (shorts 3830/3855) blown through by the 3810 low -> "
         "stopped; calls settled worthless (close 3901 << 3975/4000); ATM flies stopped both sides "
         "by the round trip. puts_band -2203 = eodic_p -1171.52 + openic_p -1031.52."),
    dict(key="overnight", value="China cut 5y LPR 15bp (more than expected); HSI +2%, Asia/Europe up, "
         "US futures up ~1% -> +0.69% gap up, VIX -1.61 to ~29.35 premarket direction. Risk-ON open."),
    dict(key="prior_days", value="5/17 Powell hawkish WSJ remarks; 5/18 Target earnings shock, SPX "
         "-4.04% worst day since Jun-2020; 5/19 -0.58% w/ 4.86 VIX pop to 30.96; 7th straight losing "
         "week (longest since 2001)."),
    dict(key="aftermath", value="Snap-back: Mon 5/23 +1.86%; following week ~+6.6%. No continuation."),
    dict(key="knowable_0830ct", value="OpEx date (calendar, deterministic); VIX ~29 elevated regime; "
         "prior2_ret -4.04% (post-crash fragility); prior_range 1.78 after 3.57; EM 72.1 pts huge; "
         "call credit 4.8 vs put credit 0.95 (17x downside skew in credit terms = market paying "
         "nothing for put spreads at our band -> terrible risk/reward on the put side); gap-up-into-"
         "downtrend pattern. NO specific news trigger was visible - the intraday reversal itself was "
         "the ambush, but the fragile-regime + OpEx + thin-put-credit combination was fully knowable."),
    dict(key="intraday_shock", value="Yes - quiet green open, no intraday headline; damage came from "
         "an OpEx flow-driven reversal."),
])
findings.to_csv(OUT / f"findings_{DAY}.csv", index=False)

print(ctx_win.to_string(index=False))
print(trades.to_string(index=False))
print(f"wrote {OUT / f'context_window_{DAY}.csv'}")
print(f"wrote {OUT / f'trades_{DAY}.csv'}")
print(f"wrote {OUT / f'findings_{DAY}.csv'}")
