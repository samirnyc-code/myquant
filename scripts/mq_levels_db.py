"""MenthorQ levels database + visual viewer (S75B).

Two jobs in one, both QUIN-free (uses the direct gamma-levels API, which is not
gated by the QUIN quota):

1. CAPTURE — pull today's FULL level set for every tracked instrument and append one
   row per (date, symbol) to data/menthorq/levels_db.csv (idempotent). Also ingests
   any historical quin_*.json already on disk so past days aren't lost. Replaces the
   locked mq_quin_harvest.py as the clean-levels feed.

2. VIEW — render data/menthorq/levels_db.html: one card per instrument with a visual
   "level ladder" (put/call walls, flip, 0DTE pin band, all gamma walls as ticks, spot),
   the FULL numeric level list, and a day-by-day history strip. Opens in the browser.

Run: .venv/Scripts/python.exe scripts/mq_levels_db.py [--no-pull] [--open]
"""
import datetime as dt
import glob
import json
import sys
import webbrowser
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mq_api import MQ, GW

ROOT = Path(__file__).resolve().parents[1]
HARVEST = ROOT / "data" / "menthorq" / "harvest"
CSV = ROOT / "data" / "menthorq" / "levels_db.csv"
HTML = ROOT / "data" / "menthorq" / "levels_db.html"

FUTURES = ["ES1!", "NQ1!", "RTY1!", "CL1!", "GC1!"]
STOCKS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]
SYMBOLS = ["SPX"] + FUTURES + STOCKS
GROUP = {"SPX": "Index", **{s: "Future" for s in FUTURES}, **{s: "Stock" for s in STOCKS}}
NAMES = {"SPX": "S&P 500", "ES1!": "S&P (ES)", "NQ1!": "Nasdaq (NQ)", "RTY1!": "Russell (RTY)",
         "CL1!": "Crude (CL)", "GC1!": "Gold (GC)", "AAPL": "Apple", "MSFT": "Microsoft",
         "NVDA": "Nvidia", "AMZN": "Amazon", "GOOGL": "Alphabet", "META": "Meta", "TSLA": "Tesla"}

GEXN = [f"gex_{i}" for i in range(1, 11)]  # the 10 gamma walls, ranked by size
COLS = (["date", "symbol", "spot", "cr", "ps", "cr0", "ps0", "hvl", "hvl0", "gw0",
         "d1_min", "d1_max"] + GEXN + ["source"])


def spot_of(mq, sym):
    now = int(dt.datetime.now().timestamp() * 1000)
    try:
        r = mq.s.get(f"{GW}/tickers/{sym}/candles", headers={"authorization": mq.token},
                     params={"interval": "5m", "from": now - 4 * 24 * 3600 * 1000,
                             "to": now, "countBack": 20}, timeout=30)
        c = r.json()
        return float(c[-1]["c"]) if isinstance(c, list) and c else None
    except Exception:
        return None


def pull_today():
    mq = MQ()
    today = dt.date.today().isoformat()
    rows = []
    for sym in SYMBOLS:
        try:
            lv = mq.levels(sym)
        except Exception as e:
            print(f"  {sym}: levels FAIL ({str(e)[:60]})")
            continue
        row = {"date": today, "symbol": sym, "spot": spot_of(mq, sym),
               "cr": lv.get("call_resistance"), "ps": lv.get("put_support"),
               "cr0": lv.get("call_resistance_0dte"), "ps0": lv.get("put_support_0dte"),
               "hvl": lv.get("hvl"), "hvl0": lv.get("hvl_0dte"), "gw0": lv.get("gamma_wall_0dte"),
               "d1_min": lv.get("min_1d"), "d1_max": lv.get("max_1d"), "source": "api"}
        for g in GEXN:
            row[g] = lv.get(g)
        rows.append(row)
        print(f"  {sym}: ok  cr={lv.get('call_resistance')} ps={lv.get('put_support')} "
              f"walls={sum(lv.get(g) is not None for g in GEXN)}")
    return rows


def ingest_quin():
    rows = []
    for f in glob.glob(str(HARVEST / "*" / "quin_*.json")):
        try:
            q = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not q.get("symbol") or not q.get("date"):
            continue
        row = {"date": q["date"], "symbol": q["symbol"], "spot": None,
               "cr": q.get("cr"), "ps": q.get("ps"), "cr0": q.get("cr0"), "ps0": q.get("ps0"),
               "hvl": q.get("hvl"), "hvl0": q.get("hvl0"), "gw0": q.get("gw0"),
               "d1_min": q.get("d1_min"), "d1_max": q.get("d1_max"), "source": "quin"}
        gs = q.get("gex_strikes") or []
        for i, g in enumerate(GEXN):
            row[g] = gs[i] if i < len(gs) else None
        rows.append(row)
    return rows


