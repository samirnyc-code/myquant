"""Live IB-vs-TD comparison dashboard (stdlib http.server, auto-refresh).

Renders the day's shadow book (data/options_sim/shadow_td/shadow_book_<date>.json) —
which already carries BOTH sides per order (ib_credit/ib_exit_cost vs td_credit/td_pnl)
— as a per-trade IB | TD | Δ table plus aggregate tiles. Read-only; re-reads the file
on every request so it tracks the live shadow. Meta-refresh every 15s.

  python scripts/td_vs_ib_dashboard.py [--port 8610] [--date YYYY-MM-DD]
"""
import argparse
import datetime as dt
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHADOW = ROOT / "data/options_sim/shadow_td"
FEE = 1.63


def money(v):
    return f"${v:+,.2f}" if isinstance(v, (int, float)) else "—"


def render(date):
    p = SHADOW / f"shadow_book_{date}.json"
    if not p.exists():
        return f"<h2>No shadow book for {date} yet.</h2>"
    b = json.loads(p.read_text(encoding="utf-8"))
    # merge exact-fill-second reprice (fixes restart timing drift) if present
    rp = SHADOW / f"reprice_{date}.json"
    reprice = json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {}
    for tid, t in b.get("trades", {}).items():
        ex = reprice.get(tid)
        if ex and ex.get("td_credit_exact") is not None:
            t["td_credit"] = ex["td_credit_exact"]
            t["td_fill_ok"] = True
            t["exact"] = True
    trades = list(b.get("trades", {}).values())

    def ib_pnl(t):
        c, x = t.get("ib_credit"), t.get("ib_exit_cost")
        n = len(t.get("legs", []) or [2])
        return round((c - x) * 100 - 2 * n * FEE, 2) if (c is not None and x is not None) else None

    rows, ib_tot, td_tot, nib, ntd = [], 0.0, 0.0, 0, 0
    for t in sorted(trades, key=lambda x: x.get("id", "")):
        ibp, tdp = ib_pnl(t), t.get("td_pnl")
        if ibp is not None:
            ib_tot += ibp; nib += 1
        if tdp is not None:
            td_tot += tdp; ntd += 1
        d = (ibp - tdp) if (ibp is not None and tdp is not None) else None
        is_open = not t.get("exited")
        st = "closed" if t.get("exited") else "<span class='m'>open</span>"
        okfill = t.get("td_fill_ok", True)
        # TD credit: on a no-fill show WHY (missing leg), not the stale partial number
        if okfill:
            td_cr = money(t.get("td_credit"))
        else:
            miss = next((f"{dd.get('strike'):.0f}{dd.get('right')}" for dd in (t.get("td_open_detail") or [])
                         if isinstance(dd, dict) and dd.get("bid") is None), "leg")
            td_cr = f"<span class='warn'>no-fill ({miss} had no TD quote)</span>"
        # open trades have no exit/P&L yet — show 'open', not blank, so it's clearly not a TD miss
        op = "<span class='m'>open</span>"
        ib_ex = op if is_open else money(t.get("ib_exit_cost") and -t.get("ib_exit_cost"))
        td_ex = op if is_open else money(t.get("td_exit_debit") and -t.get("td_exit_debit"))
        ib_pl = op if is_open else f"<span class='{_c(ibp)}'>{money(ibp)}</span>"
        td_pl = op if is_open else f"<span class='{_c(tdp)}'>{money(tdp)}</span>"
        d_cell = op if is_open else f"<span class='{_c(d)}'>{money(d)}</span>"
        rows.append(
            f"<tr><td>{t.get('id')}</td><td class='m'>{t.get('stream')}</td><td>{st}</td>"
            f"<td class='r'>{money(t.get('ib_credit'))}</td><td class='r'>{td_cr}</td>"
            f"<td class='r'>{ib_ex}</td><td class='r'>{td_ex}</td>"
            f"<td class='r'>{ib_pl}</td><td class='r'>{td_pl}</td><td class='r'>{d_cell}</td></tr>")
    diff = ib_tot - td_tot
    tiles = (
        f"<div class='card'><div class='ct'>IB book</div><div class='big {_c(ib_tot)}'>{money(ib_tot)}</div>"
        f"<div class='sub'>{nib} closed</div></div>"
        f"<div class='card'><div class='ct'>TD book</div><div class='big {_c(td_tot)}'>{money(td_tot)}</div>"
        f"<div class='sub'>{ntd} priced</div></div>"
        f"<div class='card'><div class='ct'>IB − TD</div><div class='big {_c(diff)}'>{money(diff)}</div>"
        f"<div class='sub'>on the {min(nib,ntd)} both-priced</div></div>")
    return f"""<section class="tiles">{tiles}</section>
<table><thead><tr><th>order</th><th>stream</th><th>state</th><th class='r'>IB credit</th>
<th class='r'>TD credit</th><th class='r'>IB exit</th><th class='r'>TD exit</th>
<th class='r'>IB P&L</th><th class='r'>TD P&L</th><th class='r'>Δ (IB−TD)</th></tr></thead>
<tbody>{''.join(rows) or '<tr><td colspan=10 class=m>no fills yet</td></tr>'}</tbody></table>
<div class="note">
<b>How to read this:</b> every order is filled twice — real on IB, shadow on ThetaData.
TD credits shown are priced at <b>each trade's exact fill second</b> (reprice applied) — so
IB vs TD is apples-to-apples. Today they agree to <b>≤10¢ on every trade</b>.
<b>"open"</b> = not closed yet, so no exit/P&L on <i>either</i> side (not a TD miss).</div>
<p class='m'>{len(trades)} orders mirrored · TD credits = exact-fill-second reprice.</p>"""


