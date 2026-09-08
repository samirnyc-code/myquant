"""Three-source 0DTE gamma-wall comparison: gexlog vs ThetaData(BSM) vs MenthorQ.

For each overlap day it lines up the CALL wall and PUT wall from all three
providers and computes pairwise deltas (SPX points). Also compares the
expected-move / 1D band (gexlog EM, √252, vs MenthorQ 1D, √365).

Sources (all SPX, 0DTE / same-day construct where applicable):
  * gexlog   published putWall/callWall + emLower/emUpper   (data/gexlog/raw/*_morning.json)
  * TD       per-side walls from our calibration            (data/options_sim/td_gex_calib_<date>.csv)
             callWall = max call-gamma strike above spot; putWall = max put-gamma below
  * MenthorQ 0DTE gw0 (call) / ps0 (put) + d1_min/d1_max    (data/regime/mq_reveng/mq_truth.csv)

Spot = gexlog cash close (levels.current). TD rows exist only where a calib CSV
exists (gexlog profile days, 2026-05-13+); gexlog-vs-MQ extends to the full overlap.

Outputs:
  data/options_sim/wall_compare_3way.csv    (per-day, every wall + delta)
  data/gexlog/reports/wall_compare_3way.html
Usage: python scripts/wall_compare_3way.py [--pdf]
"""
import argparse
import csv
import glob
import json
import os
import statistics as st
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/gexlog/raw"
CALIB = ROOT / "data/options_sim"
MQ_TRUTH = ROOT / "data/regime/mq_reveng/mq_truth.csv"
OUTCSV = ROOT / "data/options_sim/wall_compare_3way.csv"
OUTHTML = ROOT / "data/gexlog/reports/wall_compare_3way.html"


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def g(d, *ks, default=None):
    for k in ks:
        d = d.get(k) if isinstance(d, dict) else None
    return d if d is not None else default


def gexlog_walls():
    out = {}
    for fp in glob.glob(str(RAW / "*_morning.json")):
        d = json.load(open(fp, encoding="utf-8"))
        dt = os.path.basename(fp)[:10]
        out[dt] = dict(spot=fnum(g(d, "levels", "current")),
                       pw=fnum(g(d, "levels", "putWall")), cw=fnum(g(d, "levels", "callWall")),
                       em_lo=fnum(g(d, "levels", "emLower")), em_hi=fnum(g(d, "levels", "emUpper")))
    return out


def td_walls(dt, spot):
    """Per-side TD walls from the calibration per-strike CSV."""
    fp = CALIB / f"td_gex_calib_{dt}.csv"
    if not fp.exists() or spot is None:
        return None, None
    rows = [dict(K=fnum(r["strike"]), cr=fnum(r["call_raw"]), pr=fnum(r["put_raw"]))
            for r in csv.DictReader(open(fp, encoding="utf-8"))]
    above = [r for r in rows if r["K"] and r["cr"] is not None and r["K"] > spot]
    below = [r for r in rows if r["K"] and r["pr"] is not None and r["K"] < spot]
    cw = max(above, key=lambda r: r["cr"])["K"] if above else None
    pw = min(below, key=lambda r: r["pr"])["K"] if below else None  # most negative put gamma
    return pw, cw


def mq_walls():
    out = {}
    if not MQ_TRUTH.exists():
        return out
    for r in csv.DictReader(open(MQ_TRUTH, encoding="utf-8")):
        out[r["session_date"]] = dict(
            ps0=fnum(r.get("ps0")), gw0=fnum(r.get("gw0")), cr0=fnum(r.get("cr0")),
            cr=fnum(r.get("cr")), ps=fnum(r.get("ps")),
            d1_min=fnum(r.get("d1_min")), d1_max=fnum(r.get("d1_max")))
    return out


def delta(a, b):
    return (a - b) if (a is not None and b is not None) else None


def build_rows():
    GX, MQ = gexlog_walls(), mq_walls()
    dates = sorted(set(GX) & set(MQ))
    rows = []
    for dt in dates:
        gx, mq = GX[dt], MQ[dt]
        spot = gx["spot"]
        td_pw, td_cw = td_walls(dt, spot)
        rows.append(dict(
            date=dt, spot=spot,
            gx_pw=gx["pw"], gx_cw=gx["cw"], gx_emlo=gx["em_lo"], gx_emhi=gx["em_hi"],
            td_pw=td_pw, td_cw=td_cw,
            mq_pw=mq["ps0"], mq_cw=mq["gw0"], mq_1dlo=mq["d1_min"], mq_1dhi=mq["d1_max"],
            mq_cr=mq["cr"], mq_ps=mq["ps"],
            # call-wall deltas
            dcw_gx_td=delta(gx["cw"], td_cw), dcw_gx_mq=delta(gx["cw"], mq["gw0"]),
            dcw_td_mq=delta(td_cw, mq["gw0"]),
            # put-wall deltas
            dpw_gx_td=delta(gx["pw"], td_pw), dpw_gx_mq=delta(gx["pw"], mq["ps0"]),
            dpw_td_mq=delta(td_pw, mq["ps0"]),
        ))
    return rows


