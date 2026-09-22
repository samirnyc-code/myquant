"""wedge_climax_confluence.py — does tempo climax confluence improve MyWedge signals? (S116-tempo)

User observation (2026-09-10 screenshots): MyWedge signal bars firing AT or one bar
after a tempo climax mark the good reversals. Test on the 6-month wedge export
(data/wedge/wedge_signals_ES_2000t_6mo.csv, 2026-02..08).

=== FROZEN SPEC ===
Match: wedge SignalTime -> nearest trove 2000t bar END within 45s, after an
  auto-detected constant hour offset (chosen to maximize matches with
  |wedge close - trove close| <= 1.5 pts); unmatched signals dropped (counted).
  Consecutive same-side signal bars deduped to the FIRST of each run (gap > 3 bars).
Tempo pctile: identical to climax_at_high_test (rank vs prior <=480 same-bucket
  values, min 30) — replicates the v2 indicator.
Groups: CLIMAX confluence = max tpct over [t-1..t] >= 95 at the matched bar;
  PLAIN = that max < 80; 80-95 gray zone excluded.
Outcome (directional, BL=long / BR=short, from matched bar close):
  WIN  = favorable 0.25 x ADR before adverse 0.10 x ADR (intrabar walk, day end /
  same-bar-both dropped). ADR = trailing 8-day mean daily range.
Report: win rates by group, by side, by month; z for the headline diff.

    python tempo/scripts/wedge_climax_confluence.py
"""
from __future__ import annotations
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tempo" / "scripts"))
from climax_at_high_test import rolling_bucket_pct  # noqa: E402

BARS = ROOT / "tempo" / "outputs" / "bars_2000t_all.parquet"
WEDGE = ROOT / "data" / "wedge" / "wedge_signals_ES_2000t_6mo.csv"
OUT = ROOT / "tempo" / "outputs"

