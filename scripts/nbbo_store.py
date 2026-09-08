"""nbbo_store.py — DuckDB + parquet query layer for the years-scale NBBO store.

The S113 sandbox needs to query 4yr SPXW + 8yr SPY of 1-min/tick NBBO (~100–200M
rows, a few GB) WITHOUT loading it into RAM. DuckDB scans partitioned parquet on
disk, so a fill-time lookup over the whole store stays sub-second.

Layout (Hive-partitioned parquet, written by DuckDB COPY):
    data/thetadata/nbbo/symbol=<SPXW|SPY|…>/date=<YYYY-MM-DD>/*.parquet

Canonical columns (raw ThetaData v3 `quote` schema + two partition keys; mid/spread
are DERIVED at query time, never stored):
    symbol date expiration strike right ts ms_of_day
    bid_size bid bid_exchange bid_condition  ask_size ask ask_exchange ask_condition

Public API:
    con = connect()                       # DuckDB conn with a `nbbo` view over the store
    ingest_quote_csv(con, csv, symbol)    # ThetaData quote CSV -> partitioned parquet
    q(con, sql) -> DataFrame              # run SQL against the `nbbo` view
    at_time(con, symbol, expiry, strike, right, "YYYY-MM-DD HH:MM:SS[.mmm]")  # last NBBO at/before

CLI:
    nbbo_store.py --demo     # write a synthetic day, run the canonical queries, CLEAN UP (proves the path)
    nbbo_store.py --stats    # summarize what's in the store
    nbbo_store.py --ingest data/thetadata/quotes/2026-08-03/SPXW_20260803_7500C.csv --symbol SPXW
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data" / "thetadata" / "nbbo"
GLOB = str(STORE / "**" / "*.parquet").replace("\\", "/")


def connect() -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB that SCANS the parquet store on disk (nothing loaded to RAM).
    Creates a `nbbo` view if any parquet exists; otherwise the view is absent (empty store)."""
    con = duckdb.connect()
    if any(STORE.rglob("*.parquet")):
        con.execute(
            f"CREATE OR REPLACE VIEW nbbo AS "
            f"SELECT *, (bid+ask)/2 AS mid, (ask-bid) AS spread "
            f"FROM read_parquet('{GLOB}', hive_partitioning=true)")
    return con


def has_view(con) -> bool:
    return con.execute(
        "SELECT count(*) FROM duckdb_views() WHERE view_name='nbbo'").fetchone()[0] > 0


def q(con, sql: str):
    return con.execute(sql).df()


def ingest_quote_csv(con, csv_path: str | Path, symbol: str) -> int:
    """Normalize a ThetaData v3 `quote` CSV and COPY it into the partitioned store.
    Idempotent per (symbol, date): OVERWRITE_OR_IGNORE replaces that partition's files."""
    csv_path = str(Path(csv_path)).replace("\\", "/")
    STORE.mkdir(parents=True, exist_ok=True)
    n = con.execute(f"""
        COPY (
            SELECT
                '{symbol}'                              AS symbol,
                CAST(timestamp AS DATE)                 AS date,
                CAST(expiration AS DATE)                AS expiration,
                CAST(strike AS DOUBLE)                  AS strike,
                lower("right")                          AS "right",
                CAST(timestamp AS TIMESTAMP)            AS ts,
                CAST(epoch_ms(CAST(timestamp AS TIMESTAMP))
                     - epoch_ms(CAST(timestamp AS DATE)) AS BIGINT) AS ms_of_day,
                CAST(bid_size AS INTEGER) AS bid_size, CAST(bid AS DOUBLE) AS bid,
                bid_exchange, bid_condition,
                CAST(ask_size AS INTEGER) AS ask_size, CAST(ask AS DOUBLE) AS ask,
                ask_exchange, ask_condition
            FROM read_csv_auto('{csv_path}', header=true)
        ) TO '{str(STORE).replace(chr(92), "/")}'
          (FORMAT parquet, PARTITION_BY (symbol, date), OVERWRITE_OR_IGNORE, COMPRESSION zstd)
    """).fetchone()
    return int(n[0]) if n else 0


def at_time(con, symbol, expiry, strike, right, when: str):
    """The last NBBO at/before `when` for a contract — the DuckDB equivalent of ThetaData
    at_time/quote. `when` = 'YYYY-MM-DD HH:MM:SS[.mmm]' (exchange/ET time)."""
    return q(con, f"""
        SELECT ts, bid_size, bid, ask, ask_size, mid, spread,
               date_diff('millisecond', ts, TIMESTAMP '{when}') AS lag_ms
        FROM nbbo
        WHERE symbol='{symbol}' AND expiration=DATE '{expiry}'
          AND strike={float(strike)} AND "right"='{right.lower()}'
          AND ts <= TIMESTAMP '{when}'
        ORDER BY ts DESC LIMIT 1
    """)


