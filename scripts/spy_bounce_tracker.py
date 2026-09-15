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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "data" / "spy_bounce"
OUT.mkdir(parents=True, exist_ok=True)
STATE = OUT / "tracker_state.json"
TS = OUT / "pnl_timeseries.csv"
DASH = OUT / "tracker_dashboard.html"
POLL = 30

# (right, strike, qty)  qty +1 long / -1 short
STRUCTS = [
    {"id": "#1 Long 758C", "exp": "20260916", "legs": [("C", 758.0, +1)]},
    {"id": "#2 757/759C debit", "exp": "20260916", "legs": [("C", 757.0, +1), ("C", 759.0, -1)]},
    {"id": "#3 756/754P credit", "exp": "20260916", "legs": [("P", 756.0, -1), ("P", 754.0, +1)]},
    {"id": "#4 Long 757C (~1wk)", "exp": "20260922", "legs": [("C", 757.0, +1)]},
]


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

    # subscribe streaming tickers for every leg + a 757 C/P pair for spot (parity)
    legs = uniq_legs()
    SPOT_EXP, SPOT_K = STRUCTS[1]["exp"], 757.0
    for r in ("C", "P"):
        if (SPOT_EXP, SPOT_K, r) not in legs:
            legs.append((SPOT_EXP, SPOT_K, r))
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

    # ---- 30s mark loop ----
    while True:
        try:
            ib.sleep(POLL)
            now = dt.datetime.now()
            spot = spy_spot()
            row = {"ts": now.strftime("%Y-%m-%d %H:%M:%S"), "spy": spot, "pnl": {}}
            for st in STRUCTS:
                sid = st["id"]; e = st["exp"]
                expired = now.strftime("%Y%m%d") > e or \
                    (now.strftime("%Y%m%d") == e and now.hour >= 23)   # after 16:00 ET close (machine = ET+6/7)
                ev = state["entry"][sid]["entry_val"]
                if expired and spot:
                    cv = 0.0
                    for r, k, qty in st["legs"]:
                        intr = max(0.0, spot - k) if r == "C" else max(0.0, k - spot)
                        cv += qty * intr
                    pnl = round((cv - ev) * 100, 0)
                    state["settled"][sid] = {"spy_settle": spot, "pnl_$": pnl,
                                             "at": now.isoformat(timespec="seconds")}
                else:
                    cv = 0.0; bad = False
                    for r, k, qty in st["legs"]:
                        m = leg_px((e, k, r), "mid")
                        if m is None:
                            bad = True; break
                        cv += qty * m
                    pnl = None if bad else round((cv - ev) * 100, 0)
                row["pnl"][sid] = pnl
            with TS.open("a") as f:
                f.write(row["ts"] + f",{spot}," +
                        ",".join(str(row["pnl"].get(st["id"], "")) for st in STRUCTS) + "\n")
            write_dash(state, row)
            print(row["ts"], "SPY", spot, {k: v for k, v in row["pnl"].items()}, flush=True)
            if len(state["settled"]) == len(STRUCTS):
                print("all structures settled — done."); break
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
        STATE.write_text(json.dumps(state, indent=2))
    ib.disconnect()


def write_dash(state, row):
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
        rows += (f"<tr><td>{sid}</td><td class='lg'>{legs}</td>"
                 f"<td>{abs(dc):,.0f} {kind}</td>{cell(pnl)}<td class='{ 'ex' if settled else 'op'}'>{stat}</td></tr>")
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
.lg{{color:#9fb4d8}} .op{{color:#e8c000}} .ex{{color:#888}} .tot{{font-size:18px;margin-top:14px}}</style></head>
<body><h2>SPY bounce test — 4 structures, live P&amp;L</h2>
<div class=sub>entry locked {state['locked_ct']} · SPY@entry {state['spy_entry']} · updated {row['ts']} (every {POLL}s) · SPY {row['spy']}</div>
<table><tr><th>structure</th><th>legs</th><th>entry</th><th>P&amp;L $</th><th>status</th></tr>
{rows}</table>
<div class=tot>net P&amp;L: <span class='{ 'up' if total>0 else 'dn' if total<0 else 'n'}'>{total:+,.0f}</span>
<span class=sub>(marketable entry fills; MTM at mid; intrinsic at expiry)</span></div></body></html>"""
    tmp = DASH.with_suffix(".tmp"); tmp.write_text(html, encoding="utf-8"); tmp.replace(DASH)


if __name__ == "__main__":
    main()
