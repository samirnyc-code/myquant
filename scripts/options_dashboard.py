"""Polished standalone options dashboard (S73) -> data/options_sim/dashboard.html.

Replaces the cheap-looking Streamlit UI: one self-contained, elegant dark page.
Reads the same files (trades.parquet, journal.json, marks.csv, account.csv,
live.json). Reuses the flip-card trade wall from options_build_cards. No server,
no Streamlit — just open the file (or serve the folder).

Run: .venv/Scripts/python.exe scripts/options_dashboard.py
"""
import datetime as dt
import glob
import json
from pathlib import Path

import pandas as pd

import options_build_cards as obc
import options_trade_log as tlog

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"


def last_spot():
    """Last observed SPX from today's underlying tape (delayed fallback when the
    live feed is offline). Returns (value, 'HH:MM CT') or (None, None)."""
    fs = sorted(glob.glob(str(SIM / "underlying_*.csv")))
    if fs:
        try:
            u = pd.read_csv(fs[-1])
            if len(u):
                return float(u.und.iloc[-1]), str(u.ts_et.iloc[-1])[-8:-3]
        except Exception:
            pass
    return None, None


# (MenthorQ regime/levels code removed 2026-08-04 — premium-selling only, GexLog levels.)


def _today_gameplan():
    import datetime as _dt
    from zoneinfo import ZoneInfo
    d = _dt.datetime.now(ZoneInfo("America/Chicago")).strftime("%Y%m%d")
    p = SIM / f"gameplan_{d}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def levels_regime():
    """GexLog levels + signal for the header panel and the live /state.json endpoint.
    MenthorQ fully removed — premium-selling only. Reads the day's gameplan gexlog block."""
    live = SIM / "live.json"
    spot = spot_ts = None
    if live.exists():
        try:
            d = json.loads(live.read_text())
            if d.get("state") == "live" and d.get("spx"):
                spot, spot_ts = float(d["spx"]), d.get("ts_et", "")[:5] + " live"
        except Exception:
            pass
    if spot is None:
        s, t = last_spot()
        if s is not None:
            spot, spot_ts = s, (t or "") + " delayed"
    gp = _today_gameplan() or {}
    gx = gp.get("gexlog", {}) or {}
    sig = gx.get("signal_bucket", "—")
    reg = gx.get("regime")
    detail = (f"GexLog {sig} · {gx.get('day_type', '—')} day · {reg or '—'} gamma"
              if gx else "no GexLog brief yet")
    return {
        "spot": None if spot is None else round(spot, 1),
        "spot_ts": spot_ts,
        "signal": sig,
        "regime": {"label": sig, "detail": detail,
                   "cls": {"GO": "pos", "CAUTION": "warn", "WAIT": "neg"}.get(sig, "")},
        "gexlog": {
            "putWall": gx.get("putWall"), "callWall": gx.get("callWall"),
            "gex_flip": gx.get("gex_flip"), "day_type": gx.get("day_type"),
            "net_gex": gx.get("net_gex"),
            "em_low": gp.get("em_low"), "em_high": gp.get("em_high"),
        },
        "vix": gp.get("vix"),
    }


def money(v, signed=True):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return (f"{'+' if v >= 0 else '−'}${abs(v):,.0f}") if signed else f"${abs(v):,.0f}"


# --- historical clean-up: hide the desk's known-bad early days from what the app SHOWS -
# 2026-08-04: blank-slate setup day, untracked (user recalls it wasn't right).
# 2026-08-05: dead-feed day (IB feed down till 09:26 -> late/invalid entries + 2 orphaned
#             positions; the orphans live here so this drops them too).
# Aug 6/7 are KEPT (not proven broken; Aug 7 was a +$1,367 winner). This is a FIXED
# PAST-DATE exclusion: it can never hide a current or future trade, and only affects
# DISPLAY — the desk still loads the full book via tlog for its own position logic.
EXCLUDE_DAYS = {"2026-08-04", "2026-08-05"}


def _shown(trades):
    """Display filter: drop excluded error day(s) and de-duplicate live mirrors.
    Past-only, never future. A 'real_paper' row is the live-account leg of a trade
    already in the sim book (same strategy_id + entry day); count it ONCE so
    collateral / P&L / grades never double-book (STMR sim+REAL pair)."""
    if trades is None or not len(trades):
        return trades
    ed = pd.to_datetime(trades.entry_dt, errors="coerce").dt.strftime("%Y-%m-%d")
    t = trades[~ed.isin(EXCLUDE_DAYS)].copy()
    return tlog.dedupe_mirrors(t)


def load_stats():
    trades = _shown(tlog.load())
    closed = trades[trades.exit_dt.notna()] if len(trades) else trades
    p = closed.pnl.astype(float) if len(closed) else pd.Series(dtype=float)
    pf = p[p > 0].sum() / -p[p < 0].sum() if len(p) and (p < 0).any() else None
    marks = pd.read_csv(SIM / "marks.csv") if (SIM / "marks.csv").exists() else pd.DataFrame()
    lastm = marks.groupby("trade_id").last() if len(marks) else pd.DataFrame()
    open_ids = set(trades[trades.exit_dt.isna()].trade_id) if len(trades) else set()
    unreal = float(lastm[lastm.index.isin(open_ids)].unreal_pnl.sum()) if len(lastm) else None
    acct = pd.read_csv(SIM / "account.csv").iloc[-1] if (SIM / "account.csv").exists() else None
    vix = marks.vix.dropna().iloc[-1] if len(marks) and marks.vix.notna().any() else None
    coll = float(trades[trades.exit_dt.isna()].collateral.astype(float).sum()) if len(trades) else 0
    # CLOSE NOW = TODAY only (user spec 2026-09-09): today's realized + current
    # open marks = what the DAY ends at if we flatten everything right now.
    # (Was all-time realized + marks — showed the cumulative account P&L.)
    if len(closed):
        xd = pd.to_datetime(closed.exit_dt, errors="coerce").dt.strftime("%Y-%m-%d")
        p_today = closed.pnl.astype(float)[xd == dt.datetime.now().strftime("%Y-%m-%d")]
    else:
        p_today = pd.Series(dtype=float)
    close_now_val = (float(p_today.sum()) if len(p_today) else 0.0) + (unreal or 0.0)
    # Max-profit zone for the CURRENT open book (reuses maxprofit_zone.compute_zone):
    # inside [highest short put, lowest short call] every short expires OTM -> full
    # credit. Tile shows the zone + whether spot is inside + distance to nearest edge.
    mpz, mpz_cls = "—", ""
    try:
        from maxprofit_zone import compute_zone, live_spot
        open_tr = trades[trades.exit_dt.isna()] if len(trades) else trades
        if len(open_tr):
            z = compute_zone(open_tr)
            lo, hi = z.get("zone_low"), z.get("zone_high")
            spot, _ = live_spot()
            if spot is None and len(lastm) and "und" in lastm.columns:
                spot = float(lastm["und"].dropna().iloc[-1]) if lastm["und"].notna().any() else None
            if lo is not None or hi is not None:
                zone = f"{lo:.0f}–{hi:.0f}" if (lo is not None and hi is not None) else \
                       (f">{lo:.0f}" if lo is not None else f"<{hi:.0f}")
                if spot is not None:
                    inside = (lo is None or spot >= lo) and (hi is None or spot <= hi)
                    edge = min([x for x in (spot - lo if lo is not None else None,
                                            hi - spot if hi is not None else None)
                                if x is not None])
                    mpz = f"{zone} · {'IN +' if inside else 'OUT '}{abs(edge):.0f}pt"
                    mpz_cls = "pos" if inside else "neg"
                else:
                    mpz = zone
    except Exception:
        pass
    return {
        "mpz": mpz, "mpz_cls": mpz_cls,
        "open": int(len(trades) - len(closed)), "closed": int(len(closed)),
        "win": f"{(p > 0).mean() * 100:.0f}%" if len(p) else "—",
        "pf": f"{pf:.2f}" if pf else "—",
        "realized": money(p.sum()) if len(p) else "—",
        "running": money(unreal) if unreal is not None else "—",
        "close_now": money(close_now_val),
        "collateral": money(coll, signed=False),
        "margin": money(float(acct.maint_margin), signed=False) if acct is not None else "—",
        "netliq": money(float(acct.net_liq), signed=False) if acct is not None else "—",
        "vix": f"{vix:.1f}" if vix else "—",
        "unreal_val": unreal,
    }


def _pnl_cls(v):
    if v in (None, "—", ""):
        return ""
    return "neg" if str(v).startswith("−") else "pos"


def _metrics_last():
    """Last live-metrics row per trade (POP/EV/net_mid/net_spread) from trade_metrics.csv."""
    f = ROOT / "data" / "options_sim" / "trade_metrics.csv"
    if not f.exists():
        return None
    try:
        m = pd.read_csv(f)
        return m.groupby("trade_id").last()
    except Exception:
        return None


def _reason_badge(cr):
    if not isinstance(cr, str) or not cr:
        return ""
    col = {"expired": "#8a91a0", "traded_to_close": "#2fbf8f",
           "partial_expiry": "#eda100"}.get(cr, "#8a91a0")
    return (f"<span style='background:{col}22;color:{col};border:1px solid {col}66;"
            f"border-radius:5px;padding:1px 6px;font-size:10px;font-weight:700'>{cr}</span>")


def positions_html(trades, marks_last):
    """Collapsible Open / Closed positions detail behind the KPI tiles."""
    if trades is None or not len(trades):
        return ""
    openp = trades[trades.exit_dt.isna()]
    closedp = trades[trades.exit_dt.notna()]
    met = _metrics_last()

    def mval(tid, col):
        if met is None or tid not in met.index:
            return None
        v = met.at[tid, col]
        return v if pd.notna(v) else None

    def open_rows(df):
        out = ["<tr class='ph'><td>strategy</td><td>structure</td><td>grade</td>"
               "<td class='r'>POP</td><td class='r'>EV</td><td class='r'>bid–ask (close)</td>"
               "<td class='r'>P&amp;L now</td></tr>"]
        for _, r in df.iloc[::-1].iterrows():
            pnl = marks_last.unreal_pnl.get(r.trade_id) if marks_last is not None else None
            gr = r.grade if isinstance(r.grade, str) else "—"
            pop = mval(r.trade_id, "pop"); ev = mval(r.trade_id, "ev")
            nm = mval(r.trade_id, "net_mid"); sp = mval(r.trade_id, "net_spread")
            ba = (f"{nm - sp/2:.2f}–{nm + sp/2:.2f}" if nm is not None and sp is not None else "—")
            reason = _reason_badge(r.close_reason if "close_reason" in df.columns else None)
            out.append(
                f"<tr><td><b>{r.strategy_id}</b> {reason}</td>"
                f"<td class='muted'>{r.structure or ''}</td>"
                f"<td style='color:{_grade_color(gr)};font-weight:800'>{gr}</td>"
                f"<td class='r'>{f'{pop*100:.0f}%' if pop is not None else '—'}</td>"
                f"<td class='r {_pnl_cls(money(ev))}'>{money(ev) if ev is not None else '—'}</td>"
                f"<td class='r muted'>{ba}</td>"
                f"<td class='r {_pnl_cls(money(pnl))}'>{money(pnl)}</td></tr>")
        return "".join(out)

    def closed_rows(df):
        out = ["<tr class='ph'><td>strategy</td><td>structure</td><td>grade</td>"
               "<td>close</td><td class='r'>realized</td></tr>"]
        for _, r in df.iloc[::-1].iterrows():
            pnl = float(r.pnl) if pd.notna(r.pnl) else None
            gr = r.grade if isinstance(r.grade, str) else "—"
            reason = _reason_badge(r.close_reason if "close_reason" in df.columns else None)
            out.append(
                f"<tr><td><b>{r.strategy_id}</b></td>"
                f"<td class='muted'>{r.structure or ''}</td>"
                f"<td style='color:{_grade_color(gr)};font-weight:800'>{gr}</td>"
                f"<td>{reason or '—'}</td>"
                f"<td class='r {_pnl_cls(money(pnl))}'>{money(pnl)}</td></tr>")
        return "".join(out)

    return (f"<details id='ex-positions' class='ex'>"
            f"<summary>Positions detail <span class='cnt'>{len(openp)} open · {len(closedp)} closed</span>"
            f"<span class='sp'>click to expand</span></summary>"
            f"<div class='ex-body'>"
            f"<h4>Open — live P&amp;L · POP · EV (mark-to-market)</h4>"
            f"<table class='ptable'>{open_rows(openp)}</table>"
            f"<h4>Closed — realized</h4>"
            f"<table class='ptable'>{closed_rows(closedp)}</table></div></details>")


def tile_specs(s):
    """Single source of truth for the KPI tiles — used by both the initial
    render and the live /state.json endpoint. Returns (key, label, value, cls)."""
    return [
        ("netliq", "Net Liq", s["netliq"], ""),
        ("realized", "Realized P&L", s["realized"], _pnl_cls(s["realized"])),
        ("running", "Running (open)", s["running"], _pnl_cls(s["running"])),
        ("close_now", "Close now", s["close_now"], _pnl_cls(s["close_now"])),
        ("mpz", "Max-profit zone", s["mpz"], s["mpz_cls"]),
        ("win", "Win rate", s["win"], ""),
        ("pf", "Profit factor", s["pf"], ""),
        ("openclosed", "Open / Closed", f"{s['open']} / {s['closed']}", ""),
        ("collateral", "Collateral at risk", s["collateral"], "warn"),
        ("margin", "IB maint margin", s["margin"], "warn"),
        ("vix", "VIX", s["vix"], ""),
    ]


def stat_tiles(s, only=None, skip=()):
    out = []
    for key, label, val, cls in tile_specs(s):
        if only is not None and key not in only:
            continue
        if key in skip:
            continue
        out.append(f"""<div class="tile">
          <div class="tl">{label}</div>
          <div class="tv {cls}" id="k-{key}">{val}</div></div>""")
    return "".join(out)


def journal_html(jn):
    if not jn:
        return "<p class='muted'>No journal entries.</p>"
    rows = []
    for tid, e in list(jn.items())[::-1]:
        a = e["auto"]; res = a["result"]; life = a.get("lifecycle") or {}
        pnl = res.get("pnl")
        pc = "pos" if (pnl or 0) >= 0 else "neg"
        rows.append(f"""<details id="ex-jn-{tid}" class="ex">
          <summary><b>{a['strategy']}</b>
            <span class="badge {a['state']}">{a['state'].upper()}</span>
            <span class="sp {pc}" style="font-weight:700">{money(pnl) if pnl is not None else '—'}</span></summary>
          <div class="ex-body">
          <div class="jmeta">{a['structure']} · entered {a['entry_dt']} · R {res.get('r_multiple','—')}
            {'· MFE '+money(life['mfe'])+' / MAE '+money(life['mae']) if life else ''}</div>
          <div class="jthesis">{a['plan']['thesis'][:280]}</div></div></details>""")
    return "".join(rows)


def md_to_html(md):
    """Minimal markdown -> HTML (headings, bold, tables, lists, code)."""
    try:
        import markdown
        return markdown.markdown(md, extensions=["tables", "fenced_code"])
    except Exception:
        pass
    out, in_tbl = [], False
    for ln in md.splitlines():
        if ln.startswith("### "):
            out.append(f"<h3>{ln[4:]}</h3>")
        elif ln.startswith("## "):
            out.append(f"<h2>{ln[3:]}</h2>")
        elif ln.startswith("# "):
            out.append(f"<h1>{ln[2:]}</h1>")
        elif ln.strip().startswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            if not in_tbl:
                out.append("<table>"); in_tbl = True
            tag = "th" if all(not c or c[0].isalpha() for c in cells[:1]) and not out[-1].endswith("</tr>") else "td"
            out.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
        else:
            if in_tbl:
                out.append("</table>"); in_tbl = False
            if ln.startswith("- ") or ln.startswith("* "):
                out.append(f"<li>{ln[2:]}</li>")
            elif ln.strip():
                out.append(f"<p>{ln}</p>")
    if in_tbl:
        out.append("</table>")
    import re
    html = "\n".join(out)
    html = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html)
    html = re.sub(r"`(.+?)`", r"<code>\1</code>", html)
    return html


