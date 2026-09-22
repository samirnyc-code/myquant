"""event_fingerprints.py — Stage 2 of the tempo/market-state study (S116).

Do tempo x efficiency signatures discriminate reversal from continuation at
structural events? (H4/H5 from the handoff doc.) Events are labeled with the
validated LegLab engine (leglab/scripts/leg_engine.py) run on 2000-tick bars.

=== FROZEN SPEC (pre-registered before first run; do not tune) ===
Data: tempo/outputs/bars_2000t_all.parquet. Excluded days: last bar ends
before 14:00 CT (half-days/stubs), <20 bars, no valid ADR (8-day mean of
prior daily ranges, LegLab spec). Leg threshold 0.15 x ADR (LegLab spec).

CONTRAST 1 — "extension moment" (PROSPECTIVE sampling, tradeable framing):
  Sample: first bar te where the running leg's depth (extreme - anchor)
  reaches >= 0.70 x ADR. One sample per leg. Causal by construction.
  Outcome, walked forward intrabar to day end:
    REVERSAL     adverse excursion >= 0.50 x ADR from the running extreme
                 fires before EXTENSION
    CONTINUATION price extends >= 0.25 x ADR beyond the extreme-at-te first
    both-in-one-bar -> ambiguous (dropped, counted); day-end -> unresolved
    (dropped, counted).
  Features at te (causal, trailing K=10 full bars): mean tod_adj_tempo,
  tempo_accel at te, mean directional efficiency SIGNED toward leg dir
  (eff_dir), eff_dir slope over the window, leg depth/ADR, session minute.
  H4 test: P(reversal | tempo hi/lo x eff_dir slope falling/rising), split
  at the DISCOVERY median of each feature (frozen for val/OOS).

CONTRAST 2 — pullback continue vs fail (retrospective research labels):
  Trend leg = closed leg, size >= 0.50 x ADR. Pullback = the next closed
  counter-leg. Label CONTINUE if the trend extreme is retaken before day
  end after the pullback pivot, else FAIL. Pullback must end before 14:00 CT.
  Features over the pullback's bars: mean tod_adj_tempo, mean eff signed
  toward PULLBACK direction (opposing initiative), tempo ratio pullback/
  trend leg, size ratio pullback/trend.
  H5: continuation pullbacks show lower tempo + lower opposing efficiency.

Splits: discovery <=2024-12-31, validation 2025, OOS 2026. Thresholds and
feature medians frozen from discovery.

Outputs (dated): contrast1/2 event CSVs, summary CSV, fingerprint PNG.
    python tempo/scripts/event_fingerprints.py
"""
from __future__ import annotations
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "leglab" / "scripts"))
sys.path.insert(0, str(ROOT / "tempo" / "scripts"))
from leg_engine import legs_for_day  # noqa: E402
from redundancy_gate import build_features  # noqa: E402

ALL = ROOT / "tempo" / "outputs" / "bars_2000t_all.parquet"
OUT = ROOT / "tempo" / "outputs"

ADR_LOOKBACK = 8
THRESH_FRAC = 0.15      # leg reversal threshold (LegLab spec)
DEPTH = 0.70            # contrast-1 trigger, x ADR
REV = 0.50              # contrast-1 reversal outcome, x ADR
EXT = 0.25              # contrast-1 continuation outcome, x ADR
TREND_MIN = 0.50        # contrast-2 trend-leg minimum, x ADR
K = 10                  # trailing feature window, bars
SPLITS = {"discovery": ("0000", "2024"), "validation": ("2025", "2025"),
          "oos": ("2026", "2026")}


def load():
    df = pd.read_parquet(ALL)
    df = build_features(df, horizon=1)  # adds tod_adj_tempo, tempo_accel, rv20
    sgn = np.sign(df["close"] - df["open"])
    df["eff_dir"] = df["eff"] * sgn          # signed efficiency (+ = up bar)
    # day filters + ADR
    day = df.groupby("date").agg(hi=("high", "max"), lo=("low", "min"),
                                 last_end=("end", "max"), n=("bar", "size"))
    day["rng"] = day["hi"] - day["lo"]
    day["adr"] = day["rng"].shift(1).rolling(ADR_LOOKBACK).mean()
    day["last_t"] = pd.to_datetime(day["last_end"]).dt.time
    keep = day[(day["last_t"] >= dt.time(14, 0)) & (day["n"] >= 20)
               & day["adr"].notna() & (day["adr"] > 0)]
    df = df[df["date"].isin(keep.index)].copy()
    return df, keep["adr"]


def split_of(date: str) -> str:
    y = date[:4]
    for name, (y0, y1) in SPLITS.items():
        if y0 <= y <= y1:
            return name
    return "none"


