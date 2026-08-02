#!/usr/bin/env python
"""ingest_nt_internals.py — align NT8 market-internals 5M bars to ES (S92-EA Phase 0).

WHY
    Parallel to scripts/ingest_nt_ticks.py. The MarketInternalExporter.cs dumps NYSE/Nasdaq
    internals as 5M OHLCV bars (data/nt_internals/<SYM>_5m_<stamp>.csv). Multiple export runs
    exist; most are 0-byte/header-only test runs. This picks the newest NON-EMPTY file per
    symbol, aligns them all to the ES 5M RTH grid, derives Halsey-relevant features, and writes
    ONE master parquet + a coverage/QA report — the substrate for the turning-point study.

CRITICAL RECONCILIATIONS (a silent 5-min offset would corrupt every join)
    - NT internals bars are CLOSE-LABELED (bar time = bar close). es_5m_rth.parquet is
      OPEN-LABELED. An internals bar stamped 08:35 covers 08:30..08:35 = the SAME physical bar
      as the ES bar stamped 08:30. So: ES_open_label == internals_close_label - 5min.
      We join on bar_open = (internals close time) - 5min.
    - Internals timestamps are Central time, tz-naive (matches ES). No tz conversion.
    - Master is anchored on ES RTH bars (left join). Internals that fall outside ES RTH bars
      are dropped; ES bars with no internals (e.g. 15:00-15:15 CT after NYSE close, or pre-VIX
      history) are kept with NaN internals.

NO LOOK-AHEAD
    Every derived feature uses only data up to and including its own bar: intraday cumulative
    TICK, running daily tick/price extremes, trailing breadth slope. Divergence flags compare
    the current bar's new-price-extreme vs new-tick-extreme (both known at bar close).

USAGE
    python scripts/ingest_nt_internals.py            # build + QA report + dated parquet
    python scripts/ingest_nt_internals.py --dry-run  # QA report only, write nothing
"""
from __future__ import annotations

import argparse
import glob as _glob
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "nt_internals"
OUT_DIR = RAW_DIR / "master"
ES_PARQUET = ROOT / "research" / "scalp_swing" / "es_5m_rth.parquet"

# symbol (from the `# symbol=` header line) -> clean column key
SYM_KEY = {
    "^TICK": "TICK", "^TICKQ": "TICKQ",
    "^TRIN": "TRIN", "^TRINQ": "TRINQ",
    "^VIX": "VIX",
    "^UVOL": "UVOL", "^DVOL": "DVOL",
    "^ADV": "ADV", "^ADD": "ADD", "^ADVN": "ADVN", "^DECN": "DECN", "^DECL": "DECL",
    "BANK": "BANK", "DX 09-26": "DX",
}

VIX_RISK_ON = 18.85          # Halsey: VIX < ~18.85 = risk-on gate
BREADTH_SLOPE_BARS = 6       # trailing bars for breadth-ratio slope (~30 min)