def build_db(do_pull=True):
    frames = []
    if CSV.exists():
        frames.append(pd.read_csv(CSV))
    frames.append(pd.DataFrame(ingest_quin(), columns=COLS))
    if do_pull:
        frames.append(pd.DataFrame(pull_today(), columns=COLS))
    db = pd.concat([f for f in frames if not f.empty], ignore_index=True)
    db = db[db["symbol"].isin(SYMBOLS)]                       # drop de-listed instruments
    db["_rank"] = db["source"].map({"api": 2, "quin": 1}).fillna(0)
    db = (db.sort_values("_rank").drop_duplicates(["date", "symbol"], keep="last")
            .drop(columns="_rank").sort_values(["date", "symbol"]))
    db.to_csv(CSV, index=False)
    return db


# ------------------------------ view ------------------------------
def num(x):
    try:
        v = float(x)
        return v if v == v else None
    except (TypeError, ValueError):
        return None


def fmtL(v):
    if v is None:
        return "—"
    return f"{v:,.2f}" if abs(v) < 100 else f"{v:,.0f}"


def ladder(r):
    ps, cr, ps0, cr0 = num(r.ps), num(r.cr), num(r.ps0), num(r.cr0)
    hvl, spot = num(r.hvl), num(r.spot)
    walls = [num(getattr(r, g, None)) for g in GEXN]
    walls = [w for w in walls if w is not None]
    pts = [v for v in [ps, cr, ps0, cr0, hvl, spot, *walls] if v is not None]
    if len(pts) < 2:
        return '<div class="ladder empty">no level data</div>'
    lo, hi = min(pts), max(pts)
    pad = (hi - lo) * 0.06 or 1
    lo, hi = lo - pad, hi + pad
    def pct(x):
        return None if x is None else max(0, min(100, (x - lo) / (hi - lo) * 100))
    p = ['<div class="ladder">']
    if ps0 is not None and cr0 is not None:
        a, b = sorted([pct(ps0), pct(cr0)])
        p.append(f'<div class="band" style="left:{a}%;width:{b-a}%"></div>')
    for w in walls:                                          # all gamma walls as grey ticks
        p.append(f'<div class="wall" style="left:{pct(w)}%"></div>')
    def mark(x, cls, lbl, below=True):
        q = pct(x)
        if q is None:
            return ""
        pos = "lbl" if below else "lbl up"
        return f'<div class="mk {cls}" style="left:{q}%"><span class="{pos}">{lbl}</span></div>'
    p.append(mark(ps, "sup", f"put {fmtL(ps)}"))
    p.append(mark(cr, "res", f"call {fmtL(cr)}"))
    p.append(mark(hvl, "flip", f"flip {fmtL(hvl)}"))
    if spot is not None:
        p.append(f'<div class="spot" style="left:{pct(spot)}%"><span class="lbl up">'
                 f'spot {fmtL(spot)}</span></div>')
    p.append("</div>")
    return "".join(p)


def levels_text(r):
    walls = [fmtL(num(getattr(r, g, None))) for g in GEXN if num(getattr(r, g, None)) is not None]
    bits = [
        f'<b>Call wall</b> {fmtL(num(r.cr))} <span class=d>(0DTE {fmtL(num(r.cr0))})</span>',
        f'<b>Flip</b> {fmtL(num(r.hvl))} <span class=d>(0DTE {fmtL(num(r.hvl0))})</span>',
        f'<b>Put wall</b> {fmtL(num(r.ps))} <span class=d>(0DTE {fmtL(num(r.ps0))})</span>',
        f'<b>0DTE gamma wall</b> {fmtL(num(r.gw0))}',
        f'<b>1-day range</b> {fmtL(num(r.d1_min))} – {fmtL(num(r.d1_max))}',
        f'<b>Gamma walls</b> {", ".join(walls) if walls else "—"}',
    ]
    return '<div class="lv">' + " · ".join(bits) + "</div>"


def history_text(hist):
    if len(hist) < 2:
        return ""
    rows = ""
    for _, h in hist.sort_values("date", ascending=False).head(6).iterrows():
        rows += (f'<tr><td>{h["date"]}</td><td>{fmtL(num(h.ps))}</td>'
                 f'<td>{fmtL(num(h.hvl))}</td><td>{fmtL(num(h.cr))}</td>'
                 f'<td>{fmtL(num(h.spot))}</td></tr>')
    return (f'<details class="hist"><summary>history ({len(hist)} days)</summary>'
            f'<table><tr><th>date</th><th>put</th><th>flip</th><th>call</th><th>spot</th></tr>'
            f'{rows}</table></details>')