# --- Per-setup grade ladders (curated from docs/living/options_playbook.md §§1-8) ---
# Grade scale: A+ = trigger + regime + level all aligned; A/B = most aligned;
# C = structure test / off-signal; F = broken execution. Each setup below spells
# out what actually earns each grade for THAT structure.
SETUPS = [
    {"name": "STMR Bull Put Spread", "id": "bps_stmr", "tag": "VALIDATED EDGE",
     "tagcls": "pos", "thesis": "Oversold-but-uptrend mean reversion; sell put premium into the bounce.",
     "default": "SPXW ~30Δ put / buy 50pt lower · 14 DTE · exit on SMA5 signal (NO stops/targets/holds).",
     "grades": [
        ("A+", "15:59 %K8<15 AND spot>SMA100 — the only validated edge (PF 4.45, 80% win, 16/17 yrs)."),
        ("F", "Held to expiry / price stops / profit target — the exit shootout proved these negative."),
     ]},
    {"name": "EOD-centered Iron Condor", "id": "eod", "tag": "FORWARD TEST", "tagcls": "warn",
     "thesis": "Sell the expected-move range anchored on the PRIOR CLOSE (GexLog EM band).",
     "default": "Bull put @ prior_close−EM · bear call @ prior_close+EM · 25pt wings · 0DTE · fire 08:35 CT.",
     "grades": [("C", "Unconditional data-collection — every day taken, exit on short-strike acceptance or 14:45.")]},
    {"name": "Open-centered Iron Condor", "id": "open", "tag": "FORWARD TEST", "tagcls": "warn",
     "thesis": "Same ± expected move, centered on the actual OPEN (strikes struck at 08:35).",
     "default": "Bull put @ open−EM · bear call @ open+EM · 25pt wings · 0DTE.",
     "grades": [("C", "A/B vs EOD centering — which anchor contains the session better.")]},
    {"name": "ATM Iron Fly", "id": "fly", "tag": "FORWARD TEST", "tagcls": "warn",
     "thesis": "Short straddle at the money with defined-risk wings — max theta, tightest range.",
     "default": "Short put + short call ATM(open) · 25pt wings · 0DTE.",
     "grades": [("C", "Highest credit, highest gamma — the aggressive premium sell.")]},
    {"name": "GexLog Iron Condor (its walls)", "id": "gexlog", "tag": "FORWARD TEST", "tagcls": "warn",
     "thesis": "Sell at GexLog's own suggested strikes — short put @ Put Wall, short call @ Call Wall.",
     "default": "Bull put @ putWall · bear call @ callWall · 25pt wings · 0DTE.",
     "grades": [("C", "Tests GexLog's gamma walls vs the VIX EM band as the strike source.")]},
]


def setups_html():
    scale = ("<div class='muted' style='margin:0 0 14px'>Grade = how aligned the trade is at "
             "<b>entry</b>: <b class='pos'>A+</b> trigger + regime + level all aligned · "
             "<b>A/B</b> most aligned · <b class='warn'>C</b> structure test / off-signal · "
             "<b class='neg'>F</b> broken execution. Grades are set AT ENTRY, per trade.</div>")
    gc = {"A+": "pos", "A / B": "acc", "C": "warn", "F": "neg"}
    cards = []
    for su in SETUPS:
        rows = "".join(
            f"<tr><td class='gcell {gc.get(g,'')}'>{g}</td><td>{cond}</td></tr>"
            for g, cond in su["grades"])
        cards.append(f"""<details id="ex-setup-{su['id']}" class="ex">
          <summary><b>{su['name']}</b>
            <span class="pill {su['tagcls']}">{su['tag']}</span>
            <span class="sp"><code>{su['id']}</code></span></summary>
          <div class="ex-body">
          <div class="setup-thesis">{su['thesis']}</div>
          <div class="setup-def"><b>Default:</b> {su['default']}</div>
          <table class="gtable">{rows}</table></div></details>""")
    return scale + "".join(cards)


def load_postmortem():
    import datetime as _dt
    from zoneinfo import ZoneInfo
    date = _dt.datetime.now(ZoneInfo("America/Chicago")).strftime("%Y%m%d")
    f = SIM / f"postmortem_{date}.json"
    if not f.exists():
        return None
    try:
        return _scrub_stmr(json.loads(f.read_text(encoding="utf-8")))
    except Exception:
        return None


def postmortem_html(pm):
    if not pm:
        return ("<p class='muted'>No postmortem yet for today. It runs automatically at "
                "15:15 CT (<code>options_postmortem.py</code>) once the day closes.</p>")
    reg = pm.get("regime_preopen", "")
    regcls = "pos" if reg == "positive_gamma" else "neg"
    o = pm.get("ohlc")
    ohlc = (f"<span class='muted'>day &nbsp; O {o['open']:.0f} &nbsp; H {o['high']:.0f} &nbsp; "
            f"L {o['low']:.0f} &nbsp; C {o['close']:.0f}</span>") if o else ""
    head = (f"<div class='gp-head'><span class='rlabel {regcls}'>{reg.replace('_',' ').upper()}</span>"
            f"<span class='muted'>{pm.get('date','')} · preopen {pm.get('spot_preopen','—')}</span>"
            f"<span style='margin-left:auto'>{ohlc}</span></div>")
    # paths
    pchips = "".join(
        f"<div class='path'><div class='path-h'><b>Path {pid}</b></div>"
        f"<div class='muted'>{why}</div></div>"
        for pid, why in pm.get("paths_materialized", []))
    paths = (f"<h2 style='margin:16px 0 8px'>What played out</h2><div class='paths'>{pchips}</div>"
             if pchips else "")
    # outcomes
    rows = ""
    for t in pm.get("triggers", []):
        if t.get("fired") and "pnl" in t:
            pnl = t["pnl"]
            m = money(pnl) if pnl is not None else "open/unsettled"
            oc = t.get("outcome", "")
            rows += (f"<tr><td><span class='stpill pos'>fired</span></td>"
                     f"<td class='gcell'>{t['projected_grade']} → <b>{t.get('final_grade','?')}</b></td>"
                     f"<td><b>{t['name']}</b></td>"
                     f"<td class='r {_pnl_cls(m)}'>{m}</td><td class='muted'>{oc}</td></tr>")
        elif "counterfactual" in t:
            occurred = "DID" in t["counterfactual"]
            rows += (f"<tr><td><span class='stpill {'warn' if occurred else 'mut'}'>"
                     f"{'would-fire' if occurred else 'no-signal'}</span></td>"
                     f"<td class='gcell'>{t['projected_grade']}</td>"
                     f"<td><b>{t['name']}</b></td><td></td>"
                     f"<td class='muted'>{t['counterfactual']}</td></tr>")
        elif "outcome" in t:
            rows += (f"<tr><td><span class='stpill warn'>{t.get('status','')}</span></td>"
                     f"<td class='gcell'>{t['projected_grade']}</td><td><b>{t['name']}</b></td>"
                     f"<td></td><td class='muted'>{t['outcome']}</td></tr>")
        else:
            rows += (f"<tr><td><span class='stpill mut'>{t.get('status','')}</span></td>"
                     f"<td class='gcell'>{t['projected_grade']}</td><td><b>{t['name']}</b></td>"
                     f"<td></td><td></td></tr>")
    nfired = sum(1 for t in pm.get("triggers", []) if t.get("fired"))
    note = ("<p class='muted' style='margin:14px 0 4px'>Plan vs actual. <b>Projected → final</b> grade "
            "and P&amp;L for fired trades; <b>counterfactual</b> (did the condition occur?) for unfired. "
            "This is <b>observe-only</b> — criteria never change here; the weekly review proposes changes "
            "for sign-off.</p>")
    table = (f"<h2 style='margin:18px 0 8px'>Trigger outcomes · {nfired} fired</h2>"
             f"<table class='gptable'><tr><th>Result</th><th>Grade</th><th>Setup</th>"
             f"<th>P&amp;L</th><th>Notes</th></tr>{rows}</table>")
    return head + paths + table + note


def _eod_status_files():
    return sorted((ROOT / "data" / "options_sim").glob("eod_status_*.json"), reverse=True)


def _render_eod(st):
    """Render one EOD desk-report ledger (eod_status_<date>.json) as a checklist."""
    icon = {"ok": "✓", "warn": "✗", "info": "•"}
    col = {"ok": "#1baf7a", "warn": "#e34948", "info": "#8a91a0"}
    rows = "".join(
        f"<tr><td style='color:{col.get(s['status'], '#8a91a0')};font-weight:800;width:24px'>"
        f"{icon.get(s['status'], '•')}</td><td style='font-weight:600'>{s['label']}</td>"
        f"<td class='muted'>{s.get('detail', '')}</td></tr>" for s in st.get("steps", []))
    nb = st.get("n_bad", 0)
    ok = nb == 0
    bcol = "#1baf7a" if ok else "#e34948"
    banner = (f"<span style='display:inline-block;padding:4px 12px;border-radius:999px;"
              f"font-weight:800;font-size:11px;letter-spacing:.05em;background:{bcol}22;"
              f"color:{bcol};border:1px solid {bcol}66'>"
              f"{'✓ DESK RAN CLEAN' if ok else '✗ ATTENTION NEEDED'}</span>")
    sub = (f"<span class='muted' style='margin-left:10px;font-size:12px'>{st.get('generated_ct', '')[:16]} · "
           f"{st.get('n_ok', 0)}/{len(st.get('steps', []))} green · {st.get('fired', 0)} fired</span>")
    return (f"<div style='margin:6px 0 10px'>{banner}{sub}</div>"
            f"<table class='ptable'>{rows}</table>")


def eod_report_html():
    """Today's EOD desk report (checkmarked chain + P&L) for the dashboard tab."""
    fs = _eod_status_files()
    if not fs:
        return ("<p class='muted'>No desk report yet — it runs at <code>15:20 CT</code> "
                "(<code>eod_report.py</code>). It also writes <code>eod_report_&lt;date&gt;.html</code> "
                "+ a desktop toast (+ email if configured).</p>")
    st = json.loads(fs[0].read_text(encoding="utf-8"))
    date = st.get("date")
    # prefer the full standalone report (Daily chain + P&L snapshot + Fired triggers);
    # the eod_status JSON only carries the checklist, so embedding it kept the tab partial.
    full = ROOT / "data" / "options_sim" / f"eod_report_{date}.html"
    if full.exists():
        import re
        m = re.search(r"<body[^>]*>(.*)</body>", full.read_text(encoding="utf-8"), re.S)
        if m:
            return m.group(1)
    return f"<h2 style='margin:4px 0 8px'>Desk Report — {date}</h2>{_render_eod(st)}"


def eod_report_history_html():
    """Prior days' desk reports as expanders (the logged history)."""
    fs = _eod_status_files()[1:]
    if not fs:
        return ""
    exp = "".join(
        f"<details class='ex'><summary>{json.loads(f.read_text(encoding='utf-8')).get('date')}"
        f"<span class='sp'>expand</span></summary><div class='ex-body'>"
        f"{_render_eod(json.loads(f.read_text(encoding='utf-8')))}</div></details>"
        for f in fs[:40])
    return f"<h3 style='margin:20px 0 8px'>History (logged daily)</h3>{exp}"


def analytics_payload(trades, marks_last):
    """One record per trade with every analytic dimension we slice by — consumed
    by the Journal calendar and the Analytics tab (rendered client-side)."""
    import options_tags as tags
    rows = []
    if trades is None or not len(trades):
        return rows
    for _, r in trades.iterrows():
        is_open = pd.isna(r.exit_dt)
        if is_open:
            pnl = marks_last.unreal_pnl.get(r.trade_id) if marks_last is not None else None
        else:
            pnl = float(r.pnl) if pd.notna(r.pnl) else None
        coll = float(r.collateral) if pd.notna(r.collateral) else None
        entry = str(r.entry_dt) if pd.notna(r.entry_dt) else ""
        exitd = str(r.exit_dt) if pd.notna(r.exit_dt) else ""
        try:
            dow = pd.to_datetime(entry).strftime("%a") if entry else ""
        except Exception:
            dow = ""
        # P&L buckets (calendar/equity curve) on the day it was REALIZED = exit date for
        # closed trades. 0DTE enter==exit so only multi-day trades (STMR) move; open trades
        # keep entry (unrealized). dow/hour stay entry-based (strategy-entry analytics).
        bucket_date = exitd[:10] if (not is_open and exitd) else entry[:10]
        rows.append({
            "id": r.trade_id, "strategy": r.strategy_id,
            "date": bucket_date, "entry": entry, "dow": dow,
            "hour": entry[11:13] + ":00" if len(entry) >= 13 else "?",
            "grade": r.grade if isinstance(r.grade, str) else "?",
            "regime": r.gex_regime if isinstance(r.gex_regime, str) else "unknown",
            "bias": tags.bias_of_row(r),
            "source": r.source if isinstance(r.source, str) else "?",
            "dte": int(r.dte) if pd.notna(r.dte) else None,
            "pnl": None if pnl is None else round(float(pnl)),
            "collateral": None if coll is None else round(coll),
            "roi": None if (pnl is None or not coll) else round(float(pnl) / coll * 100, 1),
            "open": bool(is_open),
            "win": None if pnl is None else bool(pnl >= 0),
            "structure": r.structure if isinstance(r.structure, str) else "",
        })
    return rows


