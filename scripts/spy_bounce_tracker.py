"""spy_bounce_tracker.py — live paper-track the 4 SPY bounce structures to expiry (S119).

Locks entry at REALISTIC marketable fills (buy=ask, sell=bid — no mid fantasy), then
every 30s re-marks each structure off live OPRA mids, appends a P&L timeseries, and
rewrites a self-refreshing dashboard. Settles each structure at intrinsic on its expiry.

State persists (data/spy_bounce/tracker_state.json) so a restart resumes the SAME entry.

  .venv/Scripts/python.exe scripts/spy_bounce_tracker.py            # run (background ok)
  .venv/Scripts/python.exe scripts/spy_bounce_tracker.py --reset    # re-lock entry now
"""
from __future__ import annotations
import datetime as dt
import json
import math
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "data" / "spy_bounce"
OUT.mkdir(parents=True, exist_ok=True)
STATE = OUT / "tracker_state.json"
TS = OUT / "pnl_timeseries.csv"
DASH = OUT / "tracker_dashboard.html"
POLL = 30

# ── live-data gate: SPY options (OPRA) trade 09:30–16:15 ET, Mon–Fri, ex-holidays.
#    Outside this window there are NO live SPY option quotes, so the tracker idles
#    (no CSV row, no re-mark) and only holds the last live marks on the dashboard.
ET = ZoneInfo("America/New_York")
MARKET_HOLIDAYS = {                      # NYSE full closes — SPY options do not trade
    "2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25",
    "2026-06-19", "2026-07-03", "2026-09-07", "2026-11-26", "2026-12-25",
}
EARLY_CLOSE = {"2026-11-27", "2026-12-24"}   # cash 13:00 ET / SPY options 13:15 ET


def _sched(now_et):
    """(open, mark_close, expiry_close) datetimes for now_et's date, or None if not a trading day."""
    d = now_et.strftime("%Y-%m-%d")
    if now_et.weekday() >= 5 or d in MARKET_HOLIDAYS:
        return None
    early = d in EARLY_CLOSE
    o = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    mc = now_et.replace(hour=(13 if early else 16), minute=15, second=0, microsecond=0)
    ec = now_et.replace(hour=(13 if early else 16), minute=0, second=0, microsecond=0)
    return o, mc, ec


def market_status(now_et):
    """SPY options session = 09:30–16:15 ET, Mon–Fri, ex-holidays (13:15 on early-close days)."""
    s = _sched(now_et)
    if s is None:
        return False, ("weekend" if now_et.weekday() >= 5 else "holiday")
    o, mc, _ = s
    if now_et < o:
        return False, "pre-open"
    if now_et >= mc:
        return False, "post-close"
    return True, "open"


def expiry_close_et(exp):
    """16:00 ET on the option's expiry date (13:00 on an early-close day)."""
    dstr = f"{exp[:4]}-{exp[4:6]}-{exp[6:8]}"
    base = dt.datetime(int(exp[:4]), int(exp[4:6]), int(exp[6:8]), tzinfo=ET)
    return base.replace(hour=(13 if dstr in EARLY_CLOSE else 16), minute=0)


def next_session_open(now_et):
    """Next 09:30 ET trading-day open at or after now (label like 'Wed 09:30 ET')."""
    probe = now_et
    for _ in range(10):
        s = _sched(probe)
        if s is not None and now_et < s[0]:
            return s[0].strftime("%a %b %d 09:30 ET")
        probe = (probe + dt.timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0)
    return "?"

# (right, strike, qty)  qty +1 long / -1 short. ref_k = the near-the-money strike on
# the profit (upside) side; breakeven = ref_k + net entry value; all 4 profit if S_T > BE.
STRUCTS = [
    {"id": "#1 Long 758C", "exp": "20260916", "ref_k": 758.0, "legs": [("C", 758.0, +1)]},
    {"id": "#2 757/759C debit", "exp": "20260916", "ref_k": 757.0, "legs": [("C", 757.0, +1), ("C", 759.0, -1)]},
    {"id": "#3 756/754P credit", "exp": "20260916", "ref_k": 756.0, "legs": [("P", 756.0, -1), ("P", 754.0, +1)]},
    {"id": "#4 Long 757C (~1wk)", "exp": "20260922", "ref_k": 757.0, "legs": [("C", 757.0, +1)]},
]
STRAD_K = 757.0


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def uniq_legs():
    s = {}
    for st in STRUCTS:
        for r, k, _ in st["legs"]:
            s[(st["exp"], k, r)] = None
    return list(s)


