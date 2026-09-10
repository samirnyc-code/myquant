"""Live TD shadow desk — independent execution of the SAME orders on ThetaData.

The desk's ONE strategy (options_trigger_daemon) issues orders (open at fire, close
on level-acceptance / 14:45 time-stop). Each order is filled INDEPENDENTLY here off
TD's LIVE feed, in real time, alongside the IB desk. Neither conditions on the other;
EOD we compare the two independently-executed books.

Model (per user, 2026-09-08):
  * TD fills EVERY order the strategy issues (no independent gate).
  * Fill = marketable touch on TD's live NBBO: open credit = short_bid - long_ask;
    close debit = short_ask - long_bid. Real IB fee $1.63/contract/execution.
  * If a leg has NO live TD quote at the moment -> record NO-FILL (part of the compare).

Read-only on the desk: watches gameplan_<date>.json (the daemon writes trig fills/exits
there). Writes only data/options_sim/shadow_td/shadow_book_<date>.json.

Usage:
  python scripts/td_shadow_live.py                 # today, live, until 15:00 CT
  python scripts/td_shadow_live.py --dry 2026-08-04 # parse-only test on a past day (no TD, no loop)
"""
import argparse
import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import notify_telegram as TG
except Exception:
    TG = None
SIM = ROOT / "data/options_sim"
OUTDIR = SIM / "shadow_td"
OUTDIR.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:25503/v3"
FEE = 1.63
POLL_S = 5


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def td_snapshot(expiry, strike, right, retries=3):
    """Live TD NBBO: (bid, ask, bid_size, ask_size) or None if no quote.
    Retries a few times — deep-ITM/thin 0DTE legs momentarily return no NBBO."""
    r_ = "call" if str(right).upper().startswith("C") else "put"
    u = (f"{BASE}/option/snapshot/quote?symbol=SPXW&expiration={expiry}"
         f"&strike={float(strike):.3f}&right={r_}&format=csv")
    for attempt in range(retries):
        try:
            body = urllib.request.urlopen(u, timeout=8).read().decode("utf-8", "replace")
            lines = [l for l in body.splitlines() if l.strip()]
            if len(lines) >= 2 and not lines[0].lstrip().startswith("<"):
                h = [x.strip().strip('"') for x in lines[0].split(",")]
                d = dict(zip(h, [x.strip().strip('"') for x in lines[-1].split(",")]))
                b, a = fnum(d.get("bid")), fnum(d.get("ask"))
                bs, as_ = fnum(d.get("bid_size")), fnum(d.get("ask_size"))
                if b is not None and a is not None and a >= b and a > 0:
                    return (b, a, bs or 0, as_ or 0)
        except Exception:
            pass
        if attempt < retries - 1:
            time.sleep(1.5)
    return None


def td_underlying(expiry, strike, right):
    """Live underlying_price + delta + IV from snapshot/greeks/first_order (Standard).
    underlying_price is time-synced to the option tick. Returns dict or None."""
    r_ = "call" if str(right).upper().startswith("C") else "put"
    u = (f"{BASE}/option/snapshot/greeks/first_order?symbol=SPXW&expiration={expiry}"
         f"&strike={float(strike):.3f}&right={r_}&format=csv")
    try:
        body = urllib.request.urlopen(u, timeout=8).read().decode("utf-8", "replace")
    except Exception:
        return None
    lines = [l for l in body.splitlines() if l.strip()]
    if len(lines) < 2 or lines[0].lstrip().startswith("<"):
        return None
    h = [x.strip().strip('"') for x in lines[0].split(",")]
    d = dict(zip(h, [x.strip().strip('"') for x in lines[-1].split(",")]))
    return {"underlying_price": fnum(d.get("underlying_price")),
            "underlying_ts": d.get("underlying_timestamp"),
            "delta": fnum(d.get("delta")), "iv": fnum(d.get("implied_vol"))}


def fill_open(legs):
    """Marketable-touch OPEN of a credit structure from live TD NBBO.
    legs: [{side,right,strike,expiry,qty}]. Returns (credit, detail, ok)."""
    credit, detail, ok = 0.0, [], True
    for lg in legs:
        q = td_snapshot(lg["expiry"], lg["strike"], lg["right"])
        if q is None:
            ok = False
            detail.append({**{k: lg[k] for k in ("side", "right", "strike")}, "td": None})
            continue
        b, a, bs, as_ = q
        qty = lg.get("qty", 1)
        # sell -> receive bid; buy -> pay ask (marketable to fill now)
        px = b if lg["side"] == "sell" else a
        credit += (px if lg["side"] == "sell" else -px) * qty
        need = qty
        have = bs if lg["side"] == "sell" else as_
        if have < need:
            ok = False
        detail.append({**{k: lg[k] for k in ("side", "right", "strike")},
                       "bid": b, "ask": a, "bid_size": bs, "ask_size": as_, "px": px})
    # a missing/thin leg means the spread cannot be filled — return None, never a partial sum
    return (round(credit, 2) if ok else None), detail, ok


