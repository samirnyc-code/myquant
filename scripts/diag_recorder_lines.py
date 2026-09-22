"""diag_recorder_lines.py — WHY does the recorder get 0 realtime rows while the live
desk gets realtime marks? Two candidate causes, very different fixes:

  (A) LINE CONTENTION  — the account's market-data line quota is exhausted by the desk,
      so the recorder's bulk request overflows and IB serves it delayed. If so, SMALL
      requests succeed and LARGE ones fail -> fix = shrink the recorder's simultaneous
      line demand.
  (B) ENTITLEMENT/SESSION — realtime is simply not available to this request at all
      (10197 competing session, or a blanket 10090). If so, request size won't matter
      -> fix is elsewhere (source/session), not batch size.

This probes decreasing batch sizes and prints, per size, how many came back realtime
vs delayed and the EXACT error codes. Read-only snapshots on a spare client id.

    python scripts/diag_recorder_lines.py
"""
from __future__ import annotations
import json, sys, time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
sys.path.insert(0, str(ROOT / "scripts"))


def spot():
    try:
        return float(json.loads((SIM / "live.json").read_text())["spx"])
    except Exception:
        return 7690.0


def main():
    import ib_conn
    from ib_async import Option
    codes = Counter()
    ib = ib_conn.connect(client_id=125)          # spare id, distinct from recorder(71)/desk
    ib.errorEvent += lambda rid, code, msg, c=None, *a: codes.__setitem__(code, codes[code] + 1)
    ib.reqMarketDataType(1)                       # request REALTIME
    s = spot()
    k0 = round(s / 5) * 5
    strikes = [k0 + 5 * i for i in range(-6, 6)]  # 12 strikes around ATM
    cs = ib.qualifyContracts(*[Option("SPX", __import__("datetime").date.today().strftime("%Y%m%d"),
                                       k, "C", "SMART", tradingClass="SPXW") for k in strikes])
    cs = [c for c in cs if c and c.conId]
    print(f"spot~{s:.0f}  qualified {len(cs)} SPXW 0DTE calls  (ATM {k0})")
    print(f"{'batch':>6} {'realtime':>9} {'delayed/none':>13} {'codes_this_batch':>20}")
    for size in (1, 3, 6, 12):
        codes.clear()
        grp = cs[:size]
        tks = [(c, ib.reqMktData(c, "", snapshot=True)) for c in grp]
        ib.sleep(5)
        rt = dl = 0
        for c, t in tks:
            try:
                ib.cancelMktData(c)
            except Exception:
                pass
            has = (t.bid == t.bid and t.bid >= 0) or (t.ask == t.ask and t.ask >= 0)
            mdt = getattr(t, "marketDataType", None)   # 1=RT 2=frozen 3=delayed 4=delayed-frozen
            if has and mdt in (1, None) and not any(x in codes for x in (10090, 10167, 10197)):
                rt += 1
            else:
                dl += 1
        print(f"{size:>6} {rt:>9} {dl:>13}   {dict(codes)}")
        time.sleep(1)
    ib.disconnect()
    print("\nread: realtime rises as batch shrinks => LINE CONTENTION (shrink batches).")
    print("      all-delayed at every size => ENTITLEMENT/SESSION (batch size won't help).")


if __name__ == "__main__":
    main()
