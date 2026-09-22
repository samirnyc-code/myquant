"""Killer-day forensics: 2024-12-18 (FOMC hawkish-cut massacre).

Reads data/options_sim/backtest_full/killer_context.csv, extracts the window
around 2024-12-18, and writes a dated findings CSV under
data/options_sim/backtest_full/killerday/.

Verdict (web-verified 2026-09-09, sources listed in the output CSV):
- Cause: FOMC 25bp cut (expected) + hawkish dot plot (2 cuts in 2025 vs 4 in
  Sept SEP) + Powell "cautious" presser + Hammack dissent. SPX -2.95% to
  5872.03; Dow -1123 (10th straight loss, longest since 1974); Nasdaq -3.56%;
  VIX 15.87 -> 27.62 (+74%, one of the largest 1-day % spikes on record).
  Entire move after 13:00 CT statement / 13:30 CT presser.
- Open was quiet: gap -0.05%, premarket futures slightly GREEN (+0.2/0.3%).
- Prior days: Dow had lost 9 straight into the day (breadth rot, post-election
  rotation) while SPX sat <1% from its high; VIX crept 13.81 -> 14.69 -> 15.87.
- After: 12-19 flat (-0.09%) failed bounce; 12-20 +1.09% relief on cool Nov PCE
  (2.4% y/y) at quad-witching; 12-23 +0.73%. Snap-back, not continuation.
- Observable by 08:30 CT: FOMC on the calendar (binary event), EM 60.5pts
  (vs 52.6/56.2 the two days prior), VIX 2-day creep +2.06pts to 15.87,
  call credit only 0.50 vs put 1.45 (market paying almost nothing for upside
  wings into a binary). Detectable as EVENT RISK, not as direction: the open
  itself was dead quiet -> scheduled-event ambush, 100% intraday.
"""
import os
import pandas as pd

ROOT = r"c:\Users\Admin\myquant"
SRC = os.path.join(ROOT, "data", "options_sim", "backtest_full", "killer_context.csv")
OUTDIR = os.path.join(ROOT, "data", "options_sim", "backtest_full", "killerday")
os.makedirs(OUTDIR, exist_ok=True)

DAY = "2024-12-18"

df = pd.read_csv(SRC, parse_dates=["date"])
win = df[(df["date"] >= "2024-12-16") & (df["date"] <= "2024-12-23")].copy()
win.to_csv(os.path.join(OUTDIR, f"context_window_{DAY}.csv"), index=False)

findings = pd.DataFrame(
    [
        ("cause", "FOMC hawkish cut: 25bp cut as expected but dot plot 2 cuts in 2025 (was 4); Powell 'cautious'; Hammack dissent. SPX -2.95% to 5872.03, Dow -1123 (10th straight loss, worst streak since 1974), Nasdaq -3.56%, VIX 15.87->27.62 (+74%)."),
        ("timing", "100% intraday: statement 13:00 CT, presser 13:30 CT; tape quiet before that."),
        ("overnight", "Premarket GREEN: S&P futures +0.3%, Dow +0.2%, Nasdaq +0.1%; cash gap -0.05%. 95%+ odds of 25bp cut priced; no adverse foreign/overnight news."),
        ("prior_days", "Dow 9 straight down days into FOMC (longest since 1978) on rotation/breadth rot while SPX <1% off record; SPX 12-16 -0.0%, 12-17 -0.39%; VIX crept 13.81->14.69->15.87; EM ramped 52.6->56.2->60.5."),
        ("aftermath", "12-19 -0.09% (failed bounce, VIX stayed 27.6); 12-20 +1.09% on cool Nov PCE 2.4% y/y at quad-witching; 12-23 +0.73%. Snap-back within 2 sessions, no continuation."),
        ("signal_premkt_1", "FOMC + Powell presser on calendar - known binary at 13:00/13:30 CT (knowable premarket)."),
        ("signal_premkt_2", "VIX 2-day creep +2.06 to 15.87 with SPX near highs; vix_chg +1.18 prior day (knowable premarket)."),
        ("signal_premkt_3", "EM 60.5 pts, up ~15% in 2 days (52.6->56.2->60.5): market pricing the event (at-entry)."),
        ("signal_at_entry", "Credit skew: call side 0.50 vs put side 1.45 - almost no premium for upside risk into a binary; total IC credit 1.95 vs -2990 realized = ~15x credit loss."),
        ("signal_context", "Dow 9-day losing streak / breadth divergence (knowable premarket, direction hint only)."),
        ("verdict", "DETECTABLE by 08:30 CT as event-risk day (FOMC on calendar + VIX creep + fat EM), NOT as direction; quiet green open -> scheduled-event intraday ambush. Mechanical rule that helps: no-short-premium (or size-down) on FOMC-presser days."),
        ("source", "https://www.cnbc.com/2024/12/18/fed-meeting-live-updates-traders-await-december-interest-rate-cut.html"),
        ("source", "https://www.cnbc.com/2024/12/17/stock-market-today-live-updates.html"),
        ("source", "https://www.cnbc.com/2024/12/19/stock-market-today-live-updates.html"),
        ("source", "https://www.itiger.com/news/2492183044"),
        ("source", "https://www.federalreserve.gov/monetarypolicy/fomcminutes20241218.htm"),
        ("source", "https://www.sageadvisory.com/article/december-fomc-recap-hawkish-cut-dovish-signals-and-market-reaction"),
    ],
    columns=["key", "value"],
)
findings.to_csv(os.path.join(OUTDIR, f"findings_{DAY}.csv"), index=False)

print(win.to_string(index=False))
print(f"\nwrote {OUTDIR}\\context_window_{DAY}.csv and findings_{DAY}.csv")
