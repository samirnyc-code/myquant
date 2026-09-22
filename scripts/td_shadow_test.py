"""Phantom end-to-end test of the TD shadow desk against the LIVE TD feed.

Feeds a fake 'filled' order (today's 0DTE, near-ATM bear-call spread) through the
shadow's real detect->snapshot->fill->close path, using the live td_snapshot. Proves
the TD-desk execution works right now. Does NOT touch the live desk plan or the live
book — writes nothing, in-memory only.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import td_shadow_live as S


def main():
    exp = sys.argv[1] if len(sys.argv) > 1 else "20260908"
    # near-ATM OTM verticals for today's 0DTE (phantom strikes; adjust as needed)
    sc, lc = float(sys.argv[2]) if len(sys.argv) > 2 else 7735.0, None
    lc = sc + 25
    phantom = {
        "date": "PHANTOM", "triggers": [{
            "id": "phantom_bcs", "setup": "phantom_bcs", "stream": "test",
            "trade_id": "PHANTOM_TEST_1",
            "structure": {"kind": "vertical", "right": "C", "short": sc, "long": lc, "width": 25},
            "filled_legs": [
                {"side": "sell", "right": "C", "strike": sc, "expiry": exp, "qty": 1},
                {"side": "buy", "right": "C", "strike": lc, "expiry": exp, "qty": 1},
            ],
            "fill": {"net": None, "at": "phantom"},
        }]
    }
    book = {"date": "PHANTOM", "trades": {}, "mode": "test"}

    # patch load_plan to serve the phantom, run OPEN
    S.load_plan = lambda d: phantom
    print(f"=== phantom OPEN: sell {sc:.0f}C / buy {lc:.0f}C, expiry {exp} (live TD fill) ===")
    S.process("PHANTOM", book)
    tr = book["trades"].get("PHANTOM_TEST_1")
    if not tr:
        print("  !! shadow did not detect the phantom order")
        return
    print(f"  TD credit: {tr['td_credit']}  fill_ok: {tr['td_fill_ok']}")
    for d in tr["td_open_detail"]:
        print("   ", d)

    # now simulate the desk closing it -> run CLOSE
    phantom["triggers"][0]["exited"] = True
    phantom["triggers"][0]["exit"] = {"cost": None, "at": "phantom", "why": "phantom time-stop test"}
    print("\n=== phantom CLOSE (live TD fill) ===")
    S.process("PHANTOM", book)
    tr = book["trades"]["PHANTOM_TEST_1"]
    print(f"  TD exit debit: {tr.get('td_exit_debit')}  exit_ok: {tr.get('td_exit_ok')}  "
          f"TD phantom P&L: {tr.get('td_pnl')}")
    for d in tr.get("td_exit_detail", []):
        print("   ", d)
    print("\n(no files written; live shadow + desk untouched)")


if __name__ == "__main__":
    main()
