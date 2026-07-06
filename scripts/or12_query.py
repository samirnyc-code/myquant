"""
or12_query.py — QUERY MODE: the "it's 9:35, what am I looking at?" engine.

Give it a date; it reconstructs what was knowable at 09:30 CT that day and
produces an HTML report:
  1. The day's IB (first 12 bars) as a chart — the 9:35 view
  2. Its base-rate card row (note 0012's 3 factors: open bucket, IB width
     tier, 10:30 close location) with rates computed from PAST days only
  3. Its K nearest twins (past days, same bucket) as full-day charts
  4. The twins' outcome distribution — shown as a "read" only when the vote
     is confident (>=55% on one class); otherwise explicitly "no read"
  5. --reveal adds the query day's actual full day at the bottom (study mode)

Everything conditioning is causal at 09:30; twins and card stats use only
days BEFORE the query date (walk-forward-honest, like a live tool).

Usage:
  python scripts/or12_query.py                 # latest day in the dataset
  python scripts/or12_query.py --date 2026-06-15 --k 5 --reveal

Output: docs/living/or12_query/<date>/index.html (+ PNGs)
"""
from __future__ import annotations

import argparse
import sys
from datetime import date as _date
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from or12_pattern_groups import build_features, BARS_PQ, N_BARS   # noqa: E402
from or12_outcome_agreement import day_outcome                     # noqa: E402
from or12_render_pairs_fullday import draw_day, BUCKET_TXT         # noqa: E402

CONF_GATE = 0.55


