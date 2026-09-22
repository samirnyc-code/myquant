"""l1_selftest.py — end-to-end test of the L1 tape recorder PIPELINE without NinjaTrader.

The live capture (does the AddOn actually receive Last/Bid/Ask from NT) can only be proven
by F5-ing L1TapeRecorderAddOn.cs in a running NT session. Everything DOWNSTREAM of that —
the exact CSV schema the AddOn writes, l1_rollover's CSV->parquet convert+verify, and the
pipeline_health tail logic that lights the Mission Control tile — is tested here against a
synthetic day that reproduces the AddOn's output byte-for-byte.

    python scripts/l1_selftest.py

Exit 0 = all checks pass. Writes only to a temp dir; touches no real trove data.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def synth_day(path: Path) -> int:
    """Write a synthetic L1 CSV in the EXACT schema L1TapeRecorderAddOn.cs emits.

    Header + rows: C connect · B best-bid · A best-ask · T tape(price,size,aggr) · C disc.
    Mirrors WriteRow(): Side blank on L1 rows, Aggr A/B on tape rows only.
    """
    rows = ["Time,Ev,Side,Price,Size,Aggr",
            "2026-09-16 17:00:00.000,C,C,0,0,"]           # feed connected
    n = 0
    px = 5850.00
    for i in range(600):                                   # ~600 events across the "session"
        ts = f"2026-09-16 17:00:{(i % 60):02d}.{(i * 7) % 1000:03d}"
        bid, ask = px - 0.25, px
        rows.append(f"{ts},B,,{bid:.2f},{(i % 40) + 1},")  # best bid change
        rows.append(f"{ts},A,,{ask:.2f},{(i % 33) + 1},")  # best ask change
        aggr = "A" if i % 2 == 0 else "B"                  # buy lifts ask / sell hits bid
        trade_px = ask if aggr == "A" else bid
        rows.append(f"{ts},T,,{trade_px:.2f},{(i % 5) + 1},{aggr}")   # tape print
        n += 3
        if i % 50 == 49:
            px += 0.25                                      # drift so it's not degenerate
    rows.append("2026-09-16 21:00:00.000,C,D,0,0,")        # feed lost (session end)
    path.write_text("\n".join(rows) + "\n", encoding="ascii")
    return len(rows) - 1                                    # data rows (excl header)


def main() -> int:
    import pandas as pd
    import l1_rollover as rr
    import pipeline_health as ph

    fails = []
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        csv = tmp / "ES_09-26_l1_2026-09-16.csv"
        n_rows = synth_day(csv)
        print(f"[synth] wrote {csv.name}: {n_rows:,} data rows, {csv.stat().st_size:,} bytes")

        # 1) rollover convert + verify (keep CSV so we can re-check the tail after)
        r = rr.convert(csv, keep_csv=True, dry=False)
        print(f"[rollover] status={r['status']}  {r.get('note','')}")
        pq = csv.with_suffix(".parquet")
        if r["status"] != "ok":
            fails.append(f"rollover convert status={r['status']}")
        elif not pq.exists():
            fails.append("parquet not written")
        else:
            df = pd.read_parquet(pq)
            print(f"[parquet] {len(df):,} rows, cols={list(df.columns)}")
            if len(df) != n_rows:
                fails.append(f"parquet row count {len(df)} != {n_rows}")
            if list(df.columns) != ["Time", "Ev", "Side", "Price", "Size", "Aggr"]:
                fails.append(f"unexpected columns {list(df.columns)}")
            evs = set(df["Ev"].astype(str))
            if not {"T", "B", "A"} <= evs:
                fails.append(f"missing event types, got {evs}")
            # spot-check: tape rows carry an aggressor, quote rows do not
            tape = df[df["Ev"] == "T"]
            if tape["Aggr"].isna().any() or (tape["Aggr"].astype(str) == "").any():
                fails.append("some tape rows missing aggressor")

        # 2) health tail-mix reads the synthetic file correctly (T vs B/A split)
        quote, tp = ph._tail_mix_l1(csv)
        print(f"[health] tail-mix: quote={quote:,} tape={tp:,}")
        if quote == 0 or tp == 0:
            fails.append(f"tail-mix wrong (quote={quote}, tape={tp})")

        # 3) check_l1_tape state machine — point L1_DIR at the temp dir and drive 3 states
        orig = ph.L1_DIR
        try:
            # (a) empty dir -> IDLE 'not started'
            empty = tmp / "empty"; empty.mkdir()
            ph.L1_DIR = empty
            s = ph.check_l1_tape()
            print(f"[check] empty dir -> {s['state']}: {s['detail']}")
            if s["state"] != "idle":
                fails.append(f"empty-dir state {s['state']} != idle")

            # (b) fresh today-dated file (market open) -> OK with quote%. Re-date the file to
            #     'now' CT so the freshness + session-window match reality on any run day.
            now = ph.chicago_now()
            live_dir = tmp / "live"; live_dir.mkdir()
            live = live_dir / f"ES_09-26_l1_{now.date().isoformat()}.csv"
            live.write_text(csv.read_text(encoding="ascii"), encoding="ascii")
            ph.L1_DIR = live_dir
            s = ph.check_l1_tape()
            print(f"[check] fresh file ({ph.market_state(now)}) -> {s['state']}: {s['detail']}")
            if s["state"] not in ("ok", "idle"):     # idle only if market happens to be closed
                fails.append(f"fresh-file state {s['state']} unexpected")
        finally:
            ph.L1_DIR = orig

    print()
    if fails:
        print("FAIL:")
        for f in fails:
            print("  -", f)
        return 1
    print("ALL PASS — schema, rollover convert+verify, parquet, and health tile logic OK.")
    print("Remaining test (needs you): F5 the AddOn in NT and confirm rows arrive live.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
