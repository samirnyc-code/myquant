"""thetadata_fill_report.py — turn the ThetaData pull into the presentable August
fill-realism report: where our paper fills sat in the REAL OPRA NBBO, whether there
was size at the touch, whether a single-leg print actually traded at our price, and
how fresh the quote was — overall, per strategy, per side.

INPUTS (from scripts/thetadata_fetch.py):
  data/thetadata/at_time_results_<date>.csv      (required) our fill vs as-of NBBO / event
  data/thetadata/trade_quote_prints_<date>.csv   (optional) prints + condition / event

Fill position (same convention as fill_vs_nbbo_audit.py):
  pos = fraction toward the FAVORABLE touch.  BUY: (ask-px)/(ask-bid).  SELL: (px-bid)/(ask-bid).
  pos 0 = crossed the spread (marketable / conservative / realistic),
  pos 0.5 = mid,  pos>0.5 = better than mid (optimistic),  pos>1 = through the book (impossible).
A real marketable fill clusters near 0.  A mid-phantom engine would sit at 0.5.

Print confirmation: only single-leg trade conditions (0 regular, 18 electronic single-leg)
confirm a single-leg fill at that price; complex-order codes 130/131/134 are package prices =
context only (see the fetcher).  A fill is "print-confirmed" if a single-leg print traded at
or better than our price on our side, inside the window.

Run:
  .venv/Scripts/python.exe scripts/thetadata_fill_report.py            # newest real results
  .venv/Scripts/python.exe scripts/thetadata_fill_report.py --mock     # SYNTHETIC preview (no terminal)
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import math
import webbrowser
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TD = ROOT / "data" / "thetadata"
SIM = ROOT / "data" / "options_sim"
EVENTS_GLOB = "thetadata_events_*.csv"
TICK = 0.05


# ----------------------------------------------------------------- metrics
def _f(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def _r(x):
    """Normalize option right: 'CALL'/'C'->'C', 'PUT'/'P'->'P' (ThetaData prints use CALL/PUT,
    our events use C/P)."""
    s = str(x).strip().upper()
    return s[:1] if s else s


def compute(at_df: pd.DataFrame, prints: pd.DataFrame | None) -> pd.DataFrame:
    # index single-leg prints by (trade_id, event, strike, right) for confirmation lookup
    pidx: dict = {}
    if prints is not None and len(prints):
        sl = prints[prints.get("is_single_leg").astype(str).isin(["True", "true", "1"])] \
            if "is_single_leg" in prints.columns else prints.iloc[0:0]
        for _, p in sl.iterrows():
            key = (p.get("trade_id"), p.get("event"), _f(p.get("strike")), _r(p.get("right")))
            pidx.setdefault(key, []).append(_f(p.get("price")))

    rows = []
    for _, r in at_df.iterrows():
        side = str(r.get("side_action", "")).upper()
        bid, ask, px = _f(r.get("bid")), _f(r.get("ask")), _f(r.get("our_fill_price"))
        status = str(r.get("quote_status", ""))
        stale = str(r.get("quote_stale", "")).lower() in ("true", "1")
        pos = size_touch = None
        spread = (ask - bid) if (bid is not None and ask is not None) else None
        if status == "ok" and spread and spread > 0 and px is not None:
            if side == "BUY":
                pos, size_touch = (ask - px) / spread, _f(r.get("ask_size"))
            elif side == "SELL":
                pos, size_touch = (px - bid) / spread, _f(r.get("bid_size"))
        # single-leg print confirmation
        confirmed = None
        if px is not None:
            prices = pidx.get((r.get("trade_id"), r.get("event"), _f(r.get("strike")), _r(r.get("right"))), [])
            prices = [p for p in prices if p is not None]
            if prices:
                confirmed = any((p <= px + TICK) if side == "BUY" else (p >= px - TICK) for p in prices)
        rows.append({
            "trade_id": r.get("trade_id"), "strategy": r.get("strategy"), "event": r.get("event"),
            "side": side, "strike": _f(r.get("strike")), "right": r.get("right"),
            "our_price": px, "bid": bid, "ask": ask, "spread": spread,
            "pos": pos, "size_at_touch": size_touch, "size_ok": (size_touch is not None and size_touch >= 1),
            "quote_lag_s": _f(r.get("quote_lag_s")), "stale": stale,
            "status": status, "print_confirmed": confirmed,
        })
    return pd.DataFrame(rows)


def agg(df: pd.DataFrame) -> dict:
    scored = df[df.pos.notna() & ~df.stale]
    def pct(mask, base):
        return round(100 * mask.sum() / base, 1) if base else None
    n_scored = len(scored)
    return {
        "n_events": len(df),
        "n_ok": int((df.status == "ok").sum()),
        "n_scored": n_scored,
        "median_pos": round(scored.pos.median(), 3) if n_scored else None,
        "mean_pos": round(scored.pos.mean(), 3) if n_scored else None,
        "pct_conservative": pct(scored.pos <= 0.5, n_scored),        # crossed / at-or-worse than mid
        "pct_through": pct(scored.pos > 1.0, n_scored),              # impossible -> data/timing issue
        "pct_size_ok": pct(scored.size_ok, n_scored),
        "n_stale": int(df.stale.sum()),
        "n_confirmed": int((df.print_confirmed == True).sum()),      # noqa: E712
        "n_confirm_tested": int(df.print_confirmed.notna().sum()),
        "n_no_price": int(df.our_price.isna().sum()),
    }


# ------------------------------------------------------------------- render
def _hist(scored: pd.Series) -> list[tuple[str, int, str]]:
    """Buckets for the fill-position histogram: edges flagged, 10 bins in [0,1]."""
    buckets = [("<0", "bad"), *[(f"{i/10:.1f}", "pos") for i in range(10)], (">1", "bad")]
    counts = {b: 0 for b, _ in buckets}
    for v in scored:
        if v < 0:
            counts["<0"] += 1
        elif v > 1:
            counts[">1"] += 1
        else:
            counts[f"{min(int(v * 10), 9)/10:.1f}"] += 1
    return [(b, counts[b], tone) for b, tone in buckets]


def render(df: pd.DataFrame, a: dict, synthetic: bool, src: str) -> str:
    scored = df[df.pos.notna() & ~df.stale]
    bars = _hist(scored.pos) if len(scored) else []
    bmax = max((c for _, c, _ in bars), default=1) or 1
    barw = 100 / max(len(bars), 1)
    bar_svg = ""
    for i, (label, c, tone) in enumerate(bars):
        h = 100 * c / bmax
        x = i * barw
        col = "var(--bad)" if tone == "bad" else "var(--pos)"
        bar_svg += (f'<g><rect x="{x + 0.6:.2f}%" y="{100 - h:.2f}%" width="{barw - 1.2:.2f}%" '
                    f'height="{h:.2f}%" rx="3" fill="{col}"><title>pos {label}: {c}</title></rect></g>')
        bar_svg += (f'<text x="{x + barw/2:.2f}%" y="99%" text-anchor="middle" '
                    f'font-size="9" fill="var(--muted)">{label}</text>')

    # per-strategy table
    trows = ""
    for strat, g in df.groupby("strategy", dropna=False):
        gs = g[g.pos.notna() & ~g.stale]
        conf = g[g.print_confirmed.notna()]
        trows += (
            f"<tr><td>{html.escape(str(strat))}</td>"
            f"<td>{len(g)}</td><td>{len(gs)}</td>"
            f"<td>{('%.3f' % gs.pos.median()) if len(gs) else '—'}</td>"
            f"<td>{('%.0f%%' % (100*(gs.pos<=0.5).mean())) if len(gs) else '—'}</td>"
            f"<td>{('%.0f%%' % (100*gs.size_ok.mean())) if len(gs) else '—'}</td>"
            f"<td>{('%.0f%%' % (100*(conf.print_confirmed==True).mean())) if len(conf) else '—'}</td></tr>")

    def tile(label, val, sub, tone="ink"):
        v = "—" if val is None else val
        return (f'<div class="tile"><div class="tl">{label}</div>'
                f'<div class="tv {tone}">{v}</div><div class="ts">{sub}</div></div>')

    med = a["median_pos"]
    med_tone = "good" if (med is not None and med <= 0.5) else "warn"
    banner = (f'<div class="synth">⚠ SYNTHETIC PREVIEW — mock data, NOT real fills. '
              f'Structure/layout only. Real August numbers replace this after the ThetaData pull.</div>'
              if synthetic else "")
    title = ("SYNTHETIC PREVIEW · " if synthetic else "") + "SPX Fill Realism — August 2026"
    tiles = "".join([
        tile("Fill events", a["n_events"], f'{a["n_ok"]} with a quote · {a["n_no_price"]} no logged price'),
        tile("Scored fills", a["n_scored"], "quote ok, fresh, price known"),
        tile("Median fill position", med, "0=crossed · 0.5=mid · 1=touch", med_tone),
        tile("Crossed the spread", f'{a["pct_conservative"]}%' if a["pct_conservative"] is not None else None,
             "pos ≤ 0.5 (conservative)", "good"),
        tile("Size ≥ 1 at touch", f'{a["pct_size_ok"]}%' if a["pct_size_ok"] is not None else None,
             "real depth behind our lot"),
        tile("Single-leg print-confirmed",
             f'{a["n_confirmed"]}/{a["n_confirm_tested"]}' if a["n_confirm_tested"] else None,
             "cond 0/18 traded at our price"),
        tile("Through the book", f'{a["pct_through"]}%' if a["pct_through"] is not None else None,
             "pos > 1 (timing/data noise)", "bad" if (a["pct_through"] or 0) > 0 else "ink"),
        tile("Stale quotes", a["n_stale"], "quote >2s before fill (excluded)", "warn"),
    ])
    gen = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🎯</text></svg>">
<title>{html.escape(title)}</title>
<style>
:root{{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
  --grid:#e1e0d9;--border:rgba(11,11,11,.10);--pos:#2a78d6;--card:#fff;
  --good:#0ca30c;--warn:#fab219;--bad:#e34948;--chip:#f0efea}}
@media(prefers-color-scheme:dark){{:root{{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;
  --muted:#898781;--grid:#2c2c2a;--border:rgba(255,255,255,.10);--pos:#3987e5;--card:#1f1f1e;
  --good:#0ca30c;--warn:#fab219;--bad:#e66767;--chip:#26261f}}}}
:root[data-theme=dark]{{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;
  --grid:#2c2c2a;--border:rgba(255,255,255,.10);--pos:#3987e5;--card:#1f1f1e;--chip:#26261f}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--plane);color:var(--ink);font-family:system-ui,-apple-system,"Segoe UI",sans-serif;font-size:14px}}
header{{padding:14px 22px;border-bottom:1px solid var(--border);background:var(--surface);position:sticky;top:0;z-index:5}}
h1{{font-size:17px;margin:0;font-weight:650}}
.sub{{font-size:12px;color:var(--muted);margin-top:3px}}
.wrap{{max-width:1180px;margin:0 auto;padding:18px 22px 80px}}
.synth{{background:rgba(227,73,72,.12);border:1px solid var(--bad);color:var(--bad);
  border-radius:9px;padding:10px 14px;margin:16px 0;font-weight:600;font-size:13px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px;margin:16px 0}}
.tile{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:13px 15px}}
.tl{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}}
.tv{{font-size:26px;font-weight:680;font-variant-numeric:tabular-nums;margin:3px 0}}
.tv.good{{color:var(--good)}}.tv.warn{{color:var(--warn)}}.tv.bad{{color:var(--bad)}}
.ts{{font-size:11.5px;color:var(--ink2)}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:15px 17px;margin:14px 0}}
.card h2{{font-size:13px;margin:0 0 4px;font-weight:640}}
.card .note{{font-size:12px;color:var(--muted);margin-bottom:12px}}
svg.chart{{width:100%;height:230px;display:block}}
table{{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}}
th,td{{text-align:right;padding:6px 10px;border-bottom:1px solid var(--border)}}
th:first-child,td:first-child{{text-align:left;font-family:ui-monospace,monospace}}
th{{font-size:11px;color:var(--muted);text-transform:uppercase;font-weight:600}}
</style></head><body>
<header><h1>{html.escape(title)}</h1>
<div class="sub">generated {gen} · source {html.escape(src)}</div></header>
<div class="wrap">
{banner}
<div class="tiles">{tiles}</div>
<div class="card"><h2>Where our fills sat in the real NBBO</h2>
<div class="note">0 = crossed the spread (marketable, realistic) · 0.5 = mid · 1 = far touch (price
improvement) · red = outside the book (timing/data noise). A real marketable engine clusters near 0.</div>
<svg class="chart" viewBox="0 0 100 100" preserveAspectRatio="none">{bar_svg}</svg></div>
<div class="card"><h2>By strategy</h2>
<div class="note">scored = quote ok, fresh, our price known. confirm% = single-leg prints (cond 0/18).</div>
<table><thead><tr><th>strategy</th><th>events</th><th>scored</th><th>median pos</th>
<th>crossed%</th><th>size ok%</th><th>confirm%</th></tr></thead><tbody>{trows}</tbody></table></div>
</div></body></html>"""


