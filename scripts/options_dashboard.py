"""Polished standalone options dashboard (S73) -> data/options_sim/dashboard.html.

Replaces the cheap-looking Streamlit UI: one self-contained, elegant dark page.
Reads the same files (trades.parquet, journal.json, marks.csv, account.csv,
live.json). Reuses the flip-card trade wall from options_build_cards. No server,
no Streamlit — just open the file (or serve the folder).

Run: .venv/Scripts/python.exe scripts/options_dashboard.py
"""
import datetime as dt
import json
from pathlib import Path

import pandas as pd

import options_build_cards as obc
import options_trade_log as tlog

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"


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


def stat_tiles(s):
    tiles = [
        ("Net Liq", s["netliq"], "acct", ""),
        ("Realized P&L", s["realized"], "pnl", s["realized"]),
        ("Running (open)", s["running"], "pnl", s["running"]),
        ("Win rate", s["win"], "", ""),
        ("Profit factor", s["pf"], "", ""),
        ("Open / Closed", f"{s['open']} / {s['closed']}", "", ""),
        ("Collateral at risk", s["collateral"], "warn", ""),
        ("IB maint margin", s["margin"], "warn", ""),
        ("VIX", s["vix"], "", ""),
    ]
    out = []
    for label, val, kind, signed in tiles:
        cls = ""
        if kind == "pnl" and isinstance(signed, str) and signed not in ("—", ""):
            cls = "pos" if not signed.startswith("−") else "neg"
        out.append(f"""<div class="kpi">
          <div class="kl">{label}</div>
          <div class="kv {cls}">{val}</div></div>""")
    return "".join(out)


def journal_html(jn):
    if not jn:
        return "<p class='muted'>No journal entries.</p>"
    rows = []
    for tid, e in list(jn.items())[::-1]:
        a = e["auto"]; res = a["result"]; life = a.get("lifecycle") or {}
        pnl = res.get("pnl")
        pc = "pos" if (pnl or 0) >= 0 else "neg"
        rows.append(f"""<div class="jrow">
          <div class="jhead"><b>{a['strategy']}</b>
            <span class="badge {a['state']}">{a['state'].upper()}</span>
            <span class="{pc}" style="margin-left:auto;font-weight:700">{money(pnl) if pnl is not None else '—'}</span></div>
          <div class="jmeta">{a['structure']} · entered {a['entry_dt']} · R {res.get('r_multiple','—')}
            {'· MFE '+money(life['mfe'])+' / MAE '+money(life['mae']) if life else ''}</div>
          <div class="jthesis">{a['plan']['thesis'][:280]}</div></div>""")
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
--mut:#7d8697;--acc:#5b9bff;--pos:#2fbf8f;--neg:#f0555f;--warn:#e6a84b;--chip:#1c212b}}
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
<div class="top"><span class="dot"></span><h1>Options — Forward Sim</h1></div>
<div class="sub">causal 15:59 BPS + paper strategies · live feed <b>{live_state}</b>
{'· start <code>scripts/spot_feed.py</code>' if live_state!='live' else ''}</div>

<div class="kpis">{stat_tiles(s)}</div>

<div class="tabs">
  <div class="tab on" data-p="trades">Trades</div>
  <div class="tab" data-p="journal">Journal</div>
  <div class="tab" data-p="playbook">Playbook</div>
  <div class="tab" data-p="results">Sim Results</div>
</div>

<div class="page on" id="p-trades">{card_body}</div>
<div class="page" id="p-journal">{journal_html(jn)}</div>
<div class="page prose" id="p-playbook">{playbook_html}</div>
<div class="page" id="p-results">{results_html()}</div>
</div>
<script>
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('on'));
  document.querySelectorAll('.page').forEach(x=>x.classList.remove('on'));
  t.classList.add('on'); document.getElementById('p-'+t.dataset.p).classList.add('on');
}});
</script></body></html>"""
    out = SIM / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}")
    return out


if __name__ == "__main__":
    main()