def valnum(x):
    return x if (x is not None and not math.isnan(x) and x > 0) else None


def main():
    from ib_conn import connect
    from ib_async import Option, Stock
    reset = "--reset" in sys.argv
    ib = connect(allow_live=True, market_data_type=1, timeout=20)
    ib.reqMarketDataType(1)

    # subscribe every leg + a 757 C/P pair PER expiry (spot parity + ATM straddle -> IV)
    legs = uniq_legs()
    for e in sorted({st["exp"] for st in STRUCTS}):
        for r in ("C", "P"):
            if (e, STRAD_K, r) not in legs:
                legs.append((e, STRAD_K, r))
    contracts = {kk: Option("SPY", kk[0], kk[1], kk[2], "SMART", tradingClass="SPY") for kk in legs}
    ib.qualifyContracts(*contracts.values())
    tickers = {kk: ib.reqMktData(c, "", False, False) for kk, c in contracts.items() if c.conId}
    spy = Stock("SPY", "SMART", "USD"); ib.qualifyContracts(spy)
    spy_t = ib.reqMktData(spy, "", False, False)
    ib.sleep(6)

    def leg_px(kk, kind):
        t = tickers.get(kk)
        if not t:
            return None
        return valnum(t.bid) if kind == "bid" else valnum(t.ask) if kind == "ask" \
            else (lambda b, a: round((b + a) / 2, 3) if (b and a) else None)(valnum(t.bid), valnum(t.ask))

    def spy_spot():
        # parity off the 757 strike of the nearest expiry, else delayed stock
        e = STRUCTS[1]["exp"]
        c = leg_px((e, 757.0, "C"), "mid"); p = leg_px((e, 757.0, "P"), "mid")
        if c and p:
            return round(757.0 + c - p, 2)
        return valnum(spy_t.last) or valnum(spy_t.close)

    # ---- entry (lock once) ----
    if STATE.exists() and not reset:
        state = json.loads(STATE.read_text())
    else:
        entry = {}
        for st in STRUCTS:
            ev = 0.0; ok = True
            for r, k, qty in st["legs"]:
                px = leg_px((st["exp"], k, r), "ask" if qty > 0 else "bid")
                if px is None:
                    ok = False; break
                ev += qty * px
            entry[st["id"]] = {"entry_val": round(ev, 3), "ok": ok,
                               "debit_credit_$": round(ev * 100, 0)}
        state = {"locked_ct": dt.datetime.now().isoformat(timespec="seconds"),
                 "spy_entry": spy_spot(), "entry": entry, "settled": {}}
        STATE.write_text(json.dumps(state, indent=2))
        print("ENTRY LOCKED:", json.dumps(entry, indent=2))

    if not TS.exists():
        TS.write_text("ts_ct,spy," + ",".join(st["id"] for st in STRUCTS) + "\n")

    # ---- state carried across loops ----
    last_spot = state.get("last_spot")            # last live SPY (for settlement after close / restart)
    last_row = None

    def mark_row(now, spot, mark_live):
        """Build a dashboard row. mark_live=False -> marks are None (no live quotes)."""
        strad = {}
        if mark_live:
            for e in sorted({s["exp"] for s in STRUCTS}):
                c = leg_px((e, STRAD_K, "C"), "mid"); p = leg_px((e, STRAD_K, "P"), "mid")
                strad[e] = (c + p) if (c and p) else None
        row = {"ts": now.strftime("%Y-%m-%d %H:%M:%S"), "spy": spot, "pnl": {}, "pop": {}, "be": {}}
        for st in STRUCTS:
            sid = st["id"]; e = st["exp"]
            ev = state["entry"][sid]["entry_val"]
            be = round(st["ref_k"] + ev, 2)           # all 4 profit if S_T > BE
            settled = state["settled"].get(sid)
            if settled:
                pnl = settled["pnl_$"]; pop = 100.0 if pnl > 0 else 0.0
            elif mark_live:
                cv = 0.0; bad = False
                for r, k, qty in st["legs"]:
                    m = leg_px((e, k, r), "mid")
                    if m is None:
                        bad = True; break
                    cv += qty * m
                pnl = None if bad else round((cv - ev) * 100, 0)
                sd = strad.get(e)
                pop = round(100 * (1 - norm_cdf((be - spot) / (sd / 0.7979))), 0) \
                    if (sd and sd > 0 and spot) else None
            else:
                pnl = None; pop = None
            row["pnl"][sid] = pnl; row["pop"][sid] = pop; row["be"][sid] = be
        return row

    # ---- gated mark loop: only marks/appends while SPY options quote (09:30–16:15 ET) ----
    while True:
        try:
            ib.sleep(POLL)
            now = dt.datetime.now()
            now_et = dt.datetime.now(ET)
            is_open, reason = market_status(now_et)

            # settle any structure past its 16:00 ET expiry close, at the last live SPY
            for st in STRUCTS:
                sid = st["id"]
                if sid in state["settled"]:
                    continue
                if now_et >= expiry_close_et(st["exp"]) and last_spot is not None:
                    cv = 0.0
                    for r, k, qty in st["legs"]:
                        cv += qty * (max(0.0, last_spot - k) if r == "C" else max(0.0, k - last_spot))
                    ev = state["entry"][sid]["entry_val"]
                    pnl = round((cv - ev) * 100, 0)
                    state["settled"][sid] = {"spy_settle": last_spot, "pnl_$": pnl,
                                             "at": now_et.isoformat(timespec="seconds")}
                    print(f"SETTLED {sid} @ SPY {last_spot} -> {pnl:+,.0f}", flush=True)

            all_done = len(state["settled"]) == len(STRUCTS)

            if is_open and not all_done:
                spot = spy_spot()
                if spot:
                    last_spot = spot; state["last_spot"] = spot
                row = mark_row(now, spot, mark_live=True)
                with TS.open("a") as f:                # append ONLY during the live session
                    f.write(row["ts"] + f",{spot}," +
                            ",".join(str(row["pnl"].get(st["id"], "")) for st in STRUCTS) + "\n")
                last_row = row
                write_dash(state, row, status="LIVE", reason="market open")
                print(row["ts"], "SPY", spot, {k: v for k, v in row["pnl"].items()}, flush=True)
            else:
                # closed (or all settled): hold last live marks, do NOT append the CSV
                base = dict(last_row) if last_row else mark_row(now, last_spot, mark_live=False)
                base["ts_now"] = now.strftime("%Y-%m-%d %H:%M:%S")
                write_dash(state, base,
                           status="SETTLED" if all_done else "CLOSED",
                           reason=("all structures settled" if all_done
                                   else f"{reason} — live SPY option quotes only 09:30–16:15 ET"),
                           next_open=(None if all_done else next_session_open(now_et)))
                print(now.strftime("%Y-%m-%d %H:%M:%S"),
                      ("done:" if all_done else "closed:"), reason, flush=True)

            STATE.write_text(json.dumps(state, indent=2))
            if all_done:
                print("all structures settled — done.", flush=True); break
        except Exception as ex:                       # keep the tracker alive
            print("loop error:", ex, flush=True)
            try:
                if not ib.isConnected():
                    ib = connect(allow_live=True, timeout=20); ib.reqMarketDataType(1)
                    tickers = {kk: ib.reqMktData(c, "", False, False)
                               for kk, c in contracts.items() if c.conId}
                    ib.sleep(4)
            except Exception:
                pass
    ib.disconnect()