def contrast1(df, adr_by_day):
    events = []
    for date, g in df.groupby("date"):
        g = g.reset_index(drop=True)
        adr = adr_by_day[date]
        h, l, o = g["high"].to_numpy(), g["low"].to_numpy(), g["open"].to_numpy()
        legs = legs_for_day(o, h, l, g["start"].to_numpy(), THRESH_FRAC * adr,
                            include_final=True)
        n = len(g)
        for lg in legs:
            if lg["size"] < DEPTH * adr:
                continue
            d, i0, i1, p0 = lg["dir"], lg["i0"], lg["i1"], lg["p0"]
            # te = first bar in (i0, i1] where running extreme depth >= DEPTH*ADR
            te, ext_te = None, None
            run = p0
            for i in range(i0 + 1, i1 + 1):
                run = max(run, h[i]) if d == 1 else min(run, l[i])
                if abs(run - p0) >= DEPTH * adr:
                    te, ext_te = i, run
                    break
            if te is None or te < K:
                continue
            # outcome walk: extension target FIXED at extreme-at-te + EXT (spec);
            # reversal measured from the running extreme (which may extend < EXT)
            ext_target = ext_te + d * EXT * adr
            run2, label, tr = ext_te, "unresolved", None
            for j in range(te + 1, n):
                hit_ext = (h[j] >= ext_target) if d == 1 else (l[j] <= ext_target)
                adverse = (run2 - l[j]) if d == 1 else (h[j] - run2)
                hit_rev = adverse >= REV * adr
                if hit_ext and hit_rev:
                    label = "ambiguous"; break
                if hit_ext:
                    label = "continuation"; tr = j; break
                if hit_rev:
                    label = "reversal"; tr = j; break
                run2 = max(run2, h[j]) if d == 1 else min(run2, l[j])
            w = g.iloc[te - K + 1: te + 1]
            x = np.arange(K, dtype=float)
            effd = (w["eff_dir"] * d).to_numpy()      # + = with-leg efficiency
            slope = np.polyfit(x, effd, 1)[0] if np.isfinite(effd).all() else np.nan
            events.append({
                "date": date, "split": split_of(date), "dir": d, "te": te,
                "label": label, "bars_to_resolve": (tr - te) if tr else np.nan,
                "leg_depth_adr": abs(ext_te - p0) / adr,
                "session_min": float(g["session_min"].iloc[te]),
                "tempo_mean": float(w["tod_adj_tempo"].mean()),
                "tempo_accel": float(g["tempo_accel"].iloc[te]),
                "effdir_mean": float(np.nanmean(effd)),
                "effdir_slope": float(slope),
            })
    return pd.DataFrame(events)


def contrast2(df, adr_by_day):
    events = []
    for date, g in df.groupby("date"):
        g = g.reset_index(drop=True)
        adr = adr_by_day[date]
        h, l, o = g["high"].to_numpy(), g["low"].to_numpy(), g["open"].to_numpy()
        legs = legs_for_day(o, h, l, g["start"].to_numpy(), THRESH_FRAC * adr,
                            include_final=False)
        n = len(g)
        for a in range(len(legs) - 1):
            tl, pb = legs[a], legs[a + 1]
            if tl["size"] < TREND_MIN * adr or not pb["closed"]:
                continue
            if g["end"].iloc[pb["i1"]].time() >= dt.time(14, 0):
                continue
            d = tl["dir"]
            # CONTINUE = trend extreme retaken after the pullback pivot bar
            after = g.iloc[pb["i1"] + 1: n]
            retaken = bool((after["high"] > tl["p1"]).any()) if d == 1 else \
                bool((after["low"] < tl["p1"]).any())
            wpb = g.iloc[pb["i0"] + 1: pb["i1"] + 1]
            wtr = g.iloc[tl["i0"] + 1: tl["i1"] + 1]
            if len(wpb) == 0 or len(wtr) == 0:
                continue
            opp = (wpb["eff_dir"] * (-d)).mean()      # + = efficient AGAINST trend
            events.append({
                "date": date, "split": split_of(date), "dir": d,
                "label": "continue" if retaken else "fail",
                "trend_adr": tl["size"] / adr, "pb_adr": pb["size"] / adr,
                "size_ratio": pb["size"] / tl["size"],
                "pb_bars": len(wpb),
                "pb_tempo": float(wpb["tod_adj_tempo"].mean()),
                "tempo_ratio": float(wpb["tod_adj_tempo"].mean()
                                     - wtr["tod_adj_tempo"].mean()),
                "pb_opp_eff": float(opp),
                "session_min": float(g["session_min"].iloc[pb["i1"]]),
            })
    return pd.DataFrame(events)


def cohens_d(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    sp = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1))
                 / (len(a) + len(b) - 2))
    return (a.mean() - b.mean()) / sp if sp > 0 else np.nan