def draw_ib_only(ax, g: pd.DataFrame, title: str) -> None:
    g = g.sort_values("DateTime").head(N_BARS).reset_index(drop=True)
    o = g["Open"].to_numpy(float); h = g["High"].to_numpy(float)
    l = g["Low"].to_numpy(float);  c = g["Close"].to_numpy(float)
    for i in range(len(g)):
        up = c[i] >= o[i]
        col = "#26a69a" if up else "#ef5350"
        ax.vlines(i, l[i], h[i], color=col, linewidth=1.4)
        blo, bhi = min(o[i], c[i]), max(o[i], c[i])
        if bhi - blo < 1e-9:
            bhi = blo + max(h[i] - l[i], 1e-6) * 0.02
        ax.add_patch(plt.Rectangle((i - 0.3, blo), 0.6, bhi - blo,
                                   facecolor=col, edgecolor=col))
    ax.set_xlim(-0.8, N_BARS - 0.2)
    ax.set_xticks(range(N_BARS))
    ax.set_xticklabels([str(i + 1) for i in range(N_BARS)], fontsize=9)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.grid(True, alpha=0.25)
    ax.set_facecolor("#fafafa")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default: latest)")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--reveal", action="store_true",
                    help="also show the query day's actual full day")
    args = ap.parse_args()

    bars = pd.read_parquet(BARS_PQ).drop(columns=["Contract"], errors="ignore")
    bars["DateTime"] = pd.to_datetime(bars["DateTime"])
    by_date = {d: g for d, g in bars.groupby(bars["DateTime"].dt.date)}

    daily = bars.groupby(bars["DateTime"].dt.date).agg(
        O=("Open", "first"), H=("High", "max"),
        L=("Low", "min"),    C=("Close", "last"))
    dates_sorted = list(daily.index)
    prior_of = {d: dates_sorted[i - 1] if i > 0 else None
                for i, d in enumerate(dates_sorted)}

    df, Xz, _ = build_features()
    qd = (_date.fromisoformat(args.date) if args.date else df.index.max())
    if qd not in df.index:
        raise SystemExit(f"{qd} not in feature set (holiday/short day?). "
                         f"Range: {df.index.min()}..{df.index.max()}")
    qi = df.index.get_loc(qd)
    q = df.iloc[qi]

    # ── past-only universe ───────────────────────────────────────────────────
    past_mask = np.arange(len(df)) < qi
    past = df[past_mask]
    if len(past) < 120:
        raise SystemExit("not enough history before this date")

    # card factors, computed the live way (trailing tier cuts)
    t1, t2 = past["ib_atr"].quantile([1/3, 2/3])
    tier = "narrow" if q["ib_atr"] < t1 else ("mid" if q["ib_atr"] < t2 else "wide")
    past_tier = pd.cut(past["ib_atr"], [-np.inf, t1, t2, np.inf],
                       labels=["narrow", "mid", "wide"])
    c12_band = ("low3rd" if q["close_loc"] <= 1/3 else
                "mid3rd" if q["close_loc"] <= 2/3 else "high3rd")
    past_band = pd.cut(past["close_loc"], [-0.01, 1/3, 2/3, 1.01],
                       labels=["low3rd", "mid3rd", "high3rd"])

    # outcomes for past days
    outs = {}
    for d in past.index:
        o = day_outcome(by_date[d])
        if o is not None:
            outs[d] = o
    po = pd.DataFrame.from_dict(outs, orient="index").reindex(past.index)

    def cell(mask, label):
        sub = po[mask & po["class3"].notna()]
        n = len(sub)
        if n < 30:
            return f"<tr><td>{label}</td><td colspan=5>n={n} — too thin, no read</td></tr>"
        return ("<tr><td>{}</td><td>{}</td><td>{:.0%}</td><td>{:.0%}</td>"
                "<td>{:.0%}</td><td>{:.0%}</td></tr>").format(
            label, n,
            (sub["class3"] == "above").mean(),
            (sub["class3"] == "inside").mean(),
            (sub["class3"] == "below").mean(),
            (np.maximum(sub["ext_up"], sub["ext_dn"]) > 0.5).mean())

    rows_html = [
        "<tr><th>conditioning</th><th>n</th><th>close&gt;IB</th>"
        "<th>inside</th><th>close&lt;IB</th><th>ext&gt;0.5IB</th></tr>",
        cell(pd.Series(True, index=past.index), "all past days"),
        cell(past["bucket"] == q["bucket"], f"bucket = {q['bucket']}"),
        cell((past["bucket"] == q["bucket"]) & (past_tier == tier).to_numpy(),
             f"bucket + IB {tier}"),
        cell((past_band == c12_band).to_numpy(), f"10:30 location = {c12_band}"),
    ]

    # ── twins (past, same bucket) ────────────────────────────────────────────
    pool_idx = np.where(past_mask & (df["bucket"] == q["bucket"]).to_numpy())[0]
    dist = ((Xz[pool_idx] - Xz[qi]) ** 2).sum(axis=1)
    nn = pool_idx[np.argsort(dist)[:args.k]]
    twin_dates = [df.index[j] for j in nn]

    twin_cls = [outs[d]["class3"] for d in twin_dates if d in outs]
    read = "no confident read (twins disagree)"
    if twin_cls:
        vals, cnts = np.unique(twin_cls, return_counts=True)
        conf = cnts.max() / len(twin_cls)
        if conf >= CONF_GATE:
            read = (f"<b>twin read: day closes {vals[cnts.argmax()]} the IB "
                    f"({conf:.0%} of twins)</b>")

    # ── render ───────────────────────────────────────────────────────────────
    out_dir = ROOT / "docs" / "living" / "or12_query" / str(qd)
    out_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(9, 4))
    draw_ib_only(ax, by_date[qd], f"{qd} — the 9:35 view (IB only)")
    fig.tight_layout(); fig.savefig(out_dir / "query_ib.png", dpi=110); plt.close(fig)

    imgs = ["query_ib.png"]
    for r, d in enumerate(twin_dates, 1):
        fig, ax = plt.subplots(figsize=(11, 4))
        pd_ = prior_of[d]
        prior = daily.loc[pd_] if pd_ is not None else None
        oc = outs.get(d)
        lbl = (f"twin #{r}  {d}   -> closed {oc['class3']} IB" if oc else f"twin #{r}  {d}")
        draw_day(ax, by_date[d], prior, lbl)
        fn = f"twin_{r}_{d}.png"
        fig.tight_layout(); fig.savefig(out_dir / fn, dpi=110); plt.close(fig)
        imgs.append(fn)

    if args.reveal:
        fig, ax = plt.subplots(figsize=(11, 4))
        pd_ = prior_of[qd]
        prior = daily.loc[pd_] if pd_ is not None else None
        draw_day(ax, by_date[qd], prior, f"{qd} — what actually happened")
        fig.tight_layout(); fig.savefig(out_dir / "reveal.png", dpi=110); plt.close(fig)
        imgs.append("reveal.png")

    gap_txt = f"{q['gap_norm']:+.0%} of yRange"
    html = [
        "<html><head><title>OR12 query</title><style>",
        "body{font-family:sans-serif;background:#1d1d1d;color:#eee;max-width:1150px;margin:auto}",
        "img{max-width:100%;margin:10px 0;border-radius:6px}",
        "table{border-collapse:collapse;margin:14px 0}td,th{border:1px solid #555;padding:5px 12px}",
        ".read{background:#2c3e50;padding:10px 16px;border-radius:6px;margin:12px 0}",
        "</style></head><body>",
        f"<h1>OR12 context query — {qd}</h1>",
        f"<p><b>{BUCKET_TXT[q['bucket']]}</b>, gap {gap_txt} · IB width "
        f"<b>{tier}</b> ({q['ib_atr']:.2f}x ADR14, trailing cuts {t1:.2f}/{t2:.2f}) · "
        f"10:30 close in <b>{c12_band}</b> of IB · drive {q['net_drive']:+.2f} · "
        f"flips {int(q['flips'])} · rvol {q['rvol_ib']:.2f}</p>",
        f"<img src='query_ib.png'>",
        "<h2>Base-rate card (past days only)</h2>",
        "<table>" + "".join(rows_html) + "</table>",
        f"<div class='read'>{read}</div>",
        "<p style='color:#999'>Reminder (notes 0010/0012): these condition day "
        "CHARACTER and settlement side. Direction of the move from here is not "
        "predictable from the morning.</p>",
        f"<h2>{args.k} nearest twins (past, same bucket)</h2>",
    ]
    html += [f"<div><img src='{f}'></div>" for f in imgs[1:]]
    html.append("</body></html>")
    (out_dir / "index.html").write_text("\n".join(html), encoding="utf-8")
    print(f"report: {out_dir / 'index.html'}")
    print(f"bucket={q['bucket']} tier={tier} c12={c12_band} twins={twin_dates}")


if __name__ == "__main__":
    main()
