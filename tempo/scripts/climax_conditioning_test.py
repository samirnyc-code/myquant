"""climax_conditioning_test.py — pre-registered pair on the replicated climax effect (S116-tempo).

Base framework = climax_at_high_test.py EXACTLY (new 20-bar extreme, gap 10,
self-calibrated tempo pctile, climax >=95 vs control <80, reversal = 0.25xADR
retrace before 0.10xADR extension). Adds, PRE-REGISTERED before first run:

  C1 LEVEL CONFLUENCE: event extreme within 0.15 x ADR of the PRIOR DAY's high
     or low. (Session-extreme retests excluded — entangled with the event def.)
  C2 EFFICIENCY COLLAPSE: mean toward-move signed efficiency of bars [t-2..t]
     LOWER than that of bars [t-5..t-3] (activity up, accomplishment down).
  C3 DEPTH PROFILE (descriptive): per event, max retrace from the event extreme
     BEFORE the extreme is first exceeded (day-end capped), and max extension,
     both in ADR units — the sizing-relevant distribution, not just the binary.

Report: P(rev) for climax x confluence, climax x eff-collapse, the triple, the
same splits inside CONTROL (placebo check), all by year; depth quantiles by group.

    python tempo/scripts/climax_conditioning_test.py
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
OUT = ROOT / "tempo" / "outputs"

CAP, MINS = 480, 30
NHIGH, GAP = 20, 10
CLIMAX, CTRL = 95.0, 80.0
REV_ADR, EXT_ADR = 0.25, 0.10
CONF_ADR = 0.15
ADR_LB = 8


def main():
    today = dt.date.today().isoformat()
    df = pd.read_parquet(BARS)
    df = df.sort_values(["date", "bar"]).reset_index(drop=True)
    df["bucket"] = (df["session_min"] // 15).astype(int).clip(0, 26)
    df.loc[df["ticks"] != 2000, "tempo"] = np.nan
    print("computing rolling self-calibrated percentiles...")
    df["tpct"] = rolling_bucket_pct(df)
    sgn = np.sign(df["close"] - df["open"])
    df["effdir"] = df["eff"] * sgn

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
        adr, pdh, pdl = keep.loc[date, "adr"], keep.loc[date, "pdh"], keep.loc[date, "pdl"]
        h, l = g["high"].to_numpy(), g["low"].to_numpy()
        tp, ed = g["tpct"].to_numpy(), g["effdir"].to_numpy()
        n = len(g)
        last_ev = {1: -999, -1: -999}
        for t in range(NHIGH, n):
            for side in (1, -1):
                if side == 1:
                    is_new = h[t] > h[t - NHIGH:t].max(); ext_p = h[t]
                else:
                    is_new = l[t] < l[t - NHIGH:t].min(); ext_p = l[t]
                if not is_new or t - last_ev[side] < GAP:
                    continue
                w = tp[max(0, t - 2):t + 1]; w = w[~np.isnan(w)]
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
                # C1 confluence vs prior-day H/L
                conf = min(abs(ext_p - pdh), abs(ext_p - pdl)) <= CONF_ADR * adr
                # C2 efficiency collapse (toward-move = side * effdir)
                eff_fall = np.nan
                if t >= 5:
                    recent = np.nanmean(side * ed[t - 2:t + 1])
                    prior = np.nanmean(side * ed[t - 5:t - 2])
                    eff_fall = bool(recent < prior)
                # outcome + C3 depth walk
                rev_t = ext_p - side * REV_ADR * adr
                ext_t = ext_p + side * EXT_ADR * adr
                label = "unresolved"
                max_retrace = 0.0; max_ext = 0.0; broke = False
                for j in range(t + 1, n):
                    retr = (ext_p - l[j]) if side == 1 else (h[j] - ext_p)
                    extn = (h[j] - ext_p) if side == 1 else (ext_p - l[j])
                    if not broke:
                        max_retrace = max(max_retrace, retr)
                    max_ext = max(max_ext, extn)
                    if extn > 0:
                        broke = True
                    hit_ext = h[j] >= ext_t if side == 1 else l[j] <= ext_t
                    hit_rev = l[j] <= rev_t if side == 1 else h[j] >= rev_t
                    if label == "unresolved":
                        if hit_ext and hit_rev: label = "ambiguous"
                        elif hit_ext: label = "continuation"
                        elif hit_rev: label = "reversal"
                events.append({"date": date, "side": side, "grp": grp, "label": label,
                               "conf": bool(conf), "eff_fall": eff_fall,
                               "retrace_adr": round(max_retrace / adr, 3),
                               "ext_adr": round(max_ext / adr, 3)})
    ev = pd.DataFrame(events)
    ev.to_csv(OUT / f"climax_conditioning_events_{today}.csv", index=False)
    r = ev[ev["label"].isin(["reversal", "continuation"])].copy()
    r["year"] = r["date"].str[:4]
    print(f"events {len(ev)}  resolved {len(r)}")

    lines = []
    def cell(sub, name):
        p = (sub["label"] == "reversal").mean() if len(sub) else np.nan
        lines.append(f"  {name:<38} n={len(sub):>5}  P(rev)={p:.3f}")
        return p

    for grp in ["climax", "control"]:
        g = r[r["grp"] == grp]
        lines.append(f"\n=== {grp.upper()} (base P(rev)={ (g['label']=='reversal').mean():.3f}, n={len(g)}) ===")
        cell(g[g["conf"]], "C1 at prior-day H/L")
        cell(g[~g["conf"]], "C1 away from level")
        ge = g[g["eff_fall"].notna()]
        cell(ge[ge["eff_fall"] == True], "C2 eff collapsing")      # noqa: E712
        cell(ge[ge["eff_fall"] == False], "C2 eff holding")        # noqa: E712
        cell(ge[(ge["conf"]) & (ge["eff_fall"] == True)], "C1+C2 triple")   # noqa: E712

    lines.append("\n=== by year: P(rev) climax C1+C2 vs climax rest ===")
    for yr, g in r[r["grp"] == "climax"].groupby("year"):
        ge = g[g["eff_fall"].notna()]
        both = ge[(ge["conf"]) & (ge["eff_fall"] == True)]         # noqa: E712
        rest = ge[~((ge["conf"]) & (ge["eff_fall"] == True))]      # noqa: E712
        pb = (both["label"] == "reversal").mean() if len(both) else np.nan
        pr = (rest["label"] == "reversal").mean() if len(rest) else np.nan
        lines.append(f"  {yr}: triple n={len(both):>3} P(rev)={pb:.3f}   rest n={len(rest):>4} P(rev)={pr:.3f}")

    lines.append("\n=== C3 depth profile (ADR units, retrace before extreme broken) ===")
    for grp, g in r.groupby("grp"):
        q = g["retrace_adr"].quantile([0.25, 0.5, 0.75, 0.9]).round(3)
        lines.append(f"  {grp}: retrace q25={q[0.25]} med={q[0.5]} q75={q[0.75]} q90={q[0.9]}"
                     f"   ext med={g['ext_adr'].median():.3f}")
    txt = "\n".join(lines)
    (OUT / f"climax_conditioning_{today}.txt").write_text(txt, encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
