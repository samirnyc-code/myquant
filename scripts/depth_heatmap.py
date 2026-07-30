"""depth_heatmap.py — Bookmap-style liquidity heatmap from the NT8 L2 event stream.

The AddOn (nt8/addons/MarketDepthRecorderAddOn.cs) records the ES order book as an
EVENT STREAM, not snapshots:  Time,Ev,Side,Pos,Price,Size
    Ev = A add / U update / R remove  (book, keyed by POSITION — R rows carry Pos
         only, Price/Size are 0, so the book MUST be reconstructed by level index)
       = T tape (Side = aggressor: A=buy lifting the offer, B=sell hitting the bid)
       = C connection marker
    Side = B bid / A ask     Pos = DOM row index (0 = best)     Size = resting size

This script replays that stream to reconstruct the resting book at every instant,
samples it on a fixed time grid, and renders a heatmap: time on X, price on Y,
resting size as a luminance ramp (dark = thin, bright = thick — a sequential hue,
never a rainbow). The traded price rides on top as a thin line and the tape prints
as buy/sell dots. This is the standard "see where liquidity stacks, pulls, and
absorbs" read that L2 exists for.

Reconstruction is O(events) with a per-side list indexed by Position:
    A -> insert at Pos     U -> replace at Pos     R -> delete at Pos
The matrix is cached to data/depth/heatmap_cache/ so re-renders are instant.

    python scripts/depth_heatmap.py build 2026-07-29                  # RTH, 3s buckets
    python scripts/depth_heatmap.py build 2026-07-29 --eth --bucket 10
    python scripts/depth_heatmap.py build 2026-07-29 --start 08:30 --end 15:15
    python scripts/depth_heatmap.py page                              # (re)build index.html
Times are CT (America/Chicago). Outputs: docs/depth_heatmap/ES_<date>.png + index.html
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

CT = ZoneInfo("America/Chicago")
ROOT = Path(__file__).resolve().parents[1]
DEPTH = ROOT / "data" / "depth"
ADDON = DEPTH / "addon_test"
OUT = ROOT / "docs" / "depth_heatmap"
CACHE = DEPTH / "heatmap_cache"
TICK = 0.25                       # ES tick size
RTH = ("08:30", "15:15")          # CT cash session (default render window)

# Bookmap-style heat ramp (low -> high resting size): near-black -> deep blue -> blue
# -> cyan -> green -> yellow -> orange -> red -> white-hot. This is the palette the user
# reads liquidity in, so it is the DEFAULT. (Note: unlike a single-hue sequential ramp it
# is not strictly luminance-monotonic, so it trades some CVD-safety for familiarity.)
BOOKMAP = [
    (0.00, "#05010a"), (0.12, "#0b1a6b"), (0.28, "#1e4fd6"), (0.44, "#12b6c8"),
    (0.58, "#2fd15a"), (0.72, "#e8e000"), (0.86, "#ff7a00"), (0.95, "#ff1e00"),
    (1.00, "#ffffff"),
]


def _bookmap_cmap():
    from matplotlib.colors import LinearSegmentedColormap
    cm = LinearSegmentedColormap.from_list("bookmap", [(p, c) for p, c in BOOKMAP])
    cm.set_bad(alpha=0.0)   # nan (no liquidity) -> transparent, black bg shows through
    return cm


def _cache_path(date, win0, win1, bucket_s, clip_ticks) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = f"{date}_{win0.value}_{win1.value}_{bucket_s}_{clip_ticks}"
    return CACHE / f"{key}.npz"


# --------------------------------------------------------------------- load
def _source(date: str) -> Path:
    """Prefer parquet, fall back to CSV; AddOn dir first (sole recorder since 07-24),
    then the legacy strategy dir. Returns the newest existing file for the date."""
    name = f"ES_09-26_depth_{date}"
    for d in (ADDON, DEPTH):
        pq, csv = d / f"{name}.parquet", d / f"{name}.csv"
        if pq.exists():
            return pq
        if csv.exists():
            return csv
    raise FileNotFoundError(f"no depth file for {date} in {ADDON} or {DEPTH}")


def _read(path: Path) -> pd.DataFrame:
    cols = ["Time", "Ev", "Side", "Pos", "Price", "Size"]
    if path.suffix == ".parquet":
        df = pd.read_parquet(path, columns=cols)
    else:
        df = pd.read_csv(path, usecols=cols, on_bad_lines="skip")
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df = df.dropna(subset=["Time"])
    # stamps are wall-clock CT (no tz in the file). Keep them NAIVE and treat window
    # bounds as naive CT too — bucketing only needs a consistent monotonic ns clock,
    # and staying naive avoids DST local/ambiguous headaches.
    if getattr(df["Time"].dt, "tz", None) is not None:
        df["Time"] = df["Time"].dt.tz_localize(None)
    return df


# --------------------------------------------------------------------- reconstruct
def reconstruct(df: pd.DataFrame, win0: pd.Timestamp, win1: pd.Timestamp,
                bucket_s: int, clip_ticks: int = 56):
    """Replay the whole stream (book must be built from file start), sampling the
    resting book onto a bucket grid but ONLY inside [win0, win1].

    Model — the book is NT's price-sorted DOM ladder, keyed by POSITION (rank):
        A -> insert at Pos    U -> replace at Pos    R -> delete at Pos
        C -> connection marker = a RESYNC boundary; clear the book (on reconnect NT
             re-sends the whole ladder via Adds — without clearing it stacks a second
             copy, the exact 2x-depth leak we measured).
        out-of-range ops are DROPPED (a desync symptom), never appended.

    Perfect replay of 5y-style L2 from an event log is not attainable (repricing
    Updates + any dropped event let a few stale FAR levels drift over a session), so
    for the VISUALIZATION we (a) anchor the price line to the TAPE (real trades are
    unambiguous) and (b) drop levels more than `clip_ticks` from that anchor at
    snapshot time — the near-touch book (where updates are dense) stays faithful and
    stale far junk never renders. Returns matrix[price,bucket] of resting size.
    """
    ns = df["Time"].to_numpy(dtype="datetime64[ns]").view("int64")   # naive CT -> ns
    ev = df["Ev"].astype(str).to_numpy()
    side = df["Side"].astype(str).to_numpy()
    pos = df["Pos"].to_numpy(dtype=np.int32, na_value=0)
    price = df["Price"].to_numpy(dtype=np.float64, na_value=0.0)
    size = df["Size"].to_numpy(dtype=np.int64, na_value=0)

    w0, w1 = win0.value, win1.value
    step = bucket_s * 1_000_000_000
    b0 = (w0 // step) * step

    bid: list[list[float]] = []     # index = Pos -> [price_tick, size]
    ask: list[list[float]] = []
    cols: dict[int, dict[int, int]] = {}   # bucket -> {price_tick: size}
    anchor: dict[int, float] = {}          # bucket -> last-trade price tick (the line)
    last_bucket = -1
    cur_last = None                        # last traded price (ticks), carried forward
    n = len(ns)

    def snapshot(bkt: int):
        d: dict[int, int] = {}
        for pt, sz in bid:
            if sz > 0 and (cur_last is None or abs(pt - cur_last) <= clip_ticks):
                d[pt] = d.get(pt, 0) + int(sz)
        for pt, sz in ask:
            if sz > 0 and (cur_last is None or abs(pt - cur_last) <= clip_ticks):
                d[pt] = d.get(pt, 0) + int(sz)
        cols[bkt] = d
        if cur_last is not None:
            anchor[bkt] = float(cur_last)
        else:
            bb = max((pt for pt, sz in bid if sz > 0), default=None)
            aa = min((pt for pt, sz in ask if sz > 0), default=None)
            if bb is not None and aa is not None:
                anchor[bkt] = (bb + aa) / 2.0

    tape_ns: list[int] = []
    tape_pt: list[int] = []
    tape_sz: list[int] = []
    tape_buy: list[bool] = []

    for i in range(n):
        e = ev[i]
        if e == "T":
            pt = int(round(price[i] / TICK))
            cur_last = pt
            t = ns[i]
            if w0 <= t <= w1:
                tape_ns.append(t)
                tape_pt.append(pt)
                tape_sz.append(int(size[i]))
                tape_buy.append(side[i] == "A")   # A = aggressor bought
            continue
        if e == "C":
            bid.clear(); ask.clear()              # resync boundary
            continue
        # ---- book event: apply by position (strict; drop out-of-range) ----
        lst = bid if side[i] == "B" else ask
        p = int(pos[i])
        if e == "A":
            if 0 <= p <= len(lst):
                lst.insert(p, [int(round(price[i] / TICK)), int(size[i])])
        elif e == "U":
            if 0 <= p < len(lst):
                lst[p] = [int(round(price[i] / TICK)), int(size[i])]
        elif e == "R":
            if 0 <= p < len(lst):
                del lst[p]
        # ---- sample on bucket boundary, inside the window only ----
        t = ns[i]
        if w0 <= t <= w1:
            bkt = (t - b0) // step
            if bkt != last_bucket:
                snapshot(bkt)
                last_bucket = bkt

    if not cols:
        raise RuntimeError("no book samples in window — check the date/window")

    bkts = np.array(sorted(cols), dtype=np.int64)
    a_arr = np.array([anchor[b] for b in bkts if b in anchor], dtype=np.float64)
    if a_arr.size:
        lo = int(np.floor(a_arr.min())) - clip_ticks
        hi = int(np.ceil(a_arr.max())) + clip_ticks
    else:
        all_pt = [pt for d in cols.values() for pt in d]
        lo, hi = min(all_pt), max(all_pt)
    prices = np.arange(lo, hi + 1, dtype=np.int64)
    pidx = {pt: k for k, pt in enumerate(prices)}

    mat = np.zeros((len(prices), len(bkts)), dtype=np.float32)
    for j, b in enumerate(bkts):
        for pt, sz in cols[b].items():
            k = pidx.get(pt)
            if k is not None:
                mat[k, j] = sz
    mid_line = np.array([anchor.get(b, np.nan) for b in bkts], dtype=np.float64)

    return {
        "bucket_ns": b0 + bkts * step, "prices": prices, "mat": mat,
        "mid": mid_line, "step_ns": step,
        "tape_ns": np.array(tape_ns, dtype=np.int64),
        "tape_pt": np.array(tape_pt, dtype=np.int64),
        "tape_sz": np.array(tape_sz, dtype=np.int64),
        "tape_buy": np.array(tape_buy, dtype=bool),
    }


# --------------------------------------------------------------------- render
def render(date: str, data: dict, window_label: str) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm

    OUT.mkdir(parents=True, exist_ok=True)
    prices = data["prices"] * TICK
    t = data["bucket_ns"]
    # x in matplotlib date units; ns are naive CT wall-clock already
    tx = mdates.date2num(pd.to_datetime(t).to_pydatetime())
    mat = data["mat"]
    vmax = np.percentile(mat[mat > 0], 99) if (mat > 0).any() else 1.0
    vmin = max(1.0, vmax / 400.0)

    cmap = _bookmap_cmap()
    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(18, 9), dpi=110)
    extent = [tx[0], tx[-1], prices[0], prices[-1]]
    ax.imshow(np.where(mat > 0, mat, np.nan), aspect="auto", origin="lower",
              extent=extent, cmap=cmap,
              norm=LogNorm(vmin=vmin, vmax=vmax), interpolation="nearest")

    # traded price line (tape anchor)
    mid_px = data["mid"] * TICK
    ax.plot(tx, mid_px, color="#7dd3fc", lw=0.8, alpha=0.9, label="last trade")

    # tape prints (subsample if dense) — buy/sell distinct in hue AND luminance
    tn, tp, ts, tb = (data["tape_ns"], data["tape_pt"], data["tape_sz"],
                      data["tape_buy"])
    if tn.size:
        txp = mdates.date2num(pd.to_datetime(tn).to_pydatetime())
        s = np.clip(ts.astype(float), 1, None)
        ms = 3 + 22 * (s / max(s.max(), 1)) ** 0.5
        for buy, col, lab in ((True, "#34d399", "buy"), (False, "#f87171", "sell")):
            m = tb == buy
            if m.any():
                ax.scatter(txp[m], tp[m] * TICK, s=ms[m], c=col, alpha=0.35,
                           edgecolors="none", label=f"{lab} tape")

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.MinuteLocator(byminute=range(0, 60, 30)))
    ax.set_ylabel("Price"); ax.set_xlabel("Time (CT)")
    ax.set_title(f"ES L2 liquidity heatmap — {date}  ({window_label} CT)  "
                 f"· resting size, log scale · last trade + tape",
                 fontsize=12, color="#e6edf3")
    ax.grid(True, color="#30363d", lw=0.4, alpha=0.4)
    leg = ax.legend(loc="upper left", fontsize=8, framealpha=0.3)
    for txt in leg.get_texts():
        txt.set_color("#e6edf3")

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=LogNorm(vmin=vmin, vmax=vmax))
    cb = fig.colorbar(sm, ax=ax, pad=0.01, fraction=0.03)
    cb.set_label("resting contracts", color="#8b949e")

    fig.tight_layout()
    png = OUT / f"ES_{date}.png"
    fig.savefig(png, facecolor="#0d1117", bbox_inches="tight")
    plt.close(fig)
    return png


# --------------------------------------------------------------------- interactive
def _candles(data: dict, rule: str = "1min") -> pd.DataFrame:
    """OHLC candles resampled from the file's own tape (self-contained)."""
    if not data["tape_ns"].size:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    s = pd.Series(data["tape_pt"] * TICK,
                  index=pd.to_datetime(data["tape_ns"])).sort_index()
    return s.resample(rule).ohlc().dropna()