def read_series():
    """per-structure P&L series (floats/None) from the timeseries CSV."""
    series = {st["id"]: [] for st in STRUCTS}
    if not TS.exists():
        return series
    lines = TS.read_text().splitlines()
    if len(lines) < 2:
        return series
    hdr = lines[0].split(",")
    idx = {st["id"]: (hdr.index(st["id"]) if st["id"] in hdr else None) for st in STRUCTS}
    for ln in lines[1:]:
        p = ln.split(",")
        for st in STRUCTS:
            j = idx[st["id"]]
            v = p[j] if (j is not None and j < len(p)) else ""
            series[st["id"]].append(None if v in ("", "None") else float(v))
    return series


def svg_curve(vals):
    pts = [(i, v) for i, v in enumerate(vals) if v is not None]
    if len(pts) < 2:
        return "<div class='sub' style='height:120px'>collecting…</div>"
    ys = [v for _, v in pts] + [0.0]
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or 1.0
    dlo, dhi = lo - 0.16 * span, hi + 0.16 * span        # headroom so min/max lines show
    rng = dhi - dlo
    W, H, padx, pady = 900, 120, 14, 14                  # ~7.5:1 -> uniform scale, no distortion
    n = max(1, len(vals) - 1)
    def X(i): return padx + (W - 2 * padx) * i / n
    def Y(v): return pady + (H - 2 * pady) * (1 - (v - dlo) / rng)
    poly = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in pts)
    z, ymin, ymax = Y(0.0), Y(lo), Y(hi)
    last = pts[-1][1]
    col = "#31c07a" if last > 0 else "#ef5350" if last < 0 else "#9aa"
    area = f"{X(pts[0][0]):.1f},{z:.1f} " + poly + f" {X(pts[-1][0]):.1f},{z:.1f}"
    return (f"<svg viewBox='0 0 {W} {H}' width='100%' style='height:auto;display:block'>"
            f"<line x1='{padx}' y1='{z:.1f}' x2='{W-padx}' y2='{z:.1f}' stroke='#4a4a55' stroke-dasharray='4,4'/>"
            f"<line x1='{padx}' y1='{ymax:.1f}' x2='{W-padx}' y2='{ymax:.1f}' stroke='#2f7d55' stroke-dasharray='2,4'/>"
            f"<line x1='{padx}' y1='{ymin:.1f}' x2='{W-padx}' y2='{ymin:.1f}' stroke='#8a3634' stroke-dasharray='2,4'/>"
            f"<polygon points='{area}' fill='{col}' opacity='0.12'/>"
            f"<polyline points='{poly}' fill='none' stroke='{col}' stroke-width='2' "
            f"stroke-linejoin='round' vector-effect='non-scaling-stroke'/>"
            f"<circle cx='{X(pts[-1][0]):.1f}' cy='{Y(last):.1f}' r='3.5' fill='{col}'/>"
            f"<text x='{W-padx}' y='16' fill='{col}' font-size='15' text-anchor='end'>{last:+,.0f}</text>"
            f"<text x='{padx+2}' y='{ymax-3:.1f}' fill='#3f9d6d' font-size='10'>max {hi:+.0f}</text>"
            f"<text x='{padx+2}' y='{ymin+11:.1f}' fill='#b05450' font-size='10'>min {lo:+.0f}</text>"
            f"</svg>")


