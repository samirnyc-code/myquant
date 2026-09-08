"""Wall-source 0DTE P&L: trade the SAME gexlog strategy at different wall sources
and compare. Sources:
  gx  gexlog published putWall/callWall
  td  ThetaData per-side walls (our BSM calibration)
  mq  MenthorQ 0DTE gw0(call)/ps0(put)          [only where OTM + available <=07-15]
  fx  fixed-offset baseline: short strikes at spot +- OFFSET (no wall info)

The strategy (options_gameplan.py): two 0DTE SPXW verticals at the 08:30 CT open,
WING=25, 5-pt strikes, cash settle:
  bps Bull Put   short put  @ putWall,  long put  @ putWall-25
  bcs Bear Call  short call @ callWall, long call @ callWall+25

Only the walls differ. Entry = at_time NBBO at 09:31 ET, credit = short_mid-long_mid;
settle = SPX cash close (intrinsic, liability clamped [0,WING]); fees = real IB $1.63/contract.
Size = 1 spread each side ($/pt = 100). A source-day is SKIPPED (not a loss) if its short
strike is not OTM (wall through spot) — flagged, not counted.

Day universe = every gexlog morning day that has a TD calibration CSV (the 77 profile
days, 2026-05-13+), so gx-vs-td gets the full sample; mq/fx fill in where defined.

Reads gexlog raw + td_gex_calib_<date>.csv + mq_truth.csv.
Outputs data/options_sim/wall_pnl_3way.csv + data/gexlog/reports/wall_pnl_3way.html
Usage: python scripts/wall_pnl_3way.py [--entry 09:31:00] [--offset 35] [--pdf]
"""
import argparse
import csv
import glob
import json
import os
import statistics as st
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data/options_sim"
RAW = ROOT / "data/gexlog/raw"
MQ_TRUTH = ROOT / "data/regime/mq_reveng/mq_truth.csv"
OUTCSV = SIM / "wall_pnl_3way.csv"
OUTHTML = ROOT / "data/gexlog/reports/wall_pnl_3way.html"
BASE = "http://127.0.0.1:25503/v3"
WING = 25.0
FEE = 1.63
STEP = 5.0
SOURCES = ["gx", "td", "mq", "fx"]
LABEL = {"gx": "gexlog", "td": "ThetaData", "mq": "MenthorQ", "fx": "fixed-offset"}


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def g(d, *ks, default=None):
    for k in ks:
        d = d.get(k) if isinstance(d, dict) else None
    return d if d is not None else default


def rnd(x):
    return round(x / STEP) * STEP if x is not None else None


# ---------------------------------------------------------------- TD http
def td_get(path):
    try:
        with urllib.request.urlopen(BASE + path, timeout=20) as r:
            body = r.read().decode("utf-8", "replace")
    except Exception:
        return None
    if not body or body.lstrip().startswith("<"):
        return None
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if len(lines) < 2:
        return None
    hdr = [h.strip().strip('"') for h in lines[0].split(",")]
    return dict(zip(hdr, [v.strip().strip('"') for v in lines[-1].split(",")]))


_cache = {}


def leg_mid(date, strike, right, entry):
    key = (date, strike, right)
    if key in _cache:
        return _cache[key]
    exp = date.replace("-", "")
    p = (f"/option/at_time/quote?symbol=SPXW&expiration={exp}&strike={strike:.3f}"
         f"&right={right}&start_date={exp}&end_date={exp}&time_of_day={entry}&format=csv")
    r = td_get(p)
    mid = None
    if r:
        bid, ask = fnum(r.get("bid")), fnum(r.get("ask"))
        if bid is not None and ask is not None and ask >= bid > 0:
            mid = (bid + ask) / 2
    _cache[key] = mid
    return mid


def spx_close(date):
    r = td_get(f"/index/history/eod?symbol=SPX&start_date={date.replace('-','')}"
               f"&end_date={date.replace('-','')}")
    return fnum(r.get("close")) if r else None


# ---------------------------------------------------------------- walls
def gexlog_days():
    out = {}
    for fp in glob.glob(str(RAW / "*_morning.json")):
        d = json.load(open(fp, encoding="utf-8"))
        dt = os.path.basename(fp)[:10]
        out[dt] = dict(spot=fnum(g(d, "levels", "current")),
                       pw=fnum(g(d, "levels", "putWall")), cw=fnum(g(d, "levels", "callWall")))
    return out