def interactive(date: str, data: dict, window_label: str,
                max_cols: int = 2400, candle_rule: str = "1min") -> Path:
    """Bookmap-style INTERACTIVE viewer: a resting-liquidity heatmap layer with the
    price candlesticks drawn over it, native Plotly zoom/pan/box-zoom (scroll-zoom on).
    Self-contained HTML (plotly.js inlined). Candles come from the file's own tape."""
    import plotly.graph_objects as go

    OUT.mkdir(parents=True, exist_ok=True)
    mat = data["mat"].copy()                       # [price, bucket] resting size
    prices = data["prices"] * TICK
    tns = data["bucket_ns"]

    # downsample time columns (max-pool) so the payload stays light and snappy
    ncol = mat.shape[1]
    if ncol > max_cols:
        f = int(np.ceil(ncol / max_cols))
        pad = (-ncol) % f
        if pad:
            mat = np.pad(mat, ((0, 0), (0, pad)), constant_values=0)
            tns = np.concatenate([tns, tns[-1] + np.arange(1, pad + 1) * data["step_ns"]])
        mat = mat.reshape(mat.shape[0], -1, f).max(axis=2)
        tns = tns[::f][: mat.shape[1]]

    # trim price rows that never hold liquidity in the window
    live = mat.sum(axis=1) > 0
    if live.any():
        mat, prices = mat[live], prices[live]

    z = np.where(mat > 0, np.log10(np.where(mat > 0, mat, 1)), np.nan)  # empties transparent
    pos = mat[mat > 0]
    zmax = float(np.log10(np.percentile(pos, 99.5))) if pos.size else 1.0
    zmin = max(0.0, zmax - np.log10(400))
    # colorbar ticks labelled in real contracts, not log
    ticks = [t for t in (1, 5, 20, 100, 500, 2000, 10000)
             if zmin <= np.log10(t) <= zmax + 0.3]

    x = pd.to_datetime(tns)
    fig = go.Figure()
    fig.add_trace(go.Heatmap(
        z=z, x=x, y=prices, colorscale=[[p, c] for p, c in BOOKMAP],
        zmin=zmin, zmax=zmax, zsmooth=False, name="resting size",
        hovertemplate="%{x|%H:%M:%S} · %{y:.2f} · 10^%{z:.1f} lots<extra></extra>",
        colorbar=dict(title="resting<br>lots", tickvals=[np.log10(t) for t in ticks],
                      ticktext=[f"{t:,}" for t in ticks], outlinewidth=0, len=0.9)))

    c = _candles(data, candle_rule)
    if not c.empty:
        fig.add_trace(go.Candlestick(
            x=c.index, open=c["open"], high=c["high"], low=c["low"], close=c["close"],
            increasing=dict(line=dict(color="#26e0a6", width=1)),
            decreasing=dict(line=dict(color="#ff5c7a", width=1)),
            whiskerwidth=0.4, name="ES", showlegend=False))

    fig.update_layout(
        template="plotly_dark", height=820, dragmode="zoom", hovermode="closest",
        margin=dict(l=58, r=10, t=44, b=36),
        paper_bgcolor="#05010a", plot_bgcolor="#05010a",
        title=dict(text=f"ES L2 liquidity heatmap — {date} ({window_label} CT) · "
                        f"resting size + price · scroll to zoom, drag to box-zoom, "
                        f"double-click to reset", font=dict(size=13)),
        xaxis=dict(rangeslider=dict(visible=False), title="Time (CT)",
                   gridcolor="#161b22"),
        yaxis=dict(title="Price", gridcolor="#161b22"))
    fig.update_xaxes(showspikes=True, spikemode="across", spikethickness=1,
                     spikecolor="#8b949e")

    html = OUT / f"ES_{date}.html"
    fig.write_html(html, include_plotlyjs=True, full_html=True,
                   config={"scrollZoom": True, "displaylogo": False,
                           "modeBarButtonsToRemove": ["select2d", "lasso2d"]})
    return html