def shadow_stop_html():
    """OBSERVATIONAL shadow daily-stop panel (no executions). Reads the log written
    by shadow_stop_monitor.py; shows current-book (auto-era) days only, with what
    each day WOULD have ended at under the -3k stop and a running better/worse tally."""
    import csv as _csv
    f = SIM / "shadow_stop_log.csv"
    if not f.exists():
        return ""
    rows = [r for r in _csv.DictReader(f.open()) if r["date"] >= "2026-08-04"]
    if not rows:
        return ""
    def _i(x):
        try:
            return int(x)
        except (TypeError, ValueError):
            return None
    ccls = lambda v: "pos" if v > 0 else ("neg" if v < 0 else "muted")

    def cell(cond, v, forced=None):
        if not cond or v is None:
            return "<td class='muted'>—</td>"
        return f"<td class='{forced or ('pos' if v >= 0 else 'neg')}'>{money(v)}</td>"
    # per-stop EOD + Δ shown ONLY on days that stop tripped (flatten at the ACTUAL
    # mark). ONE running Δ cum, at the end, advanced ONLY on a trigger day (deeper
    # stop wins if both fire) and shown only on those rows.
    cum = cum2 = cum3 = fires2 = fires3 = 0
    started = False
    for r in sorted(rows, key=lambda r: r["date"]):
        end = _i(r["end_pnl"])
        wf, sf = _i(r["warn_fill"]), _i(r["stop_fill"])
        c2 = r["crossed_warn"] == "True" and wf is not None
        c3 = r["crossed_stop"] == "True" and sf is not None
        r["_c2"], r["_c3"] = c2, c3
        r["_eod2"], r["_d2"] = (wf, wf - end) if c2 else (None, None)
        r["_eod3"], r["_d3"] = (sf, sf - end) if c3 else (None, None)
        cum += (r["_d3"] if c3 else (r["_d2"] if c2 else 0))
        cum2 += (wf - end) if c2 else 0
        cum3 += (sf - end) if c3 else 0
        started = started or c2 or c3
        r["_trg"], r["_cum"], r["_showcum"] = (c2 or c3), cum, started
        fires2 += c2
        fires3 += c3
        r["_badge"] = (f" <span class='midev' title='mid-session Fed event: {r['mid_event']}'>⚑</span>"
                       if r.get("mid_event") else "")
    worst = min((_i(r["trough"]) for r in rows if _i(r["trough"]) is not None), default=0)
    nev = sum(1 for r in rows if r.get("mid_event"))

    def drow(r):
        dd = _i(r["trough"])
        ddcell = (f"<td class='neg'>{money(dd)}</td>" if dd is not None else "<td class='muted'>n/a</td>")
        return (f"<tr><td>{r['date']}{r['_badge']}</td>"
                f"{cell(True, _i(r['end_pnl']))}"
                f"{ddcell}"
                f"{cell(r['_c2'], r['_eod2'])}"
                f"{cell(r['_c2'], r['_d2'], ccls(r['_d2']) if r['_c2'] else None)}"
                f"{cell(r['_c3'], r['_eod3'])}"
                f"{cell(r['_c3'], r['_d3'], ccls(r['_d3']) if r['_c3'] else None)}"
                f"{cell(r['_showcum'], r['_cum'], ccls(r['_cum']))}"
                f"<td class='muted'>{r['vix']}</td></tr>")
    months = {}
    for r in rows:
        months.setdefault(r["date"][:7], []).append(r)
    tbodies = ""
    for mk in sorted(months, reverse=True):
        drows = sorted(months[mk], key=lambda r: r["date"], reverse=True)
        mp = sum(_i(r["end_pnl"]) for r in drows)
        trg = sum(1 for r in drows if r["_trg"])
        mhead = (f"<tr class='mhead' onclick='tglMonth(this)'><td colspan='9'>"
                 f"<span class='cv'></span>{mk} · <b class='{'pos' if mp >= 0 else 'neg'}'>{money(mp)}</b> · "
                 f"{len(drows)} days · {trg} stop-hit</td></tr>")
        tbodies += f"<tbody>{mhead}{''.join(drow(r) for r in drows)}</tbody>"
    head = (f"1-lot. <b>EOD −2k / −3k</b> = what the day would have closed at, flattening at the ACTUAL mark when "
            f"the drawdown trips that line — shown only on days it fired. <b>Δ cum</b> = one running tally, "
            f"advanced only on a trigger day. Over {len(rows)} days: <b>−$2k</b> fired {fires2}× (net "
            f"<b class='{ccls(cum2)}'>{money(cum2)}</b>), <b>−$3k</b> fired {fires3}× (net "
            f"<b class='{ccls(cum3)}'>{money(cum3)}</b>). Worst intraday <b class='neg'>{money(worst)}</b>. "
            f"<span class='midev'>⚑</span> = mid-session Fed event ({nev}, none a rate decision). "
            f"Recording only — nothing is flattened.")
    return (
        "<div class='an-card' style='margin-top:14px'>"
        "<div class='an-h'>Shadow daily stop <span class='muted'>— observational · no orders placed</span></div>"
        f"<div class='muted' style='font-size:12.5px;margin:-2px 0 10px'>{head}</div>"
        "<div style='overflow-x:auto'><table class='antable shadowtbl'>"
        "<thead><tr><th>day</th><th>P&L (actual)</th><th>intraday DD</th><th>EOD −2k stop</th><th>Δ</th>"
        "<th>EOD −3k stop</th><th>Δ</th><th>Δ cum</th><th>vix</th></tr></thead>"
        f"{tbodies}</table></div>"
        "<script>function tglMonth(t){t.parentNode.classList.toggle('col');}</script></div>")


def _is_stmr(t):
    """STMR tile/trigger detector — retired 2026-09-05, hidden from all views."""
    if not isinstance(t, dict):
        return False
    return (str(t.get("setup", "")).startswith("bps_stmr")
            or t.get("stream") == "stmr"
            or "bps_stmr" in str(t.get("id", ""))
            or "STMR" in str(t.get("name", "")))


def _scrub_stmr(gp):
    """Drop STMR entries from a loaded gameplan/postmortem dict (non-destructive:
    historical JSON files are left intact; STMR is only hidden at render)."""
    if not isinstance(gp, dict):
        return gp
    for k in ("triggers", "tiles"):
        if isinstance(gp.get(k), list):
            gp[k] = [t for t in gp[k] if not _is_stmr(t)]
    return gp


def load_gameplan():
    import datetime as _dt
    from zoneinfo import ZoneInfo
    date = _dt.datetime.now(ZoneInfo("America/Chicago")).strftime("%Y%m%d")
    f = SIM / f"gameplan_{date}.json"
    if not f.exists():
        return None
    try:
        return _scrub_stmr(json.loads(f.read_text(encoding="utf-8")))
    except Exception:
        return None


def _fire_str(f):
    ty = f.get("type")
    if ty == "touch":
        return f"touch {f['level']} {f['dir'].replace('from_','')}"
    if ty == "first_of":
        return f"tag {f['touch']['level']} or {f['not_before']}"
    if ty == "time_at":
        return f"at {f['not_before']}"
    if ty == "regime_break":
        return f"break {f['dir']} {f['level']}"
    if ty == "signal_1559":
        return "15:59 signal"
    return ty or "—"


def _grade_color(g):
    c = (str(g) or "?")[0]
    return {"A": "var(--pos)", "B": "var(--acc)", "C": "var(--warn)",
            "D": "var(--orange)", "F": "var(--neg)"}.get(c, "var(--mut)")


def _struct_txt(st):
    k = st.get("kind")
    if k == "vertical":
        s, l = st.get("short"), st.get("long")
        both = isinstance(s, (int, float)) and isinstance(l, (int, float))
        return f"{st.get('right','')} {s:.0f}/{l:.0f}" if both else f"{st.get('right','')} {s} w{st.get('width','')}"
    if k == "vertical_dynamic":
        off = st.get("offset", 0)
        where = "ATM" if off == 0 else f"open{off:+.0f}"
        return f"{st.get('right','')} {where} · w{st.get('width','')} (struck at open)"
    if k == "butterfly":
        return f"C {st['lower']:.0f}/{st['center']:.0f}/{st['upper']:.0f}"
    if k == "straddle":
        return "ATM C+P"
    return k or ""


def _idea_tile(t, foot, gc=None):
    gr = (t.get("fill") or {}).get("grade") or t.get("projected_grade")
    color = gc or _grade_color(gr)
    return f"""<div class="itile" style="--gc:{color}">
      <div class="itile-h"><div class="itile-name">{t['name']}</div>
        <span class="ichip" style="background:{color}">{gr}</span></div>
      <div class="itile-sub">{_struct_txt(t['structure'])} · path {t.get('path','—')} ·
        fires <b>{_fire_str(t['fire'])}</b></div>
      <div class="itile-why">{t.get('grade_basis','')}</div>
      <div class="itile-foot">{foot}</div></div>"""


def _group_tile(ts, foot):
    """One tile for a structure — both legs of a condor/fly shown together."""
    t0 = ts[0]
    gr = t0.get("projected_grade")
    color = _grade_color(gr)
    legs = "".join(
        f"<div class='itile-sub'>{_struct_txt(t['structure'])} "
        f"<span class='muted'>· {t.get('stream', '')}</span></div>" for t in ts)
    return f"""<div class="itile" style="--gc:{color}">
      <div class="itile-h"><div class="itile-name">{t0.get('group', t0['name'])}</div>
        <span class="ichip" style="background:{color}">{gr}</span></div>
      {legs}
      <div class="itile-sub">fires <b>{_fire_str(t0['fire'])}</b></div>
      <div class="itile-foot">{foot}</div></div>"""


def _bucket(title, tiles, bid, is_open=True):
    body = "".join(tiles) if tiles else "<div class='muted' style='padding:6px 2px'>—</div>"
    return (f"<details id='ex-{bid}' class='ex ex-sec'{' open' if is_open else ''}>"
            f"<summary>{title} <span class='cnt'>{len(tiles)}</span></summary>"
            f"<div class='iboard'>{body}</div></details>")


CENTER_OF = {
    "eodic_p": "EOD", "eodic_c": "EOD", "eodfly_p": "EOD", "eodfly_c": "EOD",
    "openic_p": "Open", "openic_c": "Open", "openfly_p": "Open", "openfly_c": "Open",
    "gx_bps": "GexLog", "gx_bcs": "GexLog", "bps_stmr": "STMR",
}
STRUCT_OF = {
    "eodic_p": "Iron Condor", "eodic_c": "Iron Condor",
    "eodfly_p": "Iron Fly", "eodfly_c": "Iron Fly",
    "openic_p": "Iron Condor", "openic_c": "Iron Condor",
    "openfly_p": "Iron Fly", "openfly_c": "Iron Fly",
    "gx_bps": "GexLog Condor", "gx_bcs": "GexLog Condor", "bps_stmr": "STMR",
}


def bands_svg(gp, live_spot=None):
    """EOD vs Open bands graphic: EOD spot level, open level, both strategy bands,
    and where price is now — plus PoP (Normal, sigma = 1-day EM) per structure."""
    import math
    RES, SUP, PIV, SPOT = "#e05561", "#4cc38a", "#e0a04d", "#5b9dd9"
    eod = (gp.get("gexlog") or {}).get("current")
    move = gp.get("em_halfwidth")
    if not (eod and move):
        return ""
    op = gp.get("open_spot")
    cur = live_spot or op or eod
    e_lo, e_hi = eod - move, eod + move
    o_lo, o_hi = (op - move, op + move) if op else (None, None)
    xs = [e_lo, e_hi, cur, eod] + ([o_lo, o_hi, op] if op else [])
    lo, hi = min(xs) - move * 0.25, max(xs) + move * 0.25
    W, H = 860, 148
    X = lambda p: 30 + (p - lo) / (hi - lo) * (W - 60)

    def N(z):  # standard normal CDF
        return 0.5 * (1 + math.erf(z / math.sqrt(2)))

    def pop_band(b_lo, b_hi):
        return (N((b_hi - cur) / move) - N((b_lo - cur) / move)) * 100

    rows = []
    # EOD band row (y=44) and Open band row (y=84)
    rows.append(f"<rect x='{X(e_lo):.0f}' y='36' width='{X(e_hi)-X(e_lo):.0f}' height='16' rx='3' fill='{SUP}22' stroke='#2a3245'/>")
    rows.append(f"<text x='24' y='48' fill='#8a94a6' font-size='11'>EOD band</text>")
    if op:
        rows.append(f"<rect x='{X(o_lo):.0f}' y='76' width='{X(o_hi)-X(o_lo):.0f}' height='16' rx='3' fill='{PIV}22' stroke='#2a3245'/>")
        rows.append(f"<text x='24' y='88' fill='#8a94a6' font-size='11'>Open band</text>")
    else:
        rows.append(f"<text x='24' y='88' fill='#5a6478' font-size='11'>Open band — waits for the 08:30 bell</text>")
    # levels
    for p, c, lab, y0, y1 in [
        (eod, SPOT, f"EOD {eod:.0f}", 24, 118),
        (op, "#e8ecf4", (f"OPEN {op:.0f}" if op else None), 24, 118) if op else (None,)*5,
        (e_lo, SUP, f"{e_lo:.0f}", 30, 56), (e_hi, RES, f"{e_hi:.0f}", 30, 56),
    ]:
        if p is None:
            continue
        rows.append(f"<line x1='{X(p):.0f}' y1='{y0}' x2='{X(p):.0f}' y2='{y1}' stroke='{c}' stroke-width='1.6' stroke-dasharray='4 3'/>")
        if lab:
            rows.append(f"<text x='{X(p):.0f}' y='{y0-6}' fill='{c}' font-size='11' text-anchor='middle'>{lab}</text>")
    if op:
        for p, c in [(o_lo, SUP), (o_hi, RES)]:
            rows.append(f"<line x1='{X(p):.0f}' y1='70' x2='{X(p):.0f}' y2='96' stroke='{c}' stroke-width='1.6'/>")
            rows.append(f"<text x='{X(p):.0f}' y='108' fill='{c}' font-size='10' text-anchor='middle'>{p:.0f}</text>")
    # current price marker — id'd so the 5s poll moves it LIVE from lr.spot
    rows.append(f"<line id='bm-line' x1='{X(cur):.0f}' y1='20' x2='{X(cur):.0f}' y2='122' stroke='#fff' stroke-width='2'/>")
    rows.append(f"<text id='bm-text' x='{X(cur):.0f}' y='136' fill='#fff' font-size='12' font-weight='700' text-anchor='middle'>▲ {cur:.0f}</text>")
    # PoP legend
    pops = [f"EOD condor PoP <b style='color:{SUP}'>{pop_band(e_lo, e_hi):.0f}%</b>"]
    if op:
        pops.append(f"Open condor PoP <b style='color:{PIV}'>{pop_band(o_lo, o_hi):.0f}%</b>")
    pw, cw = (gp.get("gexlog") or {}).get("putWall"), (gp.get("gexlog") or {}).get("callWall")
    if pw and cw:
        pops.append(f"GexLog condor PoP <b style='color:{RES}'>{pop_band(pw, cw):.0f}%</b>")
    legend = " · ".join(pops) + " <span class='muted'>(Normal, σ = 1-day EM, from current price)</span>"
    return (f"<div style='background:#10141f;border:1px solid #232a3a;border-radius:8px;"
            f"padding:10px 8px 4px;margin:8px 0'>"
            f"<svg id='bands-svg' data-lo='{lo:.2f}' data-hi='{hi:.2f}' data-w='{W}' "
            f"viewBox='0 0 {W} {H}' style='width:100%;height:auto'>{''.join(rows)}</svg>"
            f"<div style='padding:2px 10px 8px;font-size:12.5px'>{legend}</div></div>")


def today_credit_line(trades):
    """Headline: today's credit collected, realized, open unrealized, buy-back cost."""
    import datetime as _dt
    from zoneinfo import ZoneInfo as _ZI
    today = _dt.datetime.now(_ZI("America/Chicago")).strftime("%Y-%m-%d")
    td = trades[trades.entry_dt.astype(str).str.startswith(today)].copy()
    if not len(td):
        return "<div id='today-banner'></div>"   # keep the id so the 5s poll can fill it later
    td["credit"] = pd.to_numeric(td.credit, errors="coerce").fillna(0)
    credit = float(td.credit.clip(lower=0).sum()) * 100          # premium sold today
    closed = td[td.exit_dt.notna()]
    realized = float(pd.to_numeric(closed.pnl, errors="coerce").sum()) if len(closed) else 0.0
    open_ = td[td.exit_dt.isna()]
    open_credit = float(open_.credit.clip(lower=0).sum()) * 100
    # unrealized from marks
    unreal = None
    mf = SIM / "marks.csv"
    if mf.exists() and len(open_):
        try:
            mk = pd.read_csv(mf).groupby("trade_id").last()
            vals = [mk.unreal_pnl.get(t) for t in open_.trade_id]
            vals = [v for v in vals if v is not None and v == v]
            unreal = float(sum(vals)) if vals else None
        except Exception:
            unreal = None
    buyback = (open_credit - unreal) if unreal is not None else None
    def m(v, signed=True):
        return money(v, signed)
    parts = [f"credit collected <b style='color:#5b9dd9'>{m(credit, False)}</b>",
             f"realized <b class='{'pos' if realized >= 0 else 'neg'}'>{m(realized)}</b>",
             f"open {len(open_)} (sold for {m(open_credit, False)})"]
    if unreal is not None:
        parts.append(f"open P&L <b class='{'pos' if unreal >= 0 else 'neg'}'>{m(unreal)}</b>")
        parts.append(f"buy-back cost now <b style='color:#e0a04d'>{m(buyback, False)}</b>")
        day = realized + unreal
        parts.append(f"→ day if closed now <b class='{'pos' if day >= 0 else 'neg'}' "
                     f"style='font-size:15px'>{m(day)}</b>")
    return ("<div id='today-banner' style='background:#131826;border:1px solid #2a3245;border-radius:8px;"
            "padding:8px 12px;margin:6px 0;font-size:13px'>📊 <b>TODAY</b> · "
            + " · ".join(parts) + "</div>")