def td_walls(dt, spot):
    fp = SIM / f"td_gex_calib_{dt}.csv"
    if not fp.exists() or spot is None:
        return None, None
    rows = [dict(K=fnum(r["strike"]), cr=fnum(r["call_raw"]), pr=fnum(r["put_raw"]))
            for r in csv.DictReader(open(fp, encoding="utf-8"))]
    above = [r for r in rows if r["K"] and r["cr"] is not None and r["K"] > spot]
    below = [r for r in rows if r["K"] and r["pr"] is not None and r["K"] < spot]
    cw = max(above, key=lambda r: r["cr"])["K"] if above else None
    pw = min(below, key=lambda r: r["pr"])["K"] if below else None
    return pw, cw


def mq_days():
    out = {}
    if MQ_TRUTH.exists():
        for r in csv.DictReader(open(MQ_TRUTH, encoding="utf-8")):
            out[r["session_date"]] = (fnum(r.get("ps0")), fnum(r.get("gw0")))
    return out


# ---------------------------------------------------------------- pricing
def vertical_pnl(date, short_k, right, entry, s_close):
    long_k = short_k - WING if right == "P" else short_k + WING
    opt = "put" if right == "P" else "call"
    sm, lm = leg_mid(date, short_k, opt, entry), leg_mid(date, long_k, opt, entry)
    if sm is None or lm is None or s_close is None:
        return None
    credit = sm - lm
    liab = min(WING, max(0.0, (short_k - s_close) if right == "P" else (s_close - short_k)))
    return (credit - liab) * 100 - 4 * FEE   # $ per 1-lot vertical (4 legs of fee)


def condor_pnl(date, pw, cw, spot, entry, sc):
    """Returns (pnl, otm_ok, bps, bcs). otm_ok False if a short strike is not OTM."""
    if pw is None or cw is None or spot is None or not (pw < spot < cw):
        return None, False, None, None
    bps = vertical_pnl(date, pw, "P", entry, sc)
    bcs = vertical_pnl(date, cw, "C", entry, sc)
    if bps is None or bcs is None:
        return None, True, None, None
    return bps + bcs, True, bps, bcs


# ---------------------------------------------------------------- run
def run(entry, offset):
    GX, MQ = gexlog_days(), mq_days()
    dates = sorted(d for d in GX if (SIM / f"td_gex_calib_{d}.csv").exists())
    closes = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        for dt, c in zip(dates, ex.map(spx_close, dates)):
            closes[dt] = c

    rows = []
    for dt in dates:
        spot = GX[dt]["spot"]
        sc = closes[dt]
        walls = {
            "gx": (rnd(GX[dt]["pw"]), rnd(GX[dt]["cw"])),
            "td": td_walls(dt, spot),
            "mq": MQ.get(dt, (None, None)),
            "fx": (rnd(spot - offset) if spot else None, rnd(spot + offset) if spot else None),
        }
        row = {"date": dt, "spot": spot, "spx_close": sc}
        for s in SOURCES:
            pw, cw = walls[s]
            pnl, otm_ok, bps, bcs = condor_pnl(dt, pw, cw, spot, entry, sc)
            row[f"{s}_pw"], row[f"{s}_cw"] = pw, cw
            row[f"{s}_pnl"], row[f"{s}_bps"], row[f"{s}_bcs"] = pnl, bps, bcs
            row[f"{s}_otm"] = otm_ok  # False = wall through spot (ITM, skipped)
        rows.append(row)
    return rows


def summarize(rows):
    agg = {}
    for s in SOURCES:
        p = [r[f"{s}_pnl"] for r in rows if r.get(f"{s}_pnl") is not None]
        itm = sum(1 for r in rows if r.get(f"{s}_otm") is False)
        pd = [r["spot"] - r[f"{s}_pw"] for r in rows if r.get(f"{s}_pnl") is not None and r[f"{s}_pw"]]
        cd = [r[f"{s}_cw"] - r["spot"] for r in rows if r.get(f"{s}_pnl") is not None and r[f"{s}_cw"]]
        agg[s] = dict(total=sum(p), n=len(p), wins=sum(1 for x in p if x > 0), itm_skipped=itm,
                      put_dist=st.mean(pd) if pd else 0, call_dist=st.mean(cd) if cd else 0)
    return agg


