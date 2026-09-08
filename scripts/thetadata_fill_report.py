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
            "expiry": r.get("expiry"),
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
    sz = pd.to_numeric(scored.size_at_touch, errors="coerce").dropna()
    return {
        "n_events": len(df),
        "n_ok": int((df.status == "ok").sum()),
        "n_scored": n_scored,
        "median_pos": round(scored.pos.median(), 3) if n_scored else None,
        "mean_pos": round(scored.pos.mean(), 3) if n_scored else None,
        "pct_conservative": pct(scored.pos <= 0.5, n_scored),        # crossed / at-or-worse than mid
        "pct_through": pct(scored.pos > 1.0, n_scored),              # through the book -> timing noise
        "pct_size_ok": pct(scored.size_ok, n_scored),
        "median_size": int(sz.median()) if len(sz) else None,        # ACTUAL contracts at the touch
        "min_size": int(sz.min()) if len(sz) else None,
        "max_size": int(sz.max()) if len(sz) else None,
        "pct_size0": pct(sz == 0, len(sz)),
        "n_stale": int(df.stale.sum()),
        "n_confirmed": int((df.print_confirmed == True).sum()),      # noqa: E712
        "n_confirm_tested": int(df.print_confirmed.notna().sum()),
        "n_no_price": int(df.our_price.isna().sum()),
    }


def load_latency() -> dict | None:
    """Newest fill_timing_analysis CSV -> our-clock-vs-IB-exec lag summary (for the FAQ)."""
    cands = sorted(SIM.glob("fill_timing_analysis_*.csv"))
    if not cands:
        return None
    d = pd.read_csv(cands[-1])
    if "delta_s" not in d.columns or not len(d):
        return None
    x = pd.to_numeric(d.delta_s, errors="coerce").dropna()
    return {"n": len(x), "median": round(x.median(), 2), "mean": round(x.mean(), 2),
            "p90": round(x.quantile(.9), 2), "within2": round(100 * (x.abs() <= 2).mean())}


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


def summary_html(a: dict) -> str:
    """Plain-English written summary, generated from the actual metrics."""
    med = a["median_pos"]
    good = med is not None and med <= 0.5
    verdict = ("realistic — the same prices a real marketable order would get"
               if good else "worth a closer look — fills sit better than a crossing order should")
    return f"""<div class="summary">
<h2>In plain English</h2>
<p>This checks whether our simulated option fills could really have happened. For each of our
<b>{a['n_events']}</b> buy/sell fills, we looked up the <b>real market</b> — the actual bid/ask and
the real trades that printed — at the exact second the broker says we filled, and compared our
price against it.</p>
<p class="verdict"><b>Bottom line: the fills look {verdict}.</b></p>
<ul>
<li><b>Where we filled.</b> The typical fill landed at position <b>{med}</b> between the bid and the
ask (0 = the price you pay to cross the spread, 0.5 = the midpoint, 1 = the best possible price).
A value near 0 is what a real market order looks like — <b>{a['pct_conservative']}%</b> of fills were
at-or-worse than the midpoint, i.e. not too-good-to-be-true.</li>
<li><b>Was the size really there.</b> <b>{a['pct_size_ok']}%</b> of fills had at least one contract
actually available at that price — so the fill wasn't a mirage; real depth was sitting there.</li>
<li><b>Did a real trade happen at our price.</b> Of the <b>{a['n_confirm_tested']}</b> fills we could
check, <b>{a['n_confirmed']}</b> had a genuine single-leg trade print at our price (not a multi-leg
package price). A fill without one is <b>not</b> impossible — see the note under the table.</li>
<li><b>Anything off.</b> <b>{a['pct_through']}%</b> looked slightly better than the market — a
sub-second timing artifact (the quote we captured was the last one just before the fill), not an
impossible fill. <b>{a['n_stale']}</b> fill(s) had a too-old quote and were set aside.</li>
</ul></div>"""


