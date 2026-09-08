"""Render a saved gexlog report (morning and/or evening) to a full, self-contained
HTML page — EVERY section/page the raw JSON carries, including the complete
Claude + Gemini markdown narratives and the per-strike gamma (GEX) profile chart.

Usage:
    python scripts/gexlog_render_report.py 2026-09-03            # both if present
    python scripts/gexlog_render_report.py 2026-09-03 --type morning
    python scripts/gexlog_render_report.py --latest              # newest date on disk

Reads   data/gexlog/raw/<date>_<morning|evening>.json
Writes  data/gexlog/reports/<date>.html   and opens it in VSCode.
Self-contained (no external CSS/JS/fonts). Nothing is fetched.
"""
import argparse
import glob
import html as _html
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "gexlog" / "raw"
OUT = ROOT / "data" / "gexlog" / "reports"
OUT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------- helpers
def g(d, *path, default=None):
    for k in path:
        d = d.get(k) if isinstance(d, dict) else None
    return d if d is not None else default


def esc(x):
    return _html.escape("" if x is None else str(x))


def num(x, dec=2):
    try:
        return f"{float(x):,.{dec}f}"
    except (TypeError, ValueError):
        return esc(x)


def sign_cls(v):
    try:
        return "pos" if float(v) > 0 else ("neg" if float(v) < 0 else "flat")
    except (TypeError, ValueError):
        return "flat"


# ---------------------------------------------------------------- markdown -> html
def md2html(md):
    """Small, dependency-free markdown renderer: headings, bold/italic, lists,
    pipe-tables, hr, paragraphs. Enough for the gexlog narrative bodies."""
    if not md:
        return ""
    lines = str(md).replace("\r\n", "\n").split("\n")
    out, i = [], 0
    list_open = False

    def inline(t):
        t = esc(t)
        t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", t)
        t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
        return t

    def close_list():
        nonlocal list_open
        if list_open:
            out.append("</ul>")
            list_open = False

    while i < len(lines):
        ln = lines[i].rstrip()
        # table block
        if "|" in ln and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|", lines[i + 1]):
            close_list()
            header = [c.strip() for c in ln.strip().strip("|").split("|")]
            out.append('<table class="md"><thead><tr>' +
                       "".join(f"<th>{inline(h)}</th>" for h in header) + "</tr></thead><tbody>")
            i += 2
            while i < len(lines) and "|" in lines[i]:
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells) + "</tr>")
                i += 1
            out.append("</tbody></table>")
            continue
        m = re.match(r"^(#{1,6})\s+(.*)", ln)
        if m:
            close_list()
            lvl = len(m.group(1))
            out.append(f"<h{lvl+2} class='md-h'>{inline(m.group(2))}</h{lvl+2}>")
        elif re.match(r"^\s*[-*]\s+", ln):
            if not list_open:
                out.append("<ul>")
                list_open = True
            out.append(f"<li>{inline(re.sub(r'^\s*[-*]\s+', '', ln))}</li>")
        elif re.match(r"^\s*(---+|\*\*\*+|___+)\s*$", ln):
            close_list()
            out.append("<hr>")
        elif ln.strip() == "":
            close_list()
        else:
            close_list()
            out.append(f"<p>{inline(ln)}</p>")
        i += 1
    close_list()
    return "\n".join(out)


