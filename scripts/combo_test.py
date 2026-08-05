"""Live paper test of atomic combo (BAG) orders — the orphan-leg cure.

Places ONE far-OTM SPXW put credit spread as a single BAG order on the paper
account, prints every quote/fill with signs, then closes it the same way.
PASS = both open and close fill atomically with sane credit signs; then flip
MYQUANT_COMBO_ORDERS=1 for the trigger daemon.

Run when a session is live (RTH, or overnight from ~19:15 CT):
  .venv/Scripts/python.exe scripts/combo_test.py
"""
import datetime as dt
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import importlib.util

spec = importlib.util.spec_from_file_location("td", Path(__file__).parent / "options_trigger_daemon.py")
td = importlib.util.module_from_spec(spec)
spec.loader.exec_module(td)

import ib_conn  # noqa: E402

CT = ZoneInfo("America/Chicago")


def next_expiry():
    d = dt.datetime.now(CT)
    e = d.date() if d.hour < 15 else d.date() + dt.timedelta(days=1)
    while e.weekday() >= 5:
        e += dt.timedelta(days=1)
    return e.strftime("%Y%m%d")


def main():
    ib = ib_conn.connect(client_id=79)
    try:
        exp = next_expiry()
        from options_sim_daemon import rough_spot
        _, spot = rough_spot(ib)
        short = round((spot - 150) / 5) * 5
        legs = [("P", short - 25, "BUY"), ("P", short, "SELL")]   # bull put, ~150 OTM
        print(f"TEST: SPXW {exp} bull put {short}/{short-25} (spot~{spot:.0f})")

        bag = td.combo_contract(ib, exp, legs)
        bid, ask = td.quote_combo(ib, bag)
        print(f"combo quote: bid={bid} ask={ask}  (credit spread should quote NEGATIVE)")

        credit, bag = td.place_combo(ib, exp, legs, 1)
        print(f"OPEN  filled atomically: net credit {credit:+.2f}  (${credit*100:+,.0f})")

        cost = td.close_combo(ib, bag, 1)
        print(f"CLOSE filled atomically: cost {cost:+.2f}  (${cost*100:+,.0f})")
        print(f"round-trip: ${ (credit - cost) * 100:+,.0f} (spread friction)")
        print("\nPASS — atomic both ways. Set MYQUANT_COMBO_ORDERS=1 for the daemon.")
    finally:
        pos = [p for p in ib.positions() if p.contract.symbol == "SPX" and abs(p.position) > 0]
        print("residual SPX positions:", [(p.contract.lastTradeDateOrContractMonth,
                                           p.contract.strike, p.contract.right, p.position) for p in pos] or "none")
        ib.disconnect()


if __name__ == "__main__":
    main()