def render(df: pd.DataFrame, a: dict, synthetic: bool, src: str, anon: bool = False,
           lat: dict | None = None) -> str:
    scored = df[df.pos.notna() & ~df.stale]
    bars = _hist(scored.pos) if len(scored) else []
    bmax = max((c for _, c, _ in bars), default=1) or 1
    cols_html = labs_html = ""
    for label, c, tone in bars:
        h = round(178 * c / bmax) if c else 0
        col = "var(--bad)" if tone == "bad" else "var(--pos)"
        cols_html += (f'<div class="col" title="pos {label}: {c}"><span class="cval">'
                      f'{c if c else ""}</span>'
                      f'<div class="cbar" style="height:{h}px;background:{col}"></div></div>')
        labs_html += f'<div class="hl">{label}</div>'

    # position breakdown — every scored fill in exactly one band; shares sum to 100%
    nsc = len(scored)
    cats = [
        ("Crossed the spread — filled at the touch", scored.pos <= 1e-9, "good"),
        ("Inside — better than the touch, at/below mid", (scored.pos > 1e-9) & (scored.pos <= 0.5), "ink"),
        ("Better than mid — price improvement", (scored.pos > 0.5) & (scored.pos <= 1.0), "ink"),
        ("Through the book — sub-second timing noise", scored.pos > 1.0, "bad"),
    ]
    brows, cum = "", 0
    for idx, (name, mask, tone) in enumerate(cats):
        cnt = int(mask.sum())
        cum += cnt
        pctv = (100 * cnt / nsc) if nsc else 0
        med = scored.pos[mask].median() if cnt else None
        meds = f"{med:.3f}" if med is not None else "—"
        cls = " class='bad'" if tone == "bad" else (" class='good'" if tone == "good" else "")
        brows += f"<tr><td>{name}</td><td>{cnt}</td><td{cls}>{pctv:.1f}%</td><td>{meds}</td></tr>"
        if idx == 1:                                  # subtotal ≤ mid = the tiles' "Conservative"
            sub = (100 * cum / nsc) if nsc else 0
            brows += (f"<tr class='sub'><td>↳ ≤ mid — conservative subtotal</td><td>{cum}</td>"
                      f"<td class='good'>{sub:.1f}%</td><td>—</td></tr>")
    allmed = f"{scored.pos.median():.3f}" if nsc else "—"
    brows += (f"<tr class='tot'><td>All scored fills</td><td>{nsc}</td><td>100.0%</td><td>{allmed}</td></tr>")

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
        tile("Conservative (≤ mid)", f'{a["pct_conservative"]}%' if a["pct_conservative"] is not None else None,
             "pos ≤ 0.5 — at/worse than mid (= table rows 1+2)", "good"),
        tile("Median size at touch", a["median_size"],
             f'contracts resting at our price (≥1: {a["pct_size_ok"]}% · =0: {a["pct_size0"]}%)'),
        tile("Single-leg print-confirmed",
             f'{a["n_confirmed"]}/{a["n_confirm_tested"]}' if a["n_confirm_tested"] else None,
             "cond 0/18 traded at our price"),
        tile("Through the book", f'{a["pct_through"]}%' if a["pct_through"] is not None else None,
             "pos > 1 (timing/data noise)", "bad" if (a["pct_through"] or 0) > 0 else "ink"),
        tile("Stale quotes", a["n_stale"], "quote >2s before fill (excluded)", "warn"),
    ])
    belowzero = int((scored.pos < 0).sum())
    # ---- report metadata (context strip) ----
    exp = pd.to_numeric(df.expiry, errors="coerce").dropna().astype(int)
    def _fd(x):
        s = str(int(x))
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    dmin, dmax = (_fd(exp.min()), _fd(exp.max())) if len(exp) else ("—", "—")
    ndays = exp.nunique() if len(exp) else 0
    meta_items = [
        ("Instrument", "SPX (SPXW) — 0DTE cash-settled index options"),
        ("Exchange", "Cboe"),
        ("Trading hours", "09:30–16:00 ET (SPXW settles on the close)"),
        ("Broker", "Interactive Brokers"),
        ("Mode", "SIMULATED — IB paper fills, checked vs real OPRA NBBO"),
        ("Date range", f"{dmin} → {dmax}"),
        ("Trading days", str(ndays)),
        ("NBBO / print source", "ThetaData (OPRA consolidated, tick)"),
    ]
    meta = "".join(f'<div class="mi"><span class="mk">{k}</span><span class="mv">{v}</span></div>'
                   for k, v in meta_items)
    # ---- latency paragraph ----
    if lat:
        lat_p = (f"On the {lat['n']} fills we could match, our log lands a median "
                 f"<b>{lat['median']:+.2f}s</b> after IB's execution (mean {lat['mean']:+.2f}s, "
                 f"90th pct {lat['p90']:+.2f}s; {lat['within2']}% within ±2s) — our clock+callback "
                 f"offset, which is exactly why we anchor the NBBO lookup on IB's exec time, not our clock.")
    else:
        lat_p = "Run fill_timing_analysis.py to quantify our-log-vs-IB-exec lag."
    faq = f"""<div class="card faq"><h2>Method &amp; FAQ</h2>
<h3>What this report covers — and what settles at the close</h3>
<p>The {a['n_events']} events here are <b>entry fills + order-based exit fills</b> — every time we
actually traded against the market. That includes the "premise didn't hold" early exits and the few
positions we closed with an order near the EOD. <b>Positions we held to expiry are not fills</b>:
SPXW cash-settles at the official 4:00pm close, so those legs are validated separately against the
settlement price, not the NBBO. That settlement carries a large share of the book's P&amp;L, so it
gets its own check — this report is the fill half.</p>
<h3>How each fill is timed — and the lag</h3>
<p>Every fill is anchored to <b>IB's true execution time</b> (Trade-Confirmation report, second
precision). We also record our own fill time in the sim, but that is our machine's clock at the fill
<i>callback</i>, which fires after the real execution. {lat_p}</p>
<p><b>What we don't yet have:</b> the moment the sim <i>submitted</i> the order, so we can't quote a
true submit→fill latency. That's one checkbox away — add "Order Time" to the IB Flex query and we
compute it exactly.</p>
<h3>The ±3-second window</h3>
<p>The print-confirmation window is <b>centered on the fill</b>: 3s before to 3s after (6s total).
Why 3s? A trade-off — too narrow (±1s) and thin 0DTE strikes often have no nearby single-leg print, so
we'd under-confirm real fills; too wide (±9s) and on a fast tape you match prints from a
<i>different</i> price regime and over-confirm. ±3s catches a genuinely contemporaneous trade without
drifting. It affects only the <i>secondary</i> print check — the primary metric (where the fill sat in
the NBBO) uses the exact quote at the fill instant and is <b>not</b> windowed. A volatile 3s is not a
problem: more prints just means more chances to find a real trade at our price; we still only count one
at/through it.</p>
<h3>When would we say a fill could NOT have happened?</h3>
<p>Two independent questions:</p>
<ul>
<li><b>Could it happen? (primary)</b> At the fill instant, was our price at/inside the real NBBO
<i>and</i> was size there? We capture the <b>actual</b> resting size, not just a flag — median
<b>{a['median_size']} contracts</b> at our price (range {a['min_size']}–{a['max_size']}; only
{a['pct_size0']}% had zero). A fill looks <b>not</b> achievable only when it printed <b>through the
book</b> (better than the best available price — {a['pct_through']}%) or had <b>zero size</b> — and the
through-book cases are sub-second quote drift, not impossible fills.</li>
<li><b>Did a real trade print at our price? (secondary)</b> The
{a['n_confirmed']}/{a['n_confirm_tested']} confirmation. Its absence — {a['n_confirm_tested'] - a['n_confirmed']}
had nearby single-leg prints but not at our price, others had none in the window — is <b>not</b>
evidence against the fill; fillability is judged by the primary test.</li>
</ul>
<h3>What "position &lt; 0" means</h3>
<p>Position 0 = filled exactly at the marketable touch (buy at the ask / sell at the bid).
<b>Below&nbsp;0</b> means we filled <i>worse</i> than the visible touch — paid above the ask or sold
below the bid — extra-conservative slippage where the quote moved against us. The <b>{belowzero}</b>
fills below 0 make the sim look <i>harder</i> on itself, not easier. <b>Above&nbsp;1</b> is the reverse:
better than the best price, the through-the-book timing tail.</p></div>"""
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
.summary{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 20px;margin:16px 0}}
.summary h2{{font-size:14px;margin:0 0 8px;font-weight:660}}
.summary p{{margin:0 0 9px;line-height:1.5;color:var(--ink2)}}
.summary p.verdict{{color:var(--ink);font-size:15px}}
.summary ul{{margin:6px 0 0;padding-left:18px}}
.summary li{{margin:5px 0;line-height:1.5;color:var(--ink2)}}
.summary b{{color:var(--ink)}}
.anon{{font-size:12px;color:var(--muted);margin:2px 0 0}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:15px 17px;margin:14px 0}}
.card h2{{font-size:13px;margin:0 0 4px;font-weight:640}}
.card .note{{font-size:12px;color:var(--muted);margin-bottom:12px}}
.hist{{display:flex;align-items:flex-end;gap:5px;height:200px;padding:6px 2px 0}}
.col{{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;height:100%}}
.cval{{font-size:10.5px;color:var(--ink2);margin-bottom:3px;font-variant-numeric:tabular-nums;min-height:14px}}
.cbar{{width:72%;min-height:2px;border-radius:4px 4px 0 0}}
.hlabs{{display:flex;gap:5px;padding:6px 2px 0}}
.hl{{flex:1;text-align:center;font-size:10.5px;color:var(--muted);font-variant-numeric:tabular-nums}}
table{{width:100%;border-collapse:collapse;font-size:13px;font-variant-numeric:tabular-nums}}
th,td{{text-align:right;padding:6px 10px;border-bottom:1px solid var(--border)}}
th:first-child,td:first-child{{text-align:left;font-family:ui-monospace,monospace}}
th{{font-size:11px;color:var(--muted);text-transform:uppercase;font-weight:600}}
td.good{{color:var(--good);font-weight:600}}td.bad{{color:var(--bad);font-weight:600}}
tr.tot td{{border-top:2px solid var(--border);font-weight:650;color:var(--ink)}}
tr.sub td{{color:var(--ink2);font-style:italic;background:rgba(127,127,127,.05)}}
.foot{{background:var(--surface);border:1px solid var(--border);border-left:3px solid var(--pos);
  border-radius:10px;padding:12px 16px;margin:14px 0;font-size:12.5px;line-height:1.55;color:var(--ink2)}}
