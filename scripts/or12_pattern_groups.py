"""
or12_pattern_groups.py — group trading days by the PATTERN of their first 12
five-minute bars (bars 1-12 from the RTH open, = first 60 min) PLUS the
prior-day open context. STRICTLY causal: nothing after bar 12 of the query day
is used anywhere; prior-day/ADR features are fully known at the open.

v2 (this version):
  SHAPE block (within-window, price-level blind):
    path        — cumulative close path (C_i - O_1) / OR12_range, 12 points
    ibs         — per-bar IBS (C-L)/(H-L), 12 points
    body        — per-bar body fraction |C-O|/(H-L) (bodies vs tails), 12 points
    sign        — per-bar direction (+1 bull, -1 bear, 0 doji: body < 20% range)
    window      — net drive, #direction flips, mean bar-to-bar overlap,
                  BO count, failed-BO count, double-top/bottom flags,
                  position of window high/low, close location in OR
  CONTEXT block (prior day, causal):
    gap_norm    — (open - yClose) / yRange
    open_loc    — (open - yLow) / yRange   (0=yLow, 1=yHigh, outside = <0 / >1)
    prng_adr    — yesterday's range / ADR14 (ADR ending the day BEFORE yesterday)
    pclose_loc  — yesterday's close location within its own range

  HARD GATE — open-location bucket. Matches are only allowed within the same
  bucket (a gap-down-below-range open must never match an at-high open):
    above_yH  : open_loc > 1.0
    upper_half: 0.5 < open_loc <= 1.0
    lower_half: 0.0 <= open_loc <= 0.5
    below_yL  : open_loc < 0.0

BO   = bar makes a new extreme beyond ALL prior bars in the window AND closes
       beyond the prior extreme (acceptance).
fBO  = bar pokes a new extreme but closes back inside the prior extreme.
DT/DB= two local extremes within 15% of OR12 range of each other, >=3 bars apart.

Grouping: KMeans on the standardized shape+context matrix -> archetypes,
plus per-day 5 nearest neighbours restricted to the SAME bucket.

Output:
  docs/living/or12_pattern_groups_<date>.csv (per-day: bucket, cluster, neighbours)
  stdout: bucket sizes + cluster summaries with member dates
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BARS_PQ  = ROOT / "data" / "bars" / "_continuous.parquet"
OUT_CSV  = ROOT / "docs" / "living" / f"or12_pattern_groups_{datetime.now():%Y%m%d}.csv"
N_BARS   = 12
K        = 10          # clusters
N_NEIGH  = 5           # nearest neighbours listed per day
DOJI_BODY_FRAC = 0.20
DTB_TOL  = 0.15        # DT/DB tolerance as fraction of OR12 range
CTX_WEIGHT = 1.8       # weight of each context feature in the distance


def day_features(g: pd.DataFrame, ema: np.ndarray | None = None) -> dict | None:
    """SHAPE block from the first 12 bars of one day.
    `ema` = EMA20 values aligned to the first 12 bars (computed on the
    continuous close series, so bar i's EMA uses only data through bar i —
    causal; carries over from prior days by design)."""
    g = g.sort_values("DateTime").head(N_BARS)
    if len(g) < N_BARS:
        return None
    o = g["Open"].to_numpy(float); h = g["High"].to_numpy(float)
    l = g["Low"].to_numpy(float);  c = g["Close"].to_numpy(float)
    rng = h - l
    rng_safe = np.where(rng > 0, rng, np.nan)

    or_hi, or_lo = h.max(), l.min()
    or_rng = or_hi - or_lo
    if or_rng <= 0:
        return None

    ibs  = np.nan_to_num((c - l) / rng_safe, nan=0.5)
    body = np.nan_to_num(np.abs(c - o) / rng_safe, nan=0.0)
    sign = np.where(body < DOJI_BODY_FRAC, 0, np.sign(c - o)).astype(int)
    path = (c - o[0]) / or_rng                      # normalized close path

    nz = sign[sign != 0]
    flips = int(np.sum(nz[1:] != nz[:-1])) if len(nz) > 1 else 0

    ov = []
    for i in range(1, N_BARS):
        inter = min(h[i], h[i-1]) - max(l[i], l[i-1])
        union = max(h[i], h[i-1]) - min(l[i], l[i-1])
        ov.append(max(inter, 0.0) / union if union > 0 else 1.0)
    overlap = float(np.mean(ov))

    bo = fbo = 0
    for i in range(1, N_BARS):
        ph, pl = h[:i].max(), l[:i].min()
        if h[i] > ph:
            bo += 1 if c[i] > ph else 0
            fbo += 1 if c[i] <= ph else 0
        if l[i] < pl:
            bo += 1 if c[i] < pl else 0
            fbo += 1 if c[i] >= pl else 0

    def _local_ext(vals, cmp):
        return [i for i in range(1, N_BARS - 1)
                if cmp(vals[i], vals[i-1]) and cmp(vals[i], vals[i+1])]
    tops = _local_ext(h, lambda a, b: a >= b)
    bots = _local_ext(l, lambda a, b: a <= b)
    dt_flag = int(any(abs(h[i] - h[j]) <= DTB_TOL * or_rng and j - i >= 3
                      for x, i in enumerate(tops) for j in tops[x+1:]))
    db_flag = int(any(abs(l[i] - l[j]) <= DTB_TOL * or_rng and j - i >= 3
                      for x, i in enumerate(bots) for j in bots[x+1:]))

    net_drive = (c[-1] - o[0]) / or_rng
    hi_pos = float(np.argmax(h)) / (N_BARS - 1)
    lo_pos = float(np.argmin(l)) / (N_BARS - 1)
    close_loc = (c[-1] - or_lo) / or_rng
    # IB extreme formation order — documented ~2:1 skew on later break
    # direction (IB high formed first → break down 44.8% vs up 24.0%, and
    # vice versa; TradingStats ES 2015-25)
    ib_high_first = float(np.argmax(h) < np.argmin(l))

    # ── Brooks trend-vs-range diagnostics ────────────────────────────────────
    # Stop-entry traders: buy 1 tick above prior bar high / sell below prior
    # low, marked at that bar's close. Limit (BLSH) traders: buy at prior bar
    # low / sell at prior bar high when touched, marked at that bar's close.
    # Positive stop-P&L = trending IB; positive limit-P&L = rotating IB.
    bull_stop = bear_stop = bull_limit = bear_limit = 0.0
    for i in range(1, N_BARS):
        if h[i] > h[i-1]:
            bull_stop += c[i] - h[i-1]
            bear_limit += h[i-1] - c[i]
        if l[i] < l[i-1]:
            bear_stop += l[i-1] - c[i]
            bull_limit += c[i] - l[i-1]
    bull_stop /= or_rng; bear_stop /= or_rng
    bull_limit /= or_rng; bear_limit /= or_rng

    # ── Swing structure (strength-2 pivots, user-specified) ─────────────────
    # Pivot high at i: higher than the 2 bars each side (>= on the right so a
    # flat retest still counts). Pushes = successively higher swing highs in an
    # up move / lower swing lows in a down move. Wedge = 3 pushes (Brooks).
    # Two-legged pullback = the counter-move off the window extreme contains
    # exactly 2 legs (pullback low, bounce, second pullback low).
    ph = [i for i in range(2, N_BARS - 2)
          if h[i] > h[i-1] and h[i] > h[i-2] and h[i] >= h[i+1] and h[i] >= h[i+2]]
    pl = [i for i in range(2, N_BARS - 2)
          if l[i] < l[i-1] and l[i] < l[i-2] and l[i] <= l[i+1] and l[i] <= l[i+2]]
    pushes_up = 1 + sum(1 for a, b_ in zip(ph, ph[1:]) if h[b_] > h[a]) if ph else 0
    pushes_dn = 1 + sum(1 for a, b_ in zip(pl, pl[1:]) if l[b_] < l[a]) if pl else 0
    wedge_up = int(pushes_up >= 3)
    wedge_dn = int(pushes_dn >= 3)

    # two-legged pullback against the dominant drive (after the window extreme)
    twoleg_pb = 0
    if net_drive > 0.15:
        k0 = int(np.argmax(h))
        seg_l = l[k0:]
        if len(seg_l) >= 4:
            sw = [j for j in range(1, len(seg_l) - 1)
                  if seg_l[j] < seg_l[j-1] and seg_l[j] <= seg_l[j+1]]
            twoleg_pb = int(len(sw) >= 2 and seg_l[sw[1]] < seg_l[sw[0]])
    elif net_drive < -0.15:
        k0 = int(np.argmin(l))
        seg_h = h[k0:]
        if len(seg_h) >= 4:
            sw = [j for j in range(1, len(seg_h) - 1)
                  if seg_h[j] > seg_h[j-1] and seg_h[j] >= seg_h[j+1]]
            twoleg_pb = int(len(sw) >= 2 and seg_h[sw[1]] > seg_h[sw[0]])

    # ── Open-type diagnostics (Dalton open classification, programmatic) ─────
    # open_revisit: did price re-trade the session open after bar 1? 0 = pure
    # open drive (highest-conviction open). drive_eff: |net move| / path length
    # (1.0 = perfectly one-sided auction).
    open_px = o[0]
    open_revisit = float(any((l[i] <= open_px <= h[i]) for i in range(1, N_BARS)))
    path_len = float(np.sum(np.abs(np.diff(c)))) + abs(c[0] - o[0])
    drive_eff = abs(c[-1] - open_px) / path_len if path_len > 0 else 0.0

    # ── One-time-framing on 15M aggregates of the IB (4 windows of 3 bars) ───
    # OTF-up = every 15M low > prior 15M low (trend-day state machine)
    h15 = [h[i:i+3].max() for i in range(0, N_BARS, 3)]
    l15 = [l[i:i+3].min() for i in range(0, N_BARS, 3)]
    otf_up = float(all(l15[k] > l15[k-1] for k in range(1, len(l15))))
    otf_dn = float(all(h15[k] < h15[k-1] for k in range(1, len(h15))))

    # ── EMA20 location + Always-In proxy at bar 12 ───────────────────────────
    if ema is not None and len(ema) >= N_BARS and np.isfinite(ema[:N_BARS]).all():
        e = ema[:N_BARS]
        ema_above = float(np.mean(c > e))
        ema_dist  = (c[-1] - e[-1]) / or_rng
        ema_slope = (e[-1] - e[0]) / or_rng
        aid       = float(np.sign(c[-1] - e[-1]))
    else:
        ema_above, ema_dist, ema_slope, aid = 0.5, 0.0, 0.0, 0.0

    feats = {}
    for i in range(N_BARS):
        feats[f"path{i+1}"] = path[i]
        feats[f"ibs{i+1}"]  = ibs[i]
        feats[f"body{i+1}"] = body[i]
        feats[f"sign{i+1}"] = float(sign[i])
    feats.update(dict(net_drive=net_drive, flips=float(flips), overlap=overlap,
                      bo=float(bo), fbo=float(fbo), dt=float(dt_flag),
                      db=float(db_flag), hi_pos=hi_pos, lo_pos=lo_pos,
                      close_loc=close_loc,
                      bull_stop=bull_stop, bear_stop=bear_stop,
                      bull_limit=bull_limit, bear_limit=bear_limit,
                      ema_above=ema_above, ema_dist=ema_dist,
                      ema_slope=ema_slope, aid=aid,
                      pushes_up=float(pushes_up), pushes_dn=float(pushes_dn),
                      wedge_up=float(wedge_up), wedge_dn=float(wedge_dn),
                      twoleg_pb=float(twoleg_pb),
                      ib_high_first=ib_high_first,
                      open_revisit=open_revisit, drive_eff=drive_eff,
                      otf_up=otf_up, otf_dn=otf_dn,
                      or_rng_pts=or_rng))
    return feats


def _bucket(open_loc: float) -> str:
    if open_loc > 1.0:
        return "above_yH"
    if open_loc > 0.5:
        return "upper_half"
    if open_loc >= 0.0:
        return "lower_half"
    return "below_yL"


def context_features(bars: pd.DataFrame) -> pd.DataFrame:
    """CONTEXT block: per-day prior-day features (causal — all known at open)."""
    daily = bars.groupby(bars["DateTime"].dt.date).agg(
        O=("Open", "first"), H=("High", "max"),
        L=("Low", "min"),    C=("Close", "last"))
    daily["rng"] = daily["H"] - daily["L"]
    # ADR14 of the 14 days ENDING yesterday (shift after rolling → causal)
    daily["adr14"] = daily["rng"].rolling(14, min_periods=7).mean().shift(1)
    p = daily.shift(1)
    ctx = pd.DataFrame(index=daily.index)
    ctx["gap_norm"]   = (daily["O"] - p["C"]) / p["rng"]
    ctx["open_loc"]   = (daily["O"] - p["L"]) / p["rng"]
    ctx["prng_adr"]   = p["rng"] / daily["adr14"]
    ctx["pclose_loc"] = (p["C"] - p["L"]) / p["rng"]
    ctx["adr14"]      = daily["adr14"]      # for IB-width-vs-ATR (joined later)
    ctx["bucket"]     = ctx["open_loc"].map(
        lambda x: _bucket(x) if np.isfinite(x) else None)
    return ctx


CTX_COLS = ["gap_norm", "open_loc", "prng_adr", "pclose_loc"]


def _weights(cols: list[str]) -> np.ndarray:
    w = np.ones(len(cols))
    for j, cname in enumerate(cols):
        if cname.startswith("path"):
            w[j] = 2.0
        elif cname.startswith(("ibs", "body", "sign")):
            w[j] = 0.7
        elif cname in ("net_drive", "flips", "overlap", "bo", "fbo"):
            w[j] = 1.5
        elif cname in ("dt", "db", "hi_pos", "lo_pos", "close_loc"):
            w[j] = 1.0
        elif cname in ("bull_stop", "bear_stop", "bull_limit", "bear_limit",
                       "ema_above", "ema_dist", "ema_slope", "aid",
                       "pushes_up", "pushes_dn", "wedge_up", "wedge_dn",
                       "twoleg_pb", "rvol_ib", "ib_high_first",
                       "open_revisit", "drive_eff", "otf_up", "otf_dn"):
            w[j] = 1.5          # Brooks trend/range + swing + volume diagnostics
        elif cname == "ib_atr":
            w[j] = 2.0          # strongest documented character conditioner
        elif cname in CTX_COLS:
            w[j] = CTX_WEIGHT
    return w


def build_features() -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    """Shared entry point (also used by or12_render_pairs.py).
    Returns (df incl. bucket/or_rng_pts, weighted standardized matrix, feat cols)."""
    bars = pd.read_parquet(BARS_PQ).drop(columns=["Contract"], errors="ignore")
    bars["DateTime"] = pd.to_datetime(bars["DateTime"])
    bars = bars.sort_values("DateTime").reset_index(drop=True)
    # EMA20 on the continuous close series — bar i's EMA uses data through
    # bar i only (carries over from the prior session: causal at the open)
    bars["_ema20"] = bars["Close"].ewm(span=20, adjust=False).mean()
    rows = {}
    ib_vol = {}
    has_vol = "Volume" in bars.columns
    for d, g in bars.groupby(bars["DateTime"].dt.date):
        f = day_features(g, ema=g["_ema20"].to_numpy(float))
        if f is not None:
            rows[d] = f
            if has_vol:
                ib_vol[d] = float(g.sort_values("DateTime")
                                  .head(N_BARS)["Volume"].sum())
    df = pd.DataFrame.from_dict(rows, orient="index").sort_index()

    # relative IB volume: today's IB volume vs median of prior 20 days (causal)
    if ib_vol:
        ibv = pd.Series(ib_vol).sort_index()
        df["rvol_ib"] = (ibv / ibv.rolling(20, min_periods=10)
                         .median().shift(1)).clip(0.0, 4.0)
    else:
        df["rvol_ib"] = 1.0

    ctx = context_features(bars)
    df = df.join(ctx, how="inner")
    # IB width vs 14-day ADR — strongest documented day-character conditioner
    # on ES (narrow IB → 98.7% break / 74.8% median extension; wide IB →
    # 66.7% / 22.3%; TradingStats 2015-25)
    df["ib_atr"] = (df["or_rng_pts"] / df["adr14"]).clip(0.0, 3.0)
    df = df.drop(columns=["adr14"])
    df = df.dropna(subset=CTX_COLS + ["bucket", "rvol_ib", "ib_atr"])
    # clip context outliers so one -8x gap doesn't own the z-scale
    for c_ in CTX_COLS:
        df[c_] = df[c_].clip(-3.0, 4.0)

    feat_cols = [c for c in df.columns if c not in ("or_rng_pts", "bucket")]
    X = df[feat_cols].to_numpy(float)
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Xz = (X - mu) / sd * _weights(feat_cols)
    return df, Xz, feat_cols


import os as _os
DIST_METRIC = _os.environ.get("OR12_METRIC", "euclidean")
# A/B on v6 features (S60): euclidean 40.5% vs lorentzian 38.4% on
# close-vs-IB — log-compression flattens ~80 z-scored dims; euclidean wins.


def pairwise_dist(X: np.ndarray, metric: str | None = None,
                  chunk: int = 128) -> np.ndarray:
    """Full pairwise distance matrix, row-chunked to bound memory.
    lorentzian = sum_j log(1+|dx_j|) — compresses event-day (CPI/FOMC)
    outliers so one wild feature can't own the similarity (LuxAlgo/jdehorty
    convention). euclidean = squared distance (legacy)."""
    metric = metric or DIST_METRIC
    n = len(X)
    D = np.empty((n, n), dtype=np.float32)
    for s in range(0, n, chunk):
        e = min(s + chunk, n)
        diff = np.abs(X[s:e, None, :] - X[None, :, :])
        if metric == "lorentzian":
            D[s:e] = np.log1p(diff).sum(-1)
        else:
            D[s:e] = (diff ** 2).sum(-1)
    return D


def same_bucket_pairs(df: pd.DataFrame, Xz: np.ndarray, n_pairs: int
                      ) -> list[tuple]:
    """Tightest (dateA, dateB, dist) pairs, same open-location bucket only."""
    d2 = pairwise_dist(Xz)
    b = df["bucket"].to_numpy()
    d2[b[:, None] != b[None, :]] = np.inf
    iu = np.triu_indices(len(Xz), 1)
    flat = d2[iu]
    order = np.argsort(flat)[:n_pairs]
    dates = df.index.to_numpy()
    return [(dates[iu[0][k]], dates[iu[1][k]], float(flat[k]))
            for k in order if np.isfinite(flat[k])]


def main() -> None:
    df, Xz, feat_cols = build_features()
    print(f"{len(df)} days with a full 12-bar opening + prior-day context "
          f"({df.index.min()} - {df.index.max()})")
    print("\nOpen-location buckets (hard gate — matches never cross buckets):")
    for bk, n in df["bucket"].value_counts().items():
        print(f"  {bk:<11} {n:>4} days")

    # KMeans on shape+context (seeded, plain numpy)
    rng = np.random.default_rng(42)
    idx0 = rng.choice(len(Xz), size=K, replace=False)
    cent = Xz[idx0].copy()
    for _ in range(100):
        d2c = ((Xz[:, None, :] - cent[None, :, :]) ** 2).sum(-1)
        lab = d2c.argmin(1)
        new = np.array([Xz[lab == k].mean(0) if (lab == k).any() else cent[k]
                        for k in range(K)])
        if np.allclose(new, cent):
            break
        cent = new
    df["cluster"] = lab

    # nearest neighbours per day — same bucket only
    d2 = pairwise_dist(Xz)
    b = df["bucket"].to_numpy()
    d2[b[:, None] != b[None, :]] = np.inf
    np.fill_diagonal(d2, np.inf)
    nn_idx = np.argsort(d2, axis=1)[:, :N_NEIGH]
    dates = df.index.to_numpy()
    for j in range(N_NEIGH):
        df[f"nn{j+1}"] = dates[nn_idx[:, j]]

    df.to_csv(OUT_CSV, index_label="Date")
    print(f"\nwritten: {OUT_CSV}\n")

    desc_bits = []
    for k in range(K):
        sub = df[df["cluster"] == k]
        if sub.empty:
            continue
        nd, fl, ovl = sub["net_drive"].mean(), sub["flips"].mean(), sub["overlap"].mean()
        gp, ol = sub["gap_norm"].mean(), sub["open_loc"].mean()
        cl = sub["close_loc"].mean()
        drive = ("strong bull drive" if nd > 0.5 else
                 "bull drift" if nd > 0.15 else
                 "strong bear drive" if nd < -0.5 else
                 "bear drift" if nd < -0.15 else "two-sided/flat")
        opng = ("opens above yH" if ol > 1.0 else
                "opens upper half" if ol > 0.5 else
                "opens lower half" if ol >= 0.0 else "opens below yL")
        desc = (f"{drive}, {opng} (gap {gp:+.0%} of yRange), "
                f"flips~{fl:.1f}, close@{cl:.0%} of OR")
        desc_bits.append((k, len(sub), desc, sub.index.tolist()))

    for k, n, desc, dts in sorted(desc_bits, key=lambda t: -t[1]):
        print(f"-- Cluster {k}  ({n} days)  {desc}")
        print("   " + ", ".join(str(d) for d in dts) + "\n")


if __name__ == "__main__":
    main()