def gx_td_breakdown(rows):
    same = mism = 0
    gap = 0.0
    biggest = []
    for r in rows:
        if r.get("gx_pnl") is None or r.get("td_pnl") is None:
            continue
        if r["gx_pw"] == r["td_pw"] and r["gx_cw"] == r["td_cw"]:
            same += 1
        else:
            mism += 1
            d = r["gx_pnl"] - r["td_pnl"]
            gap += d
            biggest.append((r["date"], d, r["gx_pw"], r["gx_cw"], r["td_pw"], r["td_cw"], r["spx_close"]))
    biggest.sort(key=lambda x: -abs(x[1]))
    return same, mism, gap, biggest[:6]


# ---------------------------------------------------------------- HTML
def html(rows, agg, offset, gtb):
    def c(v, f="{:.0f}"):
        return f.format(v) if v is not None else "—"

    def pc(v):
        if v is None:
            return "<td class='muted'>—</td>"
        return f"<td class='{'pos' if v>0 else 'neg' if v<0 else ''}'>{v:+,.0f}</td>"

    tiles = ""
    for s in SOURCES:
        a = agg[s]
        wr = f"{100*a['wins']/a['n']:.0f}%" if a['n'] else "—"
        skip = f" · {a['itm_skipped']} ITM-skip" if a['itm_skipped'] else ""
        tiles += (f"<div class='card'><div class='ct'>{LABEL[s]}</div>"
                  f"<div class='big {'pos' if a['total']>0 else 'neg'}'>${a['total']:+,.0f}</div>"
                  f"<div class='sub'>n={a['n']} · win {wr}{skip}</div>"
                  f"<div class='sub2'>short dist ~{a['put_dist']:.0f}p / {a['call_dist']:.0f}c</div></div>")

    same, mism, gap, biggest = gtb
    gtb_html = (f"<p><b>gexlog vs ThetaData (full sample):</b> {same} days walls IDENTICAL "
                f"(P&L identical) · {mism} days differ · net gap from mismatches "
                f"<b>{gap:+,.0f}</b>. The gap is convexity noise on a few days, both directions:</p>"
                f"<table class='pd'><thead><tr><th>Date</th><th>Δ(gx−td)</th><th>gx P/C</th>"
                f"<th>td P/C</th><th>SPX close</th></tr></thead><tbody>")
    for d, dd, gp, gc, tp, tc, cl in biggest:
        gtb_html += (f"<tr><td>{d}</td>{pc(dd)}<td>{c(gp)}/{c(gc)}</td>"
                     f"<td>{c(tp)}/{c(tc)}</td><td>{c(cl)}</td></tr>")
    gtb_html += "</tbody></table>"

    body = ""
    for r in rows:
        body += f"<tr><td>{r['date']}</td><td>{c(r['spot'])}</td><td>{c(r['spx_close'])}</td>"
        for s in SOURCES:
            body += f"<td>{c(r[f'{s}_pw'])}/{c(r[f'{s}_cw'])}</td>{pc(r.get(f'{s}_pnl'))}"
        body += "</tr>"
    heads = "".join(f"<th>{LABEL[s]} P/C</th><th>{LABEL[s]} P&L</th>" for s in SOURCES)

    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wall-source 0DTE P&L</title><style>{CSS}</style></head><body><div class="wrap">