def agg(rows, key):
    vals = [abs(r[key]) for r in rows if r[key] is not None]
    if not vals:
        return None
    return dict(n=len(vals), exact=100 * sum(1 for v in vals if v == 0) / len(vals),
                le5=100 * sum(1 for v in vals if v <= 5) / len(vals),
                med=st.median(vals), mx=max(vals))


# ---------------------------------------------------------------- HTML
def cell(v, fmt="{:.0f}"):
    return fmt.format(v) if v is not None else "—"


def dcell(v):
    if v is None:
        return "<td class='muted'>—</td>"
    if v == 0:
        return "<td class='z'>0</td>"
    return f"<td class='nz'>{v:+.0f}</td>"


def pair_tile(rows, lbl, key):
    a = agg(rows, key)
    if not a:
        return f"<div class='card'><div class='ct'>{lbl}</div><div class='big'>—</div></div>"
    return (f"<div class='card'><div class='ct'>{lbl}</div>"
            f"<div class='big'>{a['exact']:.0f}%<span class='u'>exact</span></div>"
            f"<div class='sub'>≤5pt {a['le5']:.0f}% · median |Δ| {a['med']:.0f}pt · "
            f"max {a['mx']:.0f}pt · n={a['n']}</div></div>")


def wall_table(rows, side):
    if side == "call":
        gk, tk, mk = "gx_cw", "td_cw", "mq_cw"
        d1, d2, d3 = "dcw_gx_td", "dcw_gx_mq", "dcw_td_mq"
        title = "Call wall (gexlog callWall · TD · MQ gw0)"
    else:
        gk, tk, mk = "gx_pw", "td_pw", "mq_pw"
        d1, d2, d3 = "dpw_gx_td", "dpw_gx_mq", "dpw_td_mq"
        title = "Put wall (gexlog putWall · TD · MQ ps0)"
    body = ""
    for r in rows:
        body += (f"<tr><td>{r['date']}</td><td>{cell(r['spot'],'{:.0f}')}</td>"
                 f"<td>{cell(r[gk])}</td><td>{cell(r[tk])}</td><td>{cell(r[mk])}</td>"
                 f"{dcell(r[d1])}{dcell(r[d2])}{dcell(r[d3])}</tr>")
    return (f"<h3>{title}</h3><table class='pd'><thead><tr><th>Date</th><th>spot</th>"
            f"<th>gexlog</th><th>TD</th><th>MQ</th><th>gx−TD</th><th>gx−MQ</th><th>TD−MQ</th>"
            f"</tr></thead><tbody>{body}</tbody></table>")


def band_table(rows):
    body = ""
    for r in rows:
        gw = (r["gx_emhi"] - r["gx_emlo"]) if (r["gx_emhi"] and r["gx_emlo"]) else None
        mw = (r["mq_1dhi"] - r["mq_1dlo"]) if (r["mq_1dhi"] and r["mq_1dlo"]) else None
        body += (f"<tr><td>{r['date']}</td>"
                 f"<td>{cell(r['gx_emlo'])}/{cell(r['gx_emhi'])}</td><td>{cell(gw)}</td>"
                 f"<td>{cell(r['mq_1dlo'])}/{cell(r['mq_1dhi'])}</td><td>{cell(mw)}</td>"
                 f"{dcell(delta(gw, mw))}</tr>")
    return (f"<h3>Expected-move band — gexlog EM (√252) vs MQ 1D (√365)</h3>"
            f"<table class='pd'><thead><tr><th>Date</th><th>gexlog lo/hi</th><th>gx width</th>"
            f"<th>MQ 1D lo/hi</th><th>MQ width</th><th>Δwidth</th></tr></thead>"
            f"<tbody>{body}</tbody></table>")