def pnl_summary_html(trades):
    """Running-P&L summary table for the main page — split by center (EOD vs Open)
    and structure. Realized (closed) P&L; open counts shown separately."""
    if trades is None or len(trades) == 0:
        return ("<div class='pnlsum'><b>Running P&L</b>"
                "<p class='muted'>No trades yet — this fills as the day trades.</p></div>")
    df = trades.copy()
    df["center"] = df.strategy_id.map(lambda s: CENTER_OF.get(str(s)))
    df["struct"] = df.strategy_id.map(lambda s: STRUCT_OF.get(str(s)))
    df = df[df.center.notna()]
    df["pnl"] = pd.to_numeric(df.pnl, errors="coerce")
    df["closed"] = df.exit_dt.notna()

    def block(sub):
        cl = sub[sub.closed]
        real = cl.pnl.sum()
        n = len(cl); nopen = int((~sub.closed).sum())
        win = (cl.pnl > 0).mean() * 100 if n else float("nan")
        cls = "pos" if real >= 0 else "neg"
        wins = f"{win:.0f}%" if n else "—"
        return (f"<td>{n}</td><td>{nopen}</td><td>{wins}</td>"
                f"<td class='{cls}'>{money(real)}</td>")

    hdr = "<tr><th>bucket</th><th>closed</th><th>open</th><th>win%</th><th>realized</th></tr>"
    # by CENTER (the headline the user wants)
    center_rows = ""
    for c in ("EOD", "Open", "GexLog", "STMR"):
        sub = df[df.center == c]
        if len(sub):
            center_rows += f"<tr><td><b>{c}</b></td>{block(sub)}</tr>"
    total = f"<tr class='tot'><td><b>TOTAL</b></td>{block(df)}</tr>"
    # by CENTER × STRUCTURE
    combo_rows = ""
    for c in ("EOD", "Open", "GexLog", "STMR"):
        for s in ("Iron Condor", "Iron Fly", "GexLog Condor", "STMR"):
            sub = df[(df.center == c) & (df.struct == s)]
            if len(sub):
                combo_rows += f"<tr><td class='muted'>{c} · {s}</td>{block(sub)}</tr>"
    return today_credit_line(df) + f"""<div class="pnlsum">
      <b>Running P&L — by center (EOD vs Open)</b>
      <table class="sumtab">{hdr}{center_rows}{total}</table>
      <b style="display:block;margin-top:10px">By structure</b>
      <table class="sumtab">{hdr}{combo_rows}</table>
    </div>"""


def gameplan_html(gp, trades=None, marks_last=None):
    if not gp:
        return ("<p class='muted'>No gameplan generated yet. Run "
                "<code>scripts/options_gameplan.py</code> (auto ~8:25 CT).</p>")
    gx = gp.get("gexlog", {}) or {}
    sig = gx.get("signal_bucket", "—")
    sigcls = {"GO": "pos", "CAUTION": "warn", "WAIT": "neg"}.get(sig, "muted")
    v = gp.get("vix")
    vixtxt = f"{v:.2f}" if isinstance(v, (int, float)) else "—"
    head = (f"<div class='gp-head'><span class='rlabel {sigcls}'>{sig}</span>"
            f"<span class='muted'>{gp.get('date','')} · preopen {gp.get('spot_preopen','—')} "
            f"({gp.get('spot_source','')}) · VIX {vixtxt}</span>")
    if gp.get("live_spot"):
        head += f"<span class='muted' style='margin-left:auto'>live {gp['live_spot']} @ {gp.get('live_ts','')}</span>"
    head += "</div>"

    # CONSISTENT level colors everywhere: resistance red / support green / flip amber
    RES, SUP, PIV = "#e05561", "#4cc38a", "#e0a04d"
    def _gxt(label, val, color=None, border=None):
        vs = f"color:{color}" if color else ""
        bd = border or "#232a3a"
        return (f"<div style='display:inline-block;padding:5px 11px;margin:3px 4px 3px 0;"
                f"background:#161b28;border:1px solid {bd};border-radius:6px;min-width:64px'>"
                f"<div style='font-size:10px;color:#8a94a6;text-transform:uppercase;letter-spacing:.3px'>{label}</div>"
                f"<div style='font-weight:600;font-size:14px;{vs}'>{val}</div></div>")
    if gx:
        reg = gx.get("regime") or "—"
        regc = SUP if reg == "POSITIVE" else (RES if reg == "NEGATIVE" else None)
        dt_ = gx.get("day_type") or "—"
        dtc = {"RANGE": SUP, "CHOP": PIV, "TREND": RES}.get(dt_)
        em_band = (f"<span style='color:{SUP}'>{gp.get('em_low', '—')}</span>"
                   f"<span style='color:#8a94a6'> – </span>"
                   f"<span style='color:{RES}'>{gp.get('em_high', '—')}</span>")
        SPOTC = "#5b9dd9"
        op = gp.get("open_spot")
        head += ("<div style='margin:8px 0 4px'>"
                 + _gxt("EOD Spot", gx.get("current") or "—", SPOTC, border=SPOTC)
                 + _gxt("Open Spot", (f"{op:.2f}" if op else "at 08:30…"),
                        "#e8ecf4" if op else "#5a6478",
                        border="#e8ecf4" if op else None)
                 + _gxt("GexLog Regime", reg, regc)
                 + _gxt("GEX Flip", gx.get("gex_flip") or "—", PIV)
                 + _gxt("Put Wall", gx.get("putWall") or "—", SUP)
                 + _gxt("Call Wall", gx.get("callWall") or "—", RES)
                 + _gxt("EM Band", em_band)
                 + _gxt("Day Type", dt_, dtc, border=dtc)
                 + "</div>")
        # brief context row: risk / confidence / streak / today's catalysts
        cat = gx.get("catalysts_today") or []
        hi_n = gx.get("high_impact_today") or 0
        catc = RES if hi_n else (PIV if cat else SUP)
        cat_txt = " · ".join(f"{c.get('time','')} {c.get('title','')}"
                             + (f" [{c.get('impact','')}]" if c.get('impact') == 'high' else "")
                             for c in cat[:5]) or "none listed"
        ctx = []
        if gx.get("risk_level"):
            ctx.append(f"risk <b>{gx['risk_level']}</b>")
        if gx.get("confidence") is not None:
            ctx.append(f"confidence <b>{gx['confidence']}%</b>")
        if gx.get("streak_label"):
            ctx.append(f"<b>{gx['streak_label']}</b>")
        if gx.get("flip_proximity") is not None:
            fp = gx["flip_proximity"]
            ctx.append(f"flip {fp:.0f}pt away" + (" <b style='color:#e0a04d'>(borderline)</b>"
                                                  if gx.get("borderline_regime") else ""))
        if gx.get("gap_note"):
            gpc = gx.get("gap_pct") or 0
            ctx.append(f"gap <b style='color:{SUP if gpc >= 0 else RES}'>{gx['gap_note']}</b>")
        if gx.get("es_premarket") and gx.get("current"):
            imp = gx["es_premarket"] - gx["current"]
            ctx.append(f"ES premkt {gx['es_premarket']:.0f} (implied {imp:+.0f}pt)")
        if gx.get("calendar_note"):
            ctx.append(f"calendar <b>{gx['calendar_note']}</b>")
        if gx.get("stale_risk"):
            ctx.append("<b style='color:#e0a04d'>⚠ their data caveat: quote-derived close</b>")
        if gx.get("corr_putWall") and gx.get("putWall") and (
                gx["corr_putWall"] != gx["putWall"] or gx.get("corr_callWall") != gx.get("callWall")):
            ctx.append(f"<b style='color:#e05561'>corrected walls {gx['corr_putWall']:.0f}/"
                       f"{gx.get('corr_callWall') or 0:.0f} ≠ published</b>")
        head += (f"<div class='muted' style='margin:2px 0 6px;font-size:12.5px'>"
                 + " · ".join(ctx)
                 + f"<br><span style='color:{catc}'>catalysts today ({len(cat)}"
                 + (f", {hi_n} HIGH" if hi_n else "") + "):</span> " + cat_txt + "</div>")
        # brief hyperlinks: today's live brief + the history/archive site
        head += ("<div style='margin:0 0 6px;font-size:12.5px'>"
                 "<a href='https://gexlog.com/dashboard/' target='_blank' style='color:#5b9dd9'>"
                 "Morning/Evening brief (gexlog.com) ↗</a> &nbsp;·&nbsp; "
                 "<a href='https://gexlog.com/dashboard/history/' target='_blank' "
                 "style='color:#5b9dd9'>Brief archive / past days ↗</a></div>")
        # live spot for the bands graphic (same live.json the ticker uses)
        _ls = None
        try:
            _d = json.loads((SIM / "live.json").read_text())
            if _d.get("spx"):
                _ls = float(_d["spx"])
        except Exception:
            pass
        head += bands_svg(gp, _ls)
    paths = ""
    for p in gp.get("scenarios", []):
        paths += (f"<div class='path'><div class='path-h'><b>{p['id']}. {p['name']}</b>"
                  f"<code>{p['path']}</code></div>"
                  f"<div class='muted'>{p['means']} → <span style='color:var(--ink)'>{p['acts']}</span></div></div>")
    paths = f"<div class='paths'>{paths}</div>" if paths else ""

    # sort each trigger into a lifecycle bucket. Armed ideas are GROUPED by
    # structure (both legs of a condor/fly in one tile); fired trades stay per-leg.
    from collections import OrderedDict
    ideas, opens, closed, never = [], [], [], []
    armed_groups = OrderedDict()
    for t in gp.get("triggers", []):
        st = t.get("status", "armed")
        tid = t.get("trade_id")
        fill = t.get("fill") or {}
        if t["fire"]["type"] == "signal_1559" or st == "armed":
            armed_groups.setdefault(t.get("group", t["id"]), []).append(t)
            continue
        if st == "fired" and tid is not None and trades is not None:
            tr = trades[trades.trade_id == tid]
            if len(tr):
                r = tr.iloc[0]
                is_open = pd.isna(r.exit_dt)
                if is_open:
                    un = marks_last.unreal_pnl.get(tid) if marks_last is not None else None
                    foot = (f"<span class='{_pnl_cls(money(un))}'>running {money(un)}</span>"
                            if un is not None else "<span class='muted'>open</span>")
                    foot += f" <span class='muted'>· grade {fill.get('grade','?')} · filled {fill.get('at','')}</span>"
                    opens.append(_idea_tile(t, foot))
                else:
                    pnl = float(r.pnl) if pd.notna(r.pnl) else None
                    foot = (f"<span class='{_pnl_cls(money(pnl))}'>{money(pnl)}</span> "
                            f"<span class='muted'>· grade {fill.get('grade','?')} · "
                            f"{'WIN' if (pnl or 0) >= 0 else 'LOSS'}</span>")
                    closed.append(_idea_tile(t, foot))
            else:
                opens.append(_idea_tile(t, "<span class='muted'>fired — trade record pending</span>"))
        elif st == "skipped_broken":
            never.append(_idea_tile(t, f"<span class='warn'>⊘ skipped: {t.get('skip_reason','broken fill')}</span>",
                                    gc="var(--warn)"))
        elif st == "expired":
            never.append(_idea_tile(t, "<span class='muted'>✕ window passed — never triggered</span>",
                                    gc="var(--mut)"))
        elif st == "error":
            never.append(_idea_tile(t, f"<span class='neg'>! error: {t.get('error','')}</span>", gc="var(--neg)"))
        else:
            ideas.append(_idea_tile(t, f"<span class='muted'>{st}</span>"))

    # render grouped armed ideas — one tile per structure, both legs together
    for g, ts in armed_groups.items():
        foot = ("<span class='wait'>◷ 15:59 signal — run by the BPS daemon</span>"
                if ts[0]["fire"]["type"] == "signal_1559"
                else "<span class='wait'>◷ armed — waiting for trigger</span>")
        ideas.append(_group_tile(ts, foot))

    note = ("<p class='muted' style='margin:14px 0 10px'>Premium-selling only. Every idea flows "
            "<b>Idea → Open → Closed</b>, or lands in <b>Never triggered</b>. Committed premarket, "
            "auto-executed by the trigger daemon at the open (1 lot). Two streams: <b>algo</b> (EM band) "
            "vs <b>gexlog</b> (its walls); iron condor = the two 1σ legs, iron fly = the ATM legs. "
            "Saved per day (<code>gameplan_*.json</code>).</p>")
    board = (_bucket("💡 IDEAS · waiting to trigger", ideas, "ideas", True)
             + _bucket("🟢 OPEN · triggered, live", opens, "opens", True)
             + _bucket("⚪ CLOSED · settled", closed, "closed", len(closed) > 0)
             + _bucket("✕ NEVER TRIGGERED", never, "never", False))
    paths_ex = (f"<details id='ex-paths' class='ex ex-sec' open><summary>Price paths "
                f"<span class='cnt'>{len(gp.get('scenarios', []))}</span></summary>"
                f"{paths}</details>") if paths else ""
    return head + pnl_summary_html(trades) + note + paths_ex + board


def levels_panel(lr):
    """GexLog levels + signal strip (MenthorQ fully removed)."""
    r = lr["regime"]
    spot = lr["spot"]
    spot_txt = f"{spot:,.1f}" if spot is not None else "—"
    g = lr.get("gexlog", {}) or {}

    def tile(label, key, cls):
        v = g.get(key)
        return (f"<div class='lv {cls}'><b>{label}</b><span>{v:,.0f}</span></div>"
                if v is not None else "")
    row = (tile("CALL WALL", "callWall", "res")
           + tile("EM HIGH", "em_high", "res")
           + f"<div class='lv spot'><b>SPOT</b><span id='lv-spot'>{spot_txt}</span></div>"
           + tile("GEX FLIP", "gex_flip", "piv")
           + tile("EM LOW", "em_low", "sup")
           + tile("PUT WALL", "putWall", "sup"))
    foot = ""
    if g.get("net_gex") is not None:
        ng = g["net_gex"] / 1e9
        foot += (f"<span class='gex' style='color:{'#4cc38a' if ng >= 0 else '#e05561'}'>"
                 f"net GEX {ng:+.1f}B</span> ")
    if g.get("day_type"):
        dtc = {"RANGE": "#4cc38a", "CHOP": "#e0a04d", "TREND": "#e05561"}.get(g["day_type"], "#8a94a6")
        foot += (f"<span class='d1' style='color:{dtc};border:1px solid {dtc};border-radius:4px;"
                 f"padding:1px 7px'>{g['day_type']} day forecast</span> ")
    return f"""<div class="lvpanel">
      <div class="lvhead">
        <span class="rlabel {r['cls']}" id="lv-regime">{r['label']}</span>
        <span class="muted" id="lv-regdetail">{r['detail']}</span>
        <span class="muted" style="margin-left:auto" id="lv-spotts">{lr['spot_ts'] or ''}</span>
      </div>
      <div class="lvrow">{row}</div>
      <div class="lvfoot">{foot}<span class="muted">GexLog SPX · today</span></div>
    </div>"""


