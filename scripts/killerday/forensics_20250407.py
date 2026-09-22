"""Killer-day forensics: 2025-04-07 (tariff 'Black Monday' / fake 90-day-pause whipsaw).

Extracts the morning-context row + all backtest trade rows for 2025-04-07 and the
surrounding days (2025-04-01 .. 2025-04-11), joins with the researched narrative,
and writes a dated summary CSV under data/options_sim/backtest_full/killerday/.

Run:  python scripts/killerday/forensics_20250407.py
"""
import csv
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
BT = os.path.join(ROOT, "data", "options_sim", "backtest_full")
OUT_DIR = os.path.join(BT, "killerday")
os.makedirs(OUT_DIR, exist_ok=True)

DAY = "2025-04-07"
WINDOW = [f"2025-04-{d:02d}" for d in range(1, 12)]

# ---- context rows ----------------------------------------------------------
with open(os.path.join(BT, "killer_context.csv"), newline="") as f:
    ctx = [r for r in csv.DictReader(f) if r["date"] in WINDOW]

# ---- trade rows (IC: vix252 stream only; fly: all) -------------------------
with open(os.path.join(BT, "rows.csv"), newline="") as f:
    ic = [r for r in csv.DictReader(f)
          if r["date"] == DAY and r["method"] == "vix252"]
with open(os.path.join(BT, "fly_rows.csv"), newline="") as f:
    fly = [r for r in csv.DictReader(f) if r["date"] == DAY]

# ---- researched narrative (web, 2026-09-10; sources in handback) -----------
NARRATIVE = {
    "date": DAY,
    "label": "tariff Black Monday + fake 90-day-pause whipsaw",
    "scheduled_event": "",
    "cause": ("3rd day of Liberation Day tariff crash. Overnight global rout "
              "(Nikkei -7.8%, Hang Seng -13.2%, ES -4%+, VIX printed ~60 "
              "premarket). ~09:10 CT a FALSE 'Hassett: 90-day tariff pause' "
              "headline ripped SPX ~+8% off the low in minutes; White House "
              "called it fake news, market gave it back; Trump then threatened "
              "an additional 50% China tariff. Record intraday range "
              "(low 4835 -> high ~5246, close 5062.25, -0.23%)."),
    "detectable_premarket": True,
    "kill_mechanism": ("Two-sided whipsaw: flies + call-side stops died on the "
                       "fake-headline UPSIDE rip, not the down open. IC vix252 "
                       "actually finished +364 (wide EM strikes survived); fly "
                       "-2473 (3 of 4 legs stopped in the 8.5% range)."),
}

# ---- write outputs ---------------------------------------------------------
with open(os.path.join(OUT_DIR, "forensics_20250407_context.csv"), "w",
          newline="") as f:
    w = csv.DictWriter(f, fieldnames=ctx[0].keys())
    w.writeheader()
    w.writerows(ctx)

trade_fields = ["date", "book", "strat", "method", "center", "em", "short_k",
                "long_k", "credit", "exit_kind", "exit_val", "pnl"]
with open(os.path.join(OUT_DIR, "forensics_20250407_trades.csv"), "w",
          newline="") as f:
    w = csv.DictWriter(f, fieldnames=trade_fields, extrasaction="ignore")
    w.writeheader()
    for r in ic:
        w.writerow({**r, "book": "ic"})
    for r in fly:
        w.writerow({**r, "book": "fly", "method": "", "em": ""})

with open(os.path.join(OUT_DIR, "forensics_20250407_narrative.csv"), "w",
          newline="") as f:
    w = csv.DictWriter(f, fieldnames=NARRATIVE.keys())
    w.writeheader()
    w.writerow(NARRATIVE)

day_ctx = next(r for r in ctx if r["date"] == DAY)
ic_sum = sum(float(r["pnl"]) for r in ic)
fly_sum = sum(float(r["pnl"]) for r in fly)
print(f"{DAY}: gap {day_ctx['gap_pct']}%  prior_ret {day_ctx['prior_ret']}%  "
      f"vix_prior {day_ctx['vix_prior']} (chg +{day_ctx['vix_chg']})  "
      f"em {day_ctx['em_pts']}pts")
print(f"IC vix252 day pnl {ic_sum:+.1f} | fly day pnl {fly_sum:+.1f} | "
      f"puts_band {day_ctx['puts_band_pnl']}")