def read_header_symbol(path: Path) -> str | None:
    """Return the symbol from the leading `# symbol=...` line, or None."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        first = fh.readline()
    m = re.match(r"#\s*symbol\s*=\s*(.+?)\s*$", first)
    return m.group(1) if m else None


def load_one(path: Path) -> pd.DataFrame:
    """Read one exporter CSV (header line + Time,O,H,L,C,V). CT-naive, close-labeled."""
    df = pd.read_csv(path, comment="#")
    df.columns = [c.strip() for c in df.columns]
    df["Time"] = pd.to_datetime(df["Time"], errors="coerce")
    df = df.dropna(subset=["Time"]).drop_duplicates(subset=["Time"]).sort_values("Time")
    for c in ("Open", "High", "Low", "Close", "Volume"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.reset_index(drop=True)


def discover(verbose: bool = True) -> tuple[dict[str, tuple[Path, pd.DataFrame]], list[dict]]:
    """Pick the newest NON-EMPTY _5m_ file per symbol. Returns ({key:(path,df)}, audit_rows)."""
    files = sorted(_glob.glob(str(RAW_DIR / "*_5m_*.csv")))
    per_sym: dict[str, list[tuple[Path, pd.DataFrame]]] = {}
    audit: list[dict] = []
    for p in files:
        fp = Path(p)
        sym = read_header_symbol(fp)
        if sym is None:
            audit.append({"file": fp.name, "symbol": "?", "rows": 0, "note": "no # symbol= header"})
            continue
        df = load_one(fp)
        key = SYM_KEY.get(sym, sym.lstrip("^").replace(" ", "_"))
        per_sym.setdefault(key, []).append((fp, df))
        audit.append({"file": fp.name, "symbol": sym, "key": key, "rows": len(df),
                      "mtime": fp.stat().st_mtime})

    chosen: dict[str, tuple[Path, pd.DataFrame]] = {}
    for key, cands in per_sym.items():
        nonempty = [(fp, df) for fp, df in cands if len(df) > 0]
        if not nonempty:
            continue
        # most rows wins; tie-break on newest mtime
        fp, df = max(nonempty, key=lambda t: (len(t[1]), t[0].stat().st_mtime))
        chosen[key] = (fp, df)
    return chosen, audit


def coverage_report(chosen, audit) -> pd.DataFrame:
    rows = []
    all_keys = sorted(set(SYM_KEY.values()) | set(chosen))
    for key in all_keys:
        if key not in chosen:
            rows.append({"key": key, "status": "EMPTY/absent", "file": "", "rows": 0,
                         "start": "", "end": "", "sess_ct": "", "close_nonnull_%": ""})
            continue
        fp, df = chosen[key]
        tod = df["Time"].dt.time
        sess = f"{min(tod)}..{max(tod)}" if len(df) else ""
        nn = 100.0 * df["Close"].notna().mean() if len(df) else 0.0
        # thin = fewer than ~20 sessions of data
        ndays = df["Time"].dt.normalize().nunique()
        status = "OK" if ndays >= 20 else f"THIN ({ndays}d)"
        rows.append({"key": key, "status": status, "file": fp.name, "rows": len(df),
                     "start": str(df["Time"].min()), "end": str(df["Time"].max()),
                     "days": ndays, "sess_ct": sess, "close_nonnull_%": round(nn, 1)})
    return pd.DataFrame(rows)


def build_master(chosen: dict[str, tuple[Path, pd.DataFrame]]) -> pd.DataFrame:
    es = pd.read_parquet(ES_PARQUET)[["DateTime", "Open", "High", "Low", "Close", "Volume",
                                      "Date", "bar"]].copy()
    es = es.rename(columns={c: f"es_{c.lower()}" for c in ("Open", "High", "Low", "Close",
                                                           "Volume")})
    m = es.copy()

    # join each internal: bar_open = close_label - 5min  (see module docstring)
    for key, (_fp, df) in chosen.items():
        g = df.copy()
        g["DateTime"] = g["Time"] - pd.Timedelta(minutes=5)
        cols = {c: f"{key.lower()}_{c.lower()}" for c in ("Open", "High", "Low", "Close",
                                                          "Volume")}
        g = g[["DateTime", "Open", "High", "Low", "Close", "Volume"]].rename(columns=cols)
        m = m.merge(g, on="DateTime", how="left")

    m = m.sort_values("DateTime").reset_index(drop=True)
    day = m["DateTime"].dt.normalize()

    # ---- TICK features -------------------------------------------------------
    if "tick_close" in m:
        m["tick_bar_ext"] = np.where(m["tick_high"].abs() >= m["tick_low"].abs(),
                                     m["tick_high"], m["tick_low"])  # signed larger-magnitude
        m["tick_cum"] = m.groupby(day)["tick_close"].cumsum()       # intraday cumulative TICK
        # running daily tick extremes (up to & incl this bar) — no look-ahead
        m["tick_day_hi"] = m.groupby(day)["tick_high"].cummax()
        m["tick_day_lo"] = m.groupby(day)["tick_low"].cummin()
        m["tick_new_hi"] = m["tick_high"] >= m["tick_day_hi"]       # bar sets a new day high-tick
        m["tick_new_lo"] = m["tick_low"] <= m["tick_day_lo"]
        m["tick_extreme_1000"] = (m["tick_high"] >= 1000) | (m["tick_low"] <= -1000)
        m["tick_extreme_800"] = (m["tick_high"] >= 800) | (m["tick_low"] <= -800)

    # ---- price (ES) running daily extremes for divergence --------------------
    m["es_day_hi"] = m.groupby(day)["es_high"].cummax()
    m["es_day_lo"] = m.groupby(day)["es_low"].cummin()
    m["px_new_hi"] = m["es_high"] >= m["es_day_hi"]
    m["px_new_lo"] = m["es_low"] <= m["es_day_lo"]

    # ---- TICK divergence (Ch 11, first-pass def) -----------------------------
    # bull div: price makes a new day high WITHOUT a new day high-tick; bear = mirror.
    if "tick_new_hi" in m:
        m["bull_div"] = m["px_new_hi"] & ~m["tick_new_hi"]
        m["bear_div"] = m["px_new_lo"] & ~m["tick_new_lo"]

    # ---- breadth = UVOL/DVOL + slope ----------------------------------------
    if "uvol_close" in m and "dvol_close" in m:
        m["breadth_ratio"] = m["uvol_close"] / m["dvol_close"].replace(0, np.nan)
        m["breadth_slope"] = m.groupby(day)["breadth_ratio"].diff(BREADTH_SLOPE_BARS)

    # ---- TRIN / VIX regimes --------------------------------------------------
    if "trin_close" in m:
        m["trin_level"] = m["trin_close"]
    if "vix_close" in m:
        m["vix_level"] = m["vix_close"]
        m["vix_risk_on"] = m["vix_close"] < VIX_RISK_ON

    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="QA report only, write nothing")
    ap.add_argument("--stamp", default="", help="override output date stamp (YYYYMMDD)")
    a = ap.parse_args()

    if not ES_PARQUET.exists():
        print(f"! missing ES parquet: {ES_PARQUET}"); return 2

    chosen, audit = discover()
    cov = coverage_report(chosen, audit)

    print("\n=== NT INTERNALS — COVERAGE / QA ===")
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(cov.to_string(index=False))

    usable = [k for k in chosen if k in ("TICK", "TICKQ", "TRIN", "TRINQ", "VIX", "UVOL",
                                         "DVOL", "ADV")]
    print(f"\nusable symbols: {sorted(usable)}")
    empty = [k for k in sorted(SYM_KEY.values()) if k not in chosen]
    print(f"empty/absent:   {empty}")

    m = build_master(chosen)
    n_es = len(m)
    # rows where core TICK present (the join actually landed)
    tick_cov = m["tick_close"].notna().mean() * 100 if "tick_close" in m else 0
    vix_cov = m["vix_close"].notna().mean() * 100 if "vix_close" in m else 0
    print(f"\nmaster: {n_es:,} ES RTH bars  {m['DateTime'].min()} .. {m['DateTime'].max()}")
    print(f"  TICK joined on {tick_cov:.1f}% of ES bars | VIX on {vix_cov:.1f}%")
    print(f"  columns: {len(m.columns)}")

    # join sanity: on days both exist, how well do timestamps line up?
    if "tick_close" in m:
        both = m.dropna(subset=["tick_close"])
        sample_days = both["DateTime"].dt.normalize().nunique()
        print(f"  TICK present on {sample_days} ES trading days")

    # ---- ALIGNMENT SELF-CHECK (proves the -5min offset direction, no look-ahead) ----
    if "tick_close" in m:
        print("\n=== ALIGNMENT SELF-CHECK ===")
        # 1) the RTH-open bar (bar==0, 08:30 open-label) should have TICK on ~all VIX-era days.
        b0 = m[m["bar"] == 0]
        b0_cov = b0["tick_close"].notna().mean() * 100
        print(f"  RTH-open bar (08:30) TICK-present: {b0_cov:.1f}%  "
              f"(if the offset were flipped +5, this would collapse toward 0)")
        # 2) per-bar-of-day TICK coverage: RTH bars high, post-NYSE-close (15:00+) low.
        by_bar = m.groupby("bar")["tick_close"].apply(lambda s: s.notna().mean() * 100)
        late = by_bar[by_bar.index >= 78]  # bars at/after 15:00 CT (NYSE close)
        print(f"  bars 0-77 (NYSE RTH) median TICK-cov: {by_bar[by_bar.index < 78].median():.1f}%"
              f" | bars 78+ (post-close): {late.mean() if len(late) else float('nan'):.1f}%")
        # 3) directional agreement: signed TICK extreme should lean with the bar's ES return.
        bb = m.dropna(subset=["tick_bar_ext", "es_close", "es_open"])
        es_ret = bb["es_close"] - bb["es_open"]
        agree = ((np.sign(bb["tick_bar_ext"]) == np.sign(es_ret)) & (es_ret != 0)).mean() * 100
        print(f"  sign(TICK bar-extreme)==sign(ES bar return): {agree:.1f}% "
              f"(expect >55%; near 50% would suggest a mis-join)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = a.stamp or pd.Timestamp(m["DateTime"].max()).strftime("%Y%m%d")
    cov_path = OUT_DIR / f"coverage_qa_{stamp}.csv"
    cov.to_csv(cov_path, index=False)
    print(f"\nwrote coverage report -> {cov_path.relative_to(ROOT)}")

    if a.dry_run:
        print("DRY-RUN — master parquet not written.")
        return 0

    out = OUT_DIR / f"internals_es_5m_{stamp}.parquet"
    m.to_parquet(out, index=False)
    print(f"wrote master             -> {out.relative_to(ROOT)}  ({len(m):,} rows, "
          f"{len(m.columns)} cols)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
