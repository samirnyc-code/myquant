"""Killer-day forensics: 2024-12-20 (post-FOMC snap-back rally, triple witching, cool PCE).

Extracts the context row + all backtest trade rows for the day and writes a dated
findings CSV under data/options_sim/backtest_full/killerday/.

Verified facts (web, 2026-09-09):
- 2024-12-18 FOMC: hawkish cut (dots -> 2 cuts in 2025), SPX -2.95%, VIX 2nd-biggest
  spike ever (~15.9 -> 27.6). 2024-12-19: flat (-0.09%), VIX eased to 24.09.
- Thu night 12/19: House vote on spending bill FAILED (Trump/Musk killed the CR);
  government shutdown deadline midnight Friday. Overnight ES futures -1%.
- Fri 12/20 07:30 CT (8:30 ET): November PCE cool across the board — headline
  +0.1% m/m / 2.4% y/y (vs 2.5% est), core +0.1% m/m / 2.8% y/y (vs 2.9% est).
  Futures pared losses premarket, BEFORE the 08:30 CT entry.
- Cash open still -0.43% gap down (~5842 vs 5867.08 prior close). Goolsbee dovish
  comments late morning; day rallied ~1.7% off the open/low to close 5930.85
  (+1.09%). VIX crushed 24.09 -> ~18.4. Triple witching: ~$6.6T notional expiring,
  biggest S&P volume day of 2024 — dealer/expiry flows amplified the up-move.
- Damage: ALL call spreads premium-stopped (shorts 5890/5915/5930/5940/5955);
  every put spread settled worthless. Close 5930.85 never breached the vix252
  short call 5955 — the stop rule (exit at 12.9 vs 0.2 credit) made the loss.
- Aftermath: shutdown averted over the weekend (signed Sat 12/21); Mon 12/23
  SPX +0.73% (continuation up — no snap-back against the move).
"""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BT = ROOT / "data" / "options_sim" / "backtest_full"
OUT = BT / "killerday"
OUT.mkdir(exist_ok=True)
DAY = "2024-12-20"

ctx = pd.read_csv(BT / "killer_context.csv")
row = ctx[ctx["date"] == DAY]

rows = pd.read_csv(BT / "rows.csv")
day_rows = rows[rows["date"] == DAY].copy()

fly = pd.read_csv(BT / "fly_rows.csv")
day_fly = fly[fly["date"] == DAY].copy()

row.to_csv(OUT / f"context_{DAY}.csv", index=False)
day_rows.to_csv(OUT / f"ic_rows_{DAY}.csv", index=False)
day_fly.to_csv(OUT / f"fly_rows_{DAY}.csv", index=False)

signals = pd.DataFrame([
    {"signal": "Cool Nov PCE public at 07:30 CT (core 0.1% m/m vs 0.2% est)",
     "knowable_at": "premarket",
     "note": "Dovish upside catalyst out a full hour before entry; futures already paring losses"},
    {"signal": "VIX 24.09 two days after 2nd-biggest spike ever, already -3.53 d/d",
     "knowable_at": "premarket",
     "note": "Elevated-and-falling VIX post-shock = vol-crush / violent relief-rally regime"},
    {"signal": "Quarterly triple witching, ~$6.6T notional (largest of 2024)",
     "knowable_at": "premarket",
     "note": "On the calendar weeks ahead; expiry/dealer flows amplify directional moves"},
    {"signal": "Call credit 0.2 vs put credit 2.6 (vix252 EOD IC)",
     "knowable_at": "at-entry",
     "note": "Market priced near-zero upside premium; 0.2 credit vs ~12.9 stop exit is grotesque R:R — min-credit filter skips the call side"},
    {"signal": "Gap -0.43% after -2.95% two days prior, with dovish data in hand",
     "knowable_at": "at-entry",
     "note": "Classic post-FOMC snap-back setup; short calls = wrong side of the relief rally"},
    {"signal": "EM 89 pts (~1.5%) — close 5930.85 never breached 5955 short call",
     "knowable_at": "at-entry",
     "note": "Loss was manufactured by the premium stop, not a strike breach; day settled inside the EM"},
])
signals.to_csv(OUT / f"signals_{DAY}.csv", index=False)

print(row.to_string(index=False))
print(day_rows.to_string(index=False))
print(day_fly.to_string(index=False))
print(signals.to_string(index=False))
