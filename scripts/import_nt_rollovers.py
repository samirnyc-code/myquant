"""
import_nt_rollovers.py — turn NinjaTrader's exported rollover CSV into our
rolls_{key}.json files.

Input : data/nt_rollovers_export.csv  (written by the RolloverProbe NinjaScript
        indicator: instrument, contract_month(yyyy-MM), rollover_date, offset)
Output: rolls_{NQ,YM,GC,CL,6E,6J}.json in our schema {ticker:{roll_date,offset}}

NT's Rollover.Date == our roll_date, NT's Rollover.Offset == our offset (verified
against ES: 2026-09 -> 61.25, 2026-06 -> 49.75 both match rolls.json exactly).

ES is NOT written (it lives in rolls.json / contracts.py); instead we VALIDATE the
exported ES rows against rolls.json to confirm the convention still holds.
NaN offsets (pre-history contracts with no prior, and not-yet-rolled future
contracts) are stored as null — get_offset() treats null as 0.0 (the newest
contract is the un-shifted anchor, so its forward NaNs are harmless).
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from instruments import INSTRUMENTS, CATALOGS  # noqa: E402

CSV = ROOT / "data" / "nt_rollovers_export.csv"


def parse_off(s: str):
    s = s.strip()
    if not s or s.lower() == "nan":
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    return None if math.isnan(v) else v


def load_rows() -> dict[str, list[tuple[str, str, str]]]:
    rows: dict[str, list[tuple[str, str, str]]] = {}
    lines = CSV.read_text(encoding="utf-8").splitlines()
    for ln in lines[1:]:                       # skip header
        if not ln.strip():
            continue
        inst, cm, rd, off = ln.split(",")
        rows.setdefault(inst, []).append((cm, rd, off))
    return rows


def nt_map(rows, root):
    """{full 'yyyy-MM' -> (roll_date, offset)} for one instrument. Keyed on the
    FULL year to avoid single-digit-year collisions (e.g. 2018-03 vs 2028-03)."""
    return {cm: (rd, parse_off(off)) for cm, rd, off in rows.get(root, [])}


def main() -> None:
    rows = load_rows()

    # ── ES validation against rolls.json (do not overwrite) ──────────────────
    import contracts  # ES catalog: ticker <-> (year, month)
    es_ref = json.loads((ROOT / "rolls.json").read_text(encoding="utf-8"))
    nt_es = nt_map(rows, "ES")
    mism, checked = [], 0
    for c in contracts.CATALOG:
        ym = f"{c.year:04d}-{c.month:02d}"
        if c.ticker in es_ref and ym in nt_es:
            checked += 1
            nt_rd, nt_off = nt_es[ym]
            ref = es_ref[c.ticker]
            r_off, r_rd = ref.get("offset"), ref.get("roll_date")
            off_ok = (r_off is None and nt_off is None) or (
                r_off is not None and nt_off is not None and abs(r_off - nt_off) < 1e-6)
            if not (off_ok and r_rd == nt_rd):
                mism.append((c.ticker, ref, (nt_rd, nt_off)))
    print(f"ES validation: {checked} overlapping contracts vs rolls.json, "
          f"{len(mism)} mismatch(es).")
    for tk, ref, got in mism:
        print(f"  MISMATCH {tk}: rolls.json={ref}  NT={got}")

    # ── Write rolls_{key}.json for each multi-instrument ─────────────────────
    print()
    for key, spec in INSTRUMENTS.items():
        nt = nt_map(rows, spec.root)
        catalog = CATALOGS[key]

        out: dict[str, dict] = {}
        orphans: list[str] = []
        for c in catalog:
            ym = f"{c.year:04d}-{c.month:02d}"
            if ym in nt:
                rd, off = nt[ym]
                out[c.ticker] = {"roll_date": rd, "offset": off}
            else:
                orphans.append(c.ticker)

        # write
        path = INSTRUMENTS[key].rolls_path()
        path.write_text(json.dumps(out, indent=2), encoding="utf-8")

        # coverage report
        with_off = [t for t, v in out.items() if v["offset"] is not None]
        dates = sorted(v["roll_date"] for v in out.values())
        print(f"{key}: wrote {len(out)}/{len(catalog)} catalog contracts "
              f"({len(with_off)} with offset) -> {path.name}")
        if dates:
            print(f"     roll dates {dates[0]} .. {dates[-1]}")
        if orphans:
            print(f"     ⚠ {len(orphans)} catalog contract(s) NOT in NT export: "
                  f"{', '.join(orphans[:8])}{'…' if len(orphans) > 8 else ''}")


if __name__ == "__main__":
    main()