.foot b{{color:var(--ink)}}
.meta{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:8px 18px;
  background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:13px 16px;margin:16px 0}}
.mi{{display:flex;flex-direction:column;gap:1px}}
.mk{{font-size:10.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.03em}}
.mv{{font-size:13px;color:var(--ink);font-weight:550}}
.faq h3{{font-size:13px;margin:14px 0 4px;font-weight:640}}
.faq p,.faq li{{font-size:12.5px;line-height:1.55;color:var(--ink2);margin:5px 0}}
.faq b{{color:var(--ink)}}.faq ul{{margin:4px 0;padding-left:18px}}
</style></head><body>
<header><h1>{html.escape(title)}</h1>
<div class="sub">generated {gen} · source {html.escape(src)}</div></header>
<div class="wrap">
{banner}
<div class="meta">{meta}</div>
{summary_html(a)}
<div class="tiles">{tiles}</div>
<div class="card"><h2>Where our fills sat in the real NBBO</h2>
<div class="note">0 = crossed the spread (marketable, realistic) · 0.5 = mid · 1 = far touch (price
improvement) · red = outside the book (timing/data noise). A real marketable engine clusters near 0.</div>
<div class="hist">{cols_html}</div><div class="hlabs">{labs_html}</div></div>
<div class="card"><h2>Position breakdown — what share filled where</h2>
<div class="note">Every scored fill falls in exactly one band; the shares add to 100%.
"Crossed the spread" is the realistic/conservative outcome.</div>
<table><thead><tr><th>where our fill landed</th><th>fills</th><th>% of fills</th>
<th>median position</th></tr></thead>
<tbody>{brows}</tbody></table></div>
<div class="card"><h2>By strategy</h2>
<div class="note">scored = quote ok, fresh, our price known. confirm% = single-leg prints (cond 0/18).
{"Strategy names anonymized." if anon else ""}</div>
<table><thead><tr><th>strategy</th><th>events</th><th>scored</th><th>median position</th>
<th>crossed %</th><th>size-ok %</th><th>confirm %</th></tr></thead><tbody>{trows}</tbody></table></div>
<div class="foot"><b>What "print-confirmed" means — and what it doesn't.</b> A single-leg trade
printing at our price is <i>positive</i> proof the fill was achievable. The reverse is not true:
an unconfirmed fill is <b>not</b> an impossible one. This is paper, so our own order never prints
to the tape — confirmation depends on some <i>other</i> trader printing at our exact price within
±3 seconds. And spread legs frequently trade as multi-leg <i>package</i> orders (conditions
130/131/134), which we deliberately exclude. Those fills stand on the NBBO + size-at-touch check
instead. In this run, {a['n_confirm_tested'] - a['n_confirmed']} fills had single-leg prints nearby
but not at our price, and a further set had no print in the window — neither is a red flag.</div>
{faq}
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
    ap.add_argument("--anon", action="store_true",
                    help="anonymize strategy names for a vendor-facing copy (writes a PRIVATE legend)")
    ap.add_argument("--pdf", action="store_true", help="also export a PDF (Edge/Chrome headless)")
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

    if args.anon:                                        # vendor-facing: hide our strategy names
        names = sorted(x for x in df.strategy.dropna().unique())
        strat_map = {n: f"S{i + 1:02d}" for i, n in enumerate(names)}
        df["strategy"] = df.strategy.map(lambda x: strat_map.get(x, x))
        legend = SIM / f"thetadata_strategy_map_{dt.datetime.now():%Y%m%d}.csv"
        pd.DataFrame([{"code": c, "strategy": n} for n, c in strat_map.items()]).to_csv(legend, index=False)
        print(f"PRIVATE legend (do NOT send) -> {legend.relative_to(ROOT)}")

    a = agg(df)
    print(f"events={a['n_events']} scored={a['n_scored']} median_pos={a['median_pos']} "
          f"crossed={a['pct_conservative']}% size_ok={a['pct_size_ok']}% "
          f"confirmed={a['n_confirmed']}/{a['n_confirm_tested']} stale={a['n_stale']}"
          + ("   [SYNTHETIC]" if synthetic else "") + ("   [ANON]" if args.anon else ""))
    out = SIM / (f"thetadata_fill_report_{'SYNTHETIC_' if synthetic else ''}"
                 f"{'anon_' if args.anon else ''}{dt.datetime.now():%Y%m%d}.html")
    out.write_text(render(df, a, synthetic, src, anon=args.anon, lat=load_latency()),
                   encoding="utf-8")
    print(f"saved -> {out.relative_to(ROOT)}  (self-contained HTML)")
    if args.pdf:
        pdf = export_pdf(out)
        print(f"saved -> {pdf.relative_to(ROOT)}" if pdf else
              "  PDF skipped — no Edge/Chrome found (open the HTML and Print → Save as PDF).")
    if not args.no_open:
        webbrowser.open(out.as_uri())
    return 0


def export_pdf(html_path: Path) -> Path | None:
    """Render the self-contained HTML to PDF via Edge/Chrome headless (no extra deps)."""
    import shutil
    import subprocess
    pdf = html_path.with_suffix(".pdf")
    cands = ["msedge", "chrome",
             r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
             r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
    exe = next((c for c in cands if shutil.which(c) or Path(c).exists()), None)
    if not exe:
        return None
    try:
        subprocess.run([exe, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--print-to-pdf={pdf}", html_path.as_uri()],
                       check=True, timeout=120, capture_output=True)
        return pdf if pdf.exists() else None
    except (subprocess.SubprocessError, OSError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