<header><h1>Same strategy, four wall sources — 0DTE P&L</h1>
<div class="lede">gx_bps + gx_bcs (WING 25, 08:30 CT open, cash settle), priced from ThetaData.
{len(rows)} days (2026-05-13+). Only the walls differ. fixed-offset = spot ± {offset:.0f} (a
wall-free baseline). MenthorQ only where its 0DTE walls are OTM and available (≤07-15).</div></header>
<section class="tiles">{tiles}</section>
<section class="note"><b>⚠ Read P&L as structure, not skill.</b> A source with wider short
strikes (see "short dist") breaches less and looks better on a calm sample — that's conservatism,
not wall quality. MenthorQ's walls sit ~1.7× farther out (its gamma walls also pass through spot
on some days → those are ITM-skipped, not counted). The <b>fixed-offset baseline</b> (no wall info)
is here so you can see how much any wall source beats a dumb symmetric condor. Judge wall quality
only over many days incl. stress — not this window.</section>
<section><h2>gexlog vs ThetaData — the replication check</h2>{gtb_html}
<p class="muted">On identical-wall days P&L is identical by construction; the gap is a few
convex 0DTE days and cuts both ways — noise, not a systematic TD bias. Needs a multi-year sample to
resolve any real bias.</p></section>
<section><h2>Per-day P&L</h2><table class="pd"><thead><tr><th>Date</th><th>spot</th>
<th>close</th>{heads}</tr></thead><tbody>{body}</tbody></table></section>
<footer>wall_pnl_3way.py · ThetaData entry NBBO + SPX settle · WING={int(WING)} · fee ${FEE} · mid-fill</footer>
</div></body></html>"""


CSS = """
:root{color-scheme:light dark}*{box-sizing:border-box}
body{margin:0;font:14px/1.55 -apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#0d1117;color:#e6edf3}
@media(prefers-color-scheme:light){body{background:#fff;color:#1a1a1a}}
.wrap{max-width:1040px;margin:0 auto;padding:26px 20px 70px}
h1{font-size:23px;margin:0 0 6px}h2{font-size:18px;border-bottom:1px solid #30363d;padding-bottom:6px}
.lede{color:#8b949e}@media(prefers-color-scheme:light){.lede{color:#555}}
section{margin:22px 0}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.card{background:#161b22;border:1px solid #30363d;border-radius:11px;padding:13px}
@media(prefers-color-scheme:light){.card{background:#f6f8fa;border-color:#d0d7de}}
.ct{font-size:11.5px;text-transform:uppercase;color:#8b949e;font-weight:700}
.big{font-size:26px;font-weight:800;margin:4px 0}
.sub{font-size:11.5px;color:#adbac7}.sub2{font-size:11px;color:#8b949e;margin-top:2px}
.pos{color:#3fb950}.neg{color:#f85149}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}
th{text-align:left;color:#8b949e;font-size:11px;border-bottom:1px solid #30363d;padding:5px 6px}
td{padding:4px 6px;border-bottom:1px solid #21262d}
@media(prefers-color-scheme:light){td{border-color:#eaecef}}
td.pos{color:#3fb950;font-weight:600}td.neg{color:#f85149;font-weight:600}.muted{color:#8b949e}
.note{background:#2b1a0e;border-left:3px solid #d29922;padding:11px 15px;border-radius:6px;font-size:13px}
@media(prefers-color-scheme:light){.note{background:#fff8e6}}
footer{margin-top:32px;color:#6e7681;font-size:12px;border-top:1px solid #21262d;padding-top:12px}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", default="09:31:00")
    ap.add_argument("--offset", type=float, default=35.0, help="fixed-offset baseline distance")
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    rows = run(a.entry, a.offset)
    agg = summarize(rows)
    gtb = gx_td_breakdown(rows)
    cols = list(rows[0].keys())
    with open(OUTCSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    OUTHTML.write_text(html(rows, agg, a.offset, gtb), encoding="utf-8")

    print(f"\n{len(rows)} days (2026-05-13+). offset baseline=+/-{a.offset:.0f}")
    print(f"{'source':>12} {'total P&L':>12} {'n':>4} {'win%':>6} {'ITMskip':>8} {'dist p/c':>10}")
    for s in SOURCES:
        x = agg[s]
        wr = 100 * x['wins'] / x['n'] if x['n'] else 0
        print(f"{LABEL[s]:>12} {x['total']:>12,.0f} {x['n']:>4} {wr:>5.0f}% {x['itm_skipped']:>8} "
              f"{f'{x['put_dist']:.0f}/{x['call_dist']:.0f}':>10}")
    same, mism, gap, big = gtb
    print(f"\ngexlog vs TD: {same} identical-wall days, {mism} differ, gap {gap:+,.0f}")
    print("  top mismatch days (date, delta gx-td):", ", ".join(f"{d} {dd:+.0f}" for d, dd, *_ in big[:4]))
    print(f"-> {OUTCSV}\n-> {OUTHTML}")
    if a.pdf:
        import shutil
        exe = next((c for c in ["msedge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
                    if shutil.which(c) or Path(c).exists()), None)
        if exe:
            subprocess.run([exe, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={OUTHTML.with_suffix('.pdf')}", OUTHTML.as_uri()],
                           check=False, timeout=120, capture_output=True)
    if not a.no_open:
        subprocess.run(["cmd", "/c", "start", "", str(OUTHTML)], shell=True, check=False)
        subprocess.run(["code", str(OUTHTML)], shell=True, check=False)


if __name__ == "__main__":
    main()
