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
    walls = [num(getattr(r, g, None)) for g in GEXN]
    walls = [w for w in walls if w is not None]
    wstr = " · ".join(f'<i>{i+1}</i> {fmtL(w)}' for i, w in enumerate(walls)) or "—"

    def c(cls, label, v):                       # colored label+value chip
        return f'<span class="{cls}">{label} {fmtL(v)}</span>'

    def row(k, v):
        return f'<div class="row"><span class="k">{k}</span><span class="v">{v}</span></div>'
    allexp = " · ".join([c("cc", "call", num(r.cr)), c("cf", "gamma flip", num(r.hvl)),
                         c("cp", "put", num(r.ps))])
    odte = " · ".join([c("cc", "call", num(r.cr0)), c("cf", "gamma flip", num(r.hvl0)),
                       c("cp", "put", num(r.ps0)), c("cg", "gamma-wall", num(r.gw0))])
    rng = " · ".join([c("ce", "1D min", num(r.d1_min)), c("ce", "1D max", num(r.d1_max))])
    return ('<div class="mlv">'
            + row("All-exp", allexp)
            + row("0DTE", odte)
            + row("GEX walls", wstr)
            + row("1-day", rng)
            + '</div>')


def history_text(hist):
    if len(hist) < 2:
        return ""
    rows = ""
    for _, h in hist.sort_values("date", ascending=False).head(250).iterrows():
        rows += (f'<tr><td>{h["date"]}</td><td>{fmtL(num(h.ps))}</td>'
                 f'<td>{fmtL(num(h.hvl))}</td><td>{fmtL(num(h.cr))}</td>'
                 f'<td>{fmtL(num(h.spot))}</td></tr>')
    return (f'<details class="hist"><summary>history ({len(hist)} days)</summary>'
            f'<div style="max-height:340px;overflow-y:auto">'
            f'<table><tr><th>date</th><th>put</th><th>flip</th><th>call</th><th>spot</th></tr>'
            f'{rows}</table></div></details>')


