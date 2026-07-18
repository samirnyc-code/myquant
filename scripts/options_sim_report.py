"""Render the options forward-sim state into one HTML dashboard (S73).

Reads decisions.csv + trades.parquet + the quote tapes and writes
data/options_sim/report.html — open it in a browser after any daemon run:

  .venv/Scripts/python.exe scripts/options_sim_report.py
"""
import datetime as dt
import glob
import json
from pathlib import Path

import pandas as pd

import options_trade_log as tlog

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "options_sim"
PARAMS = {"strategy": "bps_stmr (causal 15:59)", "structure": "SPXW bull put spread",
          "short leg": "~30Δ put", "width": "50 pts", "DTE": "14 (nearest)",
          "entry": "K8 < 15 AND spot > SMA100 @ 15:59 ET",
          "exit": "spot > SMA5 @ 15:59 ET, else settle at expiry",
          "fill": "real OPRA NBBO, first quote ≥ 16:00 ET, sell-bid/buy-ask",
          "fees": "$1.30/contract"}

CSS = """
body{font:14px/1.5 system-ui,Segoe UI,sans-serif;margin:0;background:#0f1115;color:#d7dae0}
.wrap{max-width:1100px;margin:0 auto;padding:24px}
h1{font-size:20px} h2{font-size:15px;margin:26px 0 8px;color:#8ab4f8}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{padding:5px 9px;text-align:right;border-bottom:1px solid #23262d}
th{color:#9aa0a6;font-weight:600} td:first-child,th:first-child{text-align:left}
.pos{color:#4cc38a}.neg{color:#f2555a}.fire{color:#f2b84b;font-weight:700}
.kv{display:grid;grid-template-columns:160px 1fr;gap:2px 14px;font-size:13px}
.kv b{color:#9aa0a6;font-weight:600}
.card{background:#161920;border:1px solid #23262d;border-radius:10px;padding:14px 18px;margin:10px 0}
.stat{display:inline-block;margin-right:26px}.stat b{display:block;font-size:11px;color:#9aa0a6}
.stat span{font-size:19px;font-weight:700}
.muted{color:#7a808a}
"""


def cls(v):
    try:
        return "pos" if float(v) > 0 else ("neg" if float(v) < 0 else "")
    except (TypeError, ValueError):
        return ""


def tbl(df, money=(), signal_col=None):
    if df is None or len(df) == 0:
        return "<p class='muted'>nothing yet</p>"
    h = "".join(f"<th>{c}</th>" for c in df.columns)
    rows = []
    for _, r in df.iterrows():
        tds = []
        for c in df.columns:
            v = r[c]
            klass = cls(v) if c in money else ""
            if c == signal_col and v is True:
                klass, v = "fire", "FIRE"
            if isinstance(v, float):
                v = f"{v:+,.0f}" if c in money else f"{v:,.2f}"
            tds.append(f"<td class='{klass}'>{'' if v is None or v != v else v}</td>"
                       if not isinstance(v, str) else f"<td class='{klass}'>{v}</td>")
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return f"<table><tr>{h}</tr>{''.join(rows)}</table>"


def main():
    trades = tlog.load()
    if len(trades):
        trades = trades.copy()
        trades["legs"] = trades.legs.map(
            lambda s: " / ".join(f"{l['side'][0].upper()} {l['strike']:.0f}P {l['expiry']}"
                                 for l in json.loads(s)) if isinstance(s, str) else s)
    dec_f = OUT / "decisions.csv"
    dec = pd.read_csv(dec_f).tail(30).iloc[::-1] if dec_f.exists() else None

    closed = trades[trades.exit_dt.notna()] if len(trades) else trades
    p = closed.pnl.astype(float) if len(closed) else pd.Series(dtype=float)
    pf = (p[p > 0].sum() / -p[p < 0].sum()) if len(p) and (p < 0).any() else None
    stats = [("closed trades", len(closed)), ("open", len(trades) - len(closed)),
             ("win %", f"{(p > 0).mean() * 100:.0f}%" if len(p) else "—"),
             ("PF", f"{pf:.2f}" if pf else "—"),
             ("total P&L", f"${p.sum():+,.0f}" if len(p) else "—")]

    tapes = sorted(glob.glob(str(OUT / "quotes_*.csv")))
    tape_rows = []
    for f in tapes[-10:]:
        q = pd.read_csv(f)
        tape_rows.append({"tape": Path(f).name, "quotes": len(q),
                          "first": q.ts_et.iloc[0] if len(q) else "", "last": q.ts_et.iloc[-1] if len(q) else ""})

    kv = "".join(f"<b>{k}</b><span>{v}</span>" for k, v in PARAMS.items())
    st = "".join(f"<div class='stat'><b>{k}</b><span>{v}</span></div>" for k, v in stats)
    html = f"""<!doctype html><meta charset="utf-8"><title>Options Forward-Sim</title>
<style>{CSS}</style><div class="wrap">
<h1>Options Forward-Sim — causal 15:59 BPS on OPRA</h1>
<p class="muted">generated {dt.datetime.now():%Y-%m-%d %H:%M} · data: data/options_sim/ + data/options_log/trades.parquet</p>
<div class="card">{st}</div>
<h2>Setup parameters</h2><div class="card kv">{kv}</div>
<h2>Trades</h2>{tbl(trades[["trade_id","entry_dt","exit_dt","legs","credit","exit_cost","collateral","pnl","slippage","vix","vix_rank","er10","dow","fill_model"]] if len(trades) else trades, money=("pnl",))}
<h2>Decisions (last 30 runs, newest first)</h2>{tbl(dec, signal_col="fire")}
<h2>Fill tapes (16:00–16:15 NBBO logs)</h2>{tbl(pd.DataFrame(tape_rows))}
</div>"""
    out = OUT / "report.html"
    OUT.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}")
    return out


if __name__ == "__main__":
    main()