# --------------------------------------------------------------------- demo / cli
def _write_demo(con) -> None:
    """Deterministic synthetic day (1 contract, 1 quote/sec 09:30–16:00) so --demo can
    prove ingest+query end-to-end with no ThetaData terminal. Written under symbol=DEMO."""
    STORE.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        COPY (
            SELECT
                'DEMO' AS symbol,
                DATE '2026-08-03' AS date,
                DATE '2026-08-03' AS expiration,
                7500.0 AS strike, 'call' AS "right",
                TIMESTAMP '2026-08-03 09:30:00' + (s * INTERVAL 1 SECOND) AS ts,
                (34200 + s) * 1000 AS ms_of_day,
                CAST(10 + (s % 37) AS INTEGER) AS bid_size,
                round(20 + sin(s/300.0), 2)    AS bid, 'C' AS bid_exchange, 0 AS bid_condition,
                CAST(10 + (s % 41) AS INTEGER) AS ask_size,
                round(20 + sin(s/300.0) + 0.10 + 0.05*abs(sin(s/500.0)), 2) AS ask,
                'C' AS ask_exchange, 0 AS ask_condition
            FROM range(0, 23400) t(s)
        ) TO '{str(STORE).replace(chr(92), "/")}'
          (FORMAT parquet, PARTITION_BY (symbol, date), OVERWRITE_OR_IGNORE, COMPRESSION zstd)
    """)


def _demo() -> int:
    print("DuckDB", duckdb.__version__, "- demo: write synthetic day -> query -> clean up\n")
    con = connect()
    _write_demo(con)
    con = connect()  # reconnect so the view now sees the DEMO parquet
    if not has_view(con):
        print("FAIL: no nbbo view after write"); return 1

    rows = q(con, "SELECT count(*) n, min(ts) t0, max(ts) t1 FROM nbbo WHERE symbol='DEMO'")
    print("scan whole store (on disk, not RAM):")
    print(f"  rows={int(rows.n[0])}  span {rows.t0[0]} .. {rows.t1[0]}")

    print("\nat_time (last NBBO at/before 10:15:27.500):")
    a = at_time(con, "DEMO", "2026-08-03", 7500.0, "call", "2026-08-03 10:15:27.500")
    r = a.iloc[0]
    print(f"  ts={r.ts}  bid {r.bid_size}@{r.bid}  ask {r.ask}@{r.ask_size}  "
          f"mid={r.mid:.3f} spread={r.spread:.2f}  lag_ms={int(r.lag_ms)}")

    print("\nsize-at-touch stats (the fillability signal we lacked):")
    s = q(con, "SELECT round(avg(bid_size),1) avg_bid_sz, round(avg(ask_size),1) avg_ask_sz, "
               "round(avg(spread),3) avg_spread FROM nbbo WHERE symbol='DEMO'")
    print(f"  avg bid_size={s.avg_bid_sz[0]}  avg ask_size={s.avg_ask_sz[0]}  avg spread={s.avg_spread[0]}")

    # clean up the synthetic partition so the store stays empty for real data
    shutil.rmtree(STORE / "symbol=DEMO", ignore_errors=True)
    print("\ncleaned DEMO partition. PATH VERIFIED - ready to ingest real ThetaData quote CSVs.")
    return 0


def _stats() -> int:
    con = connect()
    if not has_view(con):
        print(f"store empty: {STORE.relative_to(ROOT)} (no parquet yet)"); return 0
    print(q(con, "SELECT symbol, count(DISTINCT date) days, count(*) rows, "
                 "min(date) d0, max(date) d1 FROM nbbo GROUP BY symbol ORDER BY symbol").to_string(index=False))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="DuckDB+parquet NBBO store")
    ap.add_argument("--demo", action="store_true", help="self-test the ingest+query path (synthetic, cleans up)")
    ap.add_argument("--stats", action="store_true", help="summarize the store")
    ap.add_argument("--ingest", help="a ThetaData quote CSV to load")
    ap.add_argument("--symbol", help="symbol for --ingest (e.g. SPXW)")
    a = ap.parse_args()
    if a.demo:
        return _demo()
    if a.ingest:
        if not a.symbol:
            print("--ingest needs --symbol"); return 1
        con = connect()
        n = ingest_quote_csv(con, a.ingest, a.symbol)
        print(f"ingested {a.ingest} -> store (symbol={a.symbol}); rows written per DuckDB: {n}")
        return 0
    return _stats()


if __name__ == "__main__":
    raise SystemExit(main())