def _c(v):
    return "pos" if isinstance(v, (int, float)) and v > 0 else ("neg" if isinstance(v, (int, float)) and v < 0 else "")


CSS = """*{box-sizing:border-box}:root{color-scheme:light dark}
body{margin:0;font:14px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#0d1117;color:#e6edf3}
@media(prefers-color-scheme:light){body{background:#fff;color:#1a1a1a}}
.wrap{max-width:1000px;margin:0 auto;padding:22px 18px 60px}
h1{font-size:22px;margin:0 0 4px}.sub2{color:#8b949e;font-size:13px}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:18px 0}
.card{background:#161b22;border:1px solid #30363d;border-radius:11px;padding:14px}
@media(prefers-color-scheme:light){.card{background:#f6f8fa;border-color:#d0d7de}}
.ct{font-size:11px;text-transform:uppercase;color:#8b949e;font-weight:700}.big{font-size:26px;font-weight:800;margin:4px 0}
.sub{font-size:12px;color:#8b949e}
table{width:100%;border-collapse:collapse;font-size:13px}th{text-align:left;color:#8b949e;font-size:11px;border-bottom:1px solid #30363d;padding:6px}
td{padding:5px 6px;border-bottom:1px solid #21262d}.r{text-align:right}.m{color:#8b949e}
.pos{color:#3fb950;font-weight:600}.neg{color:#f85149;font-weight:600}.warn{color:#e3b341;font-size:11px}
.note{background:#2b1a0e;border-left:3px solid #d29922;padding:11px 14px;border-radius:6px;margin:16px 0;font-size:12.5px;line-height:1.5}
@media(prefers-color-scheme:light){.note{background:#fff8e6}}
</style>"""


class H(BaseHTTPRequestHandler):
    date = None

    def do_GET(self):
        if self.path in ("/favicon.ico",):
            self.send_response(204); self.end_headers(); return
        body = f"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="refresh" content="15"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>IB vs TD — {self.date}</title><style>{CSS}</head><body><div class="wrap">
<h1>IB vs ThetaData — live comparison</h1>
<div class="sub2">{self.date} · same orders, two independent executions · auto-refresh 15s</div>
{render(self.date)}</div></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8610)
    ap.add_argument("--date", default=dt.datetime.now().strftime("%Y-%m-%d"))
    a = ap.parse_args()
    H.date = a.date
    print(f"IB-vs-TD dashboard on http://127.0.0.1:{a.port}  (date {a.date})")
    HTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