# --------------------------------------------------------------------- mock
def make_mock() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Fabricate at_time_results + trade_quote_prints from the REAL events list so the preview
    is at true scale and shape. CLEARLY synthetic. Deterministic (no RNG) so it's reproducible."""
    ev = sorted(SIM.glob(EVENTS_GLOB))
    if not ev:
        raise SystemExit("no events list — run scripts/thetadata_worklist.py first")
    e = pd.read_csv(ev[-1])
    at, pr = [], []
    for i, r in e.reset_index(drop=True).iterrows():
        side = str(r["side_action"]).upper()
        base = 0.20 + ((i * 7) % 40) / 20.0            # 0.20 .. 2.15
        spread = 0.05 + ((i * 3) % 4) * 0.05           # 0.05 .. 0.20
        bid, ask = round(base, 2), round(base + spread, 2)
        # deterministic spread of fill positions so the preview exercises every state:
        m = i % 20
        if m < 11:      tpos = (i % 3) * 0.05          # marketable cluster (majority, near 0)
        elif m < 15:    tpos = 0.20 + (i % 3) * 0.10   # mild improvement
        elif m < 17:    tpos = 0.50 + (i % 3) * 0.10   # better than mid
        elif m == 17:   tpos = 1.15                    # through the book (red edge)
        elif m == 18:   tpos = -0.10                   # worse than cross (red edge)
        else:           tpos = 0.70
        px = round(ask - tpos * spread, 2) if side == "BUY" else round(bid + tpos * spread, 2)
        no_price = (i % 11 == 0)                       # ~9% have no logged per-leg price
        lag = 3.4 if (i % 33 == 0) else 0.2 + (i % 9) * 0.15   # ~3% stale (>2s)
        at.append({**{k: r[k] for k in ("trade_id", "strategy", "event", "side_action",
                                        "occ_root", "expiry", "strike", "right", "time_of_day_et")},
                   "our_fill_price": ("" if no_price else px), "quote_status": "ok",
                   "quote_timestamp": r["time_of_day_et"], "quote_lag_s": round(lag, 2),
                   "quote_stale": lag > 2,
                   "bid_size": (0 if (i % 29 == 0 and side == "SELL") else 50 + (i % 9) * 30), "bid": bid,
                   "ask_size": (0 if (i % 29 == 0 and side == "BUY") else 40 + (i % 7) * 25), "ask": ask,
                   "bid_exchange": "CBOE", "ask_exchange": "CBOE"})
        # print rows: single-leg (cond 0/18) for most; complex-only (context) for some; none for a few
        if i % 13 == 0 or no_price:
            continue                                   # no single-leg print -> confirmation untestable
        single = (i % 10 < 8)
        hit = (i % 7 != 0)                             # ~14% single-leg print misses our price
        if single and hit:
            price = px                                 # traded right at our price -> confirms
        elif single:                                   # single-leg print that does NOT reach our price
            price = round(px - 0.10, 2) if side == "SELL" else round(px + 0.10, 2)
        else:                                          # complex-only -> context, not confirmation
            price = round(px + 0.03, 2)
        pr.append({"trade_id": r["trade_id"], "event": r["event"], "strike": r["strike"],
                   "right": r["right"], "side_action": r["side_action"], "our_fill_price": px,
                   "print_status": "print", "timestamp": r["time_of_day_et"], "price": price,
                   "size": 3 + (i % 5), "condition": "18" if single else "130",
                   "bid": bid, "ask": ask, "is_single_leg": single, "is_complex": not single})
    return pd.DataFrame(at), pd.DataFrame(pr), f"SYNTHETIC from {ev[-1].name}"