def results_html():
    f = SIM / "sim_ledger.csv"
    if not f.exists():
        return "<p class='muted'>No sim results yet.</p>"
    df = pd.read_csv(f)
    cols = ["market", "level", "n", "win_pct", "pf", "expectancy", "total",
            "maxdd", "cells_pos", "oos_exp", "verdict"]
    cols = [c for c in cols if c in df.columns]
    rows = "".join("<tr>" + "".join(
        f"<td>{r[c]}</td>" for c in cols) + "</tr>" for _, r in df.iterrows())
    head = "".join(f"<th>{c}</th>" for c in cols)
    note = ("<p class='muted'>Level-fade sim results (VIRGIN_FIRST_TOUCH, real fills). "
            "Thin: 1yr data, small n. Not validated.</p>")
    return note + f"<table><tr>{head}</tr>{rows}</table>"


def levels_html():
    """MenthorQ levels DB removed — premium-selling only. GexLog levels live in the
    header strip + the gameplan board."""
    return ("<p class='muted'>MenthorQ removed. GexLog levels (Put/Call Wall, GEX Flip, "
            "EM band) are in the header strip and on each gameplan tile.</p>")


def _history_dates(prefix):
    import datetime as _dt
    import glob
    from zoneinfo import ZoneInfo
    today = _dt.datetime.now(ZoneInfo("America/Chicago")).strftime("%Y%m%d")
    ds = []
    for f in glob.glob(str(SIM / f"{prefix}_*.json")):
        d = Path(f).stem.split("_")[-1]
        if len(d) == 8 and d.isdigit():
            ds.append(d)
    return sorted(set(ds), reverse=True), today


def gameplan_history_html():
    dates, today = _history_dates("gameplan")
    past = [d for d in dates if d != today]
    if not past:
        return ("<h2 style='margin:24px 0 8px'>History</h2><p class='muted'>No prior gameplans "
                "logged yet — they accumulate one per trading day.</p>")
    out = [f"<h2 style='margin:24px 0 8px'>History — {len(past)} logged gameplan(s)</h2>"]
    for d in past:
        try:
            gp = _scrub_stmr(json.loads((SIM / f"gameplan_{d}.json").read_text(encoding="utf-8")))
        except Exception:
            continue
        trigs = gp.get("triggers", [])
        fired = [t for t in trigs if t.get("fired")]
        reg = (gp.get("regime") or "").replace("_", " ")
        ds = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        lv = gp.get("levels") or {}
        lv_txt = " · ".join(f"{k.upper()} {v:.0f}" for k, v in lv.items() if v is not None)
        scen = "".join(
            f"<div style='margin:3px 0'><b style='color:var(--acc)'>{p['id']}. {p['name']}</b> "
            f"<code>{p.get('path','')}</code> <span class='muted'>→ {p['acts']}</span></div>"
            for p in gp.get("scenarios", []))
        scen_block = (f"<div style='margin:2px 0 12px'><div class='muted' style='font-size:11px;"
                      f"text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px'>Premarket price paths</div>"
                      f"{scen}</div>") if scen else ""
        rows = "".join(
            f"<tr><td><b>{t['name']}</b></td><td class='muted'>{t.get('status', '')}</td>"
            f"<td style='color:{_grade_color((t.get('fill') or {}).get('grade') or t.get('projected_grade'))};"
            f"font-weight:800'>{(t.get('fill') or {}).get('grade') or t.get('projected_grade')}</td></tr>"
            for t in trigs)
        out.append(
            f"<details id='ex-gph-{d}' class='ex'><summary>{ds} · <span class='muted'>{reg}</span> · "
            f"{len(trigs)} triggers · <b>{len(fired)} fired</b></summary>"
            f"<div class='ex-body'><div class='muted' style='font-size:11.5px;margin-bottom:8px'>{lv_txt}</div>"
            f"{scen_block}<table class='antable'><tr><th>Setup</th><th>Status</th>"
            f"<th>Grade</th></tr>{rows}</table></div></details>")
    return "".join(out)


def postmortem_history_html():
    dates, today = _history_dates("postmortem")
    past = [d for d in dates if d != today]
    if not past:
        return ("<h2 style='margin:24px 0 8px'>History</h2><p class='muted'>No prior postmortems "
                "logged yet.</p>")
    out = [f"<h2 style='margin:24px 0 8px'>History — {len(past)} logged postmortem(s)</h2>"]
    for d in past:
        try:
            pm = _scrub_stmr(json.loads((SIM / f"postmortem_{d}.json").read_text(encoding="utf-8")))
        except Exception:
            continue
        o = pm.get("ohlc") or {}
        ds = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        ohlc = (f"O {o['open']:.0f} H {o['high']:.0f} L {o['low']:.0f} C {o['close']:.0f}"
                if o else "no tape")
        paths = ", ".join(str(p[0]) for p in pm.get("paths_materialized", []))
        nfired = sum(1 for t in pm.get("triggers", []) if t.get("fired"))
        rows = ""
        for t in pm.get("triggers", []):
            res = ("fired" if t.get("fired") else t.get("status", ""))
            extra = t.get("counterfactual") or t.get("outcome") or ""
            pnl = t.get("pnl")
            pcell = money(pnl) if pnl is not None else ""
            rows += (f"<tr><td><b>{t['name']}</b></td><td class='muted'>{res}</td>"
                     f"<td class='{_pnl_cls(pcell)}' style='text-align:right'>{pcell}</td>"
                     f"<td class='muted'>{extra}</td></tr>")
        out.append(
            f"<details id='ex-pmh-{d}' class='ex'><summary>{ds} · <span class='muted'>{ohlc}</span> · "
            f"path {paths} · <b>{nfired} fired</b></summary>"
            f"<div class='ex-body'><table class='antable'><tr><th>Setup</th><th>Result</th>"
            f"<th>P&amp;L</th><th>Notes</th></tr>{rows}</table></div></details>")
    return "".join(out)


ANALYTICS_CSS = r"""
.an-charts{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
@media(max-width:820px){.an-charts{grid-template-columns:1fr}}
.an-card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:13px;padding:14px 16px}
.an-h{font-size:13px;font-weight:700;margin-bottom:10px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.an-h select{background:var(--chip);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:4px 8px;font-size:13px;font-weight:600}
.bar{display:flex;align-items:center;gap:8px;margin:5px 0;font-size:12.5px}
.bar .lab{width:118px;text-align:right;flex:none}
.bar .track{flex:1;height:16px;background:var(--chip);border-radius:5px;position:relative;overflow:hidden}
.bar .fill{position:absolute;top:0;bottom:0;border-radius:5px}
.leg{display:flex;gap:16px;margin-top:8px;font-size:11px;color:var(--mut);flex-wrap:wrap}
.leg span{display:flex;align-items:center;gap:5px}
.leg i{width:14px;height:3px;border-radius:2px;display:inline-block}
.modal{position:fixed;inset:0;background:rgba(0,0,0,.62);display:none;align-items:center;justify-content:center;z-index:1000;padding:24px}
.modal.on{display:flex}
.modal-c{background:var(--panel);border:1px solid var(--line);border-radius:14px;max-width:960px;width:100%;max-height:86vh;display:flex;flex-direction:column;box-shadow:0 24px 70px rgba(0,0,0,.55)}
.modal-h{padding:14px 18px;border-bottom:1px solid var(--line);font-weight:800;font-size:16px;display:flex;justify-content:space-between;align-items:center}
.modal-x{background:none;border:none;color:var(--mut);font-size:26px;line-height:1;cursor:pointer}
.modal-body{padding:14px 18px;overflow:auto}
.mbig{margin-bottom:14px}
.mday{border-bottom:1px solid var(--line);padding:7px 0}
.mday summary{display:flex;gap:12px;align-items:center;cursor:pointer;font-weight:700;list-style:none}
.mday summary::-webkit-details-marker{display:none}
.mmon{border-bottom:1px solid var(--line);padding:4px 0 6px}
.mmon>summary{display:flex;gap:12px;align-items:center;cursor:pointer;font-weight:800;font-size:14px;list-style:none;padding:4px 0}
.mmon>summary::-webkit-details-marker{display:none}
.mmon>summary .md-d::before{content:"▸ ";color:var(--mut)}
.mmon[open]>summary .md-d::before{content:"▾ "}
.mmon .mday{margin-left:16px}
.mday .md-d{flex:1}.mday .md-p{width:90px;text-align:right;font-variant-numeric:tabular-nums}
.mday .md-c{width:120px;text-align:right;font-weight:400}
.mrow{display:flex;justify-content:space-between;padding:3px 0 3px 16px;font-size:12.5px;color:var(--mut)}
.chartwrap{position:relative}
.xh-tip{position:absolute;top:4px;pointer-events:none;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:5px 9px;font-size:11.5px;line-height:1.5;font-weight:700;opacity:0;transition:opacity .08s;white-space:nowrap;z-index:5}
.mbars{max-width:660px}
.midev{color:var(--warn);cursor:help;font-size:12px}
.shadowtbl .mhead{cursor:pointer}
.shadowtbl .mhead td{background:var(--panel2);font-weight:700;padding:9px 12px;border-top:1px solid var(--line)}
.shadowtbl .mhead .cv::before{content:"▾ ";color:var(--mut)}
.shadowtbl tbody.col .mhead .cv::before{content:"▸ "}
.shadowtbl tbody.col tr:not(.mhead){display:none}
.mbtns{display:flex;gap:8px;margin:2px 0 12px}
.mbtns button{background:var(--chip);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:5px 10px;font-size:12px;font-weight:600;cursor:pointer}
.bar .val{width:74px;font-variant-numeric:tabular-nums;font-weight:700;text-align:right}
.antable{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:8px}
.antable th{color:var(--mut);text-align:right;font-size:10.5px;text-transform:uppercase;letter-spacing:.04em;padding:5px 8px;border-bottom:1px solid var(--line)}
.antable th:first-child,.antable td:first-child{text-align:left}
.antable td{text-align:right;padding:6px 8px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
.cal-top{display:flex;align-items:center;gap:12px;margin-bottom:12px;font-size:15px}
.cal-top button{background:var(--chip);color:var(--ink);border:1px solid var(--line);border-radius:8px;width:32px;height:32px;font-size:16px;cursor:pointer}
#cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:6px}
.cal-dow{color:var(--mut);font-size:11px;text-align:center;padding:4px;font-weight:600}
.cal-cell{background:var(--panel);border:1px solid var(--line);border-radius:9px;min-height:66px;padding:6px 8px;font-size:12px;position:relative}
.cal-cell.empty{background:transparent;border:0}
.cal-cell.has{cursor:pointer} .cal-cell.has:hover{border-color:var(--acc)}
.cal-cell .d{color:var(--mut);font-size:11px}
.cal-cell .p{font-weight:800;font-size:14px;margin-top:6px}
.cal-cell .n{color:var(--mut);font-size:10px;position:absolute;bottom:5px;right:8px}
.cal-cell.pos{background:rgba(47,191,143,.12);border-color:rgba(47,191,143,.35)}
.cal-cell.neg{background:rgba(240,85,95,.12);border-color:rgba(240,85,95,.35)}
#cal-day{margin-top:16px}
"""

