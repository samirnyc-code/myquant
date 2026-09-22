"""climax_at_high_test.py — the user's screenshot pattern, tested (S116-tempo).

Pattern (3 circled reversals, 2026-09-10 chart): new swing high printed WITH
climactic tempo (>=p95 for that time of day, self-calibrated on trailing
sessions) -> reversal. Question: does climax-at-the-high reverse MORE often
than a plain new high? (H4 retest with the v2 self-calibrating percentile and
the user's literal event definition.)

=== FROZEN SPEC (before first run) ===
Tempo pctile: rank vs the previous <=480 values (~60 sessions x 8) of the SAME
  15-min session bucket — replicates the v2 indicator. Bar skipped if <30 samples.
Event: bar t sets a new 20-bar high (high[t] > max high[t-20..t-1]), t >= 20,
  >=10 bars since the previous same-side event. Symmetric for lows.
  CLIMAX event: max tempo-pctile over [t-2..t] >= 95 (dot within 2 bars of top).
  CONTROL event: that max < 80. (80-95 excluded as gray zone.)
Outcome (walked intrabar to day end): REVERSAL if price retraces >= 0.25 x ADR
  (8-day trailing mean daily range) from the event extreme BEFORE exceeding the
  extreme by 0.10 x ADR; CONTINUATION if the extension comes first; day-end
  unresolved dropped. Both-in-one-bar dropped as ambiguous.
Days: exclude half-days (last bar end < 14:00) and days without ADR.
Report: P(reversal) climax vs control, by side, by year, plus last-250-sessions.

    python tempo/scripts/climax_at_high_test.py
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BARS = ROOT / "tempo" / "outputs" / "bars_2000t_all.parquet"
OUT = ROOT / "tempo" / "outputs"

CAP, MINS = 480, 30
NHIGH, GAP = 20, 10
CLIMAX, CTRL = 95.0, 80.0
REV_ADR, EXT_ADR = 0.25, 0.10
ADR_LB = 8


def rolling_bucket_pct(df: pd.DataFrame) -> np.ndarray:
    pct = np.full(len(df), np.nan)
    df = df.reset_index(drop=True)
    for _, idx in df.groupby("bucket").groups.items():
        idx = np.asarray(idx)
        vals = df.loc[idx, "tempo"].to_numpy()
        for j in range(len(idx)):
            lo = max(0, j - CAP)
            w = vals[lo:j]
            if len(w) < MINS:
                continue
            pct[idx[j]] = max(1, min(99, 100.0 * (w <= vals[j]).sum() / (len(w) + 1)))
    return pct


def main():
    df = pd.read_parquet(BARS)
    df = df.sort_values(["date", "bar"]).reset_index(drop=True)
    df["bucket"] = (df["session_min"] // 15).astype(int).clip(0, 26)
    df.loc[df["ticks"] != 2000, "tempo"] = np.nan          # partial bars: no tempo
    print("computing rolling self-calibrated percentiles...")
    df["tpct"] = rolling_bucket_pct(df)

    day = df.groupby("date").agg(hi=("high", "max"), lo=("low", "min"),
                                 last_end=("end", "max"))
    day["adr"] = (day["hi"] - day["lo"]).shift(1).rolling(ADR_LB).mean()
    day["last_t"] = pd.to_datetime(day["last_end"]).dt.time
    keep = day[(day["last_t"] >= dt.time(14, 0)) & day["adr"].notna() & (day["adr"] > 0)]

    events = []
    for date, g in df[df["date"].isin(keep.index)].groupby("date"):
        g = g.reset_index(drop=True)
        adr = keep.loc[date, "adr"]
        h, l = g["high"].to_numpy(), g["low"].to_numpy()
        tp = g["tpct"].to_numpy()
        n = len(g)
        last_ev = {1: -999, -1: -999}
        for t in range(NHIGH, n):
            for side in (1, -1):
                if side == 1:
                    is_new = h[t] > h[t - NHIGH:t].max()
                    ext_p = h[t]
                else:
                    is_new = l[t] < l[t - NHIGH:t].min()
                    ext_p = l[t]
                if not is_new or t - last_ev[side] < GAP:
                    continue
                w = tp[max(0, t - 2):t + 1]
                w = w[~np.isnan(w)]
                if len(w) == 0:
                    continue
                mx = w.max()
                if mx >= CLIMAX:
                    grp = "climax"
                elif mx < CTRL:
                    grp = "control"
                else:
                    continue
                last_ev[side] = t
                rev_t = ext_p - side * REV_ADR * adr
                ext_t = ext_p + side * EXT_ADR * adr
                label, ext_run = "unresolved", ext_p
                for j in range(t + 1, n):
                    hit_ext = h[j] >= ext_t if side == 1 else l[j] <= ext_t
                    hit_rev = l[j] <= rev_t if side == 1 else h[j] >= rev_t
                    if hit_ext and hit_rev:
                        label = "ambiguous"; break
                    if hit_ext:
                        label = "continuation"; break
                    if hit_rev:
                        label = "reversal"; break
                events.append({"date": date, "side": side, "t": t, "grp": grp,
                               "tpct_max": mx, "label": label,
                               "session_min": float(g["session_min"].iloc[t])})
    ev = pd.DataFrame(events)
    today = dt.date.today().isoformat()
    ev.to_csv(OUT / f"climax_at_high_events_{today}.csv", index=False)

    r = ev[ev["label"].isin(["reversal", "continuation"])].copy()
    r["year"] = r["date"].str[:4]
    last250 = sorted(r["date"].unique())[-250:]

    def tab(sub, name):
        rows = []
        for grp, gg in sub.groupby("grp"):
            p = (gg["label"] == "reversal").mean()
            rows.append({"slice": name, "grp": grp, "n": len(gg), "P_rev": round(p, 3)})
        return rows

    out_rows = []
    out_rows += tab(r, "ALL")
    out_rows += tab(r[r["side"] == 1], "highs")
    out_rows += tab(r[r["side"] == -1], "lows")
    for yr, gg in r.groupby("year"):
        out_rows += tab(gg, yr)
    out_rows += tab(r[r["date"].isin(last250)], "last250d")
    res = pd.DataFrame(out_rows)
    res.to_csv(OUT / f"climax_at_high_summary_{today}.csv", index=False)

    print(f"\nevents: {len(ev)}  resolved: {len(r)}  "
          f"(unresolved {int((ev['label']=='unresolved').sum())}, ambiguous {int((ev['label']=='ambiguous').sum())})")
    piv = res.pivot(index="slice", columns="grp", values=["n", "P_rev"])
    print(piv.to_string())
    # simple z for the headline
    a = r[r["grp"] == "climax"]; b = r[r["grp"] == "control"]
    pa, pb = (a["label"] == "reversal").mean(), (b["label"] == "reversal").mean()
    pp = (len(a) * pa + len(b) * pb) / (len(a) + len(b))
    se = np.sqrt(pp * (1 - pp) * (1 / len(a) + 1 / len(b)))
    print(f"\nheadline: P(rev|climax)={pa:.3f} (n={len(a)}) vs P(rev|control)={pb:.3f} "
          f"(n={len(b)})  diff={pa-pb:+.3f}  z={(pa-pb)/se:.2f}")


if __name__ == "__main__":
    main()
