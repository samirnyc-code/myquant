"""book_review.py — interactive forward-reveal REVIEW tool for THE BOOK (2E + SMA20 + skip-TD).
Self-contained: stdlib HTTP server + canvas front-end. Run it, open the browser, review 5 years
of trade-days bar-by-bar, toggle every overlay, grade/comment setups, label day-types, and it
saves everything to committed JSON so I can learn from your annotations.

  python scripts/book_review.py           # -> http://localhost:8640
Data:  data/annotations/book_review/<date>.json   (from book_review_prep.py)
Notes: data/annotations/book_review_notes/<date>.json   (your grades/comments/day-types)

Features: forward reveal (space/step/show-all) · jump next-setup / next-ungraded · toggles
(regime shading, SMA20, prior HLC, prior last-bar, gap, IB, bar#s, book-only vs all) · click a
bar or setup to grade(A/B/C)+comment+take/skip · intermediate & final day-type · setup filter
(all/long/short/win/loss/in-book) · live stats · no-lookahead (annotations keyed to reveal bar).
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAYS = ROOT / "data" / "annotations" / "book_review"
NOTES = ROOT / "data" / "annotations" / "book_review_notes"
NOTES.mkdir(parents=True, exist_ok=True)
PORT = 8640
sys.path.insert(0, str(Path(__file__).resolve().parent))   # for revdetect

# --- live MyReversals recompute ---------------------------------------------
# Detection runs on the EXACT per-day bars ChartSim draws (concatenated into a
# continuous RTH series so cross-day lookbacks / avg-range / first-bar match NT),
# so recomputed markers always land on the right bars. revdetect.py is the
# validated port of MyReversals.cs (S89: 97.4% signal match vs Thomas's NT export).
_CONT = None
_TYPE_LETTER = {"Trap": "T", "BO": "B", "OB": "O", "IB": "I"}


def _continuous():
    """Continuous RTH 5M DataFrame rebuilt from the per-day review JSON (cached)."""
    global _CONT
    if _CONT is not None:
        return _CONT
    import pandas as pd
    rows = []
    for f in sorted(DAYS.glob("2*.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        dt = d["date"]
        for b in d["bars"]:   # b = [within-day idx, "HH:MM", O, H, L, C, ema20]
            rows.append((f"{dt} {b[1]}", dt, b[0], b[2], b[3], b[4], b[5]))
    df = pd.DataFrame(rows, columns=["DateTime", "Date", "bar", "Open", "High", "Low", "Close"])
    df["DateTime"] = pd.to_datetime(df["DateTime"])
    _CONT = df
    return _CONT


_CSVSIG = None


def csv_signals():
    """Parse Thomas's NT MyReversals export (data/signals/*RTH*.txt, newest) into
    {date: [[ftbar, dir(+1/-1), typeletter, revbar, btc, stop, lmt], ...]}.
    NT stamps bars by CLOSE time and 1-indexes BarNo; ChartSim indexes bars by OPEN
    time from 0 -> the FT/confirmation bar is BarNo-1, the reversal bar is BarNo-2
    (verified: LMT/stop == rev bar high/low exactly). Drawn like the computed 'rev'
    overlay (stripe + blue dot on rev bar + triangle on FT bar) but from this CSV only."""
    global _CSVSIG
    if _CSVSIG is not None:
        return _CSVSIG
    out = {}
    sigdir = ROOT / "data" / "signals"
    files = sorted(sigdir.glob("*RTH*Days.txt"), key=lambda f: f.stat().st_mtime)
    if files:
        tl = {"BO": "B", "Trap": "T", "IB": "I", "OB": "O"}
        for ln in files[-1].read_text().splitlines():
            p = ln.split()
            if len(p) != 9 or not p[0].isdigit():
                continue
            _, rt, dr, dt, tm, bn, btc, stop, lmt = p
            try:
                dd, mm, yy = dt.split("/")
                iso = f"{yy}-{mm}-{dd}"
                num = lambda s: float(s.replace(",", ""))
                ft = int(bn) - 1        # FT/triangle bar (ChartSim open-time index)
                out.setdefault(iso, []).append(
                    [ft, 1 if dr.lower().startswith("l") else -1,
                     tl.get(rt, rt[:1]), ft - 1, num(btc), num(stop), num(lmt)])
            except Exception:
                continue
    _CSVSIG = out
    return _CSVSIG


def recalc_revs(params):
    """Run revdetect with `params`, return {date: [[ftbar,dir,typeletter,revbar,entry,stop],...]}."""
    import revdetect
    sg = revdetect.detect(_continuous(), params or {})
    out = {}
    for r in sg.itertuples(index=False):
        ftbar = int(r.bar)
        out.setdefault(r.Date, []).append(
            [ftbar, int(r.side), _TYPE_LETTER.get(r.rev, str(r.rev)[:1]),
             ftbar - 1, round(float(r.entry), 2), round(float(r.stop), 2)])
    return out

DAYTYPES = ["Trend", "Trend-from-open", "Trend reversal", "Tight channel", "Broad channel",
            "Trading range", "TR breakout", "Double-distribution trend", "Normal (Dalton)",
            "Normal-variation", "Neutral (Dalton)", "Non-trend", "Other"]

_PATHS = None


def build_paths():
    """R-multiple price path (entry->exit, per bar close) for every in-book trade, from disk.
    R = (px-entry)/risk, sign-adjusted for direction; risk = |entry-stop|. Cached."""
    global _PATHS
    if _PATHS is not None:
        return _PATHS
    win, loss = [], []
    for f in sorted(DAYS.glob("2*.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        closes = [b[5] for b in d["bars"]]
        for t in d["trades"]:
            if not t.get("in_book"):
                continue
            risk = abs(t["entry_px"] - t["stop"]) or 0.25
            sgn = 1.0 if t["dir"] == "L" else -1.0
            eb, xb = t["entry_bar"], min(t["exit_bar"], len(closes) - 1)
            path = [round(sgn * (closes[i] - t["entry_px"]) / risk, 3) for i in range(eb, xb + 1)]
            path = [0.0] + path if not path or path[0] != 0.0 else path
            (win if t["net"] > 0 else loss).append({"date": d["date"], "dir": t["dir"], "net": t["net"], "r": path})
    _PATHS = {"win": win, "loss": loss}
    return _PATHS

HTML = r"""<!doctype html><html><head><meta charset=utf-8><title>Book Review</title>
<style>
:root{--bg:#0f1216;--sf:#1a1f26;--ln:#2b333d;--tx:#e6e9ec;--mut:#8b93a0;--grn:#2ecc71;--red:#e74c3c;--blu:#4a9eff;--yel:#f1c40f}
body.light{--bg:#f4f5f7;--sf:#ffffff;--ln:#d5dae1;--tx:#1c2530;--mut:#5c6673}
body.grey{--bg:#9a9a9a;--sf:#b8b8b8;--ln:#828282;--tx:#141414;--mut:#3a3a3a}
body.grey canvas{background:#b0b0b0}
body.grey button,body.grey select{background:#c4c4c4;color:#141414;border-color:#8a8a8a}
body.grey button:hover{background:#b7b7b7}
body.grey .pill,body.grey input,body.grey textarea{background:#c9c9c9;color:#141414;border-color:#8a8a8a}
body.grey #settings,body.grey #modal>div,body.grey #lens>div,body.grey #revpanel{background:#c4c4c4!important;color:#141414}
body.grey #settings *,body.light #settings *,body.grey #revpanel *,body.light #revpanel *{color:#1c2530!important}
body.light #revpanel{background:#fff!important;color:#1c2530}
#revpanel input[type=number]{width:52px;background:#0c0f13;color:#e6e9ec;border:1px solid #2b333d;border-radius:4px;padding:2px 4px;font-size:11px}
body.light #revpanel input[type=number],body.grey #revpanel input[type=number]{background:#fff;color:#1c2530}
.rvg{margin:7px 0 2px;color:#e67e22;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.3px}
.rvr{display:flex;align-items:center;justify-content:space-between;gap:6px;margin:2px 0;font-size:11.5px}
body.light canvas{background:#fbfbfa}
body.light textarea,body.light input{background:#fff;color:#1c2530;border-color:#d5dae1}
body.light button,body.light select{background:#eef0f3;color:#1c2530;border-color:#cfd5dd}
body.light button:hover{background:#e2e6ea}
body.light button.on{background:#cdeecd;border-color:#27a844;color:#14361d}
body.light .pill{background:#eef0f3;border-color:#cfd5dd;color:#1c2530}
body.light #settings,body.light #modal>div,body.light #lens>div{background:#fff!important;color:#1c2530}
body.light #sidebtn{background:#4a9eff;color:#fff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:13px/1.4 system-ui,sans-serif;display:flex;flex-direction:column;height:100vh;overflow:hidden}
#top{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:6px 10px;background:var(--sf);border-bottom:1px solid var(--ln)}
#top b{color:var(--blu)} button,select{background:#232a33;color:var(--tx);border:1px solid var(--ln);border-radius:5px;padding:4px 8px;cursor:pointer;font-size:12px}
button:hover{background:#2c3440} button.on{background:#204a2e;border-color:var(--grn)}
.tog{display:inline-flex;align-items:center;gap:3px} .tog input{accent-color:var(--grn)}
#wrap{display:flex;flex:1;min-height:0} #chart{flex:1;min-width:0;position:relative}
canvas{display:block;background:#0c0f13}
#side{width:320px;background:var(--sf);border-left:1px solid var(--ln);padding:9px;overflow:auto;font-size:12px;transition:width .12s}
.pill{background:#232a33;border:1px solid var(--ln);border-radius:10px;padding:2px 8px;font-size:11px}
h4{margin:10px 0 5px;color:var(--mut);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.4px}
textarea{width:100%;background:#0c0f13;color:var(--tx);border:1px solid var(--ln);border-radius:5px;padding:5px;resize:vertical;font:12px sans-serif}
.gr{display:flex;gap:4px}.gr button{flex:1}
.stat{display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid #222}
.win{color:var(--grn)}.loss{color:var(--red)}
/* toolbar groups (S91e): cluster the ~40 controls into labelled boxes, Time first */
#top{gap:6px}
.grp{display:inline-flex;align-items:center;gap:5px;flex-wrap:wrap;padding:3px 7px 3px 6px;
  border:1px solid var(--ln);border-radius:7px;background:#20262e;position:relative}
.grp>.glab{color:var(--mut);font-size:9.5px;text-transform:uppercase;letter-spacing:.5px;
  font-weight:700;margin-right:2px;opacity:.8}
body.light .grp{background:#eef0f3}
#tf{font-weight:700}
.grp .sep{width:1px;height:16px;background:var(--ln);margin:0 1px}
</style></head><body>
<div id=top>
 <b id=dt>—</b><span style="color:#2ecc71;font-size:10px" title="build tag — changes when new code loads">v24</span>

 <span class=grp><span class=glab>time</span>
  <select id=tf onchange=setTF(this.value) title="bar timeframe — 5M (base) / 15M / Daily"><option value=5 selected>5M</option><option value=15>15M</option><option value=D>D</option></select>
  <select id=daysel onchange=goDay(this.value)></select>
  <button onclick=nav(-1) title="previous day">◀</button><button onclick=nav(1) title="next day">▶</button>
  <button onclick=jumpUngraded() title="next ungraded day">ungr</button>
  <span class=sep></span>
  <span class=pill>reveal <b id=rev>0</b>/<b id=nb>0</b></span>
  <button onclick=play()><span id=playlbl>▶ play</span></button>
  <button onclick=step(-1) title="step back">◀</button><button onclick=step(1) title="step fwd">▶</button>
  <button onclick=showAll() title="reveal whole day">all</button>
  <button onclick=nextSetup() title="jump to next setup">setup ⤼</button>
  <select id=spd title="play speed"><option value=350>slow</option><option value=150 selected>med</option><option value=50>fast</option></select>
 </span>

 <span class=grp><span class=glab>setups</span>
  <select id=filt onchange=render() title="filter trades"><option value=all>all</option><option value=book>in-book</option><option value=fade>fades (f2E)</option><option value=L>long</option><option value=S>short</option><option value=win>winners</option><option value=loss>losers</option></select>
  <span class=tog><input type=checkbox id=t_2el checked onchange=render()>2EL</span>
  <span class=tog><input type=checkbox id=t_2es checked onchange=render()>2ES</span>
  <span class=tog><input type=checkbox id=t_f2el checked onchange=render()>f2EL</span>
  <span class=tog><input type=checkbox id=t_f2es checked onchange=render()>f2ES</span>
  <span class=sep></span>
  <span class=tog title="MyReversals indicator markers: ▲green FT-long / ▼red FT-short at the FT bar, blue dot on the reversal bar, T/B/O/I = Trap/BO/OB/IB"><input type=checkbox id=t_rev checked onchange=render()>rev</span>
  <span class=tog title="Thomas's NT MyReversals EXPORT (this CSV): diamond at limit entry + dashed stop, T/B/I letter. Separate from the computed 'rev' markers and the book trades."><input type=checkbox id=t_csv onchange=render()><b style="color:#e67e22">NT csv</b></span>
  <span class=tog title="FINAL BO SETUP: BO type, entry >=11:00, skip gap days, MARKET entry, 2R target (flat at close). Tick-accurate P&L."><input type=checkbox id=t_bo onchange=render()><b style="color:#16c60c">BO</b></span>
  <button onclick=jumpBO() title="jump to next day that has a BO setup trade (only ~227 days have one)" style="border-color:#16c60c;color:#16c60c">BO ▶</button>
  <span class=sep></span>
  <span class=tog title="L2 ABSORPTION at each setup's pullback level (badge + depth strip). Only days with recorded depth (2026-07-21..28 + going forward) show data."><input type=checkbox id=t_absorb onchange=render()><b style="color:#f1c40f">absorb</b></span>
  <span class=tog title="only days AFTER a trend day (prior range > 1.6xADR10) — the book skips these"><input type=checkbox id=t_skip onchange=applyDayFilter()>skip-days<b id=skipn></b></span>
  <button onclick=openPaths() title="winner/loser path cloud">W/L 📈</button>
 </span>

 <span class=grp><span class=glab>overlays</span>
  <span class=tog><input type=checkbox id=t_reg checked onchange=render()>regime</span>
  <span class=tog><input type=checkbox id=t_ema checked onchange=render()>EMA20</span>
  <span class=tog><input type=checkbox id=t_gap onchange=render()>gap</span>
  <span class=tog><input type=checkbox id=t_tr checked onchange=render()>trades</span>
  <span class=tog><input type=checkbox id=t_num checked onchange=render()>bar#</span>
  <span class=tog><input type=checkbox id=t_lbl checked onchange=render()>labels</span>
  <span class=tog><input type=checkbox id=t_piv onchange=render()>piv</span>
  <span class=tog><input type=checkbox id=t_pivM checked onchange=render()>maj</span>
  <span class=tog><input type=checkbox id=t_pivm checked onchange=render()>min</span>
  <span class=tog><input type=checkbox id=t_ob onchange=render()>OB</span>
  <span class=tog title="show the prior session's last bar + gap line (uncheck to readjust the chart to today only after a large gap)"><input type=checkbox id=t_prev checked onchange=render()>prev bar</span>
  <span class=tog title="Globex (overnight) high/low on the RTH chart"><input type=checkbox id=t_gx onchange=render()>GX H/L</span>
 </span>

 <span class=grp><span class=glab>view</span>
  <span class=tog title="chart theme"><select id=theme onchange=applyTheme(this.value)><option value=dark>dark</option><option value=light>light</option><option value=grey>grey · NT (Thomas)</option></select></span>
  <span style=color:var(--mut) title="line levels are configured in ⚙">Y</span><input type=range id=yzoom min=0.5 max=3.5 step=0.1 value=1 oninput=render() style="width:52px" title="Y compress/expand">
  <span style=color:var(--mut)>X</span><input type=range id=xzoom min=0.5 max=7 step=0.1 value=1 oninput=render() style="width:52px" title="X compress/expand">
  <span style=color:var(--mut)>pan</span><input type=range id=panx min=0 max=1 step=0.01 value=1 oninput=render() style="width:52px" title="horizontal pan">
  <button onclick="document.getElementById('yzoom').value=1;document.getElementById('xzoom').value=1;document.getElementById('panx').value=1;showPanel()" title="reset zoom + show panel">⟲</button>
  <button id=lensbtn onclick=toggleLens() title="movable magnifier">🔍</button>
  <button onclick=toggleSettings() title="colors &amp; opacity / line levels">⚙</button>
  <button onclick=toggleRevPanel() title="MyReversals detection parameters — adjust &amp; recalculate all signals" style="border-color:#e67e22;color:#e67e22">⚑</button>
  <button onclick=toggleSide() title="show/hide the side panel (P)" style="background:#4a9eff;color:#fff;font-weight:700">⊞</button>
 </span>
</div>
<canvas id=lenscv width=200 height=200 style="position:fixed;border-radius:50%;border:2px solid #4a9eff;box-shadow:0 6px 28px rgba(0,0,0,.6);pointer-events:none;display:none;z-index:120"></canvas>
<div id=lvltip style="display:none;position:fixed;z-index:140;background:#0f1216;color:#e6e9ec;border:1px solid #4a9eff;border-radius:5px;padding:4px 8px;font-size:12px;line-height:1.35;pointer-events:none;box-shadow:0 4px 16px rgba(0,0,0,.45)"></div>
<div id=settings style="display:none;position:absolute;top:80px;right:250px;z-index:8;background:#1a1f26;border:1px solid #2b333d;border-radius:8px;padding:10px;width:224px;box-shadow:0 6px 24px #000a">
 <b style="color:#4a9eff">colors &amp; opacity</b><div id=setbody style="margin-top:6px"></div>
 <button style="margin-top:8px;width:100%" onclick=resetCfg()>reset defaults</button>
</div>
<div id=revpanel style="display:none;position:absolute;top:80px;right:12px;z-index:8;background:#1a1f26;border:1px solid #e67e22;border-radius:8px;padding:10px;width:300px;max-height:82vh;overflow:auto;box-shadow:0 6px 24px #000a">
 <div style="display:flex;justify-content:space-between;align-items:center">
  <b style="color:#e67e22">MyReversals parameters</b>
  <button onclick=toggleRevPanel() style="padding:2px 7px">✕</button></div>
 <div style="color:#8b93a0;font-size:10px;margin:4px 0 6px">Thomas's NT settings. Change any, then <b>Recalculate</b> to redraw every chart's signals.</div>
 <div id=revbody></div>
 <div style="position:sticky;bottom:0;background:#1a1f26;padding-top:8px;margin-top:6px;border-top:1px solid #2b333d">
  <button style="width:100%;background:#e67e22;color:#111;font-weight:700;border-color:#e67e22" onclick=recalcRevs()>↻ Recalculate all signals</button>
  <button style="width:100%;margin-top:5px" onclick=resetRevParams()>reset to Thomas defaults</button>
  <div id=revstatus style="color:#8b93a0;font-size:11px;margin-top:5px;text-align:center">showing baked signals — recalculate to apply panel values</div>
 </div>
</div>
<div id=wrap><div id=chart><canvas id=cv></canvas></div>
<div id=side>
 <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:2px"><b style="color:var(--mut);font-size:11px">PANEL</b><button onclick=hidePanel() title="collapse panel" style="padding:2px 8px">⟩ hide</button></div>
 <h4>day</h4><div id=dayinfo></div>
 <h4>levels (● on-screen ○ off)</h4><div id=levels></div>
 <h4>day type</h4>
 <div class=stat>intermediate @bar <b id=ibar>—</b> <select id=dti onchange=saveDay()></select></div>
 <div class=stat>final <select id=dtf onchange=saveDay()></select></div>
 <h4>selected setup</h4><div id=selinfo style=color:var(--mut)>click a setup or bar</div>
 <div id=selpanel style=display:none>
  <div id=tagwrap style="display:none;margin-bottom:4px"><input id=tagname placeholder="name this bar (e.g. failed BO, HL, spike)" style="width:100%;padding:4px;border-radius:5px" oninput=saveTagName()></div>
  <div class=gr><button onclick=grade('A')>A</button><button onclick=grade('B')>B</button><button onclick=grade('C')>C</button><button onclick=grade('F')>F</button></div>
  <div class=gr style=margin-top:4px><button onclick=takeskip('take')>take ✓</button><button onclick=takeskip('skip')>skip ✕</button></div>
  <textarea id=note rows=3 placeholder="why? (your read)" oninput=saveSel()></textarea>
  <button style="width:100%;margin-top:4px" onclick=openLens()>🔍 zoom this setup</button>
 </div>
 <h4>stats (filter)</h4><div id=stats></div>
 <h4>NT csv setups · day P&amp;L (1R tgt, $17.5 RT)</h4><div id=csvstats style=color:var(--mut)>—</div>
 <h4 style="color:#16c60c">BO setup · day P&amp;L (2R, tick)</h4><div id=bostats style=color:var(--mut)>—</div>
</div></div>
<div id=modal style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:9">
 <div style="position:absolute;top:3%;left:3%;right:3%;bottom:3%;background:#1a1f26;border:1px solid #2b333d;border-radius:8px;padding:12px;display:flex;flex-direction:column">
  <div style="display:flex;justify-content:space-between;align-items:center">
   <b style="color:#4a9eff">Winner vs Loser price paths — R-multiple by bars-since-entry (in-book trades)</b>
   <span>
    <span class=tog><input type=checkbox id=p_win checked onchange=drawPaths()>winners</span>
    <span class=tog><input type=checkbox id=p_loss checked onchange=drawPaths()>losers</span>
    <span class=tog><input type=checkbox id=p_med checked onchange=drawPaths()>medians</span>
    <select id=p_dir onchange=drawPaths()><option value=all>both dirs</option><option value=L>long</option><option value=S>short</option></select>
    <button onclick="document.getElementById('modal').style.display='none'">✕ close</button>
   </span></div>
  <canvas id=pcv style="flex:1;background:#0c0f13;margin-top:8px;border-radius:5px"></canvas>
  <div id=pstats style="color:#8b93a0;margin-top:6px;font-size:12px"></div>
 </div></div>
<div id=lens style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:9">
 <div style="position:absolute;top:6%;left:8%;right:8%;bottom:6%;background:#12161b;border:1px solid #2b333d;border-radius:8px;padding:10px;display:flex;flex-direction:column">
  <div style="display:flex;justify-content:space-between;align-items:center">
   <b id=lenstitle style="color:#4a9eff">setup lens</b>
   <span>zoom <input type=range id=lpad min=4 max=45 value=10 oninput=drawLens() style="vertical-align:middle" title="bars each side of entry — lower = more zoom"> <button onclick="document.getElementById('lens').style.display='none'">✕ close</button></span></div>
  <canvas id=lcv style="flex:1;background:#0c0f13;margin-top:8px;border-radius:5px"></canvas>
 </div></div>
<script>
const DTS=__DTS__;
let PATHS=null;
const CFG_DEF={cUp:'#26a65b',cDn:'#d64541',cEma:'#3aa0ff',cBull:'#2ecc71',cBear:'#e74c3c',
 cIb:'#4a9eff',cEntry:'#ffffff',cStop:'#ff5a5a',cTrig:'#f1c40f',regOp:0.10,ibOp:0.06,ibFill:1,bg:'#0c0f13',
 tl:{entry:{w:1,d:'solid'},stop:{w:1,d:'dash'},trig:{w:1,d:'dot'}},
 lv:{pH:{on:1,c:'#c0392b',w:1,d:'dash',a:1},pL:{on:1,c:'#2980b9',w:1,d:'dash',a:1},pC:{on:1,c:'#8e44ad',w:1,d:'dash',a:1},
     sma:{on:1,c:'#f1c40f',w:1,d:'dot',a:1},open:{on:1,c:'#dfe4e8',w:1,d:'dash',a:1},
     ibh:{on:1,c:'#4a9eff',w:1,d:'dash',a:1},ibl:{on:1,c:'#4a9eff',w:1,d:'dash',a:1}}};
let CFG=Object.assign({},CFG_DEF,JSON.parse(localStorage.getItem('brcfg')||'{}'));
CFG.lv=CFG.lv||{};for(let k in CFG_DEF.lv)CFG.lv[k]=Object.assign({},CFG_DEF.lv[k],CFG.lv[k]||{});
CFG.tl=CFG.tl||{};for(let k in CFG_DEF.tl)CFG.tl[k]=Object.assign({},CFG_DEF.tl[k],CFG.tl[k]||{});
if(CFG.ibFill==null)CFG.ibFill=1;
function saveCfg(){localStorage.setItem('brcfg',JSON.stringify(CFG))}
const THEMES={dark:{bg:'#0c0f13',cUp:'#26a65b',cDn:'#d64541'},light:{bg:'#fbfbfa',cUp:'#1a9d54',cDn:'#d64541'},grey:{bg:'#b0b0b0',cUp:'#ffffff',cDn:'#5c5c5c'}};
function applyTheme(t){document.body.classList.remove('light','grey');if(t!=='dark')document.body.classList.add(t);
 let P=THEMES[t]||THEMES.dark;CFG.bg=P.bg;CFG.cUp=P.cUp;CFG.cDn=P.cDn;saveCfg();localStorage.setItem('brtheme',t);
 let sel=$('theme');if(sel)sel.value=t;render()}
function resetCfg(){CFG=Object.assign({},CFG_DEF);saveCfg();buildSettings();render()}
function hexa(hex,a){let h=hex.replace('#','');let r=parseInt(h.slice(0,2),16),g=parseInt(h.slice(2,4),16),b=parseInt(h.slice(4,6),16);return`rgba(${r},${g},${b},${a})`}
function darkenHex(c,f){let m=(c||'').replace('#','');if(m.length!=6)return c;let v=i=>Math.round(parseInt(m.slice(i,i+2),16)*f).toString(16).padStart(2,'0');return'#'+v(0)+v(2)+v(4)}
function ccol(c){if(!window._LTbg)return c;let m=(c||'').replace('#','');if(m.length!=6)return c;let r=parseInt(m.slice(0,2),16),g=parseInt(m.slice(2,4),16),b=parseInt(m.slice(4,6),16),L=(0.299*r+0.587*g+0.114*b)/255;return L>0.6?darkenHex(c,0.5):c}  // darken pale colours on light/grey bg
let CH={on:false,x:0,y:0};
let D=null,notes={},idx=[],curDate=null,revIdx=0,playT=null,sel=null,VX={x0:60,y0:20};
let REVS={};fetch('/revs').then(r=>r.json()).then(j=>{REVS=j}).catch(()=>{});
// --- MyReversals detection parameters (defaults = Thomas's NT screenshot) ---
const REV_DEFAULTS={
 ShowTrap:true,Trap_IBS:72,Trap_UL:80,Trap_Body:15,Trap_Tail:20,Trap_MinSize:2,Trap_ABR:0.6,Trap_Prior_OppClose:true,Trap_BodyCheck:true,
 ShowBO:true,BO_IBS:72,BO_UL:15,BO_Body:50,BO_CloseBeyond:true,BO_ABR:0.8,BO_Prior_OppClose:true,
 ShowOB:true,OB_IBS:90,OB_UL:10,OB_Body:50,OB_CloseBeyond:true,OB_CloseBeyondIB:true,OB_ABR:0.8,OB_Strict:true,OB_Prior_OppClose:true,OB_BodyCheck:true,
 ShowIB:true,IB_IBS:50,IB_Body:40,IB_BodyCheck:true,IB_Prior_Tail:49,IB_Prior_OppClose:true,
 FT_IBS:50,FT_UL:5,FT_Body:50,FT_CloseBeyond:true,FT_ABR:0.24,FT_NoDojiIB:true};
// [key,label,type]  type: n=int, f=float, b=bool
const REV_FIELDS=[
 ['Trap Reversal',[['ShowTrap','Show Trap Reversal','b'],['Trap_IBS','IBS (1-100)','n'],['Trap_UL','Underlap Max (1-100)','n'],['Trap_Body','Body Min (0-100)','n'],['Trap_Tail','Tail Min (1-100)','n'],['Trap_MinSize','Trap Min (ticks)','n'],['Trap_ABR','ABR Multiple','f'],['Trap_Prior_OppClose','Prior Body Opposite','b'],['Trap_BodyCheck','Body = Bar Direction','b']]],
 ['Breakout Reversal',[['ShowBO','Show BO Reversal','b'],['BO_IBS','IBS (1-100)','n'],['BO_UL','Breakout Min (1-100)','n'],['BO_Body','Body Min (0-100)','n'],['BO_CloseBeyond','Close beyond','b'],['BO_ABR','ABR Multiple','f'],['BO_Prior_OppClose','Prior Body Opposite','b']]],
 ['Outside Reversal',[['ShowOB','Show OB Reversal','b'],['OB_IBS','IBS (1-100)','n'],['OB_UL','Breakout Min (1-100)','n'],['OB_Body','Body Min (0-100)','n'],['OB_CloseBeyond','Close beyond','b'],['OB_CloseBeyondIB','Close beyond IB1','b'],['OB_ABR','ABR Multiple','f'],['OB_Strict','Strict OB only','b'],['OB_Prior_OppClose','Prior Body Opposite','b'],['OB_BodyCheck','Body = Bar Direction','b']]],
 ['Inside Reversal',[['ShowIB','Show IB Reversal','b'],['IB_IBS','IBS (1-100)','n'],['IB_Body','Body Min (0-100)','n'],['IB_BodyCheck','Body = Bar Direction','b'],['IB_Prior_Tail','Prior Tail Max (1-50)','n'],['IB_Prior_OppClose','Prior Body Opposite','b']]],
 ['Follow Through',[['FT_IBS','IBS (1-100)','n'],['FT_UL','Breakout Min (1-100)','n'],['FT_Body','Body Min (1-100)','n'],['FT_CloseBeyond','Close beyond','b'],['FT_ABR','ABR Multiple','f'],['FT_NoDojiIB','Filter for Doji IB','b']]]];
let REVP=Object.assign({},REV_DEFAULTS,JSON.parse(localStorage.getItem('revparams')||'{}'));
function toggleRevPanel(){let s=$('revpanel');let show=s.style.display=='none';s.style.display=show?'block':'none';if(show)buildRevPanel()}
function buildRevPanel(){let h='';for(let [grp,fields] of REV_FIELDS){h+=`<div class=rvg>${grp}</div>`;
  for(let [k,lab,ty] of fields){let v=REVP[k];
   if(ty=='b')h+=`<div class=rvr><span>${lab}</span><input type=checkbox id=rp_${k} ${v?'checked':''}></div>`;
   else h+=`<div class=rvr><span>${lab}</span><input type=number id=rp_${k} value="${v}" step="${ty=='f'?'0.01':'1'}"></div>`;}}
 $('revbody').innerHTML=h}
function collectRevParams(){let p={};for(let [grp,fields] of REV_FIELDS)for(let [k,lab,ty] of fields){let el=$('rp_'+k);if(!el)continue;
  p[k]=ty=='b'?el.checked:(ty=='f'?parseFloat(el.value):parseInt(el.value));}
 return p}
function resetRevParams(){REVP=Object.assign({},REV_DEFAULTS);localStorage.removeItem('revparams');buildRevPanel();$('revstatus').textContent='defaults restored — recalculate to apply'}
function recalcRevs(){REVP=collectRevParams();$('revstatus').textContent='recalculating all days…';
 fetch('/recalc',{method:'POST',body:JSON.stringify(REVP)}).then(r=>r.json()).then(j=>{
  if(j&&j.error){$('revstatus').textContent='error: '+j.error;return}
  REVS=j;localStorage.setItem('revparams',JSON.stringify(REVP));
  let n=Object.values(j).reduce((a,v)=>a+v.length,0),d=Object.keys(j).length;
  $('revstatus').innerHTML=`<b style="color:#2ecc71">${n} signals</b> across ${d} days ✓`;render()})
 .catch(e=>{$('revstatus').textContent='error: '+e})}
let GX={};fetch('/globex').then(r=>r.json()).then(j=>{GX=j}).catch(()=>{});
let CSVS={};fetch('/csvsig').then(r=>r.json()).then(j=>{CSVS=j;render()}).catch(()=>{});  // Thomas's NT export overlay
let BOS={};fetch('/bosetup').then(r=>r.json()).then(j=>{BOS=j;render()}).catch(()=>{});  // final BO setup (tick PnL)
function jumpBO(){let ks=Object.keys(BOS).sort();if(!ks.length){alert('BO setup data not loaded');return}
 let nx=ks.find(k=>k>(curDate||''))||ks[0];$('t_bo').checked=true;goDay(nx)}
const REVCOL={T:'#e67e22',B:'#4a9eff',O:'#c39bd3',I:'#2ecc71'}; // Trap/BO/OB/IB
const $=id=>document.getElementById(id);
for(const s of ['dti','dtf']){const e=$(s);e.innerHTML='<option value="">—</option>'+DTS.map(d=>`<option>${d}</option>`).join('')}
let ALLIDX=[];
fetch('/index').then(r=>r.json()).then(j=>{ALLIDX=j;$('skipn').textContent=' ('+ALLIDX.filter(d=>d.skipTD).length+')';applyDayFilter(true)});
applyTheme(localStorage.getItem('brtheme')||'dark');   // restore saved theme (per-browser -> Thomas keeps his grey)
function applyDayFilter(init){let sk=$('t_skip').checked;idx=sk?ALLIDX.filter(d=>d.skipTD):ALLIDX;
 if(!idx.length){$('daysel').innerHTML='<option>none</option>';return}
 $('daysel').innerHTML=idx.slice().reverse().map(d=>`<option value=${d.date}>${d.date}${d.skipTD?' ⚑':''} (${d.n_in_book}tr ${d.net>=0?'+':''}${d.net})</option>`).join('');  // newest first (S91e)
 let h=decodeURIComponent(location.hash.slice(1));
 let start=(init&&h&&idx.some(d=>d.date==h))?h:((!init&&idx.some(d=>d.date==curDate))?curDate:idx[idx.length-1].date);
 goDay(start)}
function goDay(dt){curDate=dt;$('daysel').value=dt;fetch('/day/'+dt).then(r=>r.json()).then(j=>{RAWD=j;D=(TF>5)?aggDay(j,TF/5):j;revIdx=D.bars.length-1;loadNotes(dt)})}
// ---- timeframe (S91e): 5M base, client-side 15M aggregation. Default 5M => D===raw (no change).
let TF=5,RAWD=null;
function setTF(v){if(v=='D'){alert('Daily is a separate multi-day view — coming next. Staying on '+TF+'M.');$('tf').value=TF;return}
 TF=+v;if(RAWD){D=(TF>5)?aggDay(RAWD,TF/5):RAWD;revIdx=D.bars.length-1;fit();render()}}
function aggDay(d,k){let src=d.bars||[],out=[];  // bar tuple = [i, "HH:MM", O, H, L, C, EMA]
 for(let i=0;i<src.length;i+=k){let g=src.slice(i,i+k);
  out.push([out.length,g[0][1],g[0][2],Math.max(...g.map(b=>b[3])),Math.min(...g.map(b=>b[4])),g[g.length-1][5],g[g.length-1][6]])}
 let mi=i=>Math.floor(i/k),uniq=a=>[...new Set(a)],nd=Object.assign({},d);nd.bars=out;
 nd.regime=(d.regime||[]).map(s=>Object.assign({},s,{from:mi(s.from),to:mi(s.to)}));
 nd.pivots=(d.pivots||[]).map(p=>Object.assign({},p,{b:mi(p.b)}));
 nd.obs=uniq((d.obs||[]).map(mi));nd.ibs=uniq((d.ibs||[]).map(mi));
 nd.trades=(d.trades||[]).map(t=>Object.assign({},t,{entry_bar:t.entry_bar!=null?mi(t.entry_bar):t.entry_bar,sig_bar:t.sig_bar!=null?mi(t.sig_bar):t.sig_bar}));
 nd._tf=k*5;return nd}
function loadNotes(dt){fetch('/notes/'+dt).then(r=>r.json()).then(n=>{notes=n||{};$('dti').value=notes.daytype_inter||'';$('dtf').value=notes.daytype_final||'';$('ibar').textContent=notes.daytype_inter_bar??'—';sel=null;$('selpanel').style.display='none';$('selinfo').textContent='click a setup or bar';fit();render()})}
function nav(d){let i=idx.findIndex(x=>x.date==curDate)+d;if(i>=0&&i<idx.length)goDay(idx[i].date)}
function jumpUngraded(){let start=idx.findIndex(x=>x.date==curDate);
 (function tryNext(k){if(k>=idx.length)return;let i=(start+1+k)%idx.length;fetch('/notes/'+idx[i].date).then(r=>r.json()).then(n=>{if(!n||!n.daytype_final)goDay(idx[i].date);else tryNext(k+1)})})(0)}
function play(){if(playT){clearInterval(playT);playT=null;$('playlbl').textContent='▶ play';return}$('playlbl').textContent='⏸ pause';playT=setInterval(()=>{if(revIdx<D.bars.length-1){revIdx++;render()}else play()},+$('spd').value)}
function step(d){revIdx=Math.max(0,Math.min(D.bars.length-1,revIdx+d));render()}
function showAll(){revIdx=D.bars.length-1;render()}
function nextSetup(){if(!D)return;let t=D.trades.filter(x=>x.entry_bar>revIdx).sort((a,b)=>a.entry_bar-b.entry_bar)[0];if(t){revIdx=t.entry_bar;render()}}
window.onkeydown=e=>{if(e.target.tagName=='TEXTAREA')return;if(e.key==' '){e.preventDefault();play()}else if(e.key=='ArrowRight')step(1);else if(e.key=='ArrowLeft')step(-1);else if(e.key=='a'||e.key=='s'&&0)showAll();else if(e.key=='n')nextSetup();else if(e.key=='p'||e.key=='P')toggleSide();else if(['A','B','C','F'].includes(e.key.toUpperCase())&&sel)grade(e.key.toUpperCase())}
let cv=$('cv'),ctx=cv.getContext('2d');
let DPR=1;
function fit(){DPR=Math.min(window.devicePixelRatio||1,3);let w=$('chart').clientWidth,h=$('chart').clientHeight;
 cv.width=Math.round(w*DPR);cv.height=Math.round(h*DPR);cv.style.width=w+'px';cv.style.height=h+'px';ctx.setTransform(DPR,0,0,DPR,0,0)}
window.onresize=()=>{fit();render()};
function visTrades(){let f=$('filt').value;return D.trades.filter(t=>{if(f=='book')return t.in_book;if(f=='fade')return t.is_fade;if(f=='L')return t.dir=='L';if(f=='S')return t.dir=='S';if(f=='win')return t.net>0;if(f=='loss')return t.net<0;return true})}
function showPanel(){let s=$('side');s.style.setProperty('display','block','important');s.style.width='320px';fit();render()}
function hidePanel(){$('side').style.setProperty('display','none','important');fit();render()}
function toggleSide(){if(getComputedStyle($('side')).display=='none')showPanel();else hidePanel()}
function hline(a,b,yy){ctx.beginPath();ctx.moveTo(a,yy);ctx.lineTo(b,yy);ctx.stroke()}
function dot(a,b,r){ctx.beginPath();ctx.arc(a,b,r,0,7);ctx.fill()}
function candle(i,o,h,l,c,x,y,bw,dim){let up=c>=o,col=dim?'#39424d':(up?CFG.cUp:CFG.cDn),xx=x(i);ctx.globalAlpha=dim?.55:1;ctx.strokeStyle=(window._wick&&!dim)?window._wick:col;ctx.fillStyle=col;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(xx,y(h));ctx.lineTo(xx,y(l));ctx.stroke();let yo=y(o),yc=y(c),bx=xx-bw*.32,bwd=Math.max(1,bw*.64),bh=Math.max(1,Math.abs(yo-yc));ctx.fillStyle=col;ctx.fillRect(bx,Math.min(yo,yc),bwd,bh);if(window._edge&&!dim){ctx.lineWidth=1;ctx.strokeStyle=window._edge;ctx.strokeRect(bx,Math.min(yo,yc),bwd,bh)}ctx.globalAlpha=1}
function setupLbl(t){return t.setup||((t.with_trend?'':'f')+'2E'+t.dir)}
const FAM_TOG={'2EL':'t_2el','2ES':'t_2es','f2EL':'t_f2el','f2ES':'t_f2es'};
function famVis(t){let id=FAM_TOG[setupLbl(t)];return id?$(id).checked:true}  // per-family toggle; unknown labels always show
// NT-csv setup outcome: pullback fill -> stop/1R-target/EOD exit, P&L net $17.5 RT (full day, reveal-agnostic)
function csvResult(c,bars){let bi=c[0],up=c[1]>0,stopP=c[5],lmt=c[6];
 if(bi>=bars.length)return null;
 let b=bars[bi],slo=b[4],shi=b[3],away=false,fillB=-1;
 for(let j=bi+1;j<bars.length;j++){let hh=bars[j][3],ll=bars[j][4];
  if(up){if(away&&ll<lmt){fillB=j;break} if(hh>shi)away=true;}
  else{if(away&&hh>lmt){fillB=j;break} if(ll<slo)away=true;}}
 if(fillB<0)return {bi:bi,up:up,fillB:-1};
 let risk=Math.abs(lmt-stopP),tgt=up?lmt+risk:lmt-risk,exitB=-1,exitPx=null,oc=null;
 for(let j=fillB;j<bars.length;j++){let hh=bars[j][3],ll=bars[j][4];
  if(up){if(ll<=stopP){exitB=j;exitPx=stopP;oc='stop';break} if(hh>=tgt){exitB=j;exitPx=tgt;oc='target';break}}
  else{if(hh>=stopP){exitB=j;exitPx=stopP;oc='stop';break} if(ll<=tgt){exitB=j;exitPx=tgt;oc='target';break}}}
 if(exitB<0){exitB=bars.length-1;exitPx=bars[exitB][5];oc='eod';}
 let pts=up?(exitPx-lmt):(lmt-exitPx),pnl=Math.round(pts*50-17.5);
 return {bi:bi,up:up,fillB:fillB,btf:fillB-bi,exitB:exitB,exitPx:exitPx,oc:oc,pnl:pnl,
         pts:+pts.toFixed(2),tgt:+tgt.toFixed(2),risk:+risk.toFixed(2),lmt:lmt,stopP:stopP};}
function distSeg(px,py,x1,y1,x2,y2){let dx=x2-x1,dy=y2-y1,l2=dx*dx+dy*dy;if(!l2)return Math.hypot(px-x1,py-y1);
 let t=Math.max(0,Math.min(1,((px-x1)*dx+(py-y1)*dy)/l2));return Math.hypot(px-(x1+t*dx),py-(y1+t*dy));}
function setupBox(t){let dir=t.dir=='S'?'short ▽':'long △',net=(t.net!=null&&!isNaN(t.net))?`<span style="color:${t.net>0?'#2ecc71':'#e74c3c'}">${t.net>0?'+':''}${t.net}</span>`:'—',
 status=t.is_fade?(t.fade_tradeable?'FADE · tradeable':'FADE · dead'):(t.in_book?'IN BOOK':'excluded');
 return `<b style="color:${setupCol(t)};font-size:13px">${setupLbl(t)}</b> ${dir} &nbsp;<span style="color:#aeb6c0">${status}</span>`+
   `<br><span style="color:#8b93a0">sig</span> b${t.sig_bar+1} · <span style="color:#8b93a0">fill</span> b${t.entry_bar+1} · <span style="color:#8b93a0">exit</span> b${t.exit_bar+1}`+
   `<br><span style="color:#8b93a0">trig</span> ${t.trigger} · <span style="color:#8b93a0">entry</span> ${t.entry_px} · <span style="color:#8b93a0">stop</span> ${t.stop} · <span style="color:#8b93a0">exit</span> ${t.exit_px}`+
   `<br><span style="color:#8b93a0">net</span> ${net}`;}
function setupCol(t){if(t.is_fade)return t.dir=='L'?'#e67e22':'#9b59b6';if(t.in_book)return t.dir=='L'?CFG.cBull:CFG.cBear;return '#7f8c8d'}
function render(){if(!D)return;$('dt').textContent=D.date;$('rev').textContent=revIdx+1;$('nb').textContent=D.bars.length;
 let bars=D.bars,ptA=D.prior_tail||[],pt=($('t_prev').checked&&ptA.length)?[ptA[ptA.length-1]]:[],P=pt.length,W=cv.clientWidth,H=cv.clientHeight,pad=VX,bot=H-26,lbl=$('t_lbl').checked;
 let lo=1e9,hi=-1e9;                              // scale to PRICE ACTION only (bars); far levels listed in panel
 for(let b of pt){lo=Math.min(lo,b[2]);hi=Math.max(hi,b[1])}
 for(let i=0;i<=revIdx;i++){lo=Math.min(lo,bars[i][4]);hi=Math.max(hi,bars[i][3])}
 let rng=(hi-lo)||1;lo-=rng*.06;hi+=rng*.06;rng=hi-lo;
 let yZoom=+$('yzoom').value,mid=(lo+hi)/2,half=rng/2/yZoom;lo=mid-half;hi=mid+half;rng=hi-lo;let onS=p=>p!=null&&p>=lo&&p<=hi;
 let tot=P+bars.length,vw=W-pad.x0-12,xZoom=+$('xzoom').value,bw=vw/tot*xZoom,offX=(+$('panx').value)*Math.max(0,tot*bw-vw);
 let x=i=>pad.x0+(i+P)*bw+bw/2-offX,y=p=>pad.y0+(hi-p)/rng*(bot-pad.y0);
 let GY=document.body.classList.contains('grey'),LT=document.body.classList.contains('light')||GY;
 window._LTbg=LT;window._lvlHit=[];window._setupHit=[];window._revHit=[];window._csvHit=[];window._boHit=[];   // contrast + hover tooltips
 window._edge=GY?'#111':(LT?'rgba(20,20,20,.55)':null);   // body outline: black on NT theme
 window._wick=GY?'#111':null;                             // wicks black on NT theme, else candle colour
 cv.style.background=CFG.bg;ctx.clearRect(0,0,W,H);
 // regime shading (RTH)
 if($('t_reg').checked)for(let s of D.regime){if(s.from>revIdx)continue;let to=Math.min(s.to,revIdx);let c=s.mode=='BULL'?hexa(CFG.cBull,CFG.regOp):s.mode=='BEAR'?hexa(CFG.cBear,CFG.regOp):hexa('#8b93a0',CFG.regOp*.5);ctx.fillStyle=c;ctx.fillRect(x(s.from)-bw/2,pad.y0,(to-s.from+1)*bw,bot-pad.y0)}
 // per-level style/toggle from settings
 let dashOf=d=>d=='solid'?[]:d=='dot'?[2,3]:[6,4];
 let drawLevel=(p,k,label)=>{let s=CFG.lv[k];if(!s||!s.on||!onS(p))return;let yy=y(p),al=s.a==null?1:s.a,cc=ccol(s.c);ctx.strokeStyle=hexa(cc,al);ctx.lineWidth=s.w;ctx.setLineDash(dashOf(s.d));hline(pad.x0,W-10,yy);ctx.setLineDash([]);ctx.lineWidth=1;window._lvlHit.push({y:yy,name:label,price:p,c:cc});if(lbl){ctx.font=(LT?'bold ':'')+'11.5px sans-serif';ctx.fillStyle=hexa(cc,1);ctx.textAlign='left';ctx.fillText(label,W-32,yy-3)}};
 // IB band fill (own toggle, independent of the IBH/IBL line toggles)
 if(D.ib&&CFG.ibFill&&D.ib.lo<=hi&&D.ib.hi>=lo){let y1=y(Math.min(D.ib.hi,hi)),y2=y(Math.max(D.ib.lo,lo)),xl=x(0)-bw/2;ctx.fillStyle=hexa(CFG.cIb,CFG.ibOp);ctx.fillRect(xl,y1,W-10-xl,y2-y1)}
 // grid + price axis
 ctx.font=(LT?'bold ':'')+'11px sans-serif';ctx.textAlign='right';for(let k=0;k<=6;k++){let p=lo+rng*k/6,yy=y(p);ctx.strokeStyle=LT?'#dcdcdc':'#161c23';hline(pad.x0,W-10,yy);ctx.fillStyle=LT?'#000':'#6b7480';ctx.fillText(p.toFixed(0),pad.x0-4,yy+3)}
 // Globex (overnight) H/L
 if($('t_gx').checked&&GX[D.date]){let g=GX[D.date],gc=LT?'#9a6a00':'#f5b041';[[g[0],'GXH'],[g[1],'GXL']].forEach(pl=>{if(!onS(pl[0]))return;let yy=y(pl[0]);ctx.strokeStyle=gc;ctx.setLineDash([5,3]);ctx.lineWidth=1.3;hline(pad.x0,W-10,yy);ctx.setLineDash([]);ctx.lineWidth=1;window._lvlHit.push({y:yy,name:pl[1],price:pl[0],c:gc});if(lbl){ctx.font=(LT?'bold ':'')+'11.5px sans-serif';ctx.fillStyle=gc;ctx.textAlign='left';ctx.fillText(pl[1],W-32,yy-3)}})}
 // horizontal levels
 drawLevel(D.prior.H,'pH','pH');drawLevel(D.prior.L,'pL','pL');drawLevel(D.prior.C,'pC','pC');
 drawLevel(D.sma20,'sma','SMA');drawLevel(D.today_open,'open','O');
 if(D.ib){drawLevel(D.ib.hi,'ibh','IBH');drawLevel(D.ib.lo,'ibl','IBL')}
 // prior-session LAST bar only (normal colors), + divider
 for(let j=0;j<P;j++){let b=pt[j];candle(-(P-j),b[0],b[1],b[2],b[3],x,y,bw,false);if(lbl){ctx.fillStyle='#8b93a0';ctx.font='8px sans-serif';ctx.textAlign='center';ctx.fillText('prev',x(-(P-j)),bot+12)}}
 if(P){ctx.strokeStyle='#2b333d';ctx.setLineDash([3,3]);hline2(x(-0.5),pad.y0,x(-0.5),bot);ctx.setLineDash([])}
 // RTH candles + bar numbers (b1, then every 3rd)
 for(let i=0;i<=revIdx;i++){let b=bars[i];candle(i,b[2],b[3],b[4],b[5],x,y,bw,false);if($('t_num').checked&&i%3==0){ctx.fillStyle=LT?'#000':'#7a8592';ctx.font=(LT?'bold ':'')+'10px sans-serif';ctx.textAlign='center';ctx.fillText(i+1,x(i),bot+12)}}
 // pivots (swing H/L from phase machine): opening=gold, major=bold, minor=dim
 if($('t_piv').checked&&D.pivots){let placed=[];for(let p of D.pivots){if(p.b>revIdx)continue;let big=p.major||p.open;if(big&&!$('t_pivM').checked)continue;if(!big&&!$('t_pivm').checked)continue;
  let b=bars[p.b],hiP=p.side=='H',py=hiP?b[3]:b[4],col=p.open?'#f1c40f':(hiP?'#e59866':'#5dade2'),txt=big?p.lab:(p.tag||p.lab.toLowerCase());
  ctx.fillStyle=big?col:hexa(col,.55);dot(x(p.b),y(py),big?3.4:2);
  let off=big?(hiP?-15:17):(hiP?-5:9),lx=x(p.b),ly=y(py)+off;                      // major far, minor near
  if(placed.some(q=>Math.abs(q[0]-lx)<15&&Math.abs(q[1]-ly)<11))continue;          // never overlap
  placed.push([lx,ly]);ctx.font=(big?'bold 9px':'8px')+' sans-serif';ctx.textAlign='center';ctx.fillStyle=big?col:hexa(col,.72);ctx.fillText(txt,lx,ly)}}
 // OB dots
 if($('t_ob').checked&&D.obs)for(let i of D.obs){if(i>revIdx)continue;ctx.fillStyle='#c39bd3';dot(x(i),y(bars[i][4])+9,2.2)}
 // MyReversals indicator markers: FT triangle at the FT bar (▲ green long / ▼ red short) + type letter
 if($('t_rev').checked&&REVS[D.date]){
  for(let r of REVS[D.date]){let bi=r[0],sd=r[1],typ=r[2],rvb=r[3];
   if(bi>revIdx||bi>=bars.length)continue;
   let up=sd>0,b=bars[bi],xx=x(bi),s=6,ty=up?y(b[4])+15:y(b[3])-15,col=up?'#1fae43':'#e23b3b',rc=REVCOL[typ]||'#888';
   // racing stripe spanning reversal bar -> FT bar
   let sb=(rvb>=0?rvb:bi),xa=x(sb)-bw/2,xw=Math.max(bw,x(bi)+bw/2-xa),seld=(sel&&sel.is_rev&&sel._key===('R'+D.date+bi+typ));
   ctx.fillStyle=hexa(rc,seld?.26:.12);ctx.fillRect(xa,pad.y0,xw,bot-pad.y0);
   ctx.fillStyle=hexa(rc,1);ctx.fillRect(xa,pad.y0,xw,seld?5:3);
   if(seld){ctx.strokeStyle=LT?'#111':'#fff';ctx.lineWidth=1.2;ctx.strokeRect(xa,pad.y0,xw,bot-pad.y0);ctx.lineWidth=1}
   window._revHit.push({xc:xx,x0:xa,x1:xa+xw,r:r});
   if(rvb>=0&&rvb<=revIdx){let rb=bars[rvb];ctx.fillStyle='#2b6fff';ctx.beginPath();ctx.arc(x(rvb),up?y(rb[4])+10:y(rb[3])-10,4,0,7);ctx.fill()}  // blue dot on reversal bar
   ctx.beginPath(); if(up){ctx.moveTo(xx,ty-s);ctx.lineTo(xx-s,ty+s);ctx.lineTo(xx+s,ty+s);}else{ctx.moveTo(xx,ty+s);ctx.lineTo(xx-s,ty-s);ctx.lineTo(xx+s,ty-s);} ctx.closePath();
   ctx.fillStyle=col;ctx.fill();
   ctx.font='8px sans-serif';ctx.textAlign='center';ctx.fillStyle=col;ctx.fillText(typ,xx,up?ty+s+8:ty-s-3);}}
 // NT export (Thomas's CSV): grey LMT line (signal->fill), then a BOLD straight line entry->exit,
 // green = winner / red = loser (1R target vs stop vs EOD). P&L on hover. Day P&L in the panel.
 if($('t_csv').checked&&CSVS[D.date]){
  for(let c of CSVS[D.date]){let R=csvResult(c,bars);if(!R||R.bi>revIdx)continue;
   let up=R.up,bi=R.bi,yl=y(c[6]),col=up?'#1fae43':'#e23b3b',xs=x(bi)-bw/2;
   ctx.fillStyle=hexa(col,.10);ctx.fillRect(xs,pad.y0,bw,bot-pad.y0);            // faint stripe on the signal bar
   if(R.fillB<0){                                                               // never filled -> dashed grey LMT line
    let noFill=revIdx>=bars.length-1,xe=x(revIdx)+bw*.5;
    ctx.strokeStyle='#9aa4b0';ctx.lineWidth=1.4;ctx.setLineDash(noFill?[4,3]:[2,3]);hline2(xs,yl,xe,yl);ctx.setLineDash([]);ctx.lineWidth=1;
    window._csvHit.push({segs:[[xs,yl,xe,yl]],c:c,fillB:-1,btf:null,exit:null});continue;}
   let feEnd=Math.min(R.fillB,revIdx),xfe=x(feEnd)+bw*.5;
   ctx.strokeStyle='#9aa4b0';ctx.lineWidth=1.2;ctx.setLineDash([]);hline2(xs,yl,xfe,yl);ctx.lineWidth=1;   // grey LMT entry line
   let segs=[[xs,yl,xfe,yl]];
   if(R.fillB<=revIdx&&R.exitB<=revIdx){                                        // closed & revealed -> bold win/loss line
    let win=R.pnl>0,oc=win?'#16c60c':'#ef2b2b',xf=x(R.fillB),xe2=x(R.exitB),ye=y(R.exitPx);
    ctx.strokeStyle=oc;ctx.lineWidth=2.6;ctx.beginPath();ctx.moveTo(xf,yl);ctx.lineTo(xe2,ye);ctx.stroke();ctx.lineWidth=1;
    ctx.fillStyle=oc;ctx.beginPath();ctx.arc(xe2,ye,3.4,0,7);ctx.fill();
    segs.push([xf,yl,xe2,ye]);
   } else if(R.fillB<=revIdx){                                                  // filled, not yet exited (reveal)
    ctx.strokeStyle='#9aa4b0';ctx.setLineDash([2,3]);hline2(x(R.fillB),yl,x(revIdx)+bw*.5,yl);ctx.setLineDash([]);
    segs.push([x(R.fillB),yl,x(revIdx)+bw*.5,yl]);}
   window._csvHit.push({segs:segs,c:c,fillB:R.fillB,btf:R.btf,
    exit:{oc:R.oc,pnl:R.pnl,pts:R.pts,tgt:R.tgt,risk:R.risk,exitBar:R.exitB+1}});}}
 // FINAL BO SETUP (tick-accurate): BO>=11:00, skip-gap, MARKET entry, 2R target. entry dot + stop/2R lines + win/loss line.
 if($('t_bo').checked&&BOS[D.date]){
  for(let tr of BOS[D.date]){let ft=tr[0],dir=tr[1],btc=tr[2],estop=tr[3],pnl=tr[4],reason=tr[5],xb=tr[6];
   if(ft>revIdx||ft>=bars.length)continue;
   let long=dir>0,b=bars[ft],entry=b[5],shift=entry-btc,stop=estop+shift,risk=Math.abs(btc-estop);
   let tgt=long?entry+2*risk:entry-2*risk,xx=x(ft),ye=y(entry),ys=y(stop),yt=y(tgt),win=pnl>0,col=win?'#16c60c':'#ef2b2b';
   let exEnd=Math.min(xb,revIdx),xe=x(exEnd)+bw*.5;
   ctx.fillStyle=hexa(col,.08);ctx.fillRect(xx-bw/2,pad.y0,bw,bot-pad.y0);          // stripe
   ctx.setLineDash([3,3]);ctx.lineWidth=1;
   ctx.strokeStyle=hexa('#e74c3c',.6);hline2(xx-bw*.5,ys,xe,ys);                    // stop
   ctx.strokeStyle=hexa('#2ecc71',.6);hline2(xx-bw*.5,yt,xe,yt);                    // 2R target
   ctx.setLineDash([]);
   ctx.fillStyle=col;ctx.beginPath();ctx.arc(xx,ye,3.6,0,7);ctx.fill();            // market-entry dot
   if(xb<=revIdx){let exPx=reason==0?stop:reason==1?tgt:bars[Math.min(xb,bars.length-1)][5],yex=y(exPx);
    ctx.strokeStyle=col;ctx.lineWidth=2.6;ctx.beginPath();ctx.moveTo(xx,ye);ctx.lineTo(x(xb),yex);ctx.stroke();ctx.lineWidth=1;
    ctx.fillStyle=col;ctx.beginPath();ctx.arc(x(xb),yex,3.4,0,7);ctx.fill();}
   window._boHit.push({x0:xx-bw/2,x1:xe,ylo:Math.min(ye,ys,yt)-4,yhi:Math.max(ye,ys,yt)+4,
    tr:tr,entry:entry,stop:stop,tgt:tgt,risk:risk});}}
 // user bar TAGS (name+grade+note) — always shown
 if(notes.setups)for(let k in notes.setups){let n=notes.setups[k];if(!n.is_bar)continue;let bi=n.entry_bar;if(bi>revIdx||bi>=bars.length)continue;
  let b=bars[bi],xx=x(bi),yt=y(b[3])-9;ctx.fillStyle='#f1c40f';ctx.beginPath();ctx.moveTo(xx,yt-5);ctx.lineTo(xx-4,yt+2);ctx.lineTo(xx+4,yt+2);ctx.closePath();ctx.fill();
  let lab=(n.name||'tag')+(n.grade?' ['+n.grade+']':'');ctx.font='9px sans-serif';ctx.textAlign='center';ctx.fillStyle=LT?'#8a6d00':'#f1c40f';ctx.fillText(lab,xx,yt-8);
  if(sel&&sel.is_bar&&sel.entry_bar==bi){ctx.strokeStyle=LT?'#333':'#fff';ctx.lineWidth=1.3;ctx.beginPath();ctx.arc(xx,yt-1,7,0,7);ctx.stroke();ctx.lineWidth=1}}
 // intraday EMA20 (prior tail -> revealed RTH)
 if($('t_ema').checked){ctx.strokeStyle=CFG.cEma;ctx.lineWidth=1.6;ctx.beginPath();let st=false;for(let j=0;j<P;j++){let xx=x(-(P-j)),yy=y(pt[j][4]);st?ctx.lineTo(xx,yy):ctx.moveTo(xx,yy);st=true}for(let i=0;i<=revIdx;i++){let xx=x(i),yy=y(bars[i][6]);st?ctx.lineTo(xx,yy):ctx.moveTo(xx,yy);st=true}ctx.stroke();ctx.lineWidth=1;if(lbl&&revIdx>=0){ctx.fillStyle=CFG.cEma;ctx.textAlign='left';ctx.fillText('EMA20',x(revIdx)+3,y(bars[revIdx][6]))}}
 // gap tick (open vs prior close)
 if($('t_gap').checked&&$('t_prev').checked&&D.prior.C){ctx.strokeStyle='#f39c12';ctx.lineWidth=2;hline2(x(0),y(D.prior.C),x(0),y(bars[0][2]));ctx.lineWidth=1}
 // racing stripe on the signal bar for EVERY setup (taken or not); data shown on hover
 if($('t_tr').checked)for(let t of visTrades()){if(t.sig_bar>revIdx||!famVis(t))continue;let col=setupCol(t),xs=x(t.sig_bar)-bw/2,seld=(sel&&!sel.is_rev&&!sel.is_bar&&sel.entry_bar==t.entry_bar&&sel.dir==t.dir);
  ctx.globalAlpha=1;ctx.fillStyle=hexa(col,seld?.30:.14);ctx.fillRect(xs,pad.y0,bw,bot-pad.y0);
  ctx.fillStyle=hexa(col,1);ctx.fillRect(xs,pad.y0,bw,seld?5:3);
  if(seld){ctx.strokeStyle=LT?'#111':'#fff';ctx.lineWidth=1.3;ctx.strokeRect(xs,pad.y0,bw,bot-pad.y0);ctx.lineWidth=1}
  window._setupHit.push({xc:x(t.sig_bar),t:t});}
 // reveal edge
 ctx.strokeStyle='#333c47';hline2(x(revIdx)+bw*.5,pad.y0,x(revIdx)+bw*.5,bot);
 // crosshair + hover readout
 if(CH.on){let bi=Math.round((CH.x-pad.x0+offX)/bw-P);ctx.strokeStyle='#5a6470';ctx.setLineDash([2,3]);ctx.lineWidth=1;hline2(CH.x,pad.y0,CH.x,bot);hline(pad.x0,W-10,CH.y);ctx.setLineDash([]);
  let pcur=Math.round((hi-(CH.y-pad.y0)/(bot-pad.y0)*rng)/0.25)*0.25;ctx.fillStyle='#2c3440';ctx.fillRect(W-56,CH.y-8,50,16);ctx.fillStyle='#e6e9ec';ctx.textAlign='left';ctx.font='10px sans-serif';ctx.fillText(pcur.toFixed(2),W-54,CH.y+3);
  let o,h,l,c,tm,tag;if(bi>=0&&bi<=revIdx){let b=bars[bi];o=b[2];h=b[3];l=b[4];c=b[5];tm=b[1];tag='b'+(bi+1);}else if(bi<0&&bi>=-P){let b=pt[bi+P];o=b[0];h=b[1];l=b[2];c=b[3];tm=b[5];tag='prev';}
  if(tm){let up=c>=o,dc=up?'#2ecc71':'#e74c3c',dim='#7a828c';
    let toks=[[tag,'#cbd3dc'],['  '+tm+'   ','#8b93a0'],['O','#7a828c'],[o+'  ','#d6dbe0'],['H','#7a828c'],[h+'  ','#26c281'],['L','#7a828c'],[l+'  ','#e35d4f'],['C','#7a828c'],[''+c,'#f0f3f6'],['   Δ'+(up?'+':'')+(c-o).toFixed(2),dc]];
    if(bi>=0){let cmap={OB:'#c39bd3',IB:'#5dade2',up:'#2ecc71',dn:'#e74c3c',BULL:'#2ecc71',BEAR:'#e74c3c',NEUTRAL:'#8b93a0'},cls=[];
      if(D.obs&&D.obs.includes(bi))cls.push('OB');if(D.ibs&&D.ibs.includes(bi))cls.push('IB');let pv=D.pivots&&D.pivots.find(p=>p.b==bi);if(pv)cls.push((pv.side=='H'?'swingH ':'swingL ')+pv.lab);cls.push(up?'up':'dn');let rg=D.regime&&D.regime.find(s=>bi>=s.from&&bi<=s.to);if(rg)cls.push(rg.mode);
      toks.push(['   [','#5a6470']);cls.forEach((t,ix)=>{let cc=cmap[t]||(t.indexOf('swingH')==0?'#e59866':t.indexOf('swingL')==0?'#5dade2':'#f1c40f');toks.push([t,cc]);if(ix<cls.length-1)toks.push([', ','#5a6470'])});toks.push([']','#5a6470']);}
    ctx.font='11px sans-serif';ctx.textAlign='left';let tw=toks.reduce((a,t)=>a+ctx.measureText(t[0]).width,0)+16;
    ctx.fillStyle='rgba(16,20,26,.96)';ctx.fillRect(pad.x0+4,pad.y0+3,tw,18);
    let cx=pad.x0+11;for(let [t,cc] of toks){ctx.fillStyle=cc;ctx.fillText(t,cx,pad.y0+16);cx+=ctx.measureText(t).width}}}
 window._lo=lo;window._hi=hi;renderStats();renderCsvStats();renderBoStats();renderDayInfo();renderLevels();window._x=x;window._y=y;window._bw=bw;window._P=P}
function renderBoStats(){let el=$('bostats');if(!el)return;
 if(!$('t_bo').checked||!D||!BOS[D.date]){el.innerHTML='<span style="color:#5c6673">toggle BO setup on</span>';return}
 let all=BOS[D.date].filter(t=>t[0]<=revIdx),w=all.filter(t=>t[4]>0),l=all.filter(t=>t[4]<=0);
 let net=all.reduce((a,t)=>a+t[4],0),gw=w.reduce((a,t)=>a+t[4],0),gl=-l.reduce((a,t)=>a+t[4],0);
 let pf=gl?(gw/gl):(gw>0?'∞':'0');
 el.innerHTML=`<div class=stat>trades<span>${all.length}</span></div>`+
  `<div class=stat>W / L<span><span class=win>${w.length}</span> / <span class=loss>${l.length}</span></span></div>`+
  `<div class=stat>PF<span>${typeof pf=='string'?pf:pf.toFixed(2)}</span></div>`+
  `<div class=stat>net<span class=${net>=0?'win':'loss'}>${net>=0?'+':''}$${net.toFixed(0)}</span></div>`;}
function renderLevels(){if(!D)return;let last=D.bars[revIdx][5],lo=window._lo,hi=window._hi;
 let L=CFG.lv,rows=[['last',last,'#e6e9ec'],['OPEN',D.today_open,L.open.c],['SMA20',D.sma20,L.sma.c],['pH',D.prior.H,L.pH.c],['pC',D.prior.C,L.pC.c],['pL',D.prior.L,L.pL.c]];
 if(D.ib){rows.push(['IBH',D.ib.hi,L.ibh.c],['IBL',D.ib.lo,L.ibl.c])}
 if(GX[D.date]){let g=GX[D.date];rows.push(['GXH',g[0],'#f5b041'],['GXL',g[1],'#f5b041'])}
 $('levels').innerHTML=rows.filter(r=>r[1]!=null).map(([k,v,c])=>{let on=v>=lo&&v<=hi,d=k=='last'?'':((v-last>=0?'+':'')+(v-last).toFixed(2)+'pt');return`<div class=stat><span style="color:${ccol(c)}">${on?'●':'○'} ${k}</span><span>${v} <span style="color:var(--mut)">${d}</span></span></div>`}).join('')}
function hline2(a,b,c,d){ctx.beginPath();ctx.moveTo(a,b);ctx.lineTo(c,d);ctx.stroke()}
function renderDayInfo(){let p=D.prior;$('dayinfo').innerHTML=`<div class=stat>gap<span>${p.gap_pts} (${p.gap_pct}%)</span></div><div class=stat>ADR10<span>${D.adr10}</span></div><div class=stat>SMA20<span>${D.sma20}</span></div><div class=stat>skip-after-TD<span>${D.skipTD?'<span class=loss>YES (skipped)</span>':'no'}</span></div><div class=stat>trades<span>${D.trades.length} (${D.trades.filter(t=>t.in_book).length} in-book)</span></div>`}
function renderStats(){let ts=visTrades().filter(t=>t.in_book);let w=ts.filter(t=>t.net>0),l=ts.filter(t=>t.net<0);let gp=w.reduce((a,b)=>a+b.net,0),gl=-l.reduce((a,b)=>a+b.net,0);let net=ts.reduce((a,b)=>a+b.net,0);
 $('stats').innerHTML=`<div class=stat>n<span>${ts.length}</span></div><div class=stat>PF<span>${gl?(gp/gl).toFixed(2):'∞'}</span></div><div class=stat>win%<span>${ts.length?(100*w.length/ts.length).toFixed(0):0}</span></div><div class=stat>net<span class=${net>=0?'win':'loss'}>${net>=0?'+':''}${net.toFixed(0)}</span></div>`}
function renderCsvStats(){let el=$('csvstats');if(!el)return;
 if(!$('t_csv').checked||!D||!CSVS[D.date]){el.innerHTML='<span style="color:#5c6673">toggle NT csv on</span>';return}
 let all=CSVS[D.date].filter(c=>c[0]<=revIdx),rs=all.map(c=>csvResult(c,D.bars)).filter(r=>r&&r.fillB>=0);
 let nf=all.length-rs.length,w=rs.filter(r=>r.pnl>0),l=rs.filter(r=>r.pnl<=0);
 let net=rs.reduce((a,r)=>a+r.pnl,0),gw=w.reduce((a,r)=>a+r.pnl,0),gl=-l.reduce((a,r)=>a+r.pnl,0);
 let pf=gl?(gw/gl):(gw>0?'∞':'0');
 el.innerHTML=`<div class=stat>filled<span>${rs.length} <span style="color:#5c6673">(${nf} unfilled)</span></span></div>`+
  `<div class=stat>W / L<span><span class=win>${w.length}</span> / <span class=loss>${l.length}</span></span></div>`+
  `<div class=stat>win%<span>${rs.length?(100*w.length/rs.length).toFixed(0):0}</span></div>`+
  `<div class=stat>PF<span>${typeof pf=='string'?pf:pf.toFixed(2)}</span></div>`+
  `<div class=stat>net<span class=${net>=0?'win':'loss'}>${net>=0?'+':''}$${net}</span></div>`;}
cv.onclick=e=>{if(!D)return;let r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;let best=null,bd=1e9;
 let rv=pickRev(mx,my);if(rv){selectRev(rv);return}
 for(let t of visTrades()){if(t.sig_bar>revIdx)continue;let dx=Math.abs(window._x(t.sig_bar)-mx);if(dx<bd&&dx<Math.max(9,window._bw*.6)){bd=dx;best=t}}  // select by racing-stripe column
 if(best){selectTrade(best);return}
 let bi=barAtX(mx);if(bi!=null){selectBar(bi);return}
 sel=null;$('selpanel').style.display='none';$('tagwrap').style.display='none';$('selinfo').textContent='click a setup or bar';render()}
let LENS_ON=false;
function toggleLens(){LENS_ON=!LENS_ON;$('lensbtn').classList.toggle('on',LENS_ON);$('lenscv').style.display=LENS_ON?'block':'none'}
function drawLensMag(){let lc=$('lenscv'),g=lc.getContext('2d'),S=lc.width,Z=2.8,sw=S/Z;
 g.clearRect(0,0,S,S);g.save();g.beginPath();g.arc(S/2,S/2,S/2-2,0,7);g.clip();g.fillStyle=CFG.bg;g.fillRect(0,0,S,S);
 g.imageSmoothingEnabled=false;g.drawImage(cv,(CH.x-sw/2)*DPR,(CH.y-sw/2)*DPR,sw*DPR,sw*DPR,0,0,S,S);
 g.strokeStyle='rgba(255,255,255,.22)';g.lineWidth=1;g.beginPath();g.moveTo(S/2,0);g.lineTo(S/2,S);g.moveTo(0,S/2);g.lineTo(S,S/2);g.stroke();g.restore();
 lc.style.left=(CH.cx-S/2)+'px';lc.style.top=(CH.cy-S/2)+'px'}
cv.onmousemove=e=>{if(!D)return;let r=cv.getBoundingClientRect();CH={on:true,x:e.clientX-r.left,y:e.clientY-r.top,cx:e.clientX,cy:e.clientY};
 let tip=$('lvltip'),html=null,thr=Math.max(7,(window._bw||6)*.6);
 for(let S of window._setupHit||[]){if(Math.abs(S.xc-CH.x)<thr){html=setupBox(S.t);break}}
 if(!html)for(let C of window._csvHit||[]){let hit=false;for(let s of C.segs){if(distSeg(CH.x,CH.y,s[0],s[1],s[2],s[3])<6){hit=true;break}}if(hit){html=csvBox(C.c,C);break}}
 if(!html)for(let Bh of window._boHit||[]){if(CH.x>=Bh.x0&&CH.x<=Bh.x1&&CH.y>=Bh.ylo&&CH.y<=Bh.yhi){html=boBox(Bh);break}}
 if(!html)for(let H of window._revHit||[]){if(CH.x>=H.x0&&CH.x<=H.x1){html=revBox(H.r);break}}
 if(!html)for(let L of window._lvlHit||[]){if(Math.abs(L.y-CH.y)<5){let last=D.bars[revIdx][5],d=L.price-last;html=`<b style="color:${L.c}">${L.name}</b> &nbsp;<span style="color:#fff">${L.price}</span><br><span style="color:#aeb6c0">${d>=0?'+':''}${d.toFixed(2)} pt · ${(d/D.adr10*100).toFixed(0)}% ADR from last</span>`;break}}
 if(html){tip.innerHTML=html;tip.style.display='block';tip.style.left=(e.clientX+14)+'px';tip.style.top=(e.clientY+12)+'px'}else tip.style.display='none';
 if(!CH._raf){CH._raf=requestAnimationFrame(()=>{CH._raf=0;render();if(LENS_ON)drawLensMag()})}}
cv.onmouseleave=()=>{CH.on=false;$('lenscv').style.display='none';$('lvltip').style.display='none';render()}
cv.onmouseenter=()=>{if(LENS_ON)$('lenscv').style.display='block'}
function barAtX(mx){if(!D)return null;let best=null,bd=1e9;for(let i=0;i<=revIdx;i++){let dx=Math.abs(window._x(i)-mx);if(dx<bd){bd=dx;best=i}}return bd<window._bw?best:null}
function selectBar(bi){let b=D.bars[bi];sel={is_bar:true,_key:'bar'+bi,setup:'tag',dir:'',entry_bar:bi,sig_bar:bi};
 $('selpanel').style.display='block';$('tagwrap').style.display='block';let nt=(notes.setups||{})['bar'+bi]||{};
 $('selinfo').innerHTML=`<b style="color:#f1c40f">tag bar ${bi+1}</b> · ${b[1]} · O${b[2]} H${b[3]} L${b[4]} C${b[5]}`+(nt.grade?` · grade <b>${nt.grade}</b>`:'');
 $('tagname').value=nt.name||'';$('note').value=nt.note||'';render()}
function saveTagName(){if(sel&&sel.is_bar)setNote({name:$('tagname').value})}
function selectTrade(t){sel=t;$('selpanel').style.display='block';$('tagwrap').style.display='none';let k=tkey(t);let nt=(notes.setups||{})[k]||{};
 let pills,tag,why='';
 if(t.is_fade){tag=t.fade_tradeable?'FADE (tradeable)':'FADE (DEAD)';pills=`<span class=pill>4pt stop</span> <span class=pill>${t.dir=='S'?'BEAR-gated':'BULL-gated'}</span> <span class=pill>gap ${t.pass_gap?'✓':'✕'}</span> <span class=pill>09-13 ${t.pass_window?'✓':'✕'}</span> <span class=pill style="border-color:${t.fade_tradeable?'#e67e22':'#7f8c8d'}">${tag}</span>`;if(!t.fade_tradeable)why=' — f2ES-long is DEAD (PF 0.71), do not trade';}
 else{tag=t.in_book?'IN BOOK':'EXCLUDED';why=t.in_book?'':' — excluded: '+[!t.pass_sma20?'wrong side of SMA20':'',!t.pass_skipTD?'day-after-trend-day':'',!t.pass_gap?'gap>0.54%':'',!t.pass_window?'outside 09-13':''].filter(Boolean).join(', ');pills=`<span class=pill>SMA20 ${t.pass_sma20?'✓':'✕'}</span> <span class=pill>skipTD ${t.pass_skipTD?'✓':'✕'}</span> <span class=pill>WT ${t.with_trend?'✓':'✕'}</span> <span class=pill style="border-color:${t.in_book?'#2ecc71':'#e74c3c'}">${tag}</span>`;}
 $('selinfo').innerHTML=`<b style="color:${setupCol(t)}">${setupLbl(t)}</b> ${t.dir=='S'?'short':'long'} · sig b${t.sig_bar+1} · fill b${t.entry_bar+1}<br>trigger ${t.trigger} · entry ${t.entry_px} · stop ${t.stop} · exit ${t.exit_px} (b${t.exit_bar+1})<br>net <span class=${t.net>0?'win':'loss'}>${t.net>0?'+':''}${t.net}</span> ${pills}<span style="color:#e67e22">${why}</span>`;
 $('note').value=nt.note||'';render()}
function toggleSettings(){let s=$('settings');s.style.display=s.style.display=='none'?'block':'none';if(s.style.display=='block')buildSettings()}
function buildSettings(){
 let LV=[['pH','prior high'],['pL','prior low'],['pC','prior close'],['sma','SMA20'],['open','open'],['ibh','IB high'],['ibl','IB low']];
 let dopt=d=>['solid','dash','dot'].map(o=>`<option ${o==d?'selected':''}>${o}</option>`).join('');
 let lvHtml=LV.map(([k,lab])=>{let s=CFG.lv[k];return `<div style="display:flex;align-items:center;gap:3px;margin:2px 0;font-size:11px">
   <input type=checkbox ${s.on?'checked':''} onchange="CFG.lv['${k}'].on=this.checked?1:0;saveCfg();render()">
   <span style="width:58px">${lab}</span>
   <input type=color value="${s.c}" oninput="CFG.lv['${k}'].c=this.value;saveCfg();render()">
   <input type=range min=1 max=4 step=1 value="${s.w}" title=width style="width:38px" oninput="CFG.lv['${k}'].w=+this.value;saveCfg();render()">
   <select onchange="CFG.lv['${k}'].d=this.value;saveCfg();render()" style="font-size:10px">${dopt(s.d)}</select>
   <input type=range min=0 max=1 step=0.05 value="${s.a==null?1:s.a}" title="opacity (0=transparent)" style="width:36px" oninput="CFG.lv['${k}'].a=+this.value;saveCfg();render()"></div>`}).join('');
 let TL=[['entry','entry'],['stop','stop'],['trig','trigger']];
 let tlHtml=TL.map(([k,lab])=>{let s=CFG.tl[k];return `<div style="display:flex;align-items:center;gap:3px;margin:2px 0;font-size:11px"><span style="width:58px">${lab}</span><input type=range min=1 max=4 step=1 value="${s.w}" title=width style="width:38px" oninput="CFG.tl['${k}'].w=+this.value;saveCfg();render()"><select onchange="CFG.tl['${k}'].d=this.value;saveCfg();render()" style="font-size:10px">${dopt(s.d)}</select></div>`}).join('');
 let rows=[['cUp','up candle'],['cDn','down candle'],['cEma','EMA20 line'],['cEntry','entry line'],['cStop','stop line'],['cTrig','trigger line'],['cBull','bull shade'],['cBear','bear shade'],['cIb','IB fill'],['bg','background']];
 let colHtml=rows.map(([k,lab])=>`<div class=stat><span>${lab}</span><input type=color value="${CFG[k]}" oninput="CFG['${k}']=this.value;saveCfg();render()"></div>`).join('');
 let ibFillHtml=`<div class=stat><span>IB fill shade</span><input type=checkbox ${CFG.ibFill?'checked':''} onchange="CFG.ibFill=this.checked?1:0;saveCfg();render()"></div>`;
 let opHtml=[['regOp','regime opacity'],['ibOp','IB opacity']].map(([k,lab])=>`<div class=stat><span>${lab}</span><input type=range min=0 max=0.4 step=0.01 value="${CFG[k]}" oninput="CFG['${k}']=+this.value;saveCfg();render()"></div>`).join('');
 $('setbody').innerHTML=`<div style="color:#8b93a0;font-size:10px;margin:4px 0">LEVELS (on·color·width·style·opacity)</div>${lvHtml}<div style="color:#8b93a0;font-size:10px;margin:6px 0 2px">TRADE LINES (width·style)</div>${tlHtml}<div style="color:#8b93a0;font-size:10px;margin:6px 0 2px">CHART</div>${colHtml}${ibFillHtml}${opHtml}`}
function tkey(t){return t._key||(t.entry_bar+t.dir)}
const REVNAME={T:'Trap',B:'BO',O:'OB',I:'IB'};
function pickRev(mx){let best=null,bd=1e9;for(let H of window._revHit||[]){if(mx>=H.x0&&mx<=H.x1){let d=Math.abs(H.xc-mx);if(d<bd){bd=d;best=H.r}}}return best}
function revBox(r){let up=r[1]>0,typ=r[2];return `<b style="color:${REVCOL[typ]};font-size:13px">${REVNAME[typ]} + FT</b> ${up?'long ▲':'short ▼'}`+
 `<br><span style="color:#8b93a0">reversal bar</span> ${r[3]+1} · <span style="color:#8b93a0">FT bar</span> ${r[0]+1}`+
 `<br><span style="color:#8b93a0">entry (FT close)</span> ${r[4]} · <span style="color:#8b93a0">stop</span> ${r[5]}`;}
function csvBox(c,H){let up=c[1]>0,typ=c[2],btc=c[4],stop=c[5],lmt=c[6],risk=Math.abs(lmt-stop);
 let head=`<b style="color:${REVCOL[typ]};font-size:13px">${REVNAME[typ]} · NT export</b> ${up?'long':'short'}`+
  `<br><span style="color:#8b93a0">LMT</span> <b>${lmt}</b> · <span style="color:#8b93a0">stop</span> ${stop} · <span style="color:#8b93a0">1R</span> ${risk.toFixed(2)}pt (${(risk*50).toFixed(0)}$)`;
 if(!H||H.fillB<0)return head+`<br><span style="color:#e67e22">not filled (session)</span>`;
 let e=H.exit,ft=`filled in ${H.btf} bar${H.btf==1?'':'s'}`;
 if(!e)return head+`<br><span style="color:#2ecc71">${ft}</span>`;
 let win=e.pnl>0,oc=e.oc=='target'?'1R target ✓':e.oc=='stop'?'stop ✗':'EOD flat';
 return head+`<br><span style="color:#2ecc71">${ft}</span> → <b style="color:${win?'#2ecc71':'#e74c3c'}">${oc} ${win?'+':''}$${e.pnl}</b>`+
  `<br><span style="color:#8b93a0">exit</span> b${e.exitBar} · <span style="color:#8b93a0">1R tgt</span> ${e.tgt} · <span style="color:#8b93a0">${e.pts>0?'+':''}${e.pts}pt</span>`;}
function boBox(H){let tr=H.tr,long=tr[1]>0,pnl=tr[4],reason=tr[5],win=pnl>0;
 let oc=reason==0?'stop ✗':reason==1?'2R target ✓':'flat@close';
 return `<b style="color:#16c60c;font-size:13px">BO setup</b> ${long?'long':'short'} <span style="color:#8b93a0">(market entry, 2R)</span>`+
  `<br><span style="color:#8b93a0">entry</span> ${H.entry.toFixed(2)} · <span style="color:#8b93a0">stop</span> ${H.stop.toFixed(2)} · <span style="color:#8b93a0">2R tgt</span> ${H.tgt.toFixed(2)} · <span style="color:#8b93a0">1R</span> ${H.risk.toFixed(2)}pt`+
  `<br><b style="color:${win?'#2ecc71':'#e74c3c'}">${oc} ${win?'+':''}$${pnl}</b> <span style="color:#8b93a0">(tick-accurate)</span>`;}
function selectRev(r){let bi=r[0],up=r[1]>0,typ=r[2],revbar=r[3],entry=r[4],stop=r[5];
 sel={is_rev:true,_key:'R'+D.date+bi+typ,setup:'rev'+typ,dir:up?'L':'S',entry_bar:bi,sig_bar:bi,entry_px:entry,stop:stop};
 $('selpanel').style.display='block';$('tagwrap').style.display='none';let nt=(notes.setups||{})[tkey(sel)]||{};
 $('selinfo').innerHTML=`<b style="color:${REVCOL[typ]}">${REVNAME[typ]} + FT</b> ${up?'long ▲':'short ▼'} · reversal bar ${revbar+1} · FT bar ${bi+1}`+
   `<br>entry(FT close) ${entry} · stop ${stop}`+(nt.grade?` · grade <b>${nt.grade}</b>`:'');
 $('note').value=nt.note||'';render()}
function grade(g){if(!sel)return;setNote({grade:g})}
function takeskip(v){if(!sel)return;setNote({takeskip:v})}
function saveSel(){if(!sel)return;setNote({note:$('note').value})}
function setNote(o){let k=tkey(sel);notes.setups=notes.setups||{};notes.setups[k]=Object.assign({setup:setupLbl(sel),entry_bar:sel.entry_bar,sig_bar:sel.sig_bar,dir:sel.dir,is_bar:!!sel.is_bar,with_trend:sel.with_trend,in_book:sel.in_book,net:sel.net,reveal_idx:revIdx},notes.setups[k]||{},o);save()}
function saveDay(){notes.daytype_inter=$('dti').value;notes.daytype_inter_bar=revIdx;notes.daytype_final=$('dtf').value;$('ibar').textContent=revIdx;save()}
function save(){fetch('/save/'+curDate,{method:'POST',body:JSON.stringify(notes)})}
function openLens(){if(!sel){return}$('lens').style.display='block';drawLens()}
function drawLens(){if(!sel||!D)return;let t=sel,bars=D.bars,padN=+$('lpad').value;
 let ctr=(t.entry_bar!=null?t.entry_bar:t.sig_bar);         // CENTER on entry/signal, not the far exit
 let i0=Math.max(0,ctr-padN),i1=Math.min(bars.length-1,Math.min(revIdx,ctr+padN));
 let fin=v=>typeof v=='number'&&isFinite(v);
 let entryPx=fin(t.entry_px)?t.entry_px:bars[ctr][5];       // rev/tag: use bar close as entry
 let title=t.is_bar?`tag bar ${ctr+1}`:t.is_rev?`${t.setup} ${t.dir} rev · bar ${ctr+1}`:setupLbl(t);
 $('lenstitle').textContent=`${title} — bars ${i0+1}..${i1+1}${fin(t.net)?` · net ${t.net>0?'+':''}${t.net}`:''}`;
 let LT=document.body.classList.contains('light')||document.body.classList.contains('grey');
 let GRID=LT?'#e4e7eb':'#161c23',AX=LT?'#8a94a0':'#6b7480',TX=LT?'#98a2ad':'#5a6470',BAR=LT?'#333':'#fff';
 let c=$('lcv'),dpr=Math.min(window.devicePixelRatio||1,3);let cw=c.clientWidth,chh=c.clientHeight;
 c.width=Math.round(cw*dpr);c.height=Math.round(chh*dpr);let g=c.getContext('2d');g.setTransform(dpr,0,0,dpr,0,0);
 c.style.background=LT?'#fbfbfa':'#0c0f13';let W=cw,H=chh,pl=52,bot=H-24;
 let lo=1e9,hi=-1e9;for(let i=i0;i<=i1;i++){lo=Math.min(lo,bars[i][4]);hi=Math.max(hi,bars[i][3])}
 for(let v of [entryPx,t.stop,t.trigger])if(fin(v)){lo=Math.min(lo,v);hi=Math.max(hi,v)}
 let rng=(hi-lo)||1;lo-=rng*.08;hi+=rng*.08;rng=hi-lo;let n=i1-i0+1,bw=(W-pl-14)/n;
 let x=i=>pl+(i-i0)*bw+bw/2,y=p=>10+(hi-p)/rng*(bot-10);
 g.clearRect(0,0,W,H);g.font='11px sans-serif';g.textAlign='right';
 for(let k=0;k<=8;k++){let p=lo+rng*k/8,yy=y(p);g.strokeStyle=GRID;g.beginPath();g.moveTo(pl,yy);g.lineTo(W-14,yy);g.stroke();g.fillStyle=AX;g.fillText((Math.round(p/0.25)*0.25).toFixed(2),pl-4,yy+3)}
 g.strokeStyle=CFG.cEma;g.lineWidth=1.6;g.beginPath();for(let i=i0;i<=i1;i++){let xx=x(i),yy=y(bars[i][6]);i==i0?g.moveTo(xx,yy):g.lineTo(xx,yy)}g.stroke();g.lineWidth=1;
 for(let [v,col,dash,lab] of [[t.trigger,CFG.cTrig,[1,3],'trigger'],[entryPx,CFG.cEntry,[],t.is_bar?'close':'entry'],[t.stop,CFG.cStop,[5,3],'stop']])if(fin(v)){g.strokeStyle=col;g.setLineDash(dash);g.beginPath();g.moveTo(pl,y(v));g.lineTo(W-14,y(v));g.stroke();g.setLineDash([]);g.fillStyle=col;g.textAlign='left';g.fillText(lab+' '+v,pl+3,y(v)-3)}
 for(let i=i0;i<=i1;i++){let b=bars[i],up=b[5]>=b[2],col=up?CFG.cUp:CFG.cDn,xx=x(i);g.strokeStyle=col;g.fillStyle=col;g.beginPath();g.moveTo(xx,y(b[3]));g.lineTo(xx,y(b[4]));g.stroke();let yo=y(b[2]),yc=y(b[5]);g.fillRect(xx-bw*.34,Math.min(yo,yc),Math.max(1.5,bw*.68),Math.max(1,Math.abs(yo-yc)));
  g.fillStyle=(i==t.sig_bar)?'#4a9eff':(i==ctr?BAR:TX);g.font='9px sans-serif';g.textAlign='center';g.fillText(i+1,xx,bot+12);
  if(i==ctr){g.fillStyle='#4a9eff';g.fillText(t.is_bar?'★':'fill',xx,12)}if(fin(t.exit_bar)&&i==t.exit_bar&&t.exit_bar<=revIdx){g.fillStyle=LT?'#555':'#dfe4e8';g.fillText('exit',xx,12)}}
 g.fillStyle=CFG.cEntry;if(ctr>=i0&&ctr<=i1){g.beginPath();g.arc(x(ctr),y(entryPx),4,0,7);g.fill()}
 if(fin(t.exit_bar)&&fin(t.exit_px)&&t.exit_bar<=revIdx&&t.exit_bar>=i0&&t.exit_bar<=i1){g.fillStyle=LT?'#555':'#dfe4e8';g.beginPath();g.arc(x(t.exit_bar),y(t.exit_px),4,0,7);g.fill()}}
function openPaths(){$('modal').style.display='block';if(PATHS){drawPaths();return}fetch('/allpaths').then(r=>r.json()).then(j=>{PATHS=j;drawPaths()})}
function median(a){if(!a.length)return 0;let s=[...a].sort((x,y)=>x-y),m=s.length>>1;return s.length%2?s[m]:(s[m-1]+s[m])/2}
function drawPaths(){if(!PATHS)return;let dir=$('p_dir').value;
 let win=PATHS.win.filter(t=>dir=='all'||t.dir==dir),loss=PATHS.loss.filter(t=>dir=='all'||t.dir==dir);
 let c=$('pcv');c.width=c.clientWidth;c.height=c.clientHeight;let g=c.getContext('2d'),W=c.width,H=c.height,pl=44,pb=24;
 let all=[...win,...loss];if(!all.length)return;let maxL=Math.max(...all.map(t=>t.r.length));
 let rmax=Math.max(1.5,...all.flatMap(t=>t.r.map(Math.abs)));
 let X=i=>pl+i/(maxL-1)*(W-pl-10),Y=r=>10+(rmax-r)/(2*rmax)*(H-10-pb);
 g.clearRect(0,0,W,H);g.strokeStyle='#1a2028';g.fillStyle='#6b7480';g.font='10px sans-serif';g.textAlign='right';
 for(let r=-Math.floor(rmax);r<=rmax;r++){let yy=Y(r);g.strokeStyle=r==0?'#3a444f':'#161c23';g.beginPath();g.moveTo(pl,yy);g.lineTo(W-10,yy);g.stroke();g.fillStyle='#6b7480';g.fillText(r+'R',pl-4,yy+3)}
 g.textAlign='center';for(let k=0;k<maxL;k+=Math.ceil(maxL/12)){g.fillText(k,X(k),H-8)}
 function drawSet(set,col){g.strokeStyle=col;g.lineWidth=1;for(let t of set){g.globalAlpha=.10;g.beginPath();t.r.forEach((r,i)=>i?g.lineTo(X(i),Y(r)):g.moveTo(X(i),Y(r)));g.stroke()}g.globalAlpha=1}
 function drawMed(set,col){if(!set.length)return;g.strokeStyle=col;g.lineWidth=2.4;g.beginPath();for(let i=0;i<maxL;i++){let v=set.filter(t=>i<t.r.length).map(t=>t.r[i]);if(!v.length)break;let m=median(v);i?g.lineTo(X(i),Y(m)):g.moveTo(X(i),Y(m))}g.stroke();g.lineWidth=1}
 if($('p_win').checked)drawSet(win,'#2ecc71');if($('p_loss').checked)drawSet(loss,'#e74c3c');
 if($('p_med').checked){if($('p_win').checked)drawMed(win,'#2ecc71');if($('p_loss').checked)drawMed(loss,'#e74c3c')}
 let mfeW=median(win.map(t=>Math.max(...t.r))),maeW=median(win.map(t=>Math.min(...t.r))),mfeL=median(loss.map(t=>Math.max(...t.r))),maeL=median(loss.map(t=>Math.min(...t.r)));
 $('pstats').innerHTML=`<span class=win>winners n=${win.length}</span> · med MFE ${mfeW.toFixed(2)}R · med MAE ${maeW.toFixed(2)}R &nbsp;|&nbsp; <span class=loss>losers n=${loss.length}</span> · med MFE ${mfeL.toFixed(2)}R · med MAE ${maeL.toFixed(2)}R &nbsp;→&nbsp; losers that first ran ≥+0.5R: ${(100*loss.filter(t=>Math.max(...t.r)>=.5).length/(loss.length||1)).toFixed(0)}% (giveback signal)`}
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, body, ctype="application/json", code=200):
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache"); self.send_header("Expires", "0")
        b = body if isinstance(body, bytes) else body.encode()
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        p = self.path
        if p == "/" or p.startswith("/index.html"):
            page = HTML.replace("__DTS__", json.dumps(DAYTYPES))
            return self._send(page, "text/html")
        if p == "/index":
            f = DAYS / "index.json"
            return self._send(f.read_bytes() if f.exists() else b"[]")
        if p == "/allpaths":
            return self._send(json.dumps(build_paths()))
        if p == "/revs":
            f = DAYS / "revs_index.json"
            return self._send(f.read_bytes() if f.exists() else b"{}")
        if p == "/globex":
            f = DAYS / "globex_index.json"
            return self._send(f.read_bytes() if f.exists() else b"{}")
        if p == "/csvsig":
            return self._send(json.dumps(csv_signals()))
        if p == "/bosetup":
            fp = DAYS / "bo_setup_index.json"
            return self._send(fp.read_bytes() if fp.exists() else b"{}")
        if p.startswith("/day/"):
            f = DAYS / (p[5:] + ".json")
            return self._send(f.read_bytes() if f.exists() else b"{}")
        if p.startswith("/notes/"):
            f = NOTES / (p[7:] + ".json")
            return self._send(f.read_bytes() if f.exists() else b"{}")
        self._send(b"not found", "text/plain", 404)

    def do_POST(self):
        if self.path.startswith("/save/"):
            ln = int(self.headers.get("Content-Length", 0))
            (NOTES / (self.path[6:] + ".json")).write_bytes(self.rfile.read(ln))
            return self._send(b'{"ok":1}')
        if self.path == "/recalc":
            ln = int(self.headers.get("Content-Length", 0))
            try:
                params = json.loads(self.rfile.read(ln) or b"{}")
                return self._send(json.dumps(recalc_revs(params)))
            except Exception as e:
                return self._send(json.dumps({"error": str(e)}), code=500)
        self._send(b"not found", "text/plain", 404)


if __name__ == "__main__":
    print("Book Review — warming continuous series for live MyReversals recompute…")
    try:
        _continuous()   # one-time build so the first /recalc is ~2s not ~20s
        print(f"  ready: {len(_CONT)} bars cached")
    except Exception as e:
        print(f"  warm-up skipped: {e}")
    print(f"Book Review  ->  http://localhost:{PORT}   (Ctrl-C to stop)")
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