# --------------------------------------------------------------------- build
def build(date: str, start: str, end: str, bucket_s: int, eth: bool,
          clip_ticks: int = 56, force: bool = False) -> dict:
    d0 = dt.date.fromisoformat(date)
    if eth:
        # ETH session belonging to trade date D runs 17:00 CT (D-1) -> 16:00 CT (D)
        win0 = pd.Timestamp(f"{d0 - dt.timedelta(days=1)} 17:00")
        win1 = pd.Timestamp(f"{date} 16:00")
        wl = "ETH 17:00-16:00"
    else:
        win0 = pd.Timestamp(f"{date} {start}")
        win1 = pd.Timestamp(f"{date} {end}")
        wl = f"{start}-{end}"

    cache = _cache_path(date, win0, win1, bucket_s, clip_ticks)
    if cache.exists() and not force:
        print(f"  cache hit {cache.name}", flush=True)
        z = np.load(cache)
        data = {k: z[k] for k in z.files}
        data["step_ns"] = int(data["step_ns"])
    else:
        src = _source(date)
        print(f"  reading {src.relative_to(ROOT)} …", flush=True)
        df = _read(src)
        print(f"  {len(df):,} events · reconstructing book · window {wl} · "
              f"{bucket_s}s buckets", flush=True)
        data = reconstruct(df, win0, win1, bucket_s, clip_ticks)
        np.savez_compressed(cache, **{k: np.asarray(v) for k, v in data.items()})
        print(f"  cached {cache.name}", flush=True)

    png = render(date, data, wl)
    htm = interactive(date, data, wl)
    print(f"  -> {png.relative_to(ROOT)}  ·  {htm.relative_to(ROOT)}  "
          f"({data['mat'].shape[0]} price rows x {data['mat'].shape[1]} buckets)",
          flush=True)
    return {"png": png, "html": htm}


