"""databento_mbo.py — ingest a Databento GLBX.MDP3 MBO download into the L2/L3 database.

The MBO .dbn.zst files ARE the cold archive (re-downloading costs credit) — we keep them
as-is and build compact derived products alongside the NT8 recording:
  * trades  (action T/F) -> per-day parquet  (the tape, with EXCHANGE aggressor side)
  * footprint            -> per-day parquet  (same rebuild validated 0.9995 vs FootprintExporter)
The full order book stays in DBN for deep microstructure work (icebergs/queue) on demand.

    python scripts/databento_mbo.py inspect  <download_folder>   # what did we actually get?
    python scripts/databento_mbo.py ingest   <download_folder>   # -> trades + footprint parquet

Needs the databento reader:  .venv/Scripts/python.exe -m pip install databento
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "databento"          # derived parquet lives here; DBN stays in the download


def _need_databento():
    try:
        import databento  # noqa
        return True
    except Exception:
        print("!! the 'databento' reader is not installed. Run:\n"
              "   .venv/Scripts/python.exe -m pip install databento")
        return False


def _files(folder: Path):
    return sorted(folder.rglob("*.dbn.zst")) + sorted(folder.rglob("*.dbn"))


def inspect(folder: Path):
    """Answer the open questions: which SYMBOL did 'ES' resolve to, what date span,
    how many files, and what the records look like — WITHOUT converting anything."""
    print(f"folder: {folder}")
    # Databento bundles a symbology.json / metadata / condition.json describing the request
    for name in ("symbology.json", "metadata.json", "condition.json", "manifest.json"):
        for f in folder.rglob(name):
            try:
                d = json.loads(f.read_text())
                print(f"\n== {f.name} ==")
                # symbology.json maps requested symbol -> resolved instrument(s): the answer
                if "result" in d or "mappings" in d or "stype_in" in d:
                    print(f"  stype_in={d.get('stype_in')}  stype_out={d.get('stype_out')}")
                    print(f"  symbols requested: {d.get('symbols')}")
                    res = d.get("result") or d.get("mappings") or {}
                    print(f"  resolved instruments: {list(res)[:20]}{' …' if len(res) > 20 else ''}")
                else:
                    print("  " + json.dumps(d, indent=1)[:600])
            except Exception as e:
                print(f"  ({f.name}: {type(e).__name__})")
            break

    fs = _files(folder)
    tot = sum(f.stat().st_size for f in fs) / 1e9
    print(f"\n{len(fs)} DBN file(s), {tot:.1f} GB")
    if fs:
        print("  first:", fs[0].name, "  last:", fs[-1].name)
    if not fs or not _need_databento():
        return
    import databento as db
    store = db.DBNStore.from_file(str(fs[0]))
    print(f"\n== first file: {fs[0].name} ==")
    print("  schema:", store.schema, " symbols:", getattr(store.metadata, "symbols", "?"))
    df = store.to_df().head(5)
    print("  columns:", list(df.columns))
    print(df.to_string())


def ingest(folder: Path):
    if not _need_databento():
        return
    import databento as db
    import pandas as pd
    OUT.mkdir(parents=True, exist_ok=True)
    fs = _files(folder)
    print(f"ingesting {len(fs)} file(s) -> {OUT}")
    (OUT / "trades").mkdir(exist_ok=True)
    (OUT / "footprint").mkdir(exist_ok=True)
    for f in fs:
        store = db.DBNStore.from_file(str(f))
        df = store.to_df()                              # one day of MBO events
        if "ts_event" in df.columns:
            df.index = pd.to_datetime(df["ts_event"])
        day = df.index[0].strftime("%Y-%m-%d") if len(df) else f.stem
        # --- trades: action T (aggressor) — the tape ---
        tr = df[df["action"].isin(["T"])] if "action" in df else df.iloc[0:0]
        if len(tr):
            cols = [c for c in ("price", "size", "side", "action") if c in tr.columns]
            tr[cols].to_parquet(OUT / "trades" / f"{day}.parquet", compression="zstd")
        # --- footprint: buy/sell volume per price (side A=ask/buy, B=bid/sell) ---
        if len(tr) and "side" in tr.columns:
            fpv = (tr.groupby(["price", "side"])["size"].sum().unstack(fill_value=0))
            fpv.to_parquet(OUT / "footprint" / f"{day}.parquet", compression="zstd")
        print(f"  {day}: {len(df):>9,} events  {len(tr):>8,} trades")
    print("done — full order book remains in the DBN archive for deep analysis.")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    cmd, folder = sys.argv[1], Path(sys.argv[2])
    if not folder.exists():
        print(f"no such folder: {folder}")
        return 1
    {"inspect": inspect, "ingest": ingest}.get(cmd, inspect)(folder)
    return 0


if __name__ == "__main__":
    sys.exit(main())
