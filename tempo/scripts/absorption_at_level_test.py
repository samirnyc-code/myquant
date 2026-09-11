"""absorption_at_level_test.py — the user's absorption theory (S116-tempo, 2026-09-11).

THEORY (user): lots of volume traded in a short time AROUND THE SAME PRICE at S/R
= absorption -> the level holds (rejection). Distinct from yesterday's C1 finding
(climax WITH range breaking a level leaned continuation): the low-amplitude term
is what separates "absorbed at the level" from "driving through it".

=== FROZEN SPEC (before first run) ===
Levels: prior-day HIGH and LOW (PDH/PDL). ADR = trailing 8-day mean daily range.
Touch: bar whose range contains the level, or comes within 0.10 x ADR of it.
Approach side: sign(level - close[t-10]) (+1 = testing from below/resistance).
  Bars with |approach| ambiguous (level inside close[t-10] bar) dropped.
Groups at the touch bar (self-calib rolling tod pctiles, same engine as v2):
  ABSORB = tempo >= p80 AND amplitude <= p40   (his pattern: fast, no progress)
  DRIVE  = tempo >= p80 AND amplitude >= p60   (fast, big range)
  PLAIN  = tempo in [p20, p80)                 (ordinary touch = control)
Sub-split inside ABSORB (pre-declared): avg trade size (vol/ticks) rolling-480
  global percentile >= 66 ("big prints") vs < 34 ("small prints").
Dedup: one event per (level, side) per 20 bars.
Outcome anchored at the LEVEL price, walked intrabar to day end:
  REJECT = price moves 0.25 x ADR from the level back toward the approach side
           BEFORE penetrating 0.10 x ADR beyond the level
  BREAK  = the penetration comes first; both-in-bar / day-end dropped.
Report: P(reject) by group, by year, ABSORB trade-size split; z ABSORB vs PLAIN.

    python tempo/scripts/absorption_at_level_test.py
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
ADR_LB = 8
TOUCH_ADR, REJ_ADR, PEN_ADR = 0.10, 0.25, 0.10
GAP = 20


def rolling_bucket_pct(df: pd.DataFrame, col: str) -> np.ndarray:
    pct = np.full(len(df), np.nan)
    for _, idx in df.groupby("bucket").groups.items():
        idx = np.asarray(idx)
        vals = df.loc[idx, col].to_numpy()
        for j in range(len(idx)):
            lo = max(0, j - CAP)
            w = vals[lo:j]
            w = w[~np.isnan(w)]
            if len(w) < MINS:
                continue
            if np.isnan(vals[j]):
                continue
            pct[idx[j]] = max(1, min(99, 100.0 * (w <= vals[j]).sum() / (len(w) + 1)))
    return pct


def rolling_global_pct(vals: np.ndarray) -> np.ndarray:
    out = np.full(len(vals), np.nan)
    for j in range(len(vals)):
        lo = max(0, j - CAP)
        w = vals[lo:j]
        w = w[~np.isnan(w)]
        if len(w) < MINS or np.isnan(vals[j]):
            continue
        out[j] = max(1, min(99, 100.0 * (w <= vals[j]).sum() / (len(w) + 1)))
    return out


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(BARS)
    df = df.sort_values(["date", "bar"]).reset_index(drop=True)
    df["bucket"] = (df["session_min"] // 15).astype(int).clip(0, 26)
    df.loc[df["ticks"] != 2000, ["tempo"]] = np.nan
    print("computing rolling percentiles (tempo, range, trade size)...")
    df["tpct"] = rolling_bucket_pct(df, "tempo")
    df["apct"] = rolling_bucket_pct(df, "range")
    df["szpct"] = rolling_global_pct(df["avg_trade_size"].to_numpy())

    day = df.groupby("date").agg(hi=("high", "max"), lo=("low", "min"),
                                 last_end=("end", "max"))
    day["adr"] = (day["hi"] - day["lo"]).shift(1).rolling(ADR_LB).mean()
    day["pdh"] = day["hi"].shift(1)
    day["pdl"] = day["lo"].shift(1)
    day["last_t"] = pd.to_datetime(day["last_end"]).dt.time
    keep = day[(day["last_t"] >= dt.time(14, 0)) & day["adr"].notna() & (day["adr"] > 0)
               & day["pdh"].notna()]

    events = []
    for date, g in df[df["date"].isin(keep.index)].groupby("date"):
        g = g.reset_index(drop=True)
        adr = keep.loc[date, "adr"]
        levels = {"PDH": keep.loc[date, "pdh"], "PDL": keep.loc[date, "pdl"]}
        h, l, c = g["high"].to_numpy(), g["low"].to_numpy(), g["close"].to_numpy()
        n = len(g)
        last_ev = {}
        for t in range(10, n):
            for lname, L in levels.items():
                near = (l[t] <= L <= h[t]) or min(abs(h[t] - L), abs(l[t] - L)) <= TOUCH_ADR * adr
                if not near:
                    continue
                side = np.sign(L - c[t - 10])
                if side == 0:
                    continue
                key = (lname, side)
                if t - last_ev.get(key, -999) < GAP:
                    continue
                tp, ap = g["tpct"].iloc[t], g["apct"].iloc[t]
                if np.isnan(tp) or np.isnan(ap):
                    continue
                if tp >= 80 and ap <= 40:
                    grp = "ABSORB"
                elif tp >= 80 and ap >= 60:
                    grp = "DRIVE"
                elif 20 <= tp < 80:
                    grp = "PLAIN"
                else:
                    continue
                last_ev[key] = t
                rej_t = L - side * REJ_ADR * adr
                pen_t = L + side * PEN_ADR * adr
                label = "unresolved"
                for j in range(t + 1, n):
                    hit_rej = l[j] <= rej_t if side == 1 else h[j] >= rej_t
                    hit_pen = h[j] >= pen_t if side == 1 else l[j] <= pen_t
                    if hit_rej and hit_pen:
                        label = "ambiguous"; break
                    if hit_rej:
                        label = "reject"; break
                    if hit_pen:
                        label = "break"; break
                events.append({"date": date, "level": lname, "side": int(side),
                               "grp": grp, "label": label,
                               "szpct": float(g["szpct"].iloc[t]) if np.isfinite(g["szpct"].iloc[t]) else np.nan,
                               "session_min": float(g["session_min"].iloc[t])})
    ev = pd.DataFrame(events)
    ev.to_csv(OUT / f"absorption_events_{today}.csv", index=False)
    r = ev[ev["label"].isin(["reject", "break"])].copy()
    r["year"] = r["date"].str[:4]
    print(f"events {len(ev)}  resolved {len(r)}")

    lines = ["=== P(reject) by group ==="]
    for grp, g in r.groupby("grp"):
        lines.append(f"  {grp:<7} n={len(g):>5}  P(reject)={(g['label']=='reject').mean():.3f}")
    lines.append("\n=== by year ===")
    piv = r.assign(rej=(r["label"] == "reject").astype(int)) \
        .pivot_table(index="year", columns="grp", values="rej", aggfunc=["count", "mean"]).round(3)
    lines.append(piv.to_string())
    ab = r[r["grp"] == "ABSORB"]
    big = ab[ab["szpct"] >= 66]; small = ab[ab["szpct"] < 34]
    lines.append(f"\n=== ABSORB trade-size split ===")
    lines.append(f"  big prints  n={len(big):>4}  P(reject)={(big['label']=='reject').mean():.3f}")
    lines.append(f"  small prints n={len(small):>4}  P(reject)={(small['label']=='reject').mean():.3f}")
    a = r[r["grp"] == "ABSORB"]; b = r[r["grp"] == "PLAIN"]
    if len(a) > 10 and len(b) > 10:
        pa, pb = (a["label"] == "reject").mean(), (b["label"] == "reject").mean()
        pp = (len(a) * pa + len(b) * pb) / (len(a) + len(b))
        se = np.sqrt(pp * (1 - pp) * (1 / len(a) + 1 / len(b)))
        lines.append(f"\nheadline: P(reject|ABSORB)={pa:.3f} (n={len(a)}) vs PLAIN={pb:.3f} "
                     f"(n={len(b)})  diff={pa-pb:+.3f}  z={(pa-pb)/se:.2f}")
    txt = "\n".join(lines)
    (OUT / f"absorption_test_{today}.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