def write_dash(state, row, status="LIVE", reason="", next_open=None):
    series = read_series()
    curves = ""
    for st in STRUCTS:
        sid = st["id"]
        curves += (f"<div class='card'><div class='ct'>{sid}</div>"
                   f"{svg_curve(series[sid])}</div>")

    def cell(pnl):
        if pnl is None:
            return "<td class='n'>—</td>"
        col = "up" if pnl > 0 else "dn" if pnl < 0 else "n"
        return f"<td class='{col}'>{pnl:+,.0f}</td>"
    rows = ""
    for st in STRUCTS:
        sid = st["id"]
        e = state["entry"][sid]
        dc = e["debit_credit_$"]
        kind = "credit" if dc < 0 else "debit"
        settled = state["settled"].get(sid)
        stat = "EXPIRED" if settled else "open"
        legs = " · ".join(f"{'+' if q>0 else '-'}{k:.0f}{r} {st['exp']}" for r, k, q in st["legs"])
        pnl = settled["pnl_$"] if settled else row["pnl"].get(sid)
        be = row["be"].get(sid)
        pop = row["pop"].get(sid)
        popc = "—" if pop is None else f"{pop:.0f}%"
        rows += (f"<tr><td>{sid}</td><td class='lg'>{legs}</td>"
                 f"<td>{abs(dc):,.0f} {kind}</td><td class='sub'>{be}</td>{cell(pnl)}"
                 f"<td class='pop'>{popc}</td>"
                 f"<td class='{ 'ex' if settled else 'op'}'>{stat}</td></tr>")
    total = sum((state["settled"].get(st["id"], {}).get("pnl_$")
                 if state["settled"].get(st["id"]) else row["pnl"].get(st["id"]) or 0)
                for st in STRUCTS)
    html = f"""<!doctype html><html><head><meta charset=utf-8>
<meta http-equiv=refresh content={POLL}>
<title>SPY bounce test — live P&L</title>
<style>body{{background:#0e0e12;color:#ddd;font:14px Consolas,monospace;margin:18px}}
h2{{color:#eee}} .sub{{color:#888}} table{{border-collapse:collapse;margin-top:12px;width:100%}}
td,th{{padding:7px 12px;border-bottom:1px solid #262630;text-align:right}}
td:first-child,td.lg{{text-align:left}} th{{color:#9aa;text-align:right;border-bottom:1px solid #444}}
.up{{color:#31c07a;font-weight:bold}} .dn{{color:#ef5350;font-weight:bold}} .n{{color:#888}}
.lg{{color:#9fb4d8}} .op{{color:#e8c000}} .ex{{color:#888}} .tot{{font-size:18px;margin-top:14px}}
.pop{{color:#c8a2ff;font-weight:bold}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:18px}}
.card{{background:#14141a;border:1px solid #262630;border-radius:6px;padding:8px 10px}}
.ct{{color:#9fb4d8;font-size:12px;margin-bottom:2px}}</style></head>
<body><h2>SPY bounce test — 4 structures, live P&amp;L</h2>
<div style='margin:6px 0'><span style='background:{ {"LIVE":"#31c07a","CLOSED":"#e8c000","SETTLED":"#9aa0aa"}.get(status,"#9aa") };color:#0e0e12;font-weight:bold;padding:3px 10px;border-radius:4px'>{status}</span> <span class=sub>&nbsp;{reason}{(' · next open ' + next_open) if next_open else ''}</span></div>
<div class=sub>entry locked {state['locked_ct']} · SPY@entry {state['spy_entry']} · last live mark {row['ts']} · SPY {row['spy']}{(' · checked ' + row['ts_now']) if row.get('ts_now') else ''} · poll {POLL}s</div>
<table><tr><th>structure</th><th>legs</th><th>entry</th><th>break-even</th><th>P&amp;L $</th><th>POP*</th><th>status</th></tr>
{rows}</table>
<div class=sub style='margin-top:6px'>*POP = market-implied probability of finishing profitable (risk-neutral, from the live ATM straddle) — not an edge; the FOMC move is already priced in.</div>
<div class=tot>net P&amp;L: <span class='{ 'up' if total>0 else 'dn' if total<0 else 'n'}'>{total:+,.0f}</span>
<span class=sub>(marketable entry fills; MTM at mid; intrinsic at expiry)</span></div>
<h2 style='margin-top:22px;font-size:15px'>equity curves (P&amp;L $ per trade, each 30s snapshot)</h2>
<div class=grid>{curves}</div></body></html>"""
    tmp = DASH.with_suffix(".tmp"); tmp.write_text(html, encoding="utf-8"); tmp.replace(DASH)


if __name__ == "__main__":
    main()