def render(db):
    latest = db["date"].max()
    today = db[db["date"] == latest].set_index("symbol")
    groups = {"Index": [], "Future": [], "Stock": []}
    for sym in SYMBOLS:
        if sym not in today.index:
            continue
        r = today.loc[sym]
        hist = db[db["symbol"] == sym]
        reg = ""
        s, h = num(r.spot), num(r.hvl)
        if s is not None and h is not None:
            reg = ('<span class="reg pos">above flip</span>' if s >= h
                   else '<span class="reg neg">below flip</span>')
        groups[GROUP[sym]].append(f"""
        <div class="card">
          <div class="ch"><b>{NAMES.get(sym, sym)}</b><span class="sym">{sym}</span>{reg}
            <span class="days">{hist['date'].nunique()}d</span></div>
          {ladder(r)}
          {levels_text(r)}
          {history_text(hist)}
        </div>""")
    sections = ""
    for g, title in (("Index", "Index"), ("Future", "Futures"), ("Stock", "Stocks — Mag 7")):
        if groups[g]:
            sections += f'<h2>{title}</h2><div class="grid">{"".join(groups[g])}</div>'
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>MenthorQ Levels DB</title><style>
:root{{--bg:#0e1116;--card:#171b22;--ink:#e6e9ef;--dim:#8b93a1;--line:#2a2f3a;
 --res:#ef4444;--sup:#22c55e;--flip:#eab308;--spot:#3b82f6;--band:#3b82f622;--wall:#6b7280}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);
 font:14px/1.45 -apple-system,Segoe UI,Roboto,sans-serif;padding:20px}}
h1{{margin:0 0 2px;font-size:20px}}h2{{margin:26px 0 8px;font-size:13px;color:var(--dim);
 text-transform:uppercase;letter-spacing:.06em}}.sub{{color:var(--dim);margin-bottom:8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 18px 14px}}
.ch{{display:flex;align-items:center;gap:8px;margin-bottom:34px}}
.ch .sym{{color:var(--dim);font-size:12px}}.ch .days{{margin-left:auto;color:var(--dim);
 font-size:11px;border:1px solid var(--line);border-radius:6px;padding:1px 6px}}
.reg{{font-size:11px;padding:1px 7px;border-radius:6px}}
.reg.pos{{background:#22c55e22;color:#4ade80}}.reg.neg{{background:#ef444422;color:#f87171}}
.ladder{{position:relative;height:6px;background:var(--line);border-radius:3px;margin:40px 8px 30px}}
.ladder.empty{{background:none;color:var(--dim);font-size:12px;height:auto;margin:6px 0}}
.band{{position:absolute;top:-4px;height:14px;background:var(--band);border-radius:3px}}
.wall{{position:absolute;top:-2px;width:1px;height:10px;background:var(--wall);opacity:.5;transform:translateX(-.5px)}}
.mk{{position:absolute;top:-5px;width:2px;height:16px;transform:translateX(-1px)}}
.mk.res{{background:var(--res)}}.mk.sup{{background:var(--sup)}}.mk.flip{{background:var(--flip)}}
.spot{{position:absolute;top:-6px;width:11px;height:11px;background:var(--spot);
 border:2px solid #fff;border-radius:50%;transform:translateX(-5.5px);box-shadow:0 0 6px var(--spot)}}
.lbl{{position:absolute;top:16px;left:50%;transform:translateX(-50%);white-space:nowrap;
 font-size:10px;color:var(--dim)}}.lbl.up{{top:-20px}}.spot .lbl.up{{color:var(--spot);font-weight:600}}
.lv{{font-size:12px;color:var(--ink);line-height:1.7;border-top:1px solid var(--line);padding-top:8px}}
.lv b{{color:var(--dim);font-weight:600}}.lv .d{{color:var(--dim);font-size:11px}}
.hist{{margin-top:8px;font-size:12px}}.hist summary{{cursor:pointer;color:var(--dim)}}
.hist table{{border-collapse:collapse;margin-top:6px;width:100%}}
.hist td,.hist th{{text-align:right;padding:2px 8px;border-bottom:1px solid var(--line)}}
.hist th{{color:var(--dim);font-weight:500}}.hist td:first-child,.hist th:first-child{{text-align:left}}
@media(prefers-color-scheme:light){{:root{{--bg:#f6f7f9;--card:#fff;--ink:#111;--dim:#666;--line:#e3e6ea}}}}
</style></head><body>
<h1>MenthorQ Levels — visual database</h1>
<div class="sub">snapshot <b>{latest}</b> · {len(today)} instruments · {db['date'].nunique()} day(s) stored ·
 <span style="color:var(--sup)">▏</span>put <span style="color:var(--flip)">▏</span>flip
 <span style="color:var(--res)">▏</span>call <span style="color:var(--spot)">●</span>spot
 <span style="color:var(--wall)">▏</span>gamma walls · shaded = 0DTE pin · numbers + history under each</div>
{sections}
</body></html>"""
    HTML.write_text(html, encoding="utf-8")
    return HTML


def main():
    db = build_db(do_pull="--no-pull" not in sys.argv)
    out = render(db)
    print(f"\nDB: {CSV}  ({len(db)} rows, {db['date'].nunique()} days, {db['symbol'].nunique()} symbols)")
    print(f"VIEW: {out}")
    if "--open" in sys.argv:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