# ---------------------------------------------------------------- gamma profile SVG
def gamma_svg(profile, spot, put_wall, call_wall):
    """Diverging horizontal-bar GEX profile: net_gex per strike, red left / green
    right, spot + walls marked. Labels only on spot & walls (no overlap)."""
    prof = [p for p in (profile or []) if p.get("net_gex") is not None]
    if not prof:
        return "<p class='muted'>No per-strike gamma profile in this report.</p>"
    prof = sorted(prof, key=lambda p: p["strike"])
    strikes = [p["strike"] for p in prof]
    vals = [p["net_gex"] for p in prof]
    vmax = max(abs(v) for v in vals) or 1.0
    n = len(prof)
    row_h = max(6, min(16, 720 // n))
    H = n * row_h + 40
    W = 720
    mid = W / 2
    half = mid - 70
    smin, smax = strikes[0], strikes[-1]

    def yfor(strike):
        return 30 + (smax - strike) / (smax - smin) * (H - 50) if smax != smin else H / 2

    bars = []
    for p in prof:
        v = p["net_gex"]
        w = abs(v) / vmax * half
        y = yfor(p["strike"]) - row_h / 2 + 1
        x = mid if v >= 0 else mid - w
        cls = "gpos" if v >= 0 else "gneg"
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{row_h-1.5:.1f}" class="{cls}"/>')
    marks = [f'<line x1="{mid}" y1="20" x2="{mid}" y2="{H-10}" class="axis"/>']

    def mark(strike, label, cls):
        if strike is None:
            return
        y = yfor(strike)
        marks.append(f'<line x1="30" y1="{y:.1f}" x2="{W-30}" y2="{y:.1f}" class="mk {cls}"/>')
        marks.append(f'<text x="{W-32}" y="{y-2:.1f}" class="mklab {cls}" text-anchor="end">{label} {strike:.0f}</text>')

    mark(spot, "Spot", "spot")
    mark(put_wall, "Put Wall", "pw")
    mark(call_wall, "Call Wall", "cw")
    # a few strike ticks on the left, spaced so they never collide
    ticks = []
    step = max(1, n // 12)
    for idx in range(0, n, step):
        s = strikes[idx]
        y = yfor(s)
        ticks.append(f'<text x="6" y="{y+3:.1f}" class="tick">{s:.0f}</text>')
    legend = ('<text x="{}" y="16" class="leg gpos-t" text-anchor="end">+GEX (call/support) →</text>'
              '<text x="{}" y="16" class="leg gneg-t">← −GEX (put/resistance)</text>').format(W - 30, 40)
    return (f'<svg viewBox="0 0 {W} {H}" class="gamma" role="img" '
            f'aria-label="Per-strike net GEX profile">{legend}'
            + "".join(bars) + "".join(marks) + "".join(ticks) + "</svg>")


# ---------------------------------------------------------------- section builders
def market_cards(mk):
    order = [("spx", "SPX"), ("es", "ES"), ("nq", "NQ"), ("rty", "RTY"),
             ("vix", "VIX"), ("oil", "Oil")]
    cards = []
    for key, lbl in order:
        d = mk.get(key)
        if not isinstance(d, dict):
            continue
        chg = d.get("change")
        pct = d.get("changePercent")
        cls = sign_cls(chg)
        extra = ""
        if d.get("high") is not None:
            extra = f"<div class='ohlc'>O {num(d.get('open'))} · H {num(d.get('high'))} · L {num(d.get('low'))}</div>"
        cards.append(
            f"<div class='mcard'><div class='mlbl'>{lbl}</div>"
            f"<div class='mpx'>{num(d.get('price'))}</div>"
            f"<div class='mchg {cls}'>{'+' if sign_cls(chg)=='pos' else ''}{num(chg)} "
            f"({num(pct)}%)</div>{extra}</div>")
    gl = mk.get("global") or {}
    if gl:
        gtxt = " · ".join(f"{k.title()}: {esc(v)}" for k, v in gl.items())
        cards.append(f"<div class='mcard wide'><div class='mlbl'>Global</div><div class='gtxt'>{gtxt}</div></div>")
    return "<div class='mgrid'>" + "".join(cards) + "</div>"


def catalyst_table(items, title):
    items = [c for c in (items or []) if isinstance(c, dict)]
    if not items:
        return ""
    rows = "".join(
        f"<tr><td class='ct'>{esc(c.get('time'))}</td><td>{esc(c.get('title'))}</td>"
        f"<td><span class='imp imp-{esc(c.get('impact'))}'>{esc(c.get('impact'))}</span></td>"
        f"<td class='muted'>{esc(c.get('category',''))}</td></tr>" for c in items)
    return (f"<div class='cat'><h4>{esc(title)} <span class='muted'>({len(items)})</span></h4>"
            f"<table class='tbl'><thead><tr><th>Time</th><th>Event</th><th>Impact</th>"
            f"<th>Cat</th></tr></thead><tbody>{rows}</tbody></table></div>")


def kv_row(pairs):
    return "<div class='kv'>" + "".join(
        f"<div class='kvi'><span class='k'>{esc(k)}</span><span class='v'>{v}</span></div>"
        for k, v in pairs if v is not None and v != "") + "</div>"


def render_report(d, date):
    rtype = g(d, "meta", "reportType", default="report")
    is_ev = rtype == "evening"
    lv = g(d, "levels", default={}) or {}
    gm = g(d, "forecast", "factors", "gamma", default={}) or {}
    spot = lv.get("current") or gm.get("gex_spot_ref")
    S = []

    # header
    S.append(
        f"<header class='rhead'><div><span class='rtag {rtype}'>{esc(rtype).upper()}</span>"
        f"<h1>{esc(date)}</h1></div>"
        f"<div class='rmeta'>Generated {esc(g(d,'meta','generatedAt'))} · "
        f"source {esc(g(d,'meta','dataSource'))} · v{esc(g(d,'meta','version'))}</div></header>")

    # risk banner
    rl = g(d, "risk", "level")
    if rl:
        S.append(f"<div class='risk risk-{esc(rl).lower()}'><b>Risk: {esc(rl)}</b> — "
                 f"{esc(g(d,'risk','summary'))}</div>")

    # market snapshot
    S.append("<section><h3>Market Snapshot</h3>" + market_cards(g(d, "market", default={})) + "</section>")

    # forecast + gamma
    fc_conf = g(d, "forecast", "confidence")
    rs = g(d, "forecast", "regime_streak", default={}) or {}
    fac = g(d, "forecast", "factors", default={}) or {}
    forecast_bits = kv_row([
        ("Type", esc(g(d, "forecast", "type"))),
        ("Confidence", f"{esc(fc_conf)}%" if fc_conf is not None else None),
        ("Regime", esc(rs.get("label") or gm.get("value"))),
        ("Day Type", esc(rs.get("day_type_label") or rs.get("day_type"))),
        ("GEX trend", esc(rs.get("gex_trend"))),
        ("Gap", esc(g(fac, "gap", "value"))),
        ("Volatility", esc(g(fac, "volatility", "value"))),
        ("Calendar", esc(g(fac, "calendar", "value"))),
    ])
    gamma_bits = kv_row([
        ("Regime", esc(gm.get("value"))),
        ("Method", esc(gm.get("gex_method"))),
        ("Net GEX", num(gm.get("net_gex"), 0)),
        ("Zero-gamma", num(gm.get("gex_zero_gamma") or gm.get("gex_flip") or gm.get("gex_flip_raw"))),
        ("Spot ref", num(gm.get("gex_spot_ref"))),
        ("Flip proximity", esc(gm.get("flip_proximity"))),
        ("Borderline", esc(gm.get("borderline_regime"))),
    ])
    S.append(
        "<section><h3>Forecast &amp; Gamma Regime</h3>" + forecast_bits +
        "<h4>Gamma / GEX</h4>" + gamma_bits +
        "<div class='chartwrap'>" +
        gamma_svg(gm.get("gex_profile"), spot, lv.get("putWall"), lv.get("callWall")) +
        "</div></section>")

    # levels
    lvl_bits = kv_row([
        ("R2", num(lv.get("r2"))), ("R1", num(lv.get("r1"))),
        ("Current", num(lv.get("current"))),
        ("S1", num(lv.get("s1"))), ("S2", num(lv.get("s2"))),
        ("Put Wall", num(lv.get("putWall"))), ("Call Wall", num(lv.get("callWall"))),
        ("Expected Move", num(lv.get("expectedMove"))),
        ("EM Lower", num(lv.get("emLower"))), ("EM Upper", num(lv.get("emUpper"))),
        ("Pivot source", esc(lv.get("pivotSource"))),
    ])
    S.append("<section><h3>Levels</h3>" + lvl_bits + "</section>")

    # session analysis (evening)
    sa = g(d, "session_analysis", default={}) or {}
    if sa:
        S.append("<section><h3>Session Analysis</h3>" + kv_row([
            ("SPX change %", num(sa.get("spx_change"))),
            ("VIX change %", num(sa.get("vix_change"))),
            ("Session type", esc(sa.get("session_type"))),
            ("Forecast accurate", esc(sa.get("forecast_accurate"))),
            ("EM hit", esc(sa.get("expected_move_hit"))),
        ]) + "</section>")

    # playbook (morning)
    pb = g(d, "playbook", default={}) or {}
    pb_cards = []
    for key in ("primary", "alternative", "neutral"):
        p = pb.get(key)
        if isinstance(p, dict):
            pb_cards.append(
                f"<div class='pb'><div class='pbk'>{key}</div>"
                f"<div class='pbs'>{esc(p.get('scenario'))}</div>"
                f"<div class='pbt'><b>Trigger:</b> {esc(p.get('trigger'))}</div>"
                f"<div class='pbb'>{esc(p.get('bias'))}</div></div>")
    if pb_cards:
        S.append("<section><h3>Playbook</h3><div class='pbgrid'>" + "".join(pb_cards) + "</div></section>")

    # guidance / lookahead / caveat
    guide = g(d, "guidance", default={}) or {}
    la = g(d, "lookAhead", default={}) or {}
    cav = g(d, "regime_caveat", default={}) or {}
    gbits = []
    if guide:
        gbits.append(f"<div class='note'><b>Guidance — {esc(guide.get('signal'))}: "
                     f"{esc(guide.get('message'))}</b><br>{esc(guide.get('notes'))}</div>")
    for horizon in ("tomorrow", "week"):
        h = la.get(horizon)
        if isinstance(h, dict):
            gbits.append(f"<div class='note'><b>Look ahead ({horizon}) — {esc(h.get('risk'))}:</b> "
                         f"{esc(h.get('reason'))}</div>")
    if cav.get("warning"):
        gbits.append(f"<div class='note warn'><b>Regime caveat:</b> {esc(cav.get('warning'))}</div>")
    if gbits:
        S.append("<section><h3>Guidance &amp; Look-Ahead</h3>" + "".join(gbits) + "</section>")

    # catalysts
    cats = g(d, "catalysts", default={}) or {}
    ctbl = (catalyst_table(cats.get("today"), "Today") +
            catalyst_table(cats.get("tomorrow"), "Tomorrow") +
            catalyst_table(cats.get("week"), "This Week"))
    if ctbl:
        S.append("<section><h3>Economic Calendar</h3>" + ctbl + "</section>")

    # market context
    mc = g(d, "market_context", default={}) or {}
    if mc:
        secs = mc.get("sectors") or {}
        lead = " · ".join(f"{esc(c.get('name'))} {num(c.get('change'))}%"
                          for c in (secs.get("leaders") or []) if isinstance(c, dict))
        lag = " · ".join(f"{esc(c.get('name'))} {num(c.get('change'))}%"
                         for c in (secs.get("laggards") or []) if isinstance(c, dict))
        tr = mc.get("treasury") or {}
        te = mc.get("technical") or {}
        S.append("<section><h3>Market Context</h3>" + kv_row([
            ("Sector leaders", lead), ("Sector laggards", lag),
            ("2y / 10y / 30y", f"{num(tr.get('year2'))} / {num(tr.get('year10'))} / {num(tr.get('year30'))}"),
            ("2y10y spread", num(tr.get("spread_2y10y"))),
            ("10y Δbp", num(tr.get("change_10y_bp"))),
            ("RSI(14)", f"{num(te.get('rsi_14'))} ({esc(te.get('rsi_label'))})"),
            ("vs 50/200 SMA", f"{num(te.get('vs_50sma_pct'))}% / {num(te.get('vs_200sma_pct'))}%"),
        ]) + "</section>")

    # news context
    nc = d.get("news_context")
    if nc:
        S.append("<section><h3>News Context</h3><div class='md'>" + md2html(nc) + "</div></section>")

    # full narratives
    prov = d.get("ai_narrative_provider")
    nar_c = d.get("ai_narrative_claude")
    nar_g = d.get("ai_narrative_gemini")
    if nar_c:
        S.append(f"<section class='narrative'><h3>Full Brief — Claude"
                 f"{' (primary)' if prov=='claude' else ''}</h3><div class='md'>"
                 + md2html(nar_c) + "</div></section>")
    if nar_g:
        S.append("<section class='narrative'><h3>Full Brief — Gemini</h3><div class='md'>"
                 + md2html(nar_g) + "</div></section>")

    # pipeline status footer
    ps = g(d, "pipeline_status", default={}) or {}
    if ps:
        S.append("<section><h3 class='muted'>Pipeline status</h3>" +
                 kv_row([(k, esc(v)) for k, v in ps.items()]) + "</section>")

    return f"<article class='report {rtype}'>" + "".join(S) + "</article>"


CSS = """
:root{color-scheme:dark light}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
 background:#0d1117;color:#e6edf3}
.wrap{max-width:1000px;margin:0 auto;padding:24px 20px 80px}
.tabs{display:flex;gap:8px;position:sticky;top:0;background:#0d1117;padding:12px 0;z-index:5;border-bottom:1px solid #21262d}
.tabs button{background:#161b22;color:#8b949e;border:1px solid #30363d;border-radius:8px;
 padding:8px 18px;font-size:14px;cursor:pointer;font-weight:600}
.tabs button.on{background:#1f6feb;color:#fff;border-color:#1f6feb}
article{display:none}article.show{display:block}
.rhead{display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:8px;
 margin:22px 0 6px;padding-bottom:12px;border-bottom:2px solid #30363d}
.rhead h1{margin:4px 0 0;font-size:30px}
.rtag{font-size:11px;font-weight:800;letter-spacing:.08em;padding:3px 9px;border-radius:5px}
.rtag.morning{background:#1f6feb33;color:#79c0ff}
.rtag.evening{background:#a371f733;color:#d2a8ff}
.rmeta{color:#8b949e;font-size:12.5px}
section{margin:26px 0}
h3{font-size:18px;margin:0 0 12px;padding-bottom:6px;border-bottom:1px solid #21262d}
h4{font-size:14px;margin:16px 0 8px;color:#adbac7}
.risk{padding:10px 14px;border-radius:8px;margin:14px 0;font-size:14px;border:1px solid}
.risk-low{background:#12261e;border-color:#238636}.risk-moderate{background:#2b2411;border-color:#9e6a03}
.risk-elevated,.risk-high{background:#2d1518;border-color:#da3633}
.mgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.mcard{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px}
.mcard.wide{grid-column:1/-1}
.mlbl{color:#8b949e;font-size:11px;font-weight:700;letter-spacing:.06em}
.mpx{font-size:22px;font-weight:700;margin:2px 0}
.mchg{font-size:13px;font-weight:600}.ohlc,.gtxt{color:#8b949e;font-size:11.5px;margin-top:4px}
.pos{color:#3fb950}.neg{color:#f85149}.flat{color:#8b949e}
.kv{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px 18px}
.kvi{display:flex;justify-content:space-between;gap:12px;border-bottom:1px dotted #21262d;padding:4px 0}
.kvi .k{color:#8b949e}.kvi .v{font-weight:600;text-align:right}
.chartwrap{background:#0b0f14;border:1px solid #21262d;border-radius:10px;padding:12px;margin-top:12px;overflow-x:auto}
svg.gamma{width:100%;min-width:640px;height:auto}
.gamma .gpos{fill:#238636cc}.gamma .gneg{fill:#da3633cc}
.gamma .axis{stroke:#484f58;stroke-width:1}
.gamma .mk{stroke-width:1;stroke-dasharray:4 3;opacity:.9}
.gamma .mk.spot{stroke:#e3b341}.gamma .mk.pw{stroke:#f85149}.gamma .mk.cw{stroke:#3fb950}
.gamma .mklab{font:11px sans-serif;font-weight:700}
.gamma .mklab.spot{fill:#e3b341}.gamma .mklab.pw{fill:#f85149}.gamma .mklab.cw{fill:#3fb950}
.gamma .tick{fill:#6e7681;font:9px sans-serif}
.gamma .leg{font:11px sans-serif;font-weight:700}.gamma .gpos-t{fill:#3fb950}.gamma .gneg-t{fill:#f85149}
.pbgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}
.pb{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px}
.pbk{text-transform:uppercase;font-size:11px;font-weight:800;color:#58a6ff;letter-spacing:.06em}
.pbs{font-size:16px;font-weight:700;margin:4px 0}.pbt{font-size:13px;margin:6px 0;color:#adbac7}
.pbb{font-size:13px;color:#8b949e}
.note{background:#161b22;border-left:3px solid #1f6feb;border-radius:6px;padding:10px 14px;margin:8px 0;font-size:14px}
.note.warn{border-left-color:#da3633}
.tbl{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
.tbl th{text-align:left;color:#8b949e;font-size:11px;border-bottom:1px solid #30363d;padding:6px}
.tbl td{padding:5px 6px;border-bottom:1px solid #161b22}
.ct{white-space:nowrap;color:#8b949e}
.imp{font-size:10px;font-weight:800;padding:1px 7px;border-radius:4px;text-transform:uppercase}
.imp-high{background:#da363333;color:#ff7b72}.imp-medium{background:#9e6a0333;color:#e3b341}
.imp-low{background:#30363d;color:#8b949e}
.cat{margin:14px 0}.cat h4{margin:8px 0}
.muted{color:#8b949e}
.narrative .md{background:#0b0f14;border:1px solid #21262d;border-radius:10px;padding:18px 22px}
.md h3,.md h4,.md h5,.md-h{border:0;color:#79c0ff}.md-h{margin:16px 0 8px}
.md p{margin:8px 0}.md ul{margin:8px 0 8px 4px}.md li{margin:3px 0}
.md code{background:#161b22;padding:1px 5px;border-radius:4px;font-size:12.5px}
.md hr{border:0;border-top:1px solid #21262d;margin:16px 0}
.md table.md{border-collapse:collapse;width:100%;margin:10px 0;font-size:13px}
.md table.md th,.md table.md td{border:1px solid #30363d;padding:5px 8px}
.md table.md th{background:#161b22}
"""

JS = """
const tabs=[...document.querySelectorAll('.tabs button')];
const arts=[...document.querySelectorAll('article')];
function show(id){arts.forEach(a=>a.classList.toggle('show',a.id===id));
 tabs.forEach(b=>b.classList.toggle('on',b.dataset.t===id));}
tabs.forEach(b=>b.onclick=()=>show(b.dataset.t));
if(arts.length)show(arts[0].id);
"""


def build_page(date, reports):
    tabs = "".join(
        f"<button data-t='{rt}'>{rt.title()}</button>" for rt, _ in reports)
    arts = "".join(
        f"<article class='report {rt}' id='{rt}'>{render_report(d, date)}</article>"
        for rt, d in reports)
    tabbar = f"<div class='tabs'>{tabs}</div>" if len(reports) > 1 else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>gexlog {date}</title><style>{CSS}</style></head>
<body><div class="wrap">{tabbar}{arts}</div><script>{JS}</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", help="YYYY-MM-DD")
    ap.add_argument("--type", choices=["morning", "evening", "both"], default="both")
    ap.add_argument("--latest", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    if a.latest or not a.date:
        dates = sorted({Path(p).name[:10] for p in glob.glob(str(RAW / "*_*.json"))})
        if not dates:
            raise SystemExit("no raw reports found")
        a.date = dates[-1]

    types = ["morning", "evening"] if a.type == "both" else [a.type]
    reports = []
    for rt in types:
        f = RAW / f"{a.date}_{rt}.json"
        if f.exists():
            reports.append((rt, json.loads(f.read_text(encoding="utf-8"))))
    if not reports:
        raise SystemExit(f"no reports on disk for {a.date}")

    out = OUT / f"{a.date}.html"
    out.write_text(build_page(a.date, reports), encoding="utf-8")
    print(f"wrote {out}  ({', '.join(rt for rt,_ in reports)})")
    if not a.no_open:
        try:
            subprocess.run(["code", str(out)], shell=True, check=False)
        except Exception as e:
            print("open skipped:", e)


if __name__ == "__main__":
    main()