def summarize(c1, c2):
    lines, rows = [], []
    c1r = c1[c1["label"].isin(["reversal", "continuation"])].copy()
    lines.append("=== CONTRAST 1: extension moments (prospective) ===")
    lines.append(c1["label"].value_counts().to_string())
    feats1 = ["tempo_mean", "tempo_accel", "effdir_mean", "effdir_slope",
              "leg_depth_adr", "session_min"]
    med = c1r[c1r["split"] == "discovery"][["tempo_mean", "effdir_slope"]].median()
    for sp in SPLITS:
        g = c1r[c1r["split"] == sp]
        if len(g) < 30:
            continue
        rev, cont = g[g["label"] == "reversal"], g[g["label"] == "continuation"]
        base = len(rev) / len(g)
        lines.append(f"\n--- {sp}: n={len(g)}  P(reversal)={base:.3f} ---")
        for f in feats1:
            d_ = cohens_d(rev[f].dropna(), cont[f].dropna())
            rows.append({"contrast": 1, "split": sp, "feature": f,
                         "mean_rev": rev[f].mean(), "mean_cont": cont[f].mean(),
                         "cohens_d": d_})
            lines.append(f"  {f:>15}: rev {rev[f].mean():+.3f}  cont {cont[f].mean():+.3f}  d={d_:+.2f}")
        # H4 2x2 on frozen discovery medians
        hi_t = g["tempo_mean"] >= med["tempo_mean"]
        fall_e = g["effdir_slope"] < med["effdir_slope"]
        lines.append(f"  H4 P(rev) [base {base:.3f}]:")
        for tn, tm in [("tempo_hi", hi_t), ("tempo_lo", ~hi_t)]:
            for en, em in [("eff_falling", fall_e), ("eff_rising", ~fall_e)]:
                cell = g[tm & em]
                p = (cell["label"] == "reversal").mean() if len(cell) else np.nan
                rows.append({"contrast": 1, "split": sp,
                             "feature": f"P_rev|{tn},{en}", "mean_rev": p,
                             "mean_cont": len(cell), "cohens_d": np.nan})
                lines.append(f"    {tn:>8} x {en:<11} n={len(cell):>4}  P(rev)={p:.3f}")

    lines.append("\n=== CONTRAST 2: pullback continue vs fail (retrospective) ===")
    lines.append(c2["label"].value_counts().to_string())
    feats2 = ["pb_tempo", "tempo_ratio", "pb_opp_eff", "size_ratio", "pb_bars"]
    for sp in SPLITS:
        g = c2[c2["split"] == sp]
        if len(g) < 30:
            continue
        co, fa = g[g["label"] == "continue"], g[g["label"] == "fail"]
        lines.append(f"\n--- {sp}: n={len(g)}  P(continue)={len(co)/len(g):.3f} ---")
        for f in feats2:
            d_ = cohens_d(co[f].dropna(), fa[f].dropna())
            rows.append({"contrast": 2, "split": sp, "feature": f,
                         "mean_rev": co[f].mean(), "mean_cont": fa[f].mean(),
                         "cohens_d": d_})
            lines.append(f"  {f:>12}: continue {co[f].mean():+.3f}  fail {fa[f].mean():+.3f}  d={d_:+.2f}")
    return "\n".join(lines), pd.DataFrame(rows)


def chart(c1, c2, today):
    c1r = c1[c1["label"].isin(["reversal", "continuation"])]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.6))
    d0 = c1r[c1r["split"] == "discovery"]
    for f, ax in [("effdir_slope", axes[0]), ("tempo_mean", axes[1])]:
        for lab, c in [("reversal", "#d62728"), ("continuation", "#2ca02c")]:
            ax.hist(d0[d0["label"] == lab][f], bins=40, alpha=0.5, density=True,
                    label=lab, color=c)
        ax.set_title(f"C1 discovery: {f}"); ax.legend(); ax.grid(alpha=0.25)
    for lab, c in [("continue", "#2ca02c"), ("fail", "#d62728")]:
        g = c2[(c2["split"] == "discovery") & (c2["label"] == lab)]
        axes[2].hist(g["pb_opp_eff"], bins=40, alpha=0.5, density=True,
                     label=lab, color=c)
    axes[2].set_title("C2 discovery: pullback opposing efficiency")
    axes[2].legend(); axes[2].grid(alpha=0.25)
    png = OUT / f"event_fingerprints_{today}.png"
    fig.tight_layout(); fig.savefig(png, dpi=110); plt.close(fig)
    return png


def main():
    today = dt.date.today().isoformat()
    df, adr = load()
    print(f"days after filters: {df['date'].nunique():,}")
    c1 = contrast1(df, adr)
    c2 = contrast2(df, adr)
    c1.to_csv(OUT / f"event_fp_contrast1_{today}.csv", index=False)
    c2.to_csv(OUT / f"event_fp_contrast2_{today}.csv", index=False)
    txt, summary = summarize(c1, c2)
    summary.to_csv(OUT / f"event_fp_summary_{today}.csv", index=False)
    print(txt)
    png = chart(c1, c2, today)
    (OUT / f"event_fp_summary_{today}.txt").write_text(txt, encoding="utf-8")
    print(f"\nsaved -> event_fp_contrast1/2_{today}.csv, summary csv/txt, {png.name}")


if __name__ == "__main__":
    main()