ANALYTICS_JS = r"""
(function(){
  const T = window.__T || [];
  const $ = s=>document.querySelector(s);
  const money=v=>v==null?'—':(v<0?'−':'+')+'$'+Math.abs(Math.round(v)).toLocaleString();
  const pctf=v=>v==null?'—':(v>=0?'+':'')+v.toFixed(1)+'%';
  const gcol=g=>({A:'var(--pos)',B:'var(--acc)',C:'var(--warn)',D:'var(--orange)',F:'var(--neg)'}[(g||'?')[0]]||'var(--mut)');
  const closed=T.filter(t=>t.pnl!=null);
  function statAll(rows){
    const p=rows.filter(t=>t.pnl!=null).map(t=>t.pnl);
    const w=p.filter(x=>x>=0),l=p.filter(x=>x<0),tot=p.reduce((a,b)=>a+b,0);
    const pf=l.length?w.reduce((a,b)=>a+b,0)/-l.reduce((a,b)=>a+b,0):null;
    const rois=rows.filter(t=>t.roi!=null).map(t=>t.roi);
    const avgroi=rois.length?rois.reduce((a,b)=>a+b,0)/rois.length:null;
    let eq=0,peak=0,dd=0;[...rows].filter(t=>t.pnl!=null).sort((a,b)=>(a.entry||'').localeCompare(b.entry||''))
      .forEach(t=>{eq+=t.pnl;peak=Math.max(peak,eq);dd=Math.min(dd,eq-peak);});
    return {n:p.length,tot,win:p.length?w.length/p.length*100:null,pf,exp:p.length?tot/p.length:null,avgroi,dd};
  }
  function tile(l,v,c){return '<div class="tile"><div class="tl">'+l+'</div><div class="tv '+(c||'')+'">'+v+'</div></div>';}
  function renderTiles(){const s=statAll(T),el=$('#an-tiles');if(!el)return;
    const D=(window.__DAILY||{}).days||[];const dd=D.length?Math.min.apply(0,D.map(x=>x.dd)):s.dd;
    const last=D.length?D[D.length-1]:null;
    el.innerHTML=tile('Total P&L',money(s.tot),s.tot>=0?'pos':'neg')+tile('Trades',s.n,'')+
      tile('Win rate',s.win==null?'—':s.win.toFixed(0)+'%','')+tile('Profit factor',s.pf==null?'—':s.pf.toFixed(2),'')+
      tile('Expectancy',money(s.exp),(s.exp||0)>=0?'pos':'neg')+tile('Avg ROI',pctf(s.avgroi),(s.avgroi||0)>=0?'pos':'neg')+
      tile('Max drawdown',money(dd),'neg')+
      (last?tile('Peak collateral',money(last.maxColl),''):'')+
      (last?tile('Ideal acct size',money(last.ideal),''):'');}
  // ---- DAILY engine: aggregate trades into per-day results, then derive the
  // equity / drawdown / collateral / ideal-account curves. P&L is bucketed on
  // t.date (exit date for closed, entry for still-open) to match the calendar.
  // DD is END-OF-DAY (close-to-close on realized daily results), not intraday. ----
  const IDEAL_BUFFER=0.25;   // safety cushion on ideal account size (25%)
  function buildDaily(){
    const rows=T.filter(t=>t.pnl!=null);
    const byDay={};
    rows.forEach(t=>{const d=(t.date||(t.entry||'').slice(0,10));if(!d)return;
      (byDay[d]=byDay[d]||{d:d,pnl:0,trades:[]});byDay[d].pnl+=t.pnl;byDay[d].trades.push(t);});
    const days=Object.values(byDay).sort((a,b)=>a.d.localeCompare(b.d));
    const lastDay=days.length?days[days.length-1].d:null;
    let cum=0,peak=0;
    days.forEach(x=>{cum+=x.pnl;x.cum=cum;peak=Math.max(peak,cum);x.dd=cum-peak;});
    // collateral tied up each day = sum over trades active [entryDay..exitDay]
    const collBy={};days.forEach(x=>collBy[x.d]=0);
    rows.forEach(t=>{const c=t.collateral||0;if(!c)return;
      const e=(t.entry||'').slice(0,10)||t.date;const x=t.open?lastDay:(t.date||e);
      days.forEach(day=>{if(day.d>=e&&day.d<=x)collBy[day.d]+=c;});});
    let mc=0,mdd=0;
    days.forEach(x=>{x.coll=collBy[x.d]||0;mc=Math.max(mc,x.coll);x.maxColl=mc;
      mdd=Math.max(mdd,-x.dd);x.base=mc+mdd;x.ideal=(mc+mdd)*(1+IDEAL_BUFFER);});
    return {days:days};
  }
  const monLbl=d=>{try{return new Date(d+'T00:00:00').toLocaleDateString('en',{month:'short',year:'2-digit'});}catch(e){return d.slice(0,7);}};
  // interactive multi-series line chart into `el`. series:[{name,color,get,area?}].
  // Draws month gridlines/labels on x-axis + a hover crosshair with per-series totals.
  function drawChart(el,rows,series,opts){opts=opts||{};if(!el)return;
    const W=1000,H=opts.H||330,ml=70,mb=30,mt=12,mr=16,n=rows.length;
    let vals=[];series.forEach(s=>rows.forEach(r=>{const v=s.get(r);if(v!=null)vals.push(v);}));
    vals.push(0);let ymin=Math.min.apply(0,vals),ymax=Math.max.apply(0,vals);
    const pad=(ymax-ymin)*.12||100,lo=ymin-pad,hi=ymax+pad;
    const X=i=>ml+(n<2?(W-ml-mr)/2:i/(n-1)*(W-ml-mr));
    const Y=v=>mt+(1-(v-lo)/((hi-lo)||1))*(H-mt-mb),zero=Y(0);
    let g='';let pm='';
    rows.forEach((r,i)=>{const m=(r.d||'').slice(0,7);if(m&&m!==pm){pm=m;
      if(i>0)g+='<line x1="'+X(i).toFixed(1)+'" y1="'+mt+'" x2="'+X(i).toFixed(1)+'" y2="'+(H-mb)+'" stroke="var(--line)" stroke-dasharray="3 4" opacity="0.55"/>';
      g+='<text x="'+X(i).toFixed(1)+'" y="'+(H-8)+'" fill="var(--mut)" font-size="20" text-anchor="middle">'+monLbl(r.d)+'</text>';}});
    g+='<line x1="'+ml+'" y1="'+zero+'" x2="'+(W-mr)+'" y2="'+zero+'" stroke="var(--line)"/>';
    g+='<text x="8" y="'+(Y(hi)+16)+'" fill="var(--mut)" font-size="20">'+money(hi)+'</text>';
    g+='<text x="8" y="'+(zero+6)+'" fill="var(--mut)" font-size="20">$0</text>';
    g+='<text x="8" y="'+Y(lo)+'" fill="var(--mut)" font-size="20">'+money(lo)+'</text>';
    series.forEach(s=>{const pts=rows.map((r,i)=>{const v=s.get(r);return v==null?null:X(i).toFixed(1)+','+Y(v).toFixed(1);}).filter(Boolean);
      if(!pts.length)return;
      if(s.area)g+='<polygon points="'+X(0).toFixed(1)+','+zero+' '+pts.join(' ')+' '+X(n-1).toFixed(1)+','+zero+'" fill="'+s.color+'" opacity="0.16"/>';
      g+='<polyline points="'+pts.join(' ')+'" fill="none" stroke="'+s.color+'" stroke-width="2.5"/>';});
    g+='<line class="xh" x1="0" y1="'+mt+'" x2="0" y2="'+(H-mb)+'" stroke="var(--ink)" stroke-width="1.2" opacity="0"/>';
    const svg='<svg viewBox="0 0 '+W+' '+H+'" style="width:100%;height:auto;display:block;overflow:visible">'+g+'</svg>';
    el.innerHTML='<div class="chartwrap">'+svg+'<div class="xh-tip"></div></div>';
    const wrap=el.querySelector('.chartwrap'),svgEl=wrap.querySelector('svg'),line=wrap.querySelector('.xh'),tip=wrap.querySelector('.xh-tip');
    wrap.onmousemove=function(e){const rect=svgEl.getBoundingClientRect();const frac=(e.clientX-rect.left)/rect.width;
      let i=Math.round((frac*W-ml)/(((W-ml-mr)/((n-1)||1))));i=Math.max(0,Math.min(n-1,i));const r=rows[i];
      line.setAttribute('x1',X(i));line.setAttribute('x2',X(i));line.setAttribute('opacity','0.55');
      tip.innerHTML='<b>'+r.d+'</b><br>'+series.map(s=>'<span style="color:'+s.color+'">'+(s.name?s.name+' ':'')+money(s.get(r))+'</span>').join('<br>')+(opts.tipExtra?'<br>'+opts.tipExtra(r):'');
      tip.style.opacity='1';const px=(X(i)/W)*rect.width;tip.style.left=Math.max(4,Math.min(rect.width-130,px+10))+'px';};
    wrap.onmouseleave=function(){line.setAttribute('opacity','0');tip.style.opacity='0';};}
  function eqSeries(){return[{name:'cum',color:'var(--acc)',get:r=>r.cum}];}
  function ddSeries(){return[{name:'drawdown',color:'var(--neg)',area:true,get:r=>r.dd}];}
  function capSeries(){return[{name:'daily',color:'var(--mut)',get:r=>r.coll},{name:'max',color:'var(--warn)',get:r=>r.maxColl},{name:'ideal',color:'var(--acc)',get:r=>r.ideal}];}
  function renderEquity(){const el=$('#an-equity');if(!el)return;const D=(window.__DAILY||{}).days||[];
    if(!D.length){el.innerHTML='<div class="muted">no closed trades yet</div>';return;}
    if($('#an-eqsub'))$('#an-eqsub').textContent='cum '+money(D[D.length-1].cum)+' · '+D.length+' days';
    drawChart(el,D,eqSeries(),{tipExtra:r=>'<span class="'+(r.pnl>=0?'pos':'neg')+'">day '+money(r.pnl)+'</span>'});el.style.cursor='zoom-in';el.onclick=()=>openChartModal('equity');}
  function renderDD(){const el=$('#an-dd');if(!el)return;const D=(window.__DAILY||{}).days||[];
    if(!D.length){el.innerHTML='<div class="muted">—</div>';return;}
    if($('#an-ddsub'))$('#an-ddsub').textContent='max '+money(Math.min.apply(0,D.map(x=>x.dd)))+' · EOD';
    drawChart(el,D,ddSeries(),{});el.style.cursor='zoom-in';el.onclick=()=>openChartModal('dd');}
  function renderCapital(){const el=$('#an-capital');if(!el)return;const D=(window.__DAILY||{}).days||[];
    if(!D.length){el.innerHTML='<div class="muted">—</div>';return;}const last=D[D.length-1];
    if($('#an-capsub'))$('#an-capsub').innerHTML='peak collateral '+money(last.maxColl)+' · ideal '+money(last.ideal)+' (incl '+Math.round(IDEAL_BUFFER*100)+'% buffer)';
    drawChart(el,D,capSeries(),{});
    el.insertAdjacentHTML('beforeend','<div class="leg"><span><i style="background:var(--mut)"></i>daily collateral</span><span><i style="background:var(--warn)"></i>max collateral used</span><span><i style="background:var(--acc)"></i>ideal account size (+'+Math.round(IDEAL_BUFFER*100)+'%)</span></div>');
    el.style.cursor='zoom-in';el.onclick=()=>openChartModal('capital');}
  function monthlyBarsHTML(){const D=(window.__DAILY||{}).days||[];const m={};
    D.forEach(x=>{const k=x.d.slice(0,7);m[k]=(m[k]||0)+x.pnl;});
    const keys=Object.keys(m).sort();if(!keys.length)return'<div class="muted">—</div>';
    const mx=Math.max.apply(0,[1].concat(keys.map(k=>Math.abs(m[k]))));
    return keys.map(k=>{const v=m[k],w=Math.abs(v)/mx*100;
      return '<div class="bar"><span class="lab">'+k+'</span>'+
        '<span class="track"><span class="fill" style="width:'+w+'%;background:'+(v>=0?'var(--pos)':'var(--neg)')+';'+(v>=0?'left:50%':'right:50%')+'"></span></span>'+
        '<span class="val '+(v>=0?'pos':'neg')+'">'+money(v)+'</span></div>';}).join('');}
  function renderMonthly(){const el=$('#an-monthly');if(!el)return;el.innerHTML=monthlyBarsHTML();
    el.style.cursor='zoom-in';el.onclick=()=>openChartModal('monthly');}
  // ---- pop-out modal (lightbox): large, centered, scrollable ----
  function showModal(title,html){const m=$('#an-modal');if(!m)return;
    m.querySelector('.modal-h').innerHTML='<span>'+title+'</span><button class="modal-x" aria-label="close">×</button>';
    m.querySelector('.modal-body').innerHTML=html;m.classList.add('on');
    m.querySelector('.modal-x').onclick=closeModal;}
  function closeModal(){const m=$('#an-modal');if(m)m.classList.remove('on');}
  function dayDetailHTML(x){
    const tr=x.trades.slice().sort((a,b)=>(b.pnl||0)-(a.pnl||0)).map(t=>
      '<div class="mrow"><span>'+(t.strategy||'?')+' <span class="muted">'+(t.grade||'')+(t.structure?' · '+t.structure:'')+'</span></span>'+
      '<span class="'+((t.pnl||0)>=0?'pos':'neg')+'">'+money(t.pnl)+'</span></div>').join('');
    return '<details class="mday"><summary><span class="md-d">'+x.d+' <span class="muted">'+x.trades.length+' trd</span></span>'+
      '<span class="md-p '+(x.pnl>=0?'pos':'neg')+'">'+money(x.pnl)+'</span>'+
      '<span class="muted md-c">coll $'+Math.round(x.coll||0).toLocaleString()+'</span>'+
      '<span class="muted md-c">cum '+money(x.cum)+'</span></summary>'+tr+'</details>';}
  // rows grouped under collapsible MONTH sections, so collapsing a month hides all its days
  function dailyRowsHTML(){const D=(window.__DAILY||{}).days||[];
    const byM={};D.forEach(x=>{(byM[x.d.slice(0,7)]=byM[x.d.slice(0,7)]||[]).push(x);});
    return Object.keys(byM).sort().reverse().map(mk=>{
      const dys=byM[mk].slice().sort((a,b)=>b.d.localeCompare(a.d));
      const mtot=dys.reduce((a,b)=>a+b.pnl,0);
      return '<details class="mmon" open><summary><span class="md-d">'+mk+' <span class="muted">'+dys.length+' days</span></span>'+
        '<span class="md-p '+(mtot>=0?'pos':'neg')+'">'+money(mtot)+'</span></summary>'+
        dys.map(dayDetailHTML).join('')+'</details>';}).join('');}
  function openChartModal(kind){const D=(window.__DAILY||{}).days||[];
    const TITLES={equity:'Daily results — equity detail',dd:'Drawdown (EOD)',capital:'Capital — collateral vs ideal account',monthly:'Monthly P&L',grade:'Grade calibration'};
    if(kind==='monthly'){showModal(TITLES.monthly,'<div class="mbars">'+monthlyBarsHTML()+'</div>');return;}
    if(kind==='grade'){showModal(TITLES.grade,'<div class="mbars">'+($('#an-grade')?$('#an-grade').innerHTML:'')+'</div>');return;}
    if(!D.length){showModal(TITLES[kind]||'Chart','<div class="muted">no data</div>');return;}
    const leg=kind==='capital'?'<div class="leg"><span><i style="background:var(--mut)"></i>daily collateral</span><span><i style="background:var(--warn)"></i>max collateral used</span><span><i style="background:var(--acc)"></i>ideal account size (+'+Math.round(IDEAL_BUFFER*100)+'%)</span></div>':'';
    const extra=kind==='equity'?('<div class="mbtns"><button id="mexp">Expand all</button><button id="mcol">Collapse all</button></div>'+dailyRowsHTML()):'';
    showModal(TITLES[kind]||'Chart','<div class="mbig" id="mchart"></div>'+leg+extra);
    const series=kind==='equity'?eqSeries():kind==='dd'?ddSeries():capSeries();
    drawChart($('#mchart'),D,series,{H:420,tipExtra:kind==='equity'?r=>'<span class="'+(r.pnl>=0?'pos':'neg')+'">day '+money(r.pnl)+'</span>':null});
    const mm=$('#an-modal');
    if(kind==='equity'&&mm){const ex=mm.querySelector('#mexp'),co=mm.querySelector('#mcol');
      if(ex)ex.onclick=()=>mm.querySelectorAll('.mmon,.mday').forEach(d=>d.open=true);
      if(co)co.onclick=()=>mm.querySelectorAll('.mmon,.mday').forEach(d=>d.open=false);}}
  function grp(rows,key){const m={};rows.forEach(t=>{let k=t[key];if(k===true)k='win';if(k===false)k='loss';if(k==null||k==='')k='?';(m[k]=m[k]||[]).push(t);});return m;}
  function bstat(rows){const p=rows.filter(t=>t.pnl!=null).map(t=>t.pnl),w=p.filter(x=>x>=0),l=p.filter(x=>x<0);
    const rois=rows.filter(t=>t.roi!=null).map(t=>t.roi);
    const cols=rows.filter(t=>t.collateral!=null).map(t=>t.collateral);
    return {n:p.length,tot:p.reduce((a,b)=>a+b,0),win:p.length?w.length/p.length*100:null,
      avg:p.length?p.reduce((a,b)=>a+b,0)/p.length:null,pf:l.length?w.reduce((a,b)=>a+b,0)/-l.reduce((a,b)=>a+b,0):null,
      roi:rois.length?rois.reduce((a,b)=>a+b,0)/rois.length:null,
      coll:cols.length?cols.reduce((a,b)=>a+b,0)/cols.length:null};}
  const GO=['A+','A','B+','B','B-','C+','C','C-','D','F','n/a','?'];
  function renderGrade(){const el=$('#an-grade');if(!el)return;const g=grp(closed,'grade');
    // Show real letter grades A→F, then ungraded 'n/a' (STMR) pinned at the BOTTOM.
    // Drop only '?' and unknown labels so a stray tag can't sort to the top.
    const keys=Object.keys(g).filter(k=>GO.indexOf(k)>=0&&k!=='?').sort((a,b)=>GO.indexOf(a)-GO.indexOf(b));
    const mx=Math.max.apply(0,[1].concat(keys.map(k=>Math.abs(bstat(g[k]).avg||0))));
    el.innerHTML=keys.map(k=>{const s=bstat(g[k]),a=s.avg||0,w=Math.abs(a)/mx*100;
      return '<div class="bar"><span class="lab" style="color:'+gcol(k)+';font-weight:800">'+k+' <span style="color:var(--mut);font-weight:400">n'+s.n+'</span></span>'+
        '<span class="track"><span class="fill" style="width:'+w+'%;background:'+(a>=0?'var(--pos)':'var(--neg)')+';'+(a>=0?'left:50%':'right:50%')+'"></span></span>'+
        '<span class="val '+(a>=0?'pos':'neg')+'">'+money(a)+'</span></div>';}).join('')+
      '<div class="muted" style="font-size:11px;margin-top:6px">avg P&L per trade by grade · should slope A→F if the grading works</div>';}
  function renderPivot(){const el=$('#an-pivot'),dim=$('#an-dim').value;if(!el)return;
    const g=grp(closed,dim),keys=Object.keys(g).sort((a,b)=>bstat(g[b]).tot-bstat(g[a]).tot);
    const rows=keys.map(k=>{const s=bstat(g[k]);return '<tr><td><b>'+k+'</b></td><td>'+s.n+'</td>'+
      '<td>'+(s.win==null?'—':s.win.toFixed(0)+'%')+'</td><td class="'+(s.tot>=0?'pos':'neg')+'">'+money(s.tot)+'</td>'+
      '<td class="'+((s.avg||0)>=0?'pos':'neg')+'">'+money(s.avg)+'</td>'+
      '<td>'+(s.coll==null?'—':'$'+Math.round(s.coll).toLocaleString())+'</td>'+
      '<td>'+(s.pf==null?'—':s.pf.toFixed(2))+'</td>'+
      '<td class="'+((s.roi||0)>=0?'pos':'neg')+'">'+pctf(s.roi)+'</td></tr>';}).join('');
    el.innerHTML='<table class="antable"><tr><th>'+dim+'</th><th>n</th><th>win</th><th>total</th><th>avg</th><th>avg collat</th><th>PF</th><th>ROI</th></tr>'+rows+'</table>';
    if($('#an-note'))$('#an-note').textContent=closed.length<20?'· only '+closed.length+' closed — small sample, read as noise':'';}
  const byDay={};T.forEach(t=>{if(!t.date)return;(byDay[t.date]=byDay[t.date]||{pnl:0,n:0,rows:[]});
    byDay[t.date].n++;if(t.pnl!=null)byDay[t.date].pnl+=t.pnl;byDay[t.date].rows.push(t);});
  const allDates=Object.keys(byDay).sort();
  let calM=allDates.length?new Date(allDates[allDates.length-1]+'T12:00:00'):new Date();
  function renderCal(){const grid=$('#cal-grid');if(!grid)return;const y=calM.getFullYear(),m=calM.getMonth();
    $('#cal-title').textContent=calM.toLocaleString('en',{month:'long',year:'numeric'});
    const start=new Date(y,m,1).getDay(),days=new Date(y,m+1,0).getDate();let mtot=0;
    let html=['Sun','Mon','Tue','Wed','Thu','Fri','Sat'].map(d=>'<div class="cal-dow">'+d+'</div>').join('');
    for(let i=0;i<start;i++)html+='<div class="cal-cell empty"></div>';
    for(let d=1;d<=days;d++){const ds=y+'-'+String(m+1).padStart(2,'0')+'-'+String(d).padStart(2,'0'),e=byDay[ds];
      if(e){mtot+=e.pnl;const cls=e.pnl>=0?'pos':'neg';
        html+='<div class="cal-cell has '+cls+'" data-d="'+ds+'"><div class="d">'+d+'</div><div class="p '+cls+'">'+money(e.pnl)+'</div><div class="n">'+e.n+' trd</div></div>';}
      else html+='<div class="cal-cell"><div class="d">'+d+'</div></div>';}
    grid.innerHTML=html;
    $('#cal-month-tot').innerHTML='month <b class="'+(mtot>=0?'pos':'neg')+'">'+money(mtot)+'</b>';
    grid.querySelectorAll('.cal-cell.has').forEach(c=>c.onclick=()=>showDay(c.dataset.d));}
  function showDay(ds){const e=byDay[ds],el=$('#cal-day');if(!e){el.innerHTML='';return;}
    const tiles=e.rows.map(t=>{const c=gcol(t.grade);
      return '<div class="itile" style="--gc:'+c+'"><div class="itile-h"><div class="itile-name">'+t.strategy+'</div>'+
        '<span class="ichip" style="background:'+c+'">'+t.grade+'</span></div>'+
        '<div class="itile-sub">'+t.structure+' · '+String(t.regime).replace('_gamma','')+' · '+t.bias+(t.dte!=null?' · '+t.dte+'DTE':'')+'</div>'+
        '<div class="itile-foot"><span class="'+((t.pnl||0)>=0?'pos':'neg')+'">'+money(t.pnl)+'</span>'+
        (t.roi!=null?' <span class="muted" style="font-weight:400">· ROI '+pctf(t.roi)+'</span>':'')+
        (t.open?' <span class="muted" style="font-weight:400">· open</span>':'')+'</div></div>';}).join('');
    el.innerHTML='<div class="an-h" style="margin:16px 2px 10px;font-size:15px">'+ds+
      ' — <span class="'+(e.pnl>=0?'pos':'neg')+'">'+money(e.pnl)+'</span> · '+e.n+' trades</div>'+
      '<div class="iboard">'+tiles+'</div>';}
  function initAn(){window.__DAILY=buildDaily();
    renderTiles();renderEquity();renderGrade();renderMonthly();renderDD();renderCapital();renderPivot();renderCal();
    const gc=$('#an-grade');if(gc){gc.style.cursor='zoom-in';gc.onclick=()=>openChartModal('grade');}
    const md=$('#an-modal');if(md)md.onclick=e=>{if(e.target===md)closeModal();};
    document.addEventListener('keydown',e=>{if(e.key==='Escape')closeModal();});
    const dim=$('#an-dim');if(dim)dim.onchange=renderPivot;
    const pv=$('#cal-prev'),nx=$('#cal-next');
    if(pv)pv.onclick=()=>{calM.setMonth(calM.getMonth()-1);renderCal();$('#cal-day').innerHTML='';};
    if(nx)nx.onclick=()=>{calM.setMonth(calM.getMonth()+1);renderCal();$('#cal-day').innerHTML='';};}
  if(document.readyState!=='loading')initAn();else document.addEventListener('DOMContentLoaded',initAn);
})();
"""