CLIMAX, CTRL = 95.0, 80.0
WIN_ADR, LOSS_ADR = 0.25, 0.10
ADR_LB = 8
MATCH_TOL_S, PRICE_TOL = 45.0, 1.5


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(BARS)
    df = df.sort_values(["date", "bar"]).reset_index(drop=True)
    df["bucket"] = (df["session_min"] // 15).astype(int).clip(0, 26)
    df.loc[df["ticks"] != 2000, "tempo"] = np.nan
    print("computing rolling self-calibrated percentiles...")
    df["tpct"] = rolling_bucket_pct(df)
    df["end"] = pd.to_datetime(df["end"])

    day = df.groupby("date").agg(hi=("high", "max"), lo=("low", "min"))
    day["adr"] = (day["hi"] - day["lo"]).shift(1).rolling(ADR_LB).mean()

    w = pd.read_csv(WEDGE, parse_dates=["SignalTime"])
    w = w.sort_values("SignalTime").reset_index(drop=True)
    # dedup: first of each same-side run (>3 signal-bars apart within a day)
    w["run"] = ((w["Signal"] != w["Signal"].shift()) | (w["Date"] != w["Date"].shift())
                | (w["BarNum"].diff() > 3)).cumsum()
    w = w.groupby("run").first().reset_index(drop=True)
    print(f"wedge signals: {len(w)} after dedup")

    # auto-detect constant hour offset (wedge chart clock -> trove CT)
    trove_by_day = {d: g.reset_index(drop=True) for d, g in df.groupby("date")}
    best = (None, -1)
    sample = w.sample(min(400, len(w)), random_state=42)
    for off in range(-12, 13):
        hits = 0
        for _, r in sample.iterrows():
            ts = r["SignalTime"] + pd.Timedelta(hours=off)
            g = trove_by_day.get(ts.strftime("%Y-%m-%d"))
            if g is None:
                continue
            i = (g["end"] - ts).abs().idxmin()
            if abs((g["end"].iloc[i] - ts).total_seconds()) <= MATCH_TOL_S \
                    and abs(g["close"].iloc[i] - r["Close"]) <= PRICE_TOL:
                hits += 1
        if hits > best[1]:
            best = (off, hits)
    off, hits = best
    print(f"offset detected: {off:+d}h ({hits}/{len(sample)} sample matches)")

    events = []
    unmatched = 0
    for _, r in w.iterrows():
        ts = r["SignalTime"] + pd.Timedelta(hours=off)
        date = ts.strftime("%Y-%m-%d")
        g = trove_by_day.get(date)
        if g is None or date not in day.index or not np.isfinite(day.loc[date, "adr"]):
            unmatched += 1
            continue
        i = (g["end"] - ts).abs().idxmin()
        if abs((g["end"].iloc[i] - ts).total_seconds()) > MATCH_TOL_S \
                or abs(g["close"].iloc[i] - r["Close"]) > PRICE_TOL:
            unmatched += 1
            continue
        adr = day.loc[date, "adr"]
        tp = g["tpct"].iloc[max(0, i - 1):i + 1].dropna()
        if len(tp) == 0:
            unmatched += 1
            continue
        mx = tp.max()
        grp = "climax" if mx >= CLIMAX else ("plain" if mx < CTRL else None)
        if grp is None:
            continue
        side = 1 if r["Signal"] == "BL" else -1
        entry = g["close"].iloc[i]
        tgt = entry + side * WIN_ADR * adr
        stp = entry - side * LOSS_ADR * adr
        label = "unresolved"
        h, l = g["high"].to_numpy(), g["low"].to_numpy()
        for j in range(i + 1, len(g)):
            hit_w = h[j] >= tgt if side == 1 else l[j] <= tgt
            hit_l = l[j] <= stp if side == 1 else h[j] >= stp
            if hit_w and hit_l:
                label = "ambiguous"; break
            if hit_w:
                label = "win"; break
            if hit_l:
                label = "loss"; break
        events.append({"date": date, "side": "long" if side == 1 else "short",
                       "grp": grp, "tpct_max": round(float(mx), 1), "label": label,
                       "session_min": float(g["session_min"].iloc[i])})

    ev = pd.DataFrame(events)
    ev.to_csv(OUT / f"wedge_climax_events_{today}.csv", index=False)
    r2 = ev[ev["label"].isin(["win", "loss"])].copy()
    r2["month"] = r2["date"].str[:7]
    print(f"\nmatched events: {len(ev)}  resolved: {len(r2)}  unmatched/dropped: {unmatched}")

    rows = []
    def tab(sub, name):
        for grp, gg in sub.groupby("grp"):
            rows.append({"slice": name, "grp": grp, "n": len(gg),
                         "win_rate": round((gg["label"] == "win").mean(), 3)})
    tab(r2, "ALL")
    for s, gg in r2.groupby("side"):
        tab(gg, s)
    for m, gg in r2.groupby("month"):
        tab(gg, m)
    res = pd.DataFrame(rows)
    res.to_csv(OUT / f"wedge_climax_summary_{today}.csv", index=False)
    print(res.pivot(index="slice", columns="grp", values=["n", "win_rate"]).to_string())

    a = r2[r2["grp"] == "climax"]; b = r2[r2["grp"] == "plain"]
    if len(a) > 10 and len(b) > 10:
        pa, pb = (a["label"] == "win").mean(), (b["label"] == "win").mean()
        pp = (len(a) * pa + len(b) * pb) / (len(a) + len(b))
        se = np.sqrt(pp * (1 - pp) * (1 / len(a) + 1 / len(b)))
        be = LOSS_ADR / (WIN_ADR + LOSS_ADR)
        print(f"\nheadline: win(wedge+climax)={pa:.3f} (n={len(a)}) vs win(wedge plain)={pb:.3f} "
              f"(n={len(b)})  diff={pa-pb:+.3f}  z={(pa-pb)/se:.2f}  breakeven={be:.3f}")


if __name__ == "__main__":
    main()
