"""ib_executions.py — pull IB's OWN record of today's fills + ACTUAL commissions for both
books (SPX + XSP), read-only. IB tracks the fill price and the exact commission per
execution (commissionReport) — the desk just never read them (it modeled $1.30). This is
the definitive fee/fill record, straight from IB. (IB does NOT record the bid/ask at
execution — that's market data; snapshot it separately.)

    python scripts/ib_executions.py
"""
from __future__ import annotations
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def main():
    import ib_conn
    ib = ib_conn.connect(client_id=142)      # spare id, read-only
    ib.sleep(1)
    fills = ib.reqExecutions()               # today's executions across the account
    if not fills:
        print("no fills returned (IB reqExecutions empty — may need the placing client "
              "connected, or no fills today)")
        ib.disconnect(); return

    by_sym = defaultdict(lambda: {"n": 0, "comm": 0.0, "rows": []})
    for f in fills:
        c, e = f.contract, f.execution
        cr = getattr(f, "commissionReport", None)
        comm = float(cr.commission) if cr and cr.commission == cr.commission else None
        sym = c.symbol
        by_sym[sym]["n"] += 1
        if comm is not None:
            by_sym[sym]["comm"] += comm
        by_sym[sym]["rows"].append((e.time, c.localSymbol, e.side, e.shares, e.price, comm))

    for sym in sorted(by_sym):
        d = by_sym[sym]
        percontract = d["comm"] / d["n"] if d["n"] else 0
        print(f"\n=== {sym} — {d['n']} fills | total commission ${d['comm']:.2f} "
              f"| avg ${percontract:.4f}/contract (IB ACTUAL) ===")
        for t, ls, side, sh, px, comm in sorted(d["rows"])[:40]:
            cs = f"${comm:.4f}" if comm is not None else "—"
            print(f"  {str(t)[11:19]}  {ls:<22} {side:<4} {int(sh)} @ {px:<8} comm {cs}")
    print("\nnote: commission is IB's ACTUAL charge per fill. Spread-at-execution is NOT here "
          "(IB doesn't record it) — see mini_executions.py (tape) / xsp_fills.csv (tick-exact).")
    ib.disconnect()


if __name__ == "__main__":
    main()