def main():
    s = load_stats()
    obc.main()  # refresh cards.html
    cards_inner = (SIM / "cards.html").read_text(encoding="utf-8")
    # extract just the grids + overlay + script from cards.html body
    import re
    body = re.search(r"<body>(.*)</body>", cards_inner, re.S)
    card_body = body.group(1) if body else ""
    card_style = re.search(r"<style>(.*?)</style>", cards_inner, re.S)
    card_css = card_style.group(1) if card_style else ""
    # strip GLOBAL rules that would fight the dashboard shell (root vars, body,
    # light-mode media query that was turning tiles/cards white):
    card_css = re.sub(r"@media\s*\(prefers-color-scheme:\s*light\)\s*\{[^{}]*\{[^{}]*\}[^{}]*\}", "", card_css)
    card_css = re.sub(r"@media\s*\(prefers-color-scheme:\s*light\)\s*\{(?:[^{}]|\{[^{}]*\})*\}", "", card_css)
    card_css = re.sub(r"(^|\n)\s*:root\s*\{[^}]*\}", "\n", card_css)
    card_css = re.sub(r"(^|\n)\s*body\s*\{[^}]*\}", "\n", card_css)

    lr = levels_regime()
    gp = load_gameplan()
    pm = load_postmortem()
    gp_trades = _shown(tlog.load())
    gp_marks = None
    # IB-vs-TD comparison — reuse the standalone td_vs_ib_dashboard.render() so the
    # comparison logic stays the single source of truth (the A-chat's shadow book).
    try:
        import td_vs_ib_dashboard as _tvib
        from zoneinfo import ZoneInfo as _ZI
        _ibtd_iso = dt.datetime.now(_ZI("America/Chicago")).strftime("%Y-%m-%d")
        ibtd_html = _tvib.render(_ibtd_iso)
    except Exception as _e:
        ibtd_html = f"<p class='muted'>IB vs TD comparison unavailable: {_e}</p>"
    an_json = "[]"
    _mf = SIM / "marks.csv"
    if _mf.exists():
        _mk = pd.read_csv(_mf)
        if len(_mk):
            gp_marks = _mk.groupby("trade_id").last()
    try:
        an_json = json.dumps(analytics_payload(gp_trades, gp_marks))
    except Exception:
        an_json = "[]"
    jf = ROOT / "data" / "options_log" / "journal.json"
    jn = json.loads(jf.read_text(encoding="utf-8")) if jf.exists() else {}
    pbf = ROOT / "docs" / "living" / "options_playbook.md"
    playbook_html = md_to_html(pbf.read_text(encoding="utf-8")) if pbf.exists() else "<p>No playbook.</p>"
    live = SIM / "live.json"
    live_state = "offline"
    if live.exists():
        try:
            live_state = json.loads(live.read_text()).get("state", "offline")
        except Exception:
            pass

    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>💹</text></svg>"><title>Options — Forward Sim</title>
<style>
:root{{--bg:#0b0d12;--panel:#12151c;--panel2:#171b23;--line:#232833;--ink:#e8ebf0;
--mut:#7d8697;--acc:#5b9bff;--pos:#2fbf8f;--neg:#f0555f;--warn:#e6a84b;--chip:#1c212b;
/* semantic colors the embedded flip-cards need (their own :root is stripped) */
--card:#171b23;--card2:#1b202b;--good:#2fbf8f;--crit:#f0555f;--blue:#5b9bff;
--orange:#eb6834;--vio:#9085e9}}
*{{box-sizing:border-box}}
body{{margin:0;background:radial-gradient(1200px 600px at 70% -10%,#151b28 0,var(--bg) 60%);
color:var(--ink);font:14px/1.5 -apple-system,Segoe UI,Inter,system-ui,sans-serif;
-webkit-font-smoothing:antialiased;padding:26px 30px 60px}}
.wrap{{max-width:1180px;margin:0 auto}}
.top{{display:flex;align-items:center;gap:14px;margin-bottom:4px}}
h1{{font-size:21px;font-weight:700;letter-spacing:-.01em;margin:0}}
.dot{{width:8px;height:8px;border-radius:50%;background:{'var(--pos)' if live_state=='live' else 'var(--mut)'}}}
.sub{{color:var(--mut);font-size:12.5px;margin:2px 0 20px}}
.sub code{{background:var(--chip);padding:1px 6px;border-radius:5px;color:var(--ink)}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:10px;margin-bottom:22px}}
.tile{{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);
border-radius:13px;padding:13px 15px}}
.tl{{color:var(--mut);font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase}}
.tv{{font-size:21px;font-weight:750;margin-top:5px;letter-spacing:-.02em}}
.pos{{color:var(--pos)}}.neg{{color:var(--neg)}}.muted{{color:var(--mut)}}
.ticker{{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0 20px}}
.tk{{background:var(--chip);border:1px solid var(--line);border-radius:8px;
padding:6px 11px;font-variant-numeric:tabular-nums;font-size:13px}}
.tk b{{color:var(--mut);font-weight:600;font-size:11px;letter-spacing:.03em;
text-transform:uppercase;margin-right:6px}}
.tk .v{{font-weight:700}}
.dot.pulse{{box-shadow:0 0 0 0 var(--pos);animation:pulse 2s infinite}}
@keyframes pulse{{0%{{box-shadow:0 0 0 0 rgba(47,191,143,.5)}}
70%{{box-shadow:0 0 0 7px rgba(47,191,143,0)}}100%{{box-shadow:0 0 0 0 rgba(47,191,143,0)}}}}
/* LIVE status pill */
.livebadge{{display:inline-flex;align-items:center;gap:7px;padding:5px 12px 5px 10px;
border-radius:999px;font-size:11.5px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;
border:1px solid var(--line);background:var(--chip);color:var(--mut);transition:color .3s,background .3s,border-color .3s;user-select:none}}
.livebadge .lb-dot{{width:9px;height:9px;border-radius:50%;background:var(--mut)}}
.livebadge.on{{color:var(--pos);border-color:rgba(47,191,143,.45);background:rgba(47,191,143,.10)}}
.livebadge.on .lb-dot{{background:var(--pos);box-shadow:0 0 0 0 var(--pos);animation:pulse 2s infinite}}
.acc{{color:var(--acc)}}
/* levels + regime panel */
.lvpanel{{background:linear-gradient(180deg,var(--panel2),var(--panel));
border:1px solid var(--line);border-radius:13px;padding:12px 15px;margin:0 0 22px}}
.lvhead{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px}}
.rlabel{{font-weight:800;letter-spacing:.06em;font-size:13px;padding:3px 10px;border-radius:8px;
background:var(--chip)}}
.rlabel.pos{{color:var(--pos);box-shadow:inset 0 0 0 1px rgba(47,191,143,.4)}}
.rlabel.neg{{color:var(--neg);box-shadow:inset 0 0 0 1px rgba(240,85,95,.4)}}
.lvrow{{display:grid;grid-template-columns:repeat(auto-fit,minmax(74px,1fr));gap:7px}}
.lv{{background:var(--chip);border:1px solid var(--line);border-radius:9px;padding:7px 6px;
text-align:center;font-variant-numeric:tabular-nums}}
.lv b{{display:block;font-size:9.5px;color:var(--mut);letter-spacing:.06em;margin-bottom:3px}}
.lv span{{font-size:15px;font-weight:750}}
.lv.res{{border-top:2px solid var(--neg)}} .lv.res span{{color:var(--neg)}}
.lv.sup{{border-top:2px solid var(--pos)}} .lv.sup span{{color:var(--pos)}}
.lv.piv{{border-top:2px solid var(--warn)}} .lv.piv span{{color:var(--warn)}}
.lv.spot{{border-top:2px solid var(--acc);background:rgba(91,155,255,.1)}}
.lv.spot span{{color:var(--acc)}}
.lvfoot{{display:flex;gap:16px;flex-wrap:wrap;margin-top:10px;font-size:11.5px}}
.lvfoot .d1,.lvfoot .gex{{color:var(--ink)}}
/* setups grade ladders */
.setups{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px}}
.setup{{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);
border-radius:13px;padding:14px 16px}}
.setup-h{{display:flex;align-items:center;gap:9px;font-size:15px;margin-bottom:6px}}
.pill{{font-size:9.5px;letter-spacing:.05em;padding:2px 8px;border-radius:7px;background:var(--chip);
font-weight:700;text-transform:uppercase}}
.pill.pos{{color:var(--pos)}}.pill.warn{{color:var(--warn)}}.pill.mut{{color:var(--mut)}}
.setup-thesis{{color:var(--ink);font-size:12.5px;line-height:1.5;margin-bottom:6px}}
.setup-def{{color:var(--mut);font-size:11.5px;line-height:1.45;margin-bottom:10px}}
.gtable{{width:100%;border-collapse:collapse}}
.gtable td{{border-top:1px solid var(--line);padding:7px 6px;font-size:12px;vertical-align:top}}
.gcell{{width:52px;font-weight:800;text-align:center;font-size:13px}}
.gcell.pos{{color:var(--pos)}}.gcell.acc{{color:var(--acc)}}
.gcell.warn{{color:var(--warn)}}.gcell.neg{{color:var(--neg)}}
/* game plan tab */
.gp-head{{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:6px}}
.paths{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;margin:12px 0 18px}}
.path{{background:var(--chip);border:1px solid var(--line);border-radius:10px;padding:10px 12px}}
.path-h{{display:flex;justify-content:space-between;gap:8px;margin-bottom:4px}}
.path-h code{{background:var(--panel);padding:1px 6px;border-radius:5px;font-size:11px}}
.gptable{{width:100%;border-collapse:collapse}}
.gptable th{{text-align:left;color:var(--mut);font-size:10.5px;letter-spacing:.05em;
text-transform:uppercase;padding:6px 8px;border-bottom:1px solid var(--line)}}
.gptable td{{padding:9px 8px;border-bottom:1px solid var(--line);vertical-align:top}}
.gptable code{{background:var(--chip);padding:1px 6px;border-radius:5px;font-size:11.5px}}
.stpill{{font-size:9.5px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;
padding:3px 8px;border-radius:7px;background:var(--chip);white-space:nowrap}}
.stpill.arm{{color:var(--acc);box-shadow:inset 0 0 0 1px rgba(91,155,255,.35)}}
.stpill.pos{{color:var(--pos)}}.stpill.mut{{color:var(--mut)}}
.stpill.warn{{color:var(--warn)}}.stpill.neg{{color:var(--neg)}}.stpill.acc{{color:var(--acc)}}
/* lifecycle board (Ideas / Open / Closed / Never) */
.sec-h{{display:flex;align-items:center;gap:10px;margin:20px 2px 10px;font-size:12.5px;
letter-spacing:.06em;font-weight:800;color:var(--ink)}}
.sec-h::after{{content:'';flex:1;height:1px;background:var(--line)}}
.sec-h .cnt{{background:var(--chip);border:1px solid var(--line);border-radius:8px;
padding:1px 9px;font-size:11px;color:var(--mut)}}
.iboard{{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:12px}}
.itile{{background:linear-gradient(160deg,var(--panel2),var(--panel) 60%);border:1px solid var(--line);
border-radius:14px;padding:14px 15px 12px;position:relative;overflow:hidden}}
.itile::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--gc,#777)}}
.itile-h{{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}}
.itile-name{{font-weight:800;font-size:14.5px;line-height:1.25}}
.ichip{{min-width:2em;text-align:center;padding:2px 9px;border-radius:9px;color:#fff;font-weight:800;
font-size:12.5px;box-shadow:0 2px 8px rgba(0,0,0,.35)}}
.itile-sub{{color:var(--mut);font-size:11.5px;margin:7px 0 6px;line-height:1.4}}
.itile-sub b{{color:var(--ink);font-weight:600}}
.itile-why{{font-size:12px;line-height:1.5;color:var(--ink);opacity:.9}}
.itile-foot{{margin-top:10px;padding-top:9px;border-top:1px solid var(--line);font-size:12.5px;font-weight:600}}
.itile-foot .wait{{color:var(--acc)}}
.itile-foot .pos{{color:var(--pos)}}.itile-foot .neg{{color:var(--neg)}}.itile-foot .warn{{color:var(--warn)}}
/* collapsible expanders (native <details>) */
.ex{{background:var(--panel);border:1px solid var(--line);border-radius:12px;margin:0 0 12px;overflow:hidden}}
.ex>summary{{cursor:pointer;padding:11px 15px;font-weight:700;font-size:13px;list-style:none;
display:flex;align-items:center;gap:9px;user-select:none}}
.ex>summary::-webkit-details-marker{{display:none}}
.ex>summary::before{{content:'▸';color:var(--mut);font-size:11px;transition:transform .15s}}
.ex[open]>summary::before{{transform:rotate(90deg)}}
.ex>summary .cnt{{background:var(--chip);border:1px solid var(--line);border-radius:8px;
padding:1px 9px;font-size:11px;color:var(--mut);font-weight:600}}
.ex>summary .sp{{margin-left:auto;color:var(--mut);font-weight:600;font-size:12px}}
.ex-body{{padding:2px 15px 14px}}
.ex-sec{{background:transparent;border:0;margin:14px 0 4px}}
.ex-sec>summary{{padding:8px 2px;letter-spacing:.05em;font-size:12.5px;font-weight:800;border-bottom:1px solid var(--line)}}
.ex-sec .ex-body,.ex-sec>.iboard{{padding:12px 0 4px}}
.ptable{{width:100%;border-collapse:collapse;font-size:12.5px}}
.ptable td{{padding:6px 8px;border-top:1px solid var(--line)}}
.ptable td.r{{text-align:right;font-variant-numeric:tabular-nums;font-weight:700}}
.ptable tr.ph td{{color:var(--mut);font-size:10.5px;font-weight:600;letter-spacing:.03em;text-transform:uppercase;border-top:0}}
.ptable h4,.ex-body h4{{margin:12px 0 4px;font-size:11px;color:var(--mut);letter-spacing:.06em;text-transform:uppercase}}
.tabs{{display:flex;gap:4px;border-bottom:1px solid var(--line);margin-bottom:18px}}
.tab{{padding:9px 16px;color:var(--mut);cursor:pointer;font-weight:600;font-size:13.5px;
border-bottom:2px solid transparent;margin-bottom:-1px}}
.tab.on{{color:var(--ink);border-bottom-color:var(--acc)}}
.page{{display:none}} .page.on{{display:block}}
.jrow{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:13px 16px;margin:10px 0}}
.jhead{{display:flex;align-items:center;gap:9px}}
.badge{{font-size:9.5px;letter-spacing:.1em;padding:2px 7px;border-radius:6px;background:var(--chip);color:var(--mut)}}
.badge.open{{color:var(--pos)}} .jmeta{{color:var(--mut);font-size:12px;margin:5px 0}}
.jthesis{{font-size:13px;line-height:1.55}}
h2{{font-size:15px;color:var(--acc);margin:24px 0 8px}}
{card_css}
.grid{{margin-top:0}}
</style></head><body><div class="wrap">
<div class="top"><span class="livebadge{' on' if live_state=='live' else ''}" id="livebadge" title="Live feed status"><span class="lb-dot"></span><span id="livebadge-txt">{'LIVE' if live_state=='live' else 'OFFLINE'}</span></span><h1>Options — Forward Sim</h1>
  <span class="sub" id="updated" style="margin-left:auto"></span></div>