# scoped under .mqlv so it can embed inside the options dashboard without clashing
_CSS = """
/* palette matches MenthorQ: call=red, put=green, HVL(gamma flip)=orange,
   1D expected move=blue, GEX walls=grey (secondary, no documented color) */
.mqlv{--lvcard:#171b22;--lvink:#e6e9ef;--lvdim:#8b93a1;--lvline:#2a2f3a;--res:#e5484d;
 --sup:#30a46c;--flip:#f76b15;--spot:#3b82f6;--band:#3b82f622;--wall:#8a92a6;--exp:#3b82f6;
 text-align:left;color:var(--lvink);font:14px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}
.mqlv .mlv,.mqlv .ch,.mqlv h2,.mqlv .sub{text-align:left}
.mqlv h2{margin:26px 0 8px;font-size:13px;color:var(--lvdim);text-transform:uppercase;letter-spacing:.06em}
.mqlv .sub{color:var(--lvdim);margin-bottom:8px;font-size:13px}
.mqlv .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:14px}
.mqlv .card{background:var(--lvcard);border:1px solid var(--lvline);border-radius:10px;padding:14px 18px}
.mqlv .ch{display:flex;align-items:center;gap:8px;margin-bottom:34px}
.mqlv .ch .sym{color:var(--lvdim);font-size:12px}
.mqlv .ch .days{margin-left:auto;color:var(--lvdim);font-size:11px;border:1px solid var(--lvline);border-radius:6px;padding:1px 6px}
.mqlv .reg{font-size:11px;padding:1px 7px;border-radius:6px}
.mqlv .reg.pos{background:#22c55e22;color:#4ade80}.mqlv .reg.neg{background:#ef444422;color:#f87171}
.mqlv .ladder{position:relative;height:6px;background:var(--lvline);border-radius:3px;margin:40px 8px 30px}
.mqlv .ladder.empty{background:none;color:var(--lvdim);font-size:12px;height:auto;margin:6px 0}
.mqlv .band{position:absolute;top:-4px;height:14px;background:var(--band);border-radius:3px}
.mqlv .wall{position:absolute;top:-2px;width:1.5px;height:10px;background:var(--wall);opacity:.7;transform:translateX(-.75px)}
.mqlv .mk{position:absolute;top:-5px;width:2px;height:16px;transform:translateX(-1px)}
.mqlv .mk.res{background:var(--res)}.mqlv .mk.sup{background:var(--sup)}.mqlv .mk.flip{background:var(--flip)}
.mqlv .spot{position:absolute;top:-6px;width:11px;height:11px;background:var(--spot);border:2px solid #fff;
 border-radius:50%;transform:translateX(-5.5px);box-shadow:0 0 6px var(--spot)}
.mqlv .lbl{position:absolute;top:16px;left:50%;transform:translateX(-50%);white-space:nowrap;font-size:10px;color:var(--lvdim)}
.mqlv .lbl.up{top:-20px}.mqlv .spot .lbl.up{color:var(--spot);font-weight:600}
.mqlv .mlv{font-size:12px;color:var(--lvink);border-top:1px solid var(--lvline);padding-top:8px}
.mqlv .mlv .row{display:flex;gap:8px;align-items:baseline;margin:3px 0;line-height:1.5}
.mqlv .mlv .k{flex:0 0 78px;color:var(--lvdim);font-weight:600;font-size:10px;
 text-transform:uppercase;letter-spacing:.04em}
.mqlv .mlv .v{flex:1}.mqlv .mlv .v i{color:var(--wall);font-style:normal;font-size:10px;font-weight:700}
.mqlv .mlv .cc{color:var(--res)}.mqlv .mlv .cf{color:var(--flip)}.mqlv .mlv .cp{color:var(--sup)}
.mqlv .mlv .cg{color:var(--wall)}.mqlv .mlv .ce{color:var(--exp)}.mqlv .mlv .v i{color:var(--wall)}
.mqlv .hist{margin-top:8px;font-size:12px}.mqlv .hist summary{cursor:pointer;color:var(--lvdim)}
.mqlv .hist table{border-collapse:collapse;margin-top:6px;width:100%}
.mqlv .hist td,.mqlv .hist th{text-align:right;padding:2px 8px;border-bottom:1px solid var(--lvline)}
.mqlv .hist th{color:var(--lvdim);font-weight:500}.mqlv .hist td:first-child,.mqlv .hist th:first-child{text-align:left}
"""


def load_db():
    if not CSV.exists():
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(CSV)
    return df[df["symbol"].isin(SYMBOLS)] if len(df) else df


def cards_html(db):
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
    return sections


def panel_html(db):
    """Embeddable panel (used by both the standalone page and the dashboard tab)."""
    if db is None or db.empty:
        return ('<div class="mqlv"><div class="sub">No levels captured yet — the nightly '
                'job (23:15) writes the first rows tonight.</div></div>')
    latest = db["date"].max()
    n_sym = db[db["date"] == latest]["symbol"].nunique()
    sub = (f'<div class="sub">snapshot <b>{latest}</b> · {n_sym} instruments · '
           f'{db["date"].nunique()} day(s) stored · '
           '<span style="color:var(--sup)">▏</span>put <span style="color:var(--flip)">▏</span>gamma flip (HVL) '
           '<span style="color:var(--res)">▏</span>call <span style="color:var(--spot)">●</span>spot '
           '<span style="color:var(--wall)">▏</span>GEX walls '
           '<span style="color:var(--exp)">▏</span>1D move · shaded = 0DTE pin (MenthorQ colors)</div>')
    return f'<style>{_CSS}</style><div class="mqlv">{sub}{cards_html(db)}</div>'


def render(db):
    html = (f'<!doctype html><html><head><meta charset="utf-8"><title>MenthorQ Levels DB</title>'
            f'<style>body{{margin:0;background:#0e1116;padding:20px}}'
            f'h1{{color:#e6e9ef;font:600 20px -apple-system,Segoe UI,Roboto,sans-serif;margin:0 0 6px}}'
            f'</style></head><body><h1>MenthorQ Levels — visual database</h1>'
            f'{panel_html(db)}</body></html>')
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
