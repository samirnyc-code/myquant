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
import mq_levels_db as mqdb

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
LEVELS_FILE = ROOT / "scratchpad" / "mq_levels_today.json"


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


def load_levels():
    if not LEVELS_FILE.exists():
        return None
    try:
        return json.loads(LEVELS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def regime_state(spot, lv):
    """Options dealer-gamma regime from spot vs HVL (NOT the Brooks engine).
    spot > HVL => positive gamma (dealers long gamma: mean-revert / pin bias)."""
    if spot is None or not lv or lv.get("hvl") is None:
        return {"label": "—", "detail": "need spot + HVL", "cls": ""}
    hvl = float(lv["hvl"])
    if spot >= hvl:
        return {"label": "POSITIVE GAMMA",
                "detail": f"spot {spot:.0f} > HVL {hvl:.0f} — dealers long gamma; "
                          "pin / fade-the-extremes bias. Favors premium-sell & flies.",
                "cls": "pos"}
    return {"label": "NEGATIVE GAMMA",
            "detail": f"spot {spot:.0f} < HVL {hvl:.0f} — dealers short gamma; "
                      "moves amplify. Favors long vol / straddles, avoid naked premium.",
            "cls": "neg"}


def levels_regime():
    """Bundle used by the header panel + the live /state.json endpoint."""
    lv = load_levels()
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
    spx = (lv or {}).get
    es = ((lv or {}).get("es") or {}).get
    return {
        "spot": None if spot is None else round(spot, 1),
        "spot_ts": spot_ts,
        "regime": regime_state(spot, lv),
        "spx": {k: spx(k) for k in ("ps", "ps0", "hvl", "gw0", "cr0", "cr")} if lv else {},
        "es": {k: es(k) for k in ("ps", "ps0", "hvl", "gw0", "cr0", "cr")} if lv else {},
        "d1_min": (lv or {}).get("d1_min"), "d1_max": (lv or {}).get("d1_max"),
        "gex": (lv or {}).get("gex", [])[:6] if lv else [],
    }


def money(v, signed=True):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    return (f"{'+' if v >= 0 else '−'}${abs(v):,.0f}") if signed else f"${abs(v):,.0f}"


def load_stats():
    trades = tlog.load()
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
    return {
        "open": int(len(trades) - len(closed)), "closed": int(len(closed)),
        "win": f"{(p > 0).mean() * 100:.0f}%" if len(p) else "—",
        "pf": f"{pf:.2f}" if pf else "—",
        "realized": money(p.sum()) if len(p) else "—",
        "running": money(unreal) if unreal is not None else "—",
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


def positions_html(trades, marks_last):
    """Collapsible Open / Closed positions detail behind the KPI tiles."""
    if trades is None or not len(trades):
        return ""
    openp = trades[trades.exit_dt.isna()]
    closedp = trades[trades.exit_dt.notna()]

    def rows(df, running):
        out = []
        for _, r in df.iloc[::-1].iterrows():
            if running:
                pnl = marks_last.unreal_pnl.get(r.trade_id) if marks_last is not None else None
            else:
                pnl = float(r.pnl) if pd.notna(r.pnl) else None
            gr = r.grade if isinstance(r.grade, str) else "—"
            m = money(pnl)
            out.append(
                f"<tr><td><b>{r.strategy_id}</b></td>"
                f"<td class='muted'>{r.structure or ''}</td>"
                f"<td style='color:{_grade_color(gr)};font-weight:800'>{gr}</td>"
                f"<td class='r {_pnl_cls(m)}'>{m}</td></tr>")
        return "".join(out) or "<tr><td class='muted'>none</td></tr>"

    return (f"<details id='ex-positions' class='ex'>"
            f"<summary>Positions detail <span class='cnt'>{len(openp)} open · {len(closedp)} closed</span>"
            f"<span class='sp'>click to expand</span></summary>"
            f"<div class='ex-body'>"
            f"<h4>Open — running P&amp;L (mark-to-market)</h4>"
            f"<table class='ptable'>{rows(openp, True)}</table>"
            f"<h4>Closed — realized</h4>"
            f"<table class='ptable'>{rows(closedp, False)}</table></div></details>")


def tile_specs(s):
    """Single source of truth for the KPI tiles — used by both the initial
    render and the live /state.json endpoint. Returns (key, label, value, cls)."""
    return [
        ("netliq", "Net Liq", s["netliq"], ""),
        ("realized", "Realized P&L", s["realized"], _pnl_cls(s["realized"])),
        ("running", "Running (open)", s["running"], _pnl_cls(s["running"])),
        ("win", "Win rate", s["win"], ""),
        ("pf", "Profit factor", s["pf"], ""),
        ("openclosed", "Open / Closed", f"{s['open']} / {s['closed']}", ""),
        ("collateral", "Collateral at risk", s["collateral"], "warn"),
        ("margin", "IB maint margin", s["margin"], "warn"),
        ("vix", "VIX", s["vix"], ""),
    ]


def stat_tiles(s):
    out = []
    for key, label, val, cls in tile_specs(s):
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
    {"name": "STMR Bull Put Spread", "id": "bps_stmr", "tag": "SUPPORTED (in-sample)",
     "tagcls": "pos", "thesis": "Oversold-but-uptrend mean reversion; sell put premium into the bounce.",
     "default": "SPXW ~30Δ put / buy 50pt lower · 14 DTE · exit on SMA5 signal (NO stops/targets/holds).",
     "grades": [
        ("A+", "15:59 %K8<15 AND spot>SMA100, LOW VIX-rank tercile, non-crash uptrend, no gap-down cluster."),
        ("A / B", "Trigger fires but one context off (VIX-rank mid, choppy tape). Still the only real edge — take it."),
        ("C", "Off-signal execution/labeling test (%K8 not oversold) — plumbing only, no edge."),
        ("F", "Held to expiry / used price stops / profit target — the exit shootout proved these are negative."),
     ]},
    {"name": "0DTE Premium Sell @ Wall", "id": "sell_0dte_gamma", "tag": "HYPOTHESIS (live)",
     "tagcls": "warn", "thesis": "Positive-gamma days pin; sell defined-risk premium at the walls.",
     "default": "0DTE 25pt credit spread, short AT PS0 (puts) / CR0 (calls), 8:45–9:30 CT.",
     "grades": [
        ("A+", "Positive gamma (spot>HVL), VIX<20, no FOMC/CPI, spot ≥40pt from short strike, credit ≥0.80."),
        ("A / B", "Positive gamma but closer to the wall (25–40pt) or credit 0.60–0.80."),
        ("C", "Ambiguous regime (|spot−HVL|<15) or entered late/off the wall — structure test."),
        ("F", "Zero/near-zero credit fill (wall already faded past the strike) — reject before placing."),
     ]},
    {"name": "0DTE Iron Condor (inside walls)", "id": "condor_0dte", "tag": "HYPOTHESIS",
     "tagcls": "warn", "thesis": "Add call-side credit on ~zero extra collateral on a pin day.",
     "default": "Short put AT/inside PS0 + short call AT/inside CR0 · 25pt wings · both ≥40pt OTM, total credit ≥1.50.",
     "grades": [
        ("A+", "Clean positive gamma, spot mid-channel between PS0/CR0, both strikes ≥40pt OTM, credit ≥1.50."),
        ("A / B", "Positive gamma but one side <40pt OTM (asymmetric) — the risk side is the trending one."),
        ("C", "|spot−HVL|<15 (regime ambiguity) — playbook says skip; logged only as a test."),
        ("F", "One side filled far after the other (leg risk) or a side already breached."),
     ]},
    {"name": "Long ATM Straddle", "id": "straddle_0dte", "tag": "HYPOTHESIS (counter-regime)",
     "tagcls": "warn", "thesis": "Buy vol when realized>implied is likely: events, negative-gamma days.",
     "default": "Buy ATM C+P · 0DTE (event) or nearest weekly · risk = full debit.",
     "grades": [
        ("A+", "Scheduled event (FOMC/CPI before 16:00) OR negative-gamma morning with VIX term inverted."),
        ("A / B", "Negative gamma but VIX term not clearly inverted."),
        ("C", "Taken to test debit/two-right execution with no vol catalyst."),
        ("F", "Bought on a positive-gamma pin day at low VIX — the textbook counter-regime loss (2026-07-14)."),
     ]},
    {"name": "Butterfly at the Pin", "id": "fly_gw_0dte", "tag": "HYPOTHESIS (most aligned long)",
     "tagcls": "warn", "thesis": "Positive-gamma days settle near the Gamma Wall; convex payoff into the pin.",
     "default": "Call butterfly · 25pt wings · centered ON GW0 · 0DTE · enter 10:00–12:00 · debit ≤40% of wing.",
     "grades": [
        ("A+", "Positive gamma, spot hovering near GW0, debit ≤40% of wing width, no event."),
        ("A / B", "Positive gamma but spot 25–50pt off GW0, or debit 40–50% of wing."),
        ("C", "Entered outside the 10:00–12:00 window or center guessed (no clean GW0)."),
        ("F", "Bought on a negative-gamma / trend day (no pin) — the wall won't hold price."),
     ]},
    {"name": "Directional Verticals", "id": "bull_cs_wk", "tag": "HYPOTHESIS (needs a signal)",
     "tagcls": "warn", "thesis": "A debit vertical is a delta bet; only sanctioned to express a VALIDATED futures signal.",
     "default": "Buy 50Δ / sell 25Δ · 7–14 DTE · ONLY on a validated STMR-long signal day · exit with the signal.",
     "grades": [
        ("A+", "Expresses an active validated STMR-long signal in defined-risk form; exit tied to the signal."),
        ("A / B", "Validated signal present but sizing/DTE improvised."),
        ("C", "Momentum chase with no validated signal — coin flip minus the spread (2026-07-14 sample)."),
        ("F", "Blind directional bet against the regime / no exit plan."),
     ]},
    {"name": "Put Calendar", "id": "put_cal_wk", "tag": "PARKED (structure test)",
     "tagcls": "mut", "thesis": "Short-leg theta > long-leg theta near ATM; vega hedge. No testable edge with owned data.",
     "default": "ATM put calendar (short 0DTE / long weekly) · risk = net debit.",
     "grades": [
        ("A+", "n/a — parked until term-structure history is owned."),
        ("A / B", "n/a."),
        ("C", "Logged once to prove multi-expiry handling."),
        ("F", "—"),
     ]},
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
        return json.loads(f.read_text(encoding="utf-8"))
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
        try:
            dow = pd.to_datetime(entry).strftime("%a") if entry else ""
        except Exception:
            dow = ""
        rows.append({
            "id": r.trade_id, "strategy": r.strategy_id,
            "date": entry[:10], "entry": entry, "dow": dow,
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


def load_gameplan():
    import datetime as _dt
    from zoneinfo import ZoneInfo
    date = _dt.datetime.now(ZoneInfo("America/Chicago")).strftime("%Y%m%d")
    f = SIM / f"gameplan_{date}.json"
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
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


def _bucket(title, tiles, bid, is_open=True):
    body = "".join(tiles) if tiles else "<div class='muted' style='padding:6px 2px'>—</div>"
    return (f"<details id='ex-{bid}' class='ex ex-sec'{' open' if is_open else ''}>"
            f"<summary>{title} <span class='cnt'>{len(tiles)}</span></summary>"
            f"<div class='iboard'>{body}</div></details>")


def gameplan_html(gp, trades=None, marks_last=None):
    if not gp:
        return ("<p class='muted'>No gameplan generated yet. Run "
                "<code>scripts/options_gameplan.py</code> (auto ~8:25 CT).</p>")
    regcls = "pos" if gp.get("regime") == "positive_gamma" else "neg"
    head = (f"<div class='gp-head'><span class='rlabel {regcls}'>"
            f"{gp.get('regime','').replace('_',' ').upper()}</span>"
            f"<span class='muted'>{gp.get('date','')} · preopen {gp.get('spot_preopen','—')} "
            f"({gp.get('spot_source','')})</span>")
    if gp.get("live_spot"):
        head += f"<span class='muted' style='margin-left:auto'>live {gp['live_spot']} @ {gp.get('live_ts','')}</span>"
    head += "</div>"
    paths = ""
    for p in gp.get("scenarios", []):
        paths += (f"<div class='path'><div class='path-h'><b>{p['id']}. {p['name']}</b>"
                  f"<code>{p['path']}</code></div>"
                  f"<div class='muted'>{p['means']} → <span style='color:var(--ink)'>{p['acts']}</span></div></div>")
    paths = f"<div class='paths'>{paths}</div>" if paths else ""

    # sort each trigger into a lifecycle bucket
    ideas, opens, closed, never = [], [], [], []
    for t in gp.get("triggers", []):
        st = t.get("status", "armed")
        tid = t.get("trade_id")
        fill = t.get("fill") or {}
        if t["fire"]["type"] == "signal_1559":
            ideas.append(_idea_tile(t, "<span class='wait'>◷ 15:59 signal — run by the BPS daemon</span>"))
        elif st in ("armed",):
            ideas.append(_idea_tile(t, "<span class='wait'>◷ armed — waiting for trigger</span>"))
        elif st == "fired" and tid is not None and trades is not None:
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

    note = ("<p class='muted' style='margin:14px 0 10px'>Every idea flows "
            "<b>Idea → Open → Closed</b>, or lands in <b>Never triggered</b>. Committed premarket, "
            "auto-executed by the trigger daemon on its condition (1 lot, all grades). Deduped: two "
            "one-sided spreads, no condor. This board is saved per day (<code>gameplan_*.json</code>) — "
            "the growing historical record.</p>")
    board = (_bucket("💡 IDEAS · waiting to trigger", ideas, "ideas", True)
             + _bucket("🟢 OPEN · triggered, live", opens, "opens", True)
             + _bucket("⚪ CLOSED · settled", closed, "closed", len(closed) > 0)
             + _bucket("✕ NEVER TRIGGERED", never, "never", False))
    paths_ex = (f"<details id='ex-paths' class='ex ex-sec' open><summary>Price paths "
                f"<span class='cnt'>{len(gp.get('scenarios', []))}</span></summary>"
                f"{paths}</details>") if paths else ""
    return head + note + paths_ex + board


def levels_panel(lr):
    """Server-side render of the levels + regime strip (also live-updated by poll())."""
    r = lr["regime"]
    spot = lr["spot"]
    spot_txt = f"{spot:,.1f}" if spot is not None else "—"

    def wall(label, key, cls):
        v = lr["spx"].get(key)
        return (f"<div class='lv {cls}'><b>{label}</b>"
                f"<span>{v:,.0f}</span></div>") if v is not None else ""
    walls = (wall("CR", "cr", "res") + wall("CR0", "cr0", "res")
             + wall("GW0", "gw0", "piv") + f"<div class='lv spot'><b>SPOT</b><span id='lv-spot'>{spot_txt}</span></div>"
             + wall("HVL", "hvl", "piv") + wall("PS0", "ps0", "sup") + wall("PS", "ps", "sup"))
    d1 = ""
    if lr["d1_min"] and lr["d1_max"]:
        d1 = (f"<span class='d1'>1-day range {lr['d1_min']:,.0f} – {lr['d1_max']:,.0f}</span>")
    gex = ""
    if lr["gex"]:
        gex = "<span class='gex'>top GEX: " + " · ".join(f"{int(g):,}" for g in lr["gex"]) + "</span>"
    return f"""<div class="lvpanel">
      <div class="lvhead">
        <span class="rlabel {r['cls']}" id="lv-regime">{r['label']}</span>
        <span class="muted" id="lv-regdetail">{r['detail']}</span>
        <span class="muted" style="margin-left:auto" id="lv-spotts">{lr['spot_ts'] or ''}</span>
      </div>
      <div class="lvrow">{walls}</div>
      <div class="lvfoot">{d1} {gex}
        <span class="muted">SPX $MenthorQ walls · today</span></div>
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
    """MenthorQ levels visual DB, embedded from mq_levels_db (nightly capture)."""
    try:
        return mqdb.panel_html(mqdb.load_db())
    except Exception as e:
        return f"<p class='muted'>Levels unavailable: {e}</p>"


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
            gp = json.loads((SIM / f"gameplan_{d}.json").read_text(encoding="utf-8"))
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
            pm = json.loads((SIM / f"postmortem_{d}.json").read_text(encoding="utf-8"))
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
    el.innerHTML=tile('Total P&L',money(s.tot),s.tot>=0?'pos':'neg')+tile('Trades',s.n,'')+
      tile('Win rate',s.win==null?'—':s.win.toFixed(0)+'%','')+tile('Profit factor',s.pf==null?'—':s.pf.toFixed(2),'')+
      tile('Expectancy',money(s.exp),(s.exp||0)>=0?'pos':'neg')+tile('Avg ROI',pctf(s.avgroi),(s.avgroi||0)>=0?'pos':'neg')+
      tile('Max drawdown',money(s.dd),'neg');}
  function renderEquity(){const el=$('#an-equity');if(!el)return;
    const rows=[...T].filter(t=>t.pnl!=null).sort((a,b)=>(a.entry||'').localeCompare(b.entry||''));
    if(!rows.length){el.innerHTML='<div class="muted">no closed trades yet</div>';return;}
    let eq=0;const pts=rows.map((t,i)=>{eq+=t.pnl;return{y:eq,d:t.date};});
    const W=440,H=170,ml=52,mb=16,mt=8,mr=8;
    const ys=pts.map(p=>p.y).concat([0]),ymin=Math.min.apply(0,ys),ymax=Math.max.apply(0,ys);
    const pad=(ymax-ymin)*.12||100,lo=ymin-pad,hi=ymax+pad;
    const X=i=>ml+(pts.length<2?(W-ml-mr)/2:i/(pts.length-1)*(W-ml-mr));
    const Y=v=>mt+(1-(v-lo)/(hi-lo))*(H-mt-mb),zero=Y(0);
    const line=pts.map((p,i)=>X(i).toFixed(1)+','+Y(p.y).toFixed(1)).join(' ');
    if($('#an-eqsub'))$('#an-eqsub').textContent='cum '+money(eq);
    el.innerHTML='<svg width="100%" viewBox="0 0 '+W+' '+H+'">'+
      '<line x1="'+ml+'" y1="'+zero+'" x2="'+(W-mr)+'" y2="'+zero+'" stroke="var(--line)"/>'+
      '<text x="4" y="'+(Y(hi)+9)+'" fill="var(--mut)" font-size="10">'+money(hi)+'</text>'+
      '<text x="4" y="'+(zero+3)+'" fill="var(--mut)" font-size="10">$0</text>'+
      '<text x="4" y="'+Y(lo)+'" fill="var(--mut)" font-size="10">'+money(lo)+'</text>'+
      '<polyline points="'+line+'" fill="none" stroke="var(--acc)" stroke-width="2"/>'+
      pts.map((p,i)=>'<circle cx="'+X(i).toFixed(1)+'" cy="'+Y(p.y).toFixed(1)+'" r="2.5" fill="'+(p.y>=0?'var(--pos)':'var(--neg)')+'"/>').join('')+'</svg>';}
  function grp(rows,key){const m={};rows.forEach(t=>{let k=t[key];if(k===true)k='win';if(k===false)k='loss';if(k==null||k==='')k='?';(m[k]=m[k]||[]).push(t);});return m;}
  function bstat(rows){const p=rows.filter(t=>t.pnl!=null).map(t=>t.pnl),w=p.filter(x=>x>=0),l=p.filter(x=>x<0);
    const rois=rows.filter(t=>t.roi!=null).map(t=>t.roi);
    return {n:p.length,tot:p.reduce((a,b)=>a+b,0),win:p.length?w.length/p.length*100:null,
      avg:p.length?p.reduce((a,b)=>a+b,0)/p.length:null,pf:l.length?w.reduce((a,b)=>a+b,0)/-l.reduce((a,b)=>a+b,0):null,
      roi:rois.length?rois.reduce((a,b)=>a+b,0)/rois.length:null};}
  const GO=['A+','A','B+','B','B-','C+','C','C-','D','F','?'];
  function renderGrade(){const el=$('#an-grade');if(!el)return;const g=grp(closed,'grade');
    const keys=Object.keys(g).sort((a,b)=>GO.indexOf(a)-GO.indexOf(b));
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
      '<td class="'+((s.avg||0)>=0?'pos':'neg')+'">'+money(s.avg)+'</td><td>'+(s.pf==null?'—':s.pf.toFixed(2))+'</td>'+
      '<td class="'+((s.roi||0)>=0?'pos':'neg')+'">'+pctf(s.roi)+'</td></tr>';}).join('');
    el.innerHTML='<table class="antable"><tr><th>'+dim+'</th><th>n</th><th>win</th><th>total</th><th>avg</th><th>PF</th><th>ROI</th></tr>'+rows+'</table>';
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
  function initAn(){renderTiles();renderEquity();renderGrade();renderPivot();renderCal();
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
    gp_trades = tlog.load()
    gp_marks = None
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
<title>Options — Forward Sim</title>
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
<div class="top"><span class="dot" id="livedot"></span><h1>Options — Forward Sim</h1>
  <span class="sub" id="updated" style="margin-left:auto"></span></div>
<div class="sub">causal 15:59 BPS + paper strategies · live feed
  <b id="feedstate">{live_state}</b>
  <span id="feedhint">{'· start <code>scripts/spot_feed.py</code>' if live_state!='live' else ''}</span></div>

<div class="ticker" id="ticker"></div>

<div id="lvpanel-wrap">{levels_panel(lr)}</div>

<div class="kpis">{stat_tiles(s)}</div>

{positions_html(gp_trades, gp_marks)}

<div class="tabs">
  <div class="tab on" data-p="trades">Trades</div>
  <div class="tab" data-p="gameplan">Game Plan</div>
  <div class="tab" data-p="analytics">Analytics</div>
  <div class="tab" data-p="calendar">Calendar</div>
  <div class="tab" data-p="postmortem">Postmortem</div>
  <div class="tab" data-p="setups">Setups &amp; Grades</div>
  <div class="tab" data-p="journal">Journal</div>
  <div class="tab" data-p="playbook">Playbook</div>
  <div class="tab" data-p="results">Sim Results</div>
  <div class="tab" data-p="levels">Levels</div>
</div>

<div class="page on" id="p-trades">{card_body}</div>
<div class="page" id="p-analytics">
  <div class="kpis" id="an-tiles"></div>
  <div class="an-charts">
    <div class="an-card"><div class="an-h">Equity curve <span class="muted" id="an-eqsub"></span></div><div id="an-equity"></div></div>
    <div class="an-card"><div class="an-h">Grade calibration <span class="muted">— does grade predict P&amp;L?</span></div><div id="an-grade"></div></div>
  </div>
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
  // live ticker + feed state
  const L = d.live||{{}}, live = L.state==='live';
  const dot = document.getElementById('livedot');
  if(dot) dot.className = 'dot'+(live?' pulse':'');
  dot && (dot.style.background = live ? 'var(--pos)' : 'var(--mut)');
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