<div class="sub">causal 15:59 BPS + paper strategies · live feed
  <b id="feedstate">{live_state}</b>
  <span id="feedhint">{'· start <code>scripts/spot_feed.py</code>' if live_state!='live' else ''}</span></div>

<div class="ticker" id="ticker"></div>

<div id="lvpanel-wrap">{levels_panel(lr)}</div>

<div class="kpis">{stat_tiles(s, skip=("running", "close_now", "mpz"))}</div>

{positions_html(gp_trades, gp_marks)}

<div class="tabs">
  <div class="tab on" data-p="trades">Trades</div>
  <div class="tab" data-p="gameplan">Game Plan</div>
  <div class="tab" data-p="analytics">Analytics</div>
  <div class="tab" data-p="calendar">Calendar</div>
  <div class="tab" data-p="postmortem">Postmortem</div>
  <div class="tab" data-p="eodreport">Desk Report</div>
  <div class="tab" data-p="setups">Setups &amp; Grades</div>
  <div class="tab" data-p="journal">Journal</div>
  <div class="tab" data-p="playbook">Playbook</div>
  <div class="tab" data-p="results">Sim Results</div>
  <div class="tab" data-p="levels">Levels</div>
  <div class="tab" data-p="ibtd">IB vs TD</div>
</div>

<div class="page on" id="p-trades">{pnl_summary_html(gp_trades)}{card_body}</div>
<div class="page" id="p-ibtd">
<style>
/* scoped + RESET the flip-card .big/.card leaks (options_build_cards .big = 760px tall) */
#p-ibtd .tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0}}
#p-ibtd .card{{background:var(--panel,#161b22);border:1px solid var(--line,#30363d);border-radius:11px;padding:10px 12px;height:auto;min-height:0;max-height:none;perspective:none;transform:none}}
#p-ibtd .ct{{font-size:11px;text-transform:uppercase;color:var(--mut,#8b949e);font-weight:700;letter-spacing:.04em}}
#p-ibtd .big{{font-size:21px;font-weight:800;margin:3px 0;height:auto!important;width:auto!important;perspective:none;cursor:default;box-shadow:none;background:none}}
#p-ibtd .sub{{color:var(--mut,#8b949e);font-size:11.5px}}
#p-ibtd .pos{{color:var(--pos,#2fbf8f)}}#p-ibtd .neg{{color:var(--neg,#f85149)}}
#p-ibtd table{{width:100%;border-collapse:collapse;margin-top:12px;font-size:12.5px}}
#p-ibtd th,#p-ibtd td{{padding:5px 8px;border-bottom:1px solid var(--line,#21262d);text-align:right}}
#p-ibtd th:first-child,#p-ibtd td:first-child{{text-align:left}}
</style>
<div class="muted" style="font-size:12px;margin:4px 0 8px">Live IB paper fills vs ThetaData-priced (TD) reconstruction — today's shadow book. Was the standalone :8610 page; now integrated here.</div>
<div class="kpis" style="margin:6px 0 14px">{stat_tiles(s, only=("running", "close_now", "mpz"))}</div>
{ibtd_html}
</div>
<div class="page" id="p-analytics">
  <div class="kpis" id="an-tiles"></div>
  <div class="an-charts">
    <div class="an-card"><div class="an-h">Equity curve <span class="muted" id="an-eqsub"></span></div><div id="an-equity"></div></div>
    <div class="an-card"><div class="an-h">Grade calibration <span class="muted">— does grade predict P&amp;L?</span></div><div id="an-grade"></div></div>
    <div class="an-card"><div class="an-h">Monthly P&amp;L</div><div id="an-monthly"></div></div>
    <div class="an-card"><div class="an-h">Drawdown <span class="muted" id="an-ddsub"></span></div><div id="an-dd"></div></div>
    <div class="an-card"><div class="an-h">Capital — collateral vs ideal account <span class="muted" id="an-capsub"></span></div><div id="an-capital"></div></div>
  </div>
  <div class="modal" id="an-modal"><div class="modal-c"><div class="modal-h"></div><div class="modal-body"></div></div></div>
  {shadow_stop_html()}
  <div class="an-card" style="margin-top:14px">
    <div class="an-h">Break down by
      <select id="an-dim">
        <option value="grade">Grade</option><option value="strategy">Strategy</option>
        <option value="regime">Gamma regime</option><option value="bias">Directional bias</option>
        <option value="dow">Day of week</option><option value="hour">Entry hour</option>
        <option value="source">Source</option><option value="win">Win/Loss</option>
      </select>
      <span class="muted" id="an-note"></span>
    </div>
    <div id="an-pivot"></div>
  </div>
</div>
<div class="page" id="p-calendar">
  <div class="cal-top"><button id="cal-prev">‹</button>
    <b id="cal-title"></b><button id="cal-next">›</button>
    <span class="muted" id="cal-month-tot" style="margin-left:auto"></span></div>
  <div id="cal-grid"></div>
  <div id="cal-day"></div>
</div>
<div class="page" id="p-gameplan">{gameplan_html(gp, gp_trades, gp_marks)}{gameplan_history_html()}</div>
<div class="page" id="p-postmortem">{postmortem_html(pm)}{postmortem_history_html()}</div>
<div class="page" id="p-eodreport">{eod_report_html()}{eod_report_history_html()}</div>
<div class="page" id="p-setups">{setups_html()}</div>
<div class="page" id="p-journal">{journal_html(jn)}</div>
<div class="page prose" id="p-playbook">{playbook_html}</div>
<div class="page" id="p-results">{results_html()}</div>
<div class="page" id="p-levels">{levels_html()}</div>
</div>
<script>
// ---- UI state: keep the active tab / scroll / open expanders across the
// (now rare) soft-reloads so auto-refresh never kicks you off your tab ----
const UIK='optsUI_v1';
function activateTab(p){{
  const tab=document.querySelector('.tab[data-p="'+p+'"]'); if(!tab) return;
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
  document.querySelectorAll('.page').forEach(x=>x.classList.remove('on'));
  tab.classList.add('on'); const pg=document.getElementById('p-'+p); if(pg) pg.classList.add('on');
}}
function saveUI(){{
  const on=document.querySelector('.tab.on');
  const det={{}}; document.querySelectorAll('details[id]').forEach(d=>det[d.id]=d.open);
  try{{sessionStorage.setItem(UIK, JSON.stringify({{tab:on?on.dataset.p:null, y:window.scrollY, det}}));}}catch(e){{}}
}}
function restoreUI(){{
  let st; try{{st=JSON.parse(sessionStorage.getItem(UIK));}}catch(e){{}}
  if(!st) return;
  if(st.det) document.querySelectorAll('details[id]').forEach(d=>{{ if(d.id in st.det) d.open=st.det[d.id]; }});
  if(st.tab) activateTab(st.tab);
  if(st.y) window.scrollTo(0, st.y);
}}
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{{ activateTab(t.dataset.p); saveUI(); }});
document.addEventListener('toggle', e=>{{ if(e.target.tagName==='DETAILS') saveUI(); }}, true);
window.addEventListener('beforeunload', saveUI);
restoreUI();

// ---- live polling (active only when served over http by options_dashboard_live.py) ----
// NB: the embedded card wall already defines global `fmt`/`$` — do NOT redeclare
// them here or the whole script throws and the tabs go dead.
let __dashGen = null;
function dfv(v){{ return (v===null||v===undefined) ? '—' : v; }}
function dtick(label, v){{
  return `<div class="tk"><b>${{label}}</b><span class="v">${{dfv(v)}}</span></div>`;
}}
async function poll(){{
  let d;
  try{{
    const r = await fetch('state.json?_='+Date.now(), {{cache:'no-store'}});
    if(!r.ok) return; d = await r.json();
  }}catch(e){{ return; }}  // file:// or server down -> stay static, no errors
  // KPI tiles
  for(const [k,t] of Object.entries(d.tiles||{{}})){{
    const el = document.getElementById('k-'+k);
    if(el){{ el.textContent = t.value; el.className = 'tv '+(t.cls||''); }}
  }}
  // TODAY banner — re-rendered server-side each poll from live marks, so it never goes stale
  const tb = document.getElementById('today-banner');
  if(tb && d.today_banner!==undefined){{ tb.outerHTML = d.today_banner || "<div id='today-banner'></div>"; }}
  // live ticker + feed state
  const L = d.live||{{}}, live = L.state==='live';
  const lb = document.getElementById('livebadge');
  if(lb){{ lb.className = 'livebadge'+(live?' on':'');
    const lt = document.getElementById('livebadge-txt'); if(lt) lt.textContent = live?'LIVE':'OFFLINE'; }}
  const fs = document.getElementById('feedstate'); if(fs) fs.textContent = L.state||'offline';
  const fh = document.getElementById('feedhint');
  if(fh) fh.innerHTML = live ? '' : '· start <code>scripts/spot_feed.py</code>';
  const tk = document.getElementById('ticker');
  if(tk){{
    tk.innerHTML = live
      ? dtick('SPX', L.spx) + dtick('ES est', L.es_est) + dtick('VIX', L.vix)
        + (L.basis!==null&&L.basis!==undefined ? dtick('Basis', L.basis+' @'+(L.basis_ts||'')) : '')
      : '<div class="tk muted">feed offline — spot updates paused</div>';
  }}
  // levels + regime panel (spot + gamma regime move live)
  const lr = d.lr||{{}};
  const sp = document.getElementById('lv-spot');
  if(sp && lr.spot!=null) sp.textContent = lr.spot.toLocaleString(undefined,{{minimumFractionDigits:1,maximumFractionDigits:1}});
  const sts = document.getElementById('lv-spotts'); if(sts) sts.textContent = lr.spot_ts||'';
  // LIVE band-graphic marker: move the white price line with each poll
  const bs = document.getElementById('bands-svg');
  if(bs && lr.spot!=null){{
    const blo=+bs.dataset.lo, bhi=+bs.dataset.hi, bw=+bs.dataset.w;
    if(bhi>blo){{
      const bx = 30 + (Math.min(Math.max(lr.spot,blo),bhi)-blo)/(bhi-blo)*(bw-60);
      const bl=document.getElementById('bm-line'), bt=document.getElementById('bm-text');
      if(bl){{ bl.setAttribute('x1',bx); bl.setAttribute('x2',bx); }}
      if(bt){{ bt.setAttribute('x',bx); bt.textContent='▲ '+Math.round(lr.spot); }}
    }}
  }}
  if(lr.regime){{
    const rl = document.getElementById('lv-regime');
    if(rl){{ rl.textContent = lr.regime.label; rl.className = 'rlabel '+(lr.regime.cls||''); }}
    const rd = document.getElementById('lv-regdetail'); if(rd) rd.textContent = lr.regime.detail;
  }}
  const up = document.getElementById('updated');
  if(up) up.textContent = (L.ts_et? 'feed '+L.ts_et+' CT · ':'') + 'refreshed '
    + new Date().toLocaleTimeString();
  // soft reload when trades/journal change (card wall + journal refresh) —
  // save UI first so the reload lands you back on the same tab/scroll/expanders
  if(__dashGen!==null && d.gen!==__dashGen){{ saveUI(); location.reload(); }}
  __dashGen = d.gen;
}}
poll(); setInterval(poll, 5000);
</script>
<style>{ANALYTICS_CSS}</style>
<script>
window.__T = {an_json};
{ANALYTICS_JS}
</script></body></html>"""
    out = SIM / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}")
    return out


if __name__ == "__main__":
    main()