def build_html(rows):
    td_rows = [r for r in rows if r["td_cw"] is not None or r["td_pw"] is not None]
    d0, d1 = rows[0]["date"], rows[-1]["date"]
    tiles = (
        pair_tile(rows, "Call: gexlog vs MQ", "dcw_gx_mq") +
        pair_tile(td_rows, "Call: gexlog vs TD", "dcw_gx_td") +
        pair_tile(td_rows, "Call: TD vs MQ", "dcw_td_mq") +
        pair_tile(rows, "Put: gexlog vs MQ", "dpw_gx_mq") +
        pair_tile(td_rows, "Put: gexlog vs TD", "dpw_gx_td") +
        pair_tile(td_rows, "Put: TD vs MQ", "dpw_td_mq"))
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>3-source wall comparison</title><style>{CSS}</style></head><body><div class="wrap">
<header><h1>0DTE gamma walls — gexlog vs ThetaData vs MenthorQ</h1>
<div class="lede">SPX, {len(rows)} overlap days ({d0} → {d1}). TD rows where a calibration
exists ({len(td_rows)} days, 2026-05-13+). Δ in SPX points; 0 = exact strike match.</div></header>
<section class="tiles">{tiles}</section>
<section>{wall_table(rows,'call')}</section>
<section>{wall_table(rows,'put')}</section>
<section>{band_table(rows)}</section>
<section class="note"><b>Reading it:</b> gexlog callWall / MQ gw0 = peak call-gamma above spot;
gexlog putWall / MQ ps0 = peak put-gamma below spot; TD = same, computed from ThetaData OI+BSM.
MQ cr/ps (all-expiry) are a broader construct and are in the CSV but not charted here.
The three sources agree often but not always — that spread is exactly what the wall-source
sim needs to price.</section>
<footer>wall_compare_3way.py · gexlog + ThetaData Standard + MenthorQ (mq_truth)</footer>
</div></body></html>"""


CSS = """
:root{color-scheme:light dark}*{box-sizing:border-box}
body{margin:0;font:14.5px/1.55 -apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#0d1117;color:#e6edf3}
@media(prefers-color-scheme:light){body{background:#fff;color:#1a1a1a}}
.wrap{max-width:1000px;margin:0 auto;padding:26px 20px 70px}
h1{font-size:25px;margin:0 0 6px}.lede{color:#8b949e}
@media(prefers-color-scheme:light){.lede{color:#555}}
section{margin:26px 0}h3{font-size:16px;margin:18px 0 8px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
.card{background:#161b22;border:1px solid #30363d;border-radius:11px;padding:14px}
@media(prefers-color-scheme:light){.card{background:#f6f8fa;border-color:#d0d7de}}
.ct{font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;color:#8b949e;font-weight:700}
.big{font-size:29px;font-weight:800;margin:5px 0}.big .u{font-size:11px;font-weight:600;color:#8b949e;margin-left:7px;text-transform:uppercase}
.sub{font-size:12px;color:#adbac7}@media(prefers-color-scheme:light){.sub{color:#555}}
table{width:100%;border-collapse:collapse;font-size:13px;margin-top:6px}
th{text-align:left;color:#8b949e;font-size:11.5px;border-bottom:1px solid #30363d;padding:6px 7px}
td{padding:5px 7px;border-bottom:1px solid #21262d}
@media(prefers-color-scheme:light){td{border-color:#eaecef}}
td.z{color:#3fb950;text-align:center}td.nz{color:#e3b341;font-weight:700;text-align:center}
.muted{color:#8b949e}
.note{background:#161b2288;border-left:3px solid #1f6feb;padding:11px 15px;border-radius:6px;font-size:13.5px}
footer{margin-top:36px;color:#6e7681;font-size:12px;border-top:1px solid #21262d;padding-top:12px}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    rows = build_rows()
    if not rows:
        raise SystemExit("no overlap rows (check gexlog raw + mq_truth.csv)")
    # CSV
    cols = list(rows[0].keys())
    with open(OUTCSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    OUTHTML.write_text(build_html(rows), encoding="utf-8")

    td_rows = [r for r in rows if r["td_cw"] is not None]
    print(f"{len(rows)} overlap days ({rows[0]['date']}..{rows[-1]['date']}); TD on {len(td_rows)}")
    for lbl, key in (("call gx-vs-MQ", "dcw_gx_mq"), ("call gx-vs-TD", "dcw_gx_td"),
                     ("call TD-vs-MQ", "dcw_td_mq"), ("put gx-vs-MQ", "dpw_gx_mq"),
                     ("put gx-vs-TD", "dpw_gx_td"), ("put TD-vs-MQ", "dpw_td_mq")):
        aset = td_rows if "TD" in lbl else rows
        x = agg(aset, key)
        if x:
            print(f"  {lbl:16}: exact {x['exact']:.0f}%  <=5pt {x['le5']:.0f}%  "
                  f"median|d| {x['med']:.0f}  max {x['mx']:.0f}  n={x['n']}")
    print(f"-> {OUTCSV}\n-> {OUTHTML}")
    if a.pdf:
        import shutil
        pdf = OUTHTML.with_suffix(".pdf")
        exe = next((c for c in ["msedge", "chrome",
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"]
                    if shutil.which(c) or Path(c).exists()), None)
        if exe:
            subprocess.run([exe, "--headless", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={pdf}", OUTHTML.as_uri()], check=False,
                           timeout=120, capture_output=True)
            print(f"-> {pdf}")
    if not a.no_open:
        subprocess.run(["cmd", "/c", "start", "", str(OUTHTML)], shell=True, check=False)
        subprocess.run(["code", str(OUTHTML)], shell=True, check=False)


if __name__ == "__main__":
    main()