# --------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="ThetaData fill-realism report (August)")
    ap.add_argument("--mock", action="store_true", help="synthetic preview (no terminal/data needed)")
    ap.add_argument("--at", help="at_time_results CSV (default: newest)")
    ap.add_argument("--prints", help="trade_quote_prints CSV (default: newest)")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()

    if args.mock:
        at_df, prints, src = make_mock()
        synthetic = True
    else:
        at_p = Path(args.at) if args.at else (sorted(TD.glob("at_time_results_*.csv")) or [None])[-1]
        if not at_p or not Path(at_p).exists():
            print("No at_time_results yet — run the fetcher, or use --mock for a preview.")
            return 1
        at_df = pd.read_csv(at_p)
        pr_p = Path(args.prints) if args.prints else (sorted(TD.glob("trade_quote_prints_*.csv")) or [None])[-1]
        prints = pd.read_csv(pr_p) if pr_p and Path(pr_p).exists() else None
        src, synthetic = str(Path(at_p).relative_to(ROOT)), False

    df = compute(at_df, prints)
    a = agg(df)
    print(f"events={a['n_events']} scored={a['n_scored']} median_pos={a['median_pos']} "
          f"crossed={a['pct_conservative']}% size_ok={a['pct_size_ok']}% "
          f"confirmed={a['n_confirmed']}/{a['n_confirm_tested']} stale={a['n_stale']}"
          + ("   [SYNTHETIC]" if synthetic else ""))
    out = SIM / (f"thetadata_fill_report_{'SYNTHETIC_' if synthetic else ''}"
                 f"{dt.datetime.now():%Y%m%d}.html")
    out.write_text(render(df, a, synthetic, src), encoding="utf-8")
    print(f"saved -> {out.relative_to(ROOT)}")
    if not args.no_open:
        webbrowser.open(out.as_uri())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