def fill_close(legs):
    """Marketable-touch CLOSE (reverse): buy back sells @ask, sell longs @bid."""
    debit, detail, ok = 0.0, [], True
    for lg in legs:
        q = td_snapshot(lg["expiry"], lg["strike"], lg["right"])
        if q is None:
            ok = False
            detail.append({**{k: lg[k] for k in ("side", "right", "strike")}, "td": None})
            continue
        b, a, bs, as_ = q
        qty = lg.get("qty", 1)
        # closing: original sell is bought back @ask (pay); original buy is sold @bid (receive)
        px = a if lg["side"] == "sell" else b
        debit += (px if lg["side"] == "sell" else -px) * qty
        detail.append({**{k: lg[k] for k in ("side", "right", "strike")},
                       "bid": b, "ask": a, "px": px})
    # a missing/thin leg means the close cannot be priced — return None, never a partial sum
    return (round(debit, 2) if ok else None), detail, ok


DRY = False       # set in main() for --dry; a test run must NEVER page the user


def tg(text):
    """Fire a Telegram ping (best-effort; every event, no dedup for today's live test)."""
    if TG is None or DRY:
        return
    try:
        TG.send(text, level="info", cooldown_s=0)
    except Exception as e:
        print(f"  ! telegram send failed: {e}")


def _legs_str(legs):
    return " / ".join(f"{l['side'][0].upper()} {l['strike']:.0f}{l['right']}" for l in legs)


def plan_path(date):
    return SIM / f"gameplan_{date.replace('-', '')}.json"  # gameplans are YYYYMMDD


def load_plan(date):
    p = plan_path(date)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def book_path(date):
    return OUTDIR / f"shadow_book_{date}.json"


