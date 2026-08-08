"""Validate improvement-log #20 on the 82-day archive: does the EM band hold as a
function of GAMMA REGIME (not the calendar)?

The refined rule (from 08-07 NFP, n=1): "event + neg-gamma = stand aside; event +
pos-gamma + no in-range flip = EM holds, sell it." This tests it on data we already
own — no scraping. If pos-gamma EM-hit >> neg-gamma (esp. on event days), the rule
earns going live; if not, it was over-fit to one Friday and we do NOT ship it.

Inputs  : C:\\Users\\Admin\\Desktop\\gexlog\\data\\raw\\*_morning.json / *_evening.json
Outputs : data/options_sim/event_gate_validation_YYYYMMDD.csv  (one row per paired day)
          prints the cross-tabs (EM-hit by regime x event x in-range-flip)

Fields used:
  gamma    = morning forecast.factors.gamma.value            (POSITIVE / NEGATIVE)
  em_hit   = evening session_analysis.expected_move_hit       (bool)
  event    = any high-impact macro catalyst scheduled today   (NFP/CPI/FOMC/PCE/...)
  in_flip  = morning GEX flip lies inside [emLower, emUpper]   (dealer inflection in band)
"""
import glob
import json
import re
import datetime as dt
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

RAW = Path(r"C:\Users\Admin\Desktop\gexlog\data\raw")
OUT = Path(r"c:\Users\Admin\myquant\data\options_sim")
CT = ZoneInfo("America/Chicago")

EVENT_RX = re.compile(
    r"nonfarm|payroll|\bcpi\b|inflation|\bfomc\b|fed funds|interest rate deci|"
    r"\bpce\b|jobless|unemployment|\bgdp\b|jackson hole|powell", re.I)


def g(d, *p, default=None):
    for k in p:
        d = d.get(k) if isinstance(d, dict) else None
        if d is None:
            return default
    return d


def is_high(impact):
    return "high" in str(impact).lower()


def event_today(m):
    """High-impact MACRO print scheduled today (title match OR high-impact flag on a
    macro-sounding title). Fed-speaker medium items do NOT count."""
    for c in (g(m, "catalysts", "today", default=[]) or []):
        title = str(c.get("title", ""))
        if EVENT_RX.search(title):
            return True, title
        if is_high(c.get("impact")) and EVENT_RX.search(title):
            return True, title
    return False, ""


def in_range_flip(m):
    lo, hi = g(m, "levels", "emLower"), g(m, "levels", "emUpper")
    flip = g(m, "forecast", "factors", "gamma", "gex_flip")
    if lo is None or hi is None or flip is None:
        return None
    return bool(lo <= flip <= hi)


def main():
    morn = {Path(f).name[:10]: json.load(open(f, encoding="utf-8"))
            for f in glob.glob(str(RAW / "*_morning.json"))}
    even = {Path(f).name[:10]: json.load(open(f, encoding="utf-8"))
            for f in glob.glob(str(RAW / "*_evening.json"))}
    dates = sorted(set(morn) & set(even))

    rows = []
    for d in dates:
        m, e = morn[d], even[d]
        gamma = (g(m, "forecast", "factors", "gamma", "value") or "?").upper()
        emh = g(e, "session_analysis", "expected_move_hit")
        ev, ev_title = event_today(m)
        flip_in = in_range_flip(m)
        rows.append({
            "date": d,
            "gamma": "POS" if gamma.startswith("POS") else ("NEG" if gamma.startswith("NEG") else "?"),
            "em_hit": None if emh is None else bool(emh),
            "event": ev,
            "event_title": ev_title,
            "in_range_flip": flip_in,
            "signal": (g(m, "guidance", "signal") or "?"),
            "session_type": g(e, "session_analysis", "session_type") or "?",
            "spx_change": g(e, "session_analysis", "spx_change"),
        })

    # --- cross-tabs ---
    def rate(pred):
        hit = [r for r in rows if r["em_hit"] is not None and pred(r)]
        if not hit:
            return "n=0", 0
        n = len(hit)
        h = sum(1 for r in hit if r["em_hit"])
        return f"{100*h/n:3.0f}%  (n={n:2d})", n

    lines = []
    lines.append(f"EVENT-GATE VALIDATION (#20) — {len(dates)} paired days "
                 f"({dates[0]}..{dates[-1]})\n")
    lines.append("EM-HELD RATE by gamma regime:")
    for gm in ("POS", "NEG"):
        r, _ = rate(lambda r, gm=gm: r["gamma"] == gm)
        lines.append(f"  {gm:3}                         {r}")
    lines.append("")
    lines.append("EM-HELD RATE by gamma x EVENT-day:")
    for gm in ("POS", "NEG"):
        for ev in (True, False):
            r, _ = rate(lambda r, gm=gm, ev=ev: r["gamma"] == gm and r["event"] == ev)
            lines.append(f"  {gm:3}  event={str(ev):5}          {r}")
    lines.append("")
    lines.append("EM-HELD RATE by gamma x in-range-flip (the full #20 refinement):")
    for gm in ("POS", "NEG"):
        for fl in (True, False):
            r, _ = rate(lambda r, gm=gm, fl=fl: r["gamma"] == gm and r["in_range_flip"] == fl)
            lines.append(f"  {gm:3}  in_range_flip={str(fl):5}  {r}")
    lines.append("")
    lines.append("THE KEY CELL — event days, split every way:")
    for gm in ("POS", "NEG"):
        for fl in (True, False):
            r, _ = rate(lambda r, gm=gm, fl=fl: r["event"] and r["gamma"] == gm and r["in_range_flip"] == fl)
            lines.append(f"  event & {gm:3} & flip={str(fl):5}  {r}")
    lines.append("")
    # list every event day so we can eyeball the sample
    lines.append("EVENT DAYS (the sample the rule rides on):")
    for r in rows:
        if r["event"]:
            lines.append(f"  {r['date']}  {r['gamma']:3}  EM-held={r['em_hit']}  "
                         f"flip_in={r['in_range_flip']}  {r['session_type']:14} "
                         f"[{r['event_title'][:40]}]")

    report = "\n".join(lines)
    print(report)

    # persist: dated CSV + the text report
    import csv
    stamp = dt.datetime.now(CT).strftime("%Y%m%d")
    csv_path = OUT / f"event_gate_validation_{stamp}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    (OUT / f"event_gate_validation_{stamp}.txt").write_text(report, encoding="utf-8")
    print(f"\n-> {csv_path.name}  +  event_gate_validation_{stamp}.txt")


if __name__ == "__main__":
    main()
