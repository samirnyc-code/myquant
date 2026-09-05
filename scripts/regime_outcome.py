"""Do the gex report's regime / event flags / day-type / HVL actually correlate
with our realized outcomes? Measure it — don't assert.

Joins each current-book day's realized P&L (trades.parquet, deduped, non-STMR) to
that day's gameplan_<date>.json gex fields, and per-trade P&L to hvl_side. Then
groups P&L by gamma regime, day_type, event flag, and HVL side.

N is small (auto-era only) — read the direction, not the decimals. This is
hypothesis-generation for the forward test, not proof.
"""
import json
from pathlib import Path

import pandas as pd
import options_trade_log as tlog

SIM = Path("data/options_sim")
tr = tlog.dedupe_mirrors(pd.read_parquet("data/options_log/trades.parquet"))
tr = tr[tr["pnl"].notna() & ~tr["strategy_id"].astype(str).str.contains("stmr", case=False)].copy()
tr["day"] = tr["entry_dt"].astype(str).str[:10]
tr = tr[tr["day"] >= "2026-08-04"]

# per-day gex context from the gameplan JSONs
ctx = []
for d in sorted(tr["day"].unique()):
    ymd = d.replace("-", "")
    f = SIM / f"gameplan_{ymd}.json"
    gx = {}
    if f.exists():
        try:
            gx = (json.loads(f.read_text(encoding="utf-8")).get("gexlog") or {})
        except Exception:
            pass
    ctx.append({"day": d,
                "regime": gx.get("regime", "?"),
                "day_type": gx.get("day_type", "?"),
                "signal": gx.get("signal_bucket", "?"),
                "hi_events": int(gx.get("high_impact_today") or 0)})
ctx = pd.DataFrame(ctx)
daily = tr.groupby("day")["pnl"].sum().round().rename("day_pnl").reset_index()
daily = daily.merge(ctx, on="day", how="left")
daily["event_day"] = daily["hi_events"] > 0

pd.set_option("display.width", 200)
print("=== per-day P&L with gex context (current book) ===")
print(daily[["day", "day_pnl", "regime", "day_type", "signal", "hi_events"]].to_string(index=False))


def grp(df, col, val="day_pnl"):
    g = df.groupby(col)[val].agg(["count", "mean", "sum", "min"]).round(0)
    return g.sort_values("mean", ascending=False)


print("\n=== day P&L by GAMMA REGIME ==="); print(grp(daily, "regime").to_string())
print("\n=== day P&L by DAY TYPE ==="); print(grp(daily, "day_type").to_string())
print("\n=== day P&L by EVENT DAY (high-impact print) ==="); print(grp(daily, "event_day").to_string())

# per-TRADE by HVL side (which side of the high-vol level the short sat)
if "hvl_side" in tr.columns:
    h = tr.copy()
    h["hvl_side"] = h["hvl_side"].astype(str)
    print("\n=== per-TRADE P&L by HVL SIDE ===")
    print(h.groupby("hvl_side")["pnl"].agg(["count", "mean", "sum"]).round(0).to_string())

print(f"\n[N = {len(daily)} days — directional only, not significant. Forward-collect to confirm.]")
daily.to_csv(SIM / "regime_outcome.csv", index=False)
print(f"saved {SIM/'regime_outcome.csv'}")