def process(date, book, dry=False):
    """One pass: pick up new fills/exits from the desk plan, fill them on TD."""
    plan = load_plan(date)
    if not plan:
        return
    for t in plan.get("triggers", []):
        tid = t.get("trade_id")
        legs = t.get("filled_legs")
        fill = t.get("fill")
        # OPEN order: desk actually filled it (trade_id + filled_legs + fill)
        if tid and legs and fill and tid not in book["trades"]:
            if dry:
                cr, det, ok = 0.0, [{"strike": l["strike"], "right": l["right"], "side": l["side"]} for l in legs], True
            else:
                cr, det, ok = fill_open(legs)
            und = None if dry else td_underlying(legs[0]["expiry"], legs[0]["strike"], legs[0]["right"])
            book["trades"][tid] = {
                "id": t.get("id"), "strategy": t.get("setup") or t.get("id"),
                "stream": t.get("stream"), "legs": legs,
                "ib_credit": fill.get("net"), "ib_fill_at": fill.get("at"),
                "ib_submit_at": t.get("submit_at"),   # desk's send moment (ms) once daemon restarts
                "td_credit": cr, "td_fill_ok": ok, "td_open_at": _now(), "td_open_detail": det,
                "td_open_underlying": (und or {}).get("underlying_price"),
                "td_open_underlying_ts": (und or {}).get("underlying_ts"),
                "exited": False,
            }
            print(f"  OPEN  {tid} {t.get('id')}: IB credit {fill.get('net')} | "
                  f"TD credit {cr}{' NO-FILL' if not ok else ''}")
            ibc = fnum(fill.get("net"))
            legstr = "\n".join(
                f"   {d.get('side','?')[0].upper()} {d.get('strike'):.0f}{d.get('right')}: "
                + (f"bid {d.get('bid')} ask {d.get('ask')} px {d.get('px')}"
                   if d.get("td") is not False and d.get("bid") is not None else "NO TD QUOTE")
                for d in det if isinstance(d, dict) and d.get("strike"))
            ibs = f"${ibc:.2f}" if ibc is not None else "n/a"
            if cr is None:
                tdline = f"IB credit {ibs}  |  TD credit — ⚠ NO-FILL (thin/missing leg)"
            else:
                dstr = f"Δ ${ibc - cr:+.2f}" if ibc is not None else "Δ n/a"
                tdline = f"IB credit {ibs}  |  TD credit ${cr:.2f}  |  {dstr}"
            tg(f"🟢 OPEN {t.get('id')} ({t.get('stream')})\n{_legs_str(legs)}\n{tdline}\n"
               f"underlying {book['trades'][tid].get('td_open_underlying')}\n{legstr}")
        # CLOSE order
        ex = t.get("exit")
        if tid and t.get("exited") and ex and tid in book["trades"] and not book["trades"][tid]["exited"]:
            if dry:
                db, det, ok = 0.0, [], True
            else:
                db, det, ok = fill_close(legs or book["trades"][tid]["legs"])
            tr = book["trades"][tid]
            xlegs = legs or tr["legs"]
            und = None if dry else td_underlying(xlegs[0]["expiry"], xlegs[0]["strike"], xlegs[0]["right"])
            tr.update(exited=True, ib_exit_cost=ex.get("cost"), ib_exit_at=ex.get("at"),
                      exit_why=ex.get("why"), td_exit_debit=db, td_exit_ok=ok,
                      td_exit_at=_now(), td_exit_detail=det,
                      td_exit_underlying=(und or {}).get("underlying_price"),
                      td_exit_underlying_ts=(und or {}).get("underlying_ts"))
            if tr["td_fill_ok"] and ok:
                # vertical = len(legs) legs; open+close = 2*len executions * fee
                tr["td_pnl"] = round((tr["td_credit"] - db) * 100 - 2 * len(xlegs) * FEE, 2)
            print(f"  CLOSE {tid}: IB exit {ex.get('cost')} | TD exit {db}"
                  f"{' NO-FILL' if not ok else ''} | why: {str(ex.get('why'))[:50]}")
            ibc = fnum(tr.get("ib_credit"))
            ibx = fnum(ex.get("cost"))
            nleg = len(xlegs)
            ib_pnl = round((ibc - ibx) * 100 - 2 * nleg * FEE, 2) if (ibc is not None and ibx is not None) else None
            td_pnl = tr.get("td_pnl")
            ibxs = f"${ibx:.2f}" if ibx is not None else "n/a"
            if db is None:
                xline = f"IB exit {ibxs}  |  TD exit — ⚠ NO-FILL (thin/missing leg)"
            else:
                xd = f"Δ ${ibx - db:+.2f}" if ibx is not None else "Δ n/a"
                xline = f"IB exit {ibxs}  |  TD exit ${db:.2f}  |  {xd}"
            if ib_pnl is not None and td_pnl is not None:
                pd_ = f"IB P&L ${ib_pnl:+.2f}  |  TD P&L ${td_pnl:+.2f}  |  Δ ${ib_pnl - td_pnl:+.2f}"
            elif ib_pnl is not None:
                pd_ = f"IB P&L ${ib_pnl:+.2f}  |  TD P&L — (leg not priced; EOD backstop will fill)"
            else:
                pd_ = f"TD P&L {td_pnl}"
            tg(f"🔴 CLOSE {tr.get('id')} ({tr.get('stream')})\n{xline}\n{pd_}\n"
               f"underlying {tr.get('td_exit_underlying')}\nwhy: {str(ex.get('why'))[:90]}")


def _now():
    try:
        return datetime.now().strftime("%H:%M:%S")
    except Exception:
        return "?"


def save(date, book):
    book_path(date).write_text(json.dumps(book, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", help="parse-only on a past date (no TD, no loop)")
    ap.add_argument("--until", default="22:00", help="stop time, MACHINE clock (default 22:00 = 15:00 CT)")
    a = ap.parse_args()

    if a.dry:
        global DRY
        DRY = True
        book = {"date": a.dry, "trades": {}, "mode": "dry"}
        process(a.dry, book, dry=True)
        print(json.dumps({k: {kk: v.get(kk) for kk in ("id", "stream", "exited", "ib_credit", "ib_exit_cost")}
                          for k, v in book["trades"].items()}, indent=2))
        print(f"parsed {len(book['trades'])} filled orders from gameplan_{a.dry}.json")
        return

    date = datetime.now().strftime("%Y-%m-%d")
    bp = book_path(date)
    book = json.loads(bp.read_text()) if bp.exists() else {"date": date, "trades": {}, "mode": "live"}
    hh, mm = map(int, a.until.split(":"))
    print(f"TD shadow live — {date}, polling {plan_path(date).name} every {POLL_S}s until {a.until} machine")
    while True:
        try:
            process(date, book)
            save(date, book)
        except Exception as e:
            print(f"  ! poll error: {type(e).__name__}: {e}")
        now = datetime.now()
        if (now.hour, now.minute) >= (hh, mm):
            print("stop time reached")
            break
        time.sleep(POLL_S)
    save(date, book)
    n = len(book["trades"])
    done = sum(1 for t in book["trades"].values() if t["exited"])
    print(f"done: {n} orders shadowed, {done} closed -> {bp}")


if __name__ == "__main__":
    main()
