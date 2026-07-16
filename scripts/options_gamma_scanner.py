"""Cross-symbol gamma scanner (S75) — our own MenthorQ-style screener.

Pulls net/abs GEX + walls + dominant expiry for a universe of liquid optionable
names via the direct MenthorQ API (mq_api.py — no QUIN), ranks them by dealer
gamma regime, and surfaces where the pin / momentum setups are. This is a
SCREEN (where to look), not a validated edge — every idea it prints is a
hypothesis to be tested by the same gameplan->trigger->postmortem loop.

Per symbol it reports:
  net/abs  — GEX one-sidedness: >0 pinned (dealers mean-revert), <0 explosive
  regime   — PIN(+g) / MOMO(-g) / neutral
  spot, walls (CR / PS0 / HVL) + distance-to-nearest-wall
  dom exp  — the expiration carrying the most gamma (where to trade) + its net GEX
  %ile     — 1y percentile of today's GEX (extremes = mean-revert candidates)
  idea     — the setup the structure suggests (condor/fly for pins; watch for MOMO)

Data hygiene: flags a symbol as SUSPECT if the API spot sits outside its own
wall band (the kind of bad row that showed NFLX at $73). Verify before trading.

Run:
  .venv/Scripts/python.exe scripts/options_gamma_scanner.py [--syms AAPL,NVDA,...]
Writes data/options_sim/scanner_YYYYMMDD.json and prints the ranked table.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mq_api import MQ

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
CT = ZoneInfo("America/Chicago")

DEFAULT_SYMS = ["SPX", "SPY", "QQQ", "IWM", "NVDA", "AAPL", "MSFT", "AMZN",
                "GOOGL", "META", "TSLA", "AMD", "NFLX", "AVGO"]


def scan_symbol(mq, sym):
    row = {"sym": sym}
    try:
        m = mq.matrix(sym, "eod")
        t = m["totals"]
        spot = m.get("spot_price")
        ratio = t["net_gex"] / t["abs_gex"] if t["abs_gex"] else 0.0
        exps = m.get("expirations", [])
        dom = max(exps, key=lambda e: e["abs_gex"]) if exps else None
        row.update({
            "spot": spot, "net_abs": round(ratio, 3),
            "regime": "PIN(+g)" if ratio > 0.15 else ("MOMO(-g)" if ratio < -0.15 else "neutral"),
            "dom_exp": dom["expiration_date"] if dom else None,
            "dom_net_gex_M": round(dom["net_gex"] / 1e6) if dom else None,
        })
    except Exception as e:
        row["error"] = str(e)[:60]
        return row
    # walls + distance
    try:
        lv = mq.levels(sym)
        cr = lv.get("call_resistance"); ps0 = lv.get("put_support_0dte"); hvl = lv.get("hvl")
        row["cr"], row["ps0"], row["hvl"] = cr, ps0, hvl
        if spot and cr and ps0:
            # nearest wall distance as % of spot
            near = min((abs(spot - cr), "CR"), (abs(spot - ps0), "PS0"), (abs(spot - (hvl or spot)), "HVL"))
            row["near_wall"] = near[1]
            row["near_dist_pct"] = round(near[0] / spot * 100, 2)
            # data-hygiene: spot should sit within (ps..cr-ish) band
            lo = min(x for x in (lv.get("put_support"), ps0) if x) if (lv.get("put_support") or ps0) else None
            hi = max(x for x in (lv.get("call_resistance"), cr) if x) if (lv.get("call_resistance") or cr) else None
            if lo and hi and not (lo * 0.7 <= spot <= hi * 1.3):
                row["suspect"] = f"spot {spot} outside wall band {lo}-{hi}"
    except Exception as e:
        row["levels_error"] = str(e)[:40]
    # 1y GEX percentile
    try:
        gi = mq.gamma_insights(sym, 365)
        if gi and isinstance(gi, list):
            last = gi[-1] if isinstance(gi[-1], dict) else None
            pct = (last or {}).get("percentile") or (last or {}).get("gex_percentile")
            if pct is not None:
                row["gex_pctile"] = round(float(pct))
    except Exception:
        pass
    # idea
    r = row.get("net_abs", 0)
    if row.get("suspect"):
        row["idea"] = "SUSPECT DATA — verify spot before trusting"
    elif r > 0.30:
        row["idea"] = f"strong pin → condor/fly @ {row.get('dom_exp','')} between PS0/CR"
    elif r > 0.15:
        row["idea"] = "mild pin → premium-sell at the wall"
    elif r < -0.15:
        row["idea"] = "negative gamma → momentum/breakout watch (long vol, not fade)"
    else:
        row["idea"] = "neutral — no clear gamma edge"
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--syms", help="comma list (default the liquid universe)")
    args = ap.parse_args()
    syms = args.syms.split(",") if args.syms else DEFAULT_SYMS

    mq = MQ()
    rows = [scan_symbol(mq, s.strip().upper()) for s in syms]
    ok = [r for r in rows if "error" not in r]
    ok.sort(key=lambda r: r.get("net_abs", -99), reverse=True)

    date = dt.datetime.now(CT).strftime("%Y%m%d")
    out = SIM / f"scanner_{date}.json"
    out.write_text(json.dumps({"date": date,
                               "generated_ct": dt.datetime.now(CT).strftime("%Y-%m-%d %H:%M:%S CT"),
                               "rows": ok + [r for r in rows if "error" in r]}, indent=2),
                   encoding="utf-8")

    print(f"\nGAMMA SCANNER {date}  ({len(ok)}/{len(rows)} symbols)")
    print(f"  {'SYM':6}{'spot':>9}{'net/abs':>8}{'regime':>10}{'wall':>6}{'dist%':>7}"
          f"{'dom exp':>12}{'%ile':>6}  IDEA")
    print("  " + "-" * 108)
    for r in ok:
        flag = " ⚠" if r.get("suspect") else ""
        print(f"  {r['sym']:6}{(r.get('spot') or 0):>9.1f}{r.get('net_abs', 0):>+8.2f}"
              f"{r.get('regime', ''):>10}{str(r.get('near_wall', '')):>6}"
              f"{(r.get('near_dist_pct') or 0):>6.1f}%{str(r.get('dom_exp', ''))[5:]:>12}"
              f"{str(r.get('gex_pctile', '-')):>6}  {r.get('idea', '')}{flag}")
    errs = [r for r in rows if "error" in r]
    if errs:
        print("  errors: " + ", ".join(f"{r['sym']}({r['error'][:20]})" for r in errs))
    print(f"\nwrote {out}")
    return out


if __name__ == "__main__":
    main()