# --------------------------------------------------------------------- index page
def page() -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    pngs = sorted(OUT.glob("ES_*.png"), reverse=True)
    cards = []
    for p in pngs:
        date = p.stem.replace("ES_", "")
        b64 = base64.b64encode(p.read_bytes()).decode()
        has_html = (OUT / f"ES_{date}.html").exists()
        link = (f'<a class="zoom" href="ES_{date}.html" target="_blank">↗ open '
                f'interactive (zoom / candles) ›</a>') if has_html else ""
        thumb = (f'<a href="ES_{date}.html" target="_blank">'
                 f'<img src="data:image/png;base64,{b64}" alt="L2 heatmap {date}"></a>'
                 ) if has_html else \
                f'<img src="data:image/png;base64,{b64}" alt="L2 heatmap {date}">'
        cards.append(f'<section id="d{date}"><h2>{date} {link}</h2>{thumb}</section>')
    nav = " · ".join(f'<a href="#d{p.stem.replace("ES_","")}">'
                     f'{p.stem.replace("ES_","")}</a>' for p in pngs)
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>ES L2 Liquidity Heatmap</title>
<style>
:root{{--bg:#0d1117;--fg:#e6edf3;--muted:#8b949e;--chip:#30363d}}
body{{margin:0;background:var(--bg);color:var(--fg);
  font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}}
header{{padding:14px 20px;border-bottom:1px solid var(--chip);position:sticky;top:0;
  background:var(--bg);z-index:5}}
h1{{font-size:16px;margin:0 0 6px}} a{{color:#58a6ff;text-decoration:none}}
.nav{{color:var(--muted);font-size:12.5px}}
section{{padding:16px 20px;border-bottom:1px solid var(--chip)}}
h2{{font-size:14px;margin:0 0 8px;color:var(--muted)}}
a.zoom{{margin-left:12px;color:#34d399;font-weight:600}}
img{{width:100%;height:auto;border:1px solid var(--chip);border-radius:8px;
  display:block;cursor:zoom-in}}
p.legend{{color:var(--muted);font-size:12px;max-width:1100px}}
</style></head><body>
<header><h1>ES L2 Liquidity Heatmap</h1>
<div class="nav">{nav or "no days rendered yet"}</div></header>
<section><p class="legend">Reconstructed from the NT8 AddOn L2 event stream. Bright =
thick resting liquidity (log scale); dark = thin. The cyan line is the last trade;
green/red dots are buy/sell tape prints (size ∝ √contracts). Walls that stay bright then
vanish = pulled liquidity; bright bands price repeatedly fails to cross = absorption /
support-resistance. Click a day for the interactive (zoom / candlesticks) version.
Build a day: <code>python scripts/depth_heatmap.py build YYYY-MM-DD</code>.</p></section>
{''.join(cards)}
</body></html>"""
    idx = OUT / "index.html"
    idx.write_text(html, encoding="utf-8")
    print(f"  -> {idx.relative_to(ROOT)}  ({len(pngs)} day(s))")
    return idx


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="reconstruct + render one day")
    b.add_argument("date", help="YYYY-MM-DD (trade date, CT)")
    b.add_argument("--start", default=RTH[0]); b.add_argument("--end", default=RTH[1])
    b.add_argument("--bucket", type=int, default=3, help="seconds per column")
    b.add_argument("--clip", type=int, default=56, help="ticks from last-trade to keep")
    b.add_argument("--eth", action="store_true", help="full ETH 17:00-16:00 instead of RTH")
    b.add_argument("--force", action="store_true", help="ignore the reconstruct cache")
    b.add_argument("--no-page", action="store_true")
    sub.add_parser("page", help="(re)build docs/depth_heatmap/index.html")
    a = ap.parse_args()

    if a.cmd == "build":
        build(a.date, a.start, a.end, a.bucket, a.eth, a.clip, a.force)
        if not a.no_page:
            page()
    elif a.cmd == "page":
        page()
    return 0


if __name__ == "__main__":
    sys.exit(main())
