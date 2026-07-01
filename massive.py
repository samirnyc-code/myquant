"""
massive.py — Massive data tab: contract manager, flat-file download, roll schedule,
             and quick API-based comparison.
"""

from __future__ import annotations

import gzip
import io
import os
import shutil
from datetime import date, timedelta
from pathlib import Path

import boto3
import pandas as pd
import streamlit as st
import ui_controls as controls
from botocore.config import Config

from contracts import (
    CATALOG, CATALOG_BY_TICKER,
    load_rolls, save_rolls, ensure_rolls_file,
    get_roll_date, get_offset,
    apply_back_adjustment,
    Contract,
)
from data_loader import (
    fetch_massive_trades, fetch_massive_aggs,
    fetch_massive_contract_info,
    resample_ticks_to_bars, parse_ohlc_from_upload,
    MASSIVE_CACHE_DIR, apply_data_slot, filter_excluded_dates,
)
from validation import build_comparison, get_filters, show_gate_body
from instruments import (
    INSTRUMENTS, CATALOGS,
    load_rolls as _instr_load_rolls,
    save_rolls as _instr_save_rolls,
    ensure_rolls_file as _instr_ensure_rolls,
    get_roll_date as _instr_get_roll_date,
    get_offset as _instr_get_offset,
    apply_back_adjustment as _instr_back_adjust,
    InstContract,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_API_KEY              = "4aTW6AdSEwulL86_kJnNupQppKxSgwXw"
_S3_ACCESS_KEY_ID     = "d0e1191e-61c3-454b-adcb-5bea8e9e9c6a"
_S3_SECRET_KEY        = _API_KEY
_S3_ENDPOINT          = "https://files.massive.com"
_S3_BUCKET            = "flatfiles"
_S3_PREFIX            = "us_futures_cme/trades_v1"

_DATA_DIR        = Path(__file__).parent / "data"
_GZ_CACHE_DIR    = _DATA_DIR / "flatfiles_cache"
_BARS_DIR        = _DATA_DIR / "bars"
_NT_IMPORT_DIR   = _DATA_DIR / "nt_import"
_TICKS_CONT_DIR  = _DATA_DIR / "ticks_continuous"


def _ensure_dirs():
    for d in (_GZ_CACHE_DIR, _BARS_DIR, _NT_IMPORT_DIR, _TICKS_CONT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _bars_path(ticker: str) -> Path:
    return _BARS_DIR / f"{ticker}.parquet"


def _nt_import_path(contract: Contract) -> Path:
    return _NT_IMPORT_DIR / f"{contract.nt_name}.Last.txt"


def _is_downloaded(ticker: str) -> bool:
    return _bars_path(ticker).exists()


def _status_emoji(ticker: str) -> str:
    return "✅" if _is_downloaded(ticker) else "⬜"


# ── S3 helpers ────────────────────────────────────────────────────────────────

def _make_s3():
    session = boto3.Session(
        aws_access_key_id=_S3_ACCESS_KEY_ID,
        aws_secret_access_key=_S3_SECRET_KEY,
    )
    return session.client(
        "s3",
        endpoint_url=_S3_ENDPOINT,
        config=Config(signature_version="s3v4"),
    )


def _s3_key(d: date) -> str:
    return f"{_S3_PREFIX}/{d.year}/{d.month:02d}/{d.isoformat()}.csv.gz"


def _download_day(s3, d: date) -> Path | None:
    local = _GZ_CACHE_DIR / f"{d.isoformat()}.csv.gz"
    if local.exists():
        return local
    key = _s3_key(d)
    try:
        s3.download_file(_S3_BUCKET, key, str(local))
        return local
    except Exception as e:
        if "404" in str(e) or "NoSuchKey" in str(e) or "403" in str(e) or "Forbidden" in str(e):
            return None  # day doesn't exist yet (future date, weekend, holiday)
        raise


def _load_gz(local: Path, ticker: str) -> pd.DataFrame:
    with gzip.open(local, "rb") as f:
        raw = f.read()
    df = pd.read_csv(io.BytesIO(raw))
    return df[df["ticker"] == ticker].copy()


def _resample_5m_to_15m(bars_5m: pd.DataFrame) -> pd.DataFrame:
    """Resample 5M continuous bars to 15M. Groups by date to avoid cross-session bars."""
    if bars_5m.empty:
        return pd.DataFrame()
    df = bars_5m.copy()
    df["DateTime"] = pd.to_datetime(df["DateTime"])
    df = df.set_index("DateTime").sort_index()
    # Resample within each trading day
    df["_date"] = df.index.date
    chunks = []
    for _, day in df.groupby("_date"):
        r = day[["Open", "High", "Low", "Close"]].resample("15min", label="left", closed="left")
        b = pd.DataFrame({
            "Open": r["Open"].first(),
            "High": r["High"].max(),
            "Low": r["Low"].min(),
            "Close": r["Close"].last(),
        }).dropna(subset=["Open"])
        if "Volume" in day.columns:
            b["Volume"] = day["Volume"].resample("15min", label="left", closed="left").sum()
        if "Contract" in day.columns:
            b["Contract"] = day["Contract"].resample("15min", label="left", closed="left").first()
        chunks.append(b)
    if not chunks:
        return pd.DataFrame()
    out = pd.concat(chunks).sort_index()
    out.index.name = "DateTime"
    return out.reset_index()


def _resample_ticks_to_bars(freq: str, status_placeholder=None) -> pd.DataFrame:
    """Build bars at an arbitrary pandas frequency from per-day continuous tick cache."""
    from data_loader import RTH_START, RTH_END
    all_days = sorted(f.stem for f in _TICKS_CONT_DIR.glob("*.parquet"))
    chunks = []
    for i, day_str in enumerate(all_days):
        if status_placeholder and i % 50 == 0:
            status_placeholder.text(f"Resampling {freq} bars: day {i+1}/{len(all_days)}…")
        ticks = pd.read_parquet(_TICKS_CONT_DIR / f"{day_str}.parquet")
        if ticks.empty:
            continue
        dt = pd.to_datetime(ticks["DateTime"])
        ticks = ticks.set_index(dt).sort_index()
        t = ticks.index.time
        rth = (t >= pd.Timestamp(RTH_START).time()) & (t < pd.Timestamp(RTH_END).time())
        ticks = ticks[rth]
        if ticks.empty:
            continue
        r = ticks["Price"].resample(freq, label="left", closed="left")
        b = r.ohlc().dropna(subset=["open"])
        b["Volume"] = ticks["Volume"].resample(freq, label="left", closed="left").sum() if "Volume" in ticks.columns else 0
        b = b.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"})
        b.index.name = "DateTime"
        chunks.append(b.reset_index())
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True).sort_values("DateTime").reset_index(drop=True)


def _ticks_to_5m_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Convert raw tick DataFrame → 5M RTH OHLCV bars (open times, CT naive)."""
    from data_loader import RTH_START, RTH_END

    dt_ct = (
        pd.to_datetime(df["timestamp"], unit="ns", utc=True)
        .dt.tz_convert("America/Chicago")
        .dt.tz_localize(None)
    )
    ticks = pd.DataFrame({"DateTime": dt_ct, "Price": df["price"].astype(float).values,
                          "Volume": df["size"].astype(int).values})
    ticks = ticks.set_index("DateTime").sort_index()

    # RTH filter
    t = ticks.index.time
    rth = (t >= pd.Timestamp(RTH_START).time()) & (t < pd.Timestamp(RTH_END).time())
    ticks = ticks[rth]
    if ticks.empty:
        return pd.DataFrame()

    bars = ticks["Price"].resample("5min", label="left", closed="left").ohlc()
    bars["Volume"] = ticks["Volume"].resample("5min", label="left", closed="left").sum()
    bars = bars.dropna(subset=["open"])
    bars = bars.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"})
    bars.index.name = "DateTime"
    return bars.reset_index()


# ── Continuous back-adjusted tick series (per-day cache) ──────────────────────
# Building one combined multi-year tick file isn't practical (~500M+ rows across
# the catalog). Instead each day gets its own small Parquet file: front-month
# ticker only, RTH-filtered, back-adjustment offset already applied to price.
# This reuses the existing flatfiles_cache .csv.gz (no new downloads) and
# persists to disk so repeated app reloads never re-decompress/re-filter.

def _ticks_continuous_path(d: date) -> Path:
    return _TICKS_CONT_DIR / f"{d.isoformat()}.parquet"


def build_continuous_ticks_for_date(d: date, rolls: dict) -> pd.DataFrame | None:
    """Build (and cache) one day's back-adjusted, RTH-filtered, front-month ticks.
    Returns None if there's no active contract or no local gz cache for that date."""
    from contracts import get_active_contract
    from data_loader import RTH_START, RTH_END

    out_path = _ticks_continuous_path(d)
    if out_path.exists():
        return pd.read_parquet(out_path)

    active = get_active_contract(d, rolls)
    if active is None:
        return None

    gz_path = _GZ_CACHE_DIR / f"{d.isoformat()}.csv.gz"
    if not gz_path.exists():
        return None

    raw = _load_gz(gz_path, active["ticker"])
    raw = raw[raw["correction"] == 0]
    if raw.empty:
        return None

    dt_ct = (
        pd.to_datetime(raw["timestamp"], unit="ns", utc=True)
        .dt.tz_convert("America/Chicago")
        .dt.tz_localize(None)
    )
    ticks = pd.DataFrame({
        "DateTime": dt_ct,
        "Price":    raw["price"].astype(float).values + active["cum_offset"],
        "Volume":   raw["size"].astype(int).values,
    }).sort_values("DateTime")

    t   = ticks["DateTime"].dt.time
    rth = (t >= pd.Timestamp(RTH_START).time()) & (t < pd.Timestamp(RTH_END).time())
    ticks = ticks[rth].reset_index(drop=True)
    if ticks.empty:
        return None

    _ensure_dirs()
    ticks.to_parquet(out_path, index=False)
    return ticks


def load_continuous_ticks(d: date) -> pd.DataFrame:
    """Read a previously-built day's continuous ticks. Empty DataFrame if not built."""
    p = _ticks_continuous_path(d)
    if p.exists():
        return pd.read_parquet(p)
    return pd.DataFrame(columns=["DateTime", "Price", "Volume"])


def build_all_continuous_ticks(rolls: dict, status_placeholder=None) -> int:
    """Build the per-day continuous tick cache for every date in the catalog's
    active window that doesn't already have one. Returns count of days built."""
    from contracts import CATALOG

    start = date.fromisoformat(min(c.active_from for c in CATALOG))
    end   = date.fromisoformat(max(c.last_trade  for c in CATALOG))

    built = 0
    d = start
    while d <= end:
        if not _ticks_continuous_path(d).exists():
            if status_placeholder:
                status_placeholder.write(f"  {d.isoformat()} …")
            result = build_continuous_ticks_for_date(d, rolls)
            if result is not None:
                built += 1
        d += timedelta(days=1)
    return built


def validate_ticks_vs_bars(rolls: dict) -> dict:
    """Resample the cached continuous ticks to 5M and compare against the
    Massive 5M bar series built from the same rolls. Returns summary stats.

    Processes one cached day at a time — concatenating all ~445M+ ticks into
    a single DataFrame first (the original approach) blew past available
    memory (numpy ArrayMemoryError trying to allocate a 3.3GB column)."""
    from data_loader import filter_excluded_dates

    bars_by_ticker = {c.ticker: load_bars(c.ticker) for c in CATALOG if _is_downloaded(c.ticker)}
    mas_bars = filter_excluded_dates(apply_back_adjustment(bars_by_ticker, rolls))
    mas_bars_by_date = {
        d: g.set_index("DateTime")[["Open", "High", "Low", "Close"]]
        for d, g in mas_bars.groupby(mas_bars["DateTime"].dt.date)
    }

    total_ticks       = 0
    total_matched     = 0
    total_ohlc_match  = 0
    total_extra       = 0

    for f in sorted(_TICKS_CONT_DIR.glob("*.parquet")):
        day_ticks = pd.read_parquet(f)
        if day_ticks.empty:
            continue
        total_ticks += len(day_ticks)

        day_ticks = day_ticks.set_index("DateTime").sort_index()
        resampled = day_ticks["Price"].resample("5min", label="left", closed="left").ohlc()
        resampled = resampled.dropna(subset=["open"]).rename(
            columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"})
        if resampled.empty:
            continue

        d = pd.Timestamp(f.stem).date()
        day_bars = mas_bars_by_date.get(d)
        if day_bars is None:
            total_extra += len(resampled)
            continue

        m = resampled.add_suffix("_tk").join(day_bars.add_suffix("_bar"), how="outer")
        matched = m.dropna()
        total_matched += len(matched)
        total_extra   += int(m["Open_bar"].isna().sum())
        total_ohlc_match += int((
            (matched["Open_tk"].round(2)  == matched["Open_bar"].round(2)) &
            (matched["High_tk"].round(2)  == matched["High_bar"].round(2)) &
            (matched["Low_tk"].round(2)   == matched["Low_bar"].round(2)) &
            (matched["Close_tk"].round(2) == matched["Close_bar"].round(2))
        ).sum())
        del day_ticks, resampled, m, matched

    n_mas_bars = len(mas_bars)
    return {
        "total_ticks":     total_ticks,
        "coverage_pct":    total_matched / n_mas_bars * 100 if n_mas_bars else 0.0,
        "ohlc_match_pct":  total_ohlc_match / total_matched * 100 if total_matched else 0.0,
        "extra_bars":      total_extra,
    }


# ── Download one contract ─────────────────────────────────────────────────────

def _append_nt_lines(ticks_df: pd.DataFrame, path: Path) -> int:
    """Append one day's ticks to the NT import file. Returns lines written."""
    df = ticks_df[ticks_df["correction"] == 0]
    if df.empty:
        return 0
    dt_ct = (
        pd.to_datetime(df["timestamp"], unit="ns", utc=True)
        .dt.tz_convert("America/Chicago")
        .dt.tz_localize(None)
    )
    dt_str    = dt_ct.dt.strftime("%Y%m%d %H%M%S")
    price_str = df["price"].astype(float).map("{:.2f}".format)
    size_str  = df["size"].astype(str)
    lines = (dt_str + ";" + price_str + ";" + size_str + "\n").tolist()
    with open(path, "a", encoding="utf-8") as f:
        f.writelines(lines)
    return len(lines)


def download_contract(contract: Contract, rolls: dict, status_placeholder) -> bool:
    """
    Download flat files for one contract's front-month period, build 5M bars,
    write NT import file. Returns True on success.

    Processes one day at a time and writes the NT file incrementally — holding
    every tick for a high-volume front-month contract in memory at once can run
    into multiple GB and crash the process.
    """
    _ensure_dirs()
    s3 = _make_s3()

    from_date = date.fromisoformat(contract.active_from)
    to_date   = date.fromisoformat(contract.last_trade)

    nt_path = _nt_import_path(contract)
    if nt_path.exists():
        nt_path.unlink()  # start fresh — we append per day below

    all_frames  = []
    total_lines = 0
    d = from_date

    while d <= to_date:
        status_placeholder.write(f"  {d.isoformat()} …")
        local = _download_day(s3, d)
        if local:
            day_df = _load_gz(local, contract.ticker)
            if not day_df.empty:
                bars = _ticks_to_5m_bars(day_df)
                if not bars.empty:
                    all_frames.append(bars)
                total_lines += _append_nt_lines(day_df, nt_path)
            del day_df
        d += timedelta(days=1)

    if not all_frames:
        status_placeholder.error(f"No data found for {contract.ticker}")
        return False

    # Build and cache 5M bars
    bars = pd.concat(all_frames, ignore_index=True)
    bars.sort_values("DateTime", inplace=True, ignore_index=True)
    bars.to_parquet(_bars_path(contract.ticker), index=False)

    status_placeholder.success(
        f"✅ {contract.ticker} — {len(bars):,} bars · "
        f"NT import: {nt_path.name} ({total_lines:,} ticks)"
    )
    return True


def load_bars(ticker: str) -> pd.DataFrame | None:
    p = _bars_path(ticker)
    return pd.read_parquet(p) if p.exists() else None


def bars_from_cache(ticker: str, date_start: str, date_end: str) -> pd.DataFrame:
    """
    Build 5M RTH bars for a ticker/date range using local data only.

    Priority:
      1. Contract parquet (data/bars/{ticker}.parquet) — instant, filter by date
      2. Daily gzip files in flatfiles_cache — build bar-by-bar from ticks
      3. Returns empty DataFrame if neither exists (caller falls back to API)
    """
    start = date.fromisoformat(date_start)
    end   = date.fromisoformat(date_end)

    # 1 — contract parquet already has 5M bars for the full front-month period
    parquet = _bars_path(ticker)
    if parquet.exists():
        df = pd.read_parquet(parquet)
        mask = (df["DateTime"].dt.date >= start) & (df["DateTime"].dt.date <= end)
        filtered = df[mask].reset_index(drop=True)
        if not filtered.empty:
            return filtered

    # 2 — build from individual daily gzip files in the cache
    frames = []
    d = start
    while d <= end:
        local = _GZ_CACHE_DIR / f"{d.isoformat()}.csv.gz"
        if local.exists():
            day_df = _load_gz(local, ticker)
            if not day_df.empty:
                bars = _ticks_to_5m_bars(day_df)
                if not bars.empty:
                    frames.append(bars)
        d += timedelta(days=1)

    if not frames:
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    result.sort_values("DateTime", inplace=True, ignore_index=True)
    return result


# ── Comparison helper (carried over from old massive.py) ─────────────────────

def _show_comparison(comp: pd.DataFrame, label_a: str, label_b: str):
    matched  = comp["Status"] == "Matched"
    n_match  = matched.sum()
    n_a_only = (comp["Status"] == "left only").sum()
    n_b_only = (comp["Status"] == "right only").sum()
    ohlc_pct  = comp.loc[matched, "OHLC_match"].mean()  * 100 if n_match else 0.0
    ohlcv_pct = comp.loc[matched, "OHLCV_match"].mean() * 100 if n_match else 0.0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Matched bars",     f"{n_match:,}")
    c2.metric(f"{label_a} only",  f"{n_a_only:,}")
    c3.metric(f"{label_b} only",  f"{n_b_only:,}")
    c4.metric("OHLC match",       f"{ohlc_pct:.1f}%")
    c5.metric("OHLCV match",      f"{ohlcv_pct:.1f}%")

    mismatches = comp[matched & ~comp["OHLC_match"]]
    if mismatches.empty:
        st.success("All matched bars have identical OHLC ✅")
        return
    with st.expander(f"Mismatch detail — {len(mismatches):,} bars", expanded=False):
        display = mismatches[[
            "DateTime", "BarTime",
            "Open_sc", "Open_nt", "ΔOpen",
            "High_sc", "High_nt", "ΔHigh",
            "Low_sc",  "Low_nt",  "ΔLow",
            "Close_sc","Close_nt","ΔClose",
        ]].copy()
        display.columns = [
            c.replace("_sc", f"_{label_a}").replace("_nt", f"_{label_b}")
            for c in display.columns
        ]
        st.dataframe(display, use_container_width=True, hide_index=True)


# ── Multi-instrument helpers ───────────────────────────────────────────────────

def _instr_gz_cache_dir(key: str) -> Path:
    return _DATA_DIR / INSTRUMENTS[key].gz_subdir


def _instr_continuous_path(key: str) -> Path:
    return _BARS_DIR / f"_continuous_{key}.parquet"


def _instr_s3_key(key: str, d: date) -> str:
    spec = INSTRUMENTS[key]
    return f"{spec.s3_prefix}/{d.year}/{d.month:02d}/{d.isoformat()}.csv.gz"


def _instr_download_day(s3, key: str, d: date) -> Path | None:
    """Download one day's gz from the exchange S3 bucket. Returns local path or None."""
    cache_dir = _instr_gz_cache_dir(key)
    cache_dir.mkdir(parents=True, exist_ok=True)
    local = cache_dir / f"{d.isoformat()}.csv.gz"
    if local.exists():
        return local
    try:
        s3.download_file(_S3_BUCKET, _instr_s3_key(key, d), str(local))
        return local
    except Exception as e:
        if any(x in str(e) for x in ("404", "NoSuchKey", "403", "Forbidden")):
            return None
        raise


def _instr_load_gz(local: Path, key: str, ticker: str) -> pd.DataFrame:
    """Load a gz and filter for the contract, translating ticker to massive_root format."""
    spec = INSTRUMENTS[key]
    massive_ticker = spec.massive_root + ticker[len(spec.root):]  # "YM"→"0YM"+"U6"="0YMU6"
    with gzip.open(local, "rb") as f:
        raw = f.read()
    df = pd.read_csv(io.BytesIO(raw))
    return df[df["ticker"] == massive_ticker].copy()


def _instr_build_contract_bars(key: str, contract: InstContract) -> bool:
    """
    Build 5M bar parquet for one contract from the gz cache.
    For NQ, reads from the existing CME flatfiles_cache (no download needed).
    For YM/GC/CL, downloads missing days from the exchange S3 bucket first.
    Returns True if any bars were written.
    """
    cache_dir = _instr_gz_cache_dir(key)
    from_date = date.fromisoformat(contract.active_from)
    to_date   = min(date.fromisoformat(contract.last_trade), date.today())

    s3 = _make_s3() if key != "NQ" else None

    frames = []
    d = from_date
    while d <= to_date:
        local = cache_dir / f"{d.isoformat()}.csv.gz"
        if not local.exists() and s3 is not None:
            local = _instr_download_day(s3, key, d) or local
        if local.exists():
            day_df = _instr_load_gz(local, key, contract.ticker)
            if not day_df.empty:
                bars = _ticks_to_5m_bars(day_df)
                if not bars.empty:
                    frames.append(bars)
        d += timedelta(days=1)

    if not frames:
        return False

    all_bars = pd.concat(frames, ignore_index=True)
    all_bars.sort_values("DateTime", inplace=True, ignore_index=True)
    all_bars.to_parquet(_bars_path(contract.ticker), index=False)
    return True


def build_instr_continuous(key: str, rolls: dict, status_placeholder=None) -> pd.DataFrame:
    """
    Build a back-adjusted continuous series for one instrument.
    Reads per-contract bar parquets, applies Panama method, writes _continuous_{key}.parquet.
    """
    bars_by_ticker: dict = {}
    for c in CATALOGS[key]:
        p = _bars_path(c.ticker)
        if p.exists():
            bars_by_ticker[c.ticker] = pd.read_parquet(p)

    if not bars_by_ticker:
        if status_placeholder:
            status_placeholder.warning(f"No bar files found for {key}")
        return pd.DataFrame()

    continuous = _instr_back_adjust(key, bars_by_ticker, rolls)
    if continuous.empty:
        return continuous

    continuous.sort_values("DateTime", inplace=True, ignore_index=True)
    continuous.to_parquet(_instr_continuous_path(key), index=False)
    return continuous


def _show_instrument_section(key: str) -> None:
    """Generic Streamlit section for one instrument: roll schedule + build pipeline."""
    spec    = INSTRUMENTS[key]
    _instr_ensure_rolls(key)
    rolls   = _instr_load_rolls(key)
    catalog = CATALOGS[key]

    # ── Roll schedule ─────────────────────────────────────────────────────────
    with st.expander(f"📋 Roll Schedule — {spec.name}", expanded=False):
        st.caption(
            f"Exchange: **{spec.exchange.upper()}** · "
            f"Delivery months: {list(spec.months)}  \n"
            "Edit **Roll Date** and **Offset** to match NT's Instrument Manager, then save."
        )
        rows = []
        for c in catalog:
            rd  = _instr_get_roll_date(c.ticker, rolls, key)
            off = _instr_get_offset(c.ticker, rolls)
            rows.append({
                "Contract":     c.ticker,
                "Roll Date":    rd,
                "Offset (pts)": off,
                "Bars":         "✅" if _bars_path(c.ticker).exists() else "⬜",
            })
        edited = st.data_editor(
            pd.DataFrame(rows),
            column_config={
                "Contract":     st.column_config.TextColumn(disabled=True),
                "Roll Date":    st.column_config.TextColumn("Roll Date (YYYY-MM-DD)"),
                "Offset (pts)": st.column_config.NumberColumn("Offset (pts)", format="%.4f"),
                "Bars":         st.column_config.TextColumn(disabled=True, width="small"),
            },
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key=f"rolls_editor_{key}",
        )
        if st.button(f"💾 Save {key} Rolls"):
            new_rolls = {}
            for _, row in edited.iterrows():
                off_val = row["Offset (pts)"]
                new_rolls[row["Contract"]] = {
                    "roll_date": str(row["Roll Date"]).strip(),
                    "offset":    float(off_val) if pd.notna(off_val) and off_val != "" else None,
                }
            _instr_save_rolls(key, new_rolls)
            st.success(f"{key} roll schedule saved.")
            st.rerun()

    # ── Build bars + continuous ───────────────────────────────────────────────
    rolls_fresh     = _instr_load_rolls(key)
    available_bars  = [c for c in catalog if _bars_path(c.ticker).exists()]
    missing_offsets = [
        c.ticker for c in catalog[1:]
        if _bars_path(c.ticker).exists() and _instr_get_offset(c.ticker, rolls_fresh) is None
    ]

    cont_path = _instr_continuous_path(key)
    cont_info = ""
    if cont_path.exists():
        try:
            _ct = pd.read_parquet(cont_path)
            _dt = _ct["DateTime"].dt.date
            cont_info = f" · {len(_ct):,} bars · {_dt.min()} → {_dt.max()}"
        except Exception:
            pass

    with st.expander(f"📊 Build Continuous — {spec.name}{cont_info}", expanded=False):
        col_a, col_b = st.columns(2)

        dl_label = (
            "🔨 Build Bars from CME Cache"
            if key == "NQ"
            else f"📥 Download + Build Bars ({spec.exchange.upper()})"
        )
        if col_a.button(dl_label, key=f"build_bars_{key}"):
            status = st.empty()
            built = 0
            for c in catalog:
                status.write(f"  {c.ticker}…")
                if _instr_build_contract_bars(key, c):
                    built += 1
            status.empty()
            st.success(f"Built bars: {built}/{len(catalog)} contracts")
            st.rerun()

        if missing_offsets:
            col_b.warning(
                f"Missing offsets: **{', '.join(missing_offsets[:5])}"
                f"{'…' if len(missing_offsets) > 5 else ''}** — fill in Roll Schedule."
            )
        elif len(available_bars) == 0:
            col_b.info("Build bar parquets first (button above).")
        else:
            if col_b.button(
                f"🔗 Build {key} Continuous",
                disabled=bool(missing_offsets),
                key=f"build_cont_{key}",
            ):
                with st.spinner(f"Building {key} continuous…"):
                    cont_df = build_instr_continuous(key, rolls_fresh)
                if not cont_df.empty:
                    st.session_state[f"mas_cont_{key}"] = cont_df
                    _d = cont_df["DateTime"].dt.date
                    st.success(
                        f"✅ {key} continuous: **{len(cont_df):,} bars** · "
                        f"{_d.min()} → {_d.max()}"
                    )
                    st.rerun()
                else:
                    st.error(f"No data found for {key}")

        cont_session = st.session_state.get(f"mas_cont_{key}")
        if cont_session is not None and not cont_session.empty:
            _d = cont_session["DateTime"].dt.date
            st.success(
                f"**{key}** continuous ready: **{len(cont_session):,} bars** · "
                f"{_d.min()} → {_d.max()} · {_d.nunique()} days"
            )
        elif cont_path.exists():
            st.info(f"Persisted on disk{cont_info} — click 'Build {key} Continuous' to reload.")


# ── Main tab ──────────────────────────────────────────────────────────────────

def show_massive_tab():
    ensure_rolls_file()
    rolls = load_rolls()

    # ── Auto-load persisted continuous series / NT upload on app restart ────
    if "mas_continuous" not in st.session_state:
        cont_path = _BARS_DIR / "_continuous.parquet"
        if cont_path.exists():
            st.session_state["mas_continuous"] = pd.read_parquet(cont_path)

    if "mas_continuous_15m" not in st.session_state:
        cont_15m_path = _BARS_DIR / "_continuous_15m.parquet"
        if cont_15m_path.exists():
            st.session_state["mas_continuous_15m"] = pd.read_parquet(cont_15m_path)
        elif "mas_continuous" in st.session_state:
            _c15 = _resample_5m_to_15m(st.session_state["mas_continuous"])
            st.session_state["mas_continuous_15m"] = _c15
            _c15.to_parquet(_BARS_DIR / "_continuous_15m.parquet", index=False)

    if "mas_continuous_1m" not in st.session_state:
        cont_1m_path = _BARS_DIR / "_continuous_1m.parquet"
        if cont_1m_path.exists():
            st.session_state["mas_continuous_1m"] = pd.read_parquet(cont_1m_path)

    if "mas_continuous_100s" not in st.session_state:
        cont_100s_path = _BARS_DIR / "_continuous_100s.parquet"
        if cont_100s_path.exists():
            st.session_state["mas_continuous_100s"] = pd.read_parquet(cont_100s_path)

    if "nt_cont_bars" not in st.session_state:
        from data_loader import load_csv_cache, load_csv_manifest
        _mf = load_csv_manifest()
        _info = _mf.get("nt_cont")
        if _info:
            _df = load_csv_cache("nt_cont", _info["name"], _info["size"])
            if _df is not None:
                st.session_state["nt_cont_bars"] = _df
                st.session_state["nt_cont_key"]  = f"{_info['name']}_{_info['size']}"

    for _ik in ("NQ", "YM", "GC", "CL", "6E", "6J"):
        if f"mas_cont_{_ik}" not in st.session_state:
            _cp = _instr_continuous_path(_ik)
            if _cp.exists():
                st.session_state[f"mas_cont_{_ik}"] = pd.read_parquet(_cp)

    st.markdown("### Massive — ES Contract Manager")

    mgr_tab, instr_tab, quick_tab = st.tabs(
        ["📋 ES Contracts & Rolls", "🔧 Other Instruments", "⚡ Quick Compare (API)"]
    )

    # ═════════════════════════════════════════════════════════════════════════
    with mgr_tab:
        # ── Roll schedule + download ──────────────────────────────────────
        with controls.expander("mas_roll", "📋 Roll Schedule & Downloads", expanded=False):
            st.caption(
                "Pre-populated from CME convention (expiry − 8 days). "
                "Edit **Roll Date** and **Offset** to match what you enter in NT's Instrument Manager. "
                "Check contracts you want to download, then hit **Download Selected**."
            )

            rows = []
            for c in CATALOG:
                rd  = get_roll_date(c.ticker, rolls)
                off = get_offset(c.ticker, rolls)
                rows.append({
                    "✓":            False,
                    "Contract":     c.ticker,
                    "NT Name":      c.nt_name,
                    "Period":       c.label,
                    "Roll Date":    rd,
                    "Offset (pts)": off,
                    "Downloaded":   _status_emoji(c.ticker),
                })

            df_rolls = pd.DataFrame(rows)

            edited = st.data_editor(
                df_rolls,
                column_config={
                    "✓":            st.column_config.CheckboxColumn("Select", default=False),
                    "Contract":     st.column_config.TextColumn(disabled=True),
                    "NT Name":      st.column_config.TextColumn(disabled=True),
                    "Period":       st.column_config.TextColumn(disabled=True),
                    "Roll Date":    st.column_config.TextColumn("Roll Date (YYYY-MM-DD)"),
                    "Offset (pts)": st.column_config.NumberColumn("Offset (pts)", format="%.2f"),
                    "Downloaded":   st.column_config.TextColumn(disabled=True, width="small"),
                },
                hide_index=True,
                use_container_width=True,
                num_rows="fixed",
                key="rolls_editor",
            )

            col_save, col_dl, col_clear = st.columns([1, 1, 1])

            if col_save.button("💾 Save Roll Schedule"):
                new_rolls = {}
                for _, row in edited.iterrows():
                    ticker = row["Contract"]
                    off_val = row["Offset (pts)"]
                    new_rolls[ticker] = {
                        "roll_date": str(row["Roll Date"]).strip(),
                        "offset":    float(off_val) if pd.notna(off_val) and off_val != "" else None,
                    }
                save_rolls(new_rolls)
                st.success("Roll schedule saved.")
                st.rerun()

            selected_tickers = [
                row["Contract"] for _, row in edited.iterrows() if row["✓"]
            ]

            dl_disabled = len(selected_tickers) == 0
            if col_dl.button("📥 Download Selected", disabled=dl_disabled):
                st.markdown(f"**Downloading {len(selected_tickers)} contract(s)…**")
                updated_rolls = load_rolls()
                for ticker in selected_tickers:
                    c = CATALOG_BY_TICKER[ticker]
                    st.markdown(f"**{ticker} — {c.label}** ({c.active_from} → {c.last_trade})")
                    ph = st.empty()
                    try:
                        download_contract(c, updated_rolls, ph)
                    except Exception as e:
                        ph.error(f"Failed: {e}")
                st.rerun()

            if col_clear.button("🗑️ Clear Downloaded Data"):
                if _BARS_DIR.exists():
                    shutil.rmtree(_BARS_DIR)
                    _BARS_DIR.mkdir()
                if _NT_IMPORT_DIR.exists():
                    shutil.rmtree(_NT_IMPORT_DIR)
                    _NT_IMPORT_DIR.mkdir()
                st.success("Cleared downloaded bars and NT import files.")
                st.rerun()

        # ── NT import files ───────────────────────────────────────────────
        nt_files = sorted(_NT_IMPORT_DIR.glob("*.Last.txt")) if _NT_IMPORT_DIR.exists() else []
        with controls.expander("mas_nt_files", f"📂 NT Import Files ({len(nt_files)} ready)", expanded=False):
            st.caption(
                f"After downloading, one `.Last.txt` file is written per contract to:  \n"
                f"`{_NT_IMPORT_DIR}`  \n\n"
                "**To import into NT:** Tools → Historical Data Manager → Import tab  \n"
                "Select the file · Timezone: **Central Time (US & Canada)**  \n"
                "Once imported you no longer need these files."
            )
            if nt_files:
                for f in nt_files:
                    size_kb = f.stat().st_size // 1024
                    st.write(f"📄 `{f.name}` — {size_kb:,} KB")
            else:
                st.info("No NT import files yet — download contracts above.")

        # ── Continuous series vs NT @ES ───────────────────────────────────
        downloaded = [c for c in CATALOG if _is_downloaded(c.ticker)]
        n_dl = len(downloaded)
        with controls.expander("mas_series_vs_nt", f"📊 Continuous Series vs NT @ES  ({n_dl}/{len(CATALOG)} contracts downloaded)", expanded=False):
            st.caption(
                "Validates that the Massive back-adjusted continuous matches NT's `@ES` continuous contract. "
                "This is a prerequisite for WFA — if they diverge, WFA signals from NT won't align with Massive data."
            )

            missing_offsets = [
                c.ticker for c in downloaded[1:]
                if get_offset(c.ticker, rolls) is None
            ]

            col_build, col_status = st.columns([1, 2])
            with col_build:
                build_disabled = (n_dl == 0) or bool(missing_offsets)
                if st.button("🔗 Build Continuous Series", disabled=build_disabled,
                             help="Needs all contracts downloaded + offsets filled in."):
                    bars_by_ticker = {c.ticker: load_bars(c.ticker) for c in downloaded if _is_downloaded(c.ticker)}
                    continuous = apply_back_adjustment(bars_by_ticker, rolls)
                    continuous = filter_excluded_dates(continuous)
                    st.session_state["mas_continuous"] = continuous
                    continuous.to_parquet(_BARS_DIR / "_continuous.parquet", index=False)
                    # Build 15M bars from 5M
                    cont_15m = _resample_5m_to_15m(continuous)
                    st.session_state["mas_continuous_15m"] = cont_15m
                    cont_15m.to_parquet(_BARS_DIR / "_continuous_15m.parquet", index=False)
                    st.rerun()

            with col_status:
                if missing_offsets:
                    st.warning(f"Missing offsets: **{', '.join(missing_offsets)}** — fill in Roll Schedule above and save.")
                elif n_dl == 0:
                    st.info("No contracts downloaded yet.")
                else:
                    cont = st.session_state.get("mas_continuous")
                    if cont is not None and not cont.empty:
                        d = cont["DateTime"].dt.date
                        st.success(
                            f"Continuous ready: **{len(cont):,} bars** · "
                            f"{d.min()} → {d.max()} · {d.nunique()} days · {n_dl} contracts"
                        )
                        if st.button("📊 Open in Bar Viewer"):
                            apply_data_slot("sc_5m", cont.drop(columns=["Contract"], errors="ignore"),
                                             "Massive Continuous (back-adjusted)", "mas_continuous")
                            st.rerun()
                    else:
                        st.info(f"{n_dl} contracts ready — click Build to stitch them.")

            # ── Additional bar timeframes ─────────────────────────────────────
            st.divider()
            st.markdown("**Additional Bar Timeframes**")
            _tf_col1, _tf_col2, _tf_col3 = st.columns(3)

            # 1M status/build
            with _tf_col1:
                _c1m = st.session_state.get("mas_continuous_1m")
                if _c1m is not None and not _c1m.empty:
                    st.success(f"1M bars: **{len(_c1m):,}** bars ready")
                else:
                    _has_ticks = _TICKS_CONT_DIR.exists() and any(_TICKS_CONT_DIR.glob("*.parquet"))
                    if _has_ticks:
                        if st.button("Build 1M bars (from ticks)"):
                            _status = st.empty()
                            _c1m = _resample_ticks_to_bars("1min", _status)
                            _status.empty()
                            st.session_state["mas_continuous_1m"] = _c1m
                            _c1m.to_parquet(_BARS_DIR / "_continuous_1m.parquet", index=False)
                            st.rerun()
                    else:
                        st.info("Build continuous ticks first.")

            # 15M status/build
            with _tf_col2:
                _c15 = st.session_state.get("mas_continuous_15m")
                _mas_cont_5m = st.session_state.get("mas_continuous")
                if _c15 is not None and not _c15.empty:
                    st.success(f"15M bars: **{len(_c15):,}** bars ready")
                elif _mas_cont_5m is not None and not _mas_cont_5m.empty:
                    if st.button("Build 15M bars (from 5M)"):
                        _c15 = _resample_5m_to_15m(_mas_cont_5m)
                        st.session_state["mas_continuous_15m"] = _c15
                        _c15.to_parquet(_BARS_DIR / "_continuous_15m.parquet", index=False)
                        st.rerun()
                else:
                    st.info("Build 5M continuous first.")

            # 100s status/build
            with _tf_col3:
                _c100s = st.session_state.get("mas_continuous_100s")
                if _c100s is not None and not _c100s.empty:
                    st.success(f"100s bars: **{len(_c100s):,}** bars ready")
                else:
                    _has_ticks = _TICKS_CONT_DIR.exists() and any(_TICKS_CONT_DIR.glob("*.parquet"))
                    if _has_ticks:
                        if st.button("Build 100s bars (from ticks)"):
                            _status = st.empty()
                            _c100s = _resample_ticks_to_bars("100s", _status)
                            _status.empty()
                            st.session_state["mas_continuous_100s"] = _c100s
                            _c100s.to_parquet(_BARS_DIR / "_continuous_100s.parquet", index=False)
                            st.rerun()
                    else:
                        st.info("Build continuous ticks first.")

            st.divider()

            st.markdown("**Upload NT `@ES` continuous 5M export**")
            st.caption(
                "In NT: add OHLCExporter to an `@ES` continuous chart (5M, RTH), "
                "reload the chart to export, then upload the `.txt` file here."
            )

            nt_cont_file = st.file_uploader(
                "NT @ES continuous export (.txt)", type=["txt"], key="nt_cont_upload",
            )
            if nt_cont_file:
                _key = f"{nt_cont_file.name}_{nt_cont_file.size}"
                if st.session_state.get("nt_cont_key") != _key:
                    with st.spinner("Parsing NT export…"):
                        df_nt_cont = parse_ohlc_from_upload(nt_cont_file)
                    df_nt_cont = filter_excluded_dates(df_nt_cont)
                    st.session_state["nt_cont_bars"] = df_nt_cont
                    from data_loader import save_csv_cache, load_csv_manifest, save_csv_manifest
                    save_csv_cache(df_nt_cont, "nt_cont", nt_cont_file.name, nt_cont_file.size)
                    _mf = load_csv_manifest()
                    _mf["nt_cont"] = {"name": nt_cont_file.name, "size": nt_cont_file.size}
                    save_csv_manifest(_mf)
                    st.session_state["nt_cont_key"]  = _key
                    st.rerun()

            nt_cont = st.session_state.get("nt_cont_bars")
            mas_cont = st.session_state.get("mas_continuous")

            if nt_cont is not None:
                d = nt_cont["DateTime"].dt.date
                st.success(f"NT @ES loaded: **{len(nt_cont):,} bars** · {d.min()} → {d.max()}")

            if mas_cont is not None and nt_cont is not None:
                st.divider()
                st.markdown("#### Comparison — Massive Continuous vs NT @ES")
                st.caption("Filters are set once in the 🗂️ Data tab and shared with Bar Analysis.")
                cont_filter_kwargs = get_filters("shared")
                show_gate_body(
                    mas_cont.drop(columns=["Contract"], errors="ignore"), nt_cont,
                    left_label="Massive Continuous", right_label="NT @ES",
                    gate_key="g_cont", **cont_filter_kwargs,
                )
            elif mas_cont is None and nt_cont is not None:
                st.info("Build the continuous series above to run the comparison.")
            elif mas_cont is not None and nt_cont is None:
                st.info("Upload the NT @ES export above to run the comparison.")

        # ── Continuous tick series (per-day cache, for Bar Analysis) ───────
        n_tick_days = len(list(_TICKS_CONT_DIR.glob("*.parquet"))) if _TICKS_CONT_DIR.exists() else 0
        with controls.expander("mas_tick_series", f"🧮 Continuous Tick Series  ({n_tick_days} day(s) cached)", expanded=False):
            st.caption(
                "Builds one small Parquet per trading day from the already-downloaded flat-file cache — "
                "front-month ticker only, RTH-filtered, back-adjustment offset baked into price. "
                "Used by Bar Analysis for tick-level simulation. One-time build; persists across reloads, "
                "and re-running only fills in missing days."
            )
            col_build_tk, col_val_tk = st.columns(2)
            with col_build_tk:
                if st.button("🔨 Build / Update Tick Cache", disabled=(n_dl == 0) or bool(missing_offsets)):
                    status = st.empty()
                    with st.spinner("Building per-day continuous ticks…"):
                        built = build_all_continuous_ticks(rolls, status_placeholder=status)
                    status.empty()
                    st.success(f"Built {built} new day(s). Total cached: "
                               f"{len(list(_TICKS_CONT_DIR.glob('*.parquet')))}")

            with col_val_tk:
                if st.button("✅ Validate vs 5M Bars", disabled=n_tick_days == 0):
                    with st.spinner("Resampling ticks to 5M and comparing…"):
                        result = validate_ticks_vs_bars(rolls)
                    st.session_state["mas_tick_validation"] = result

            val = st.session_state.get("mas_tick_validation")
            if val is not None:
                v1, v2, v3, v4 = st.columns(4)
                v1.metric("Total Ticks", f"{val['total_ticks']:,}")
                v2.metric("Bars w/ Tick Coverage",
                          f"{val['coverage_pct']:.1f}%", help="% of Massive 5M bars reconstructable from ticks.")
                v3.metric("OHLC Exact Match", f"{val['ohlc_match_pct']:.2f}%",
                          help="Of bars present in both, % where O/H/L/C all match exactly.")
                v4.metric("Extra Resampled Bars", f"{val['extra_bars']:,}",
                          help="Bars from resampling ticks that have no corresponding Massive 5M bar.")

    # ═════════════════════════════════════════════════════════════════════════
    with instr_tab:
        st.markdown("### Other Instruments — NQ · YM · GC · CL")
        st.caption(
            "NQ reads from the existing CME flatfiles cache (no new downloads needed). "
            "YM, GC, and CL will download from CBOT/COMEX/NYMEX on first use."
        )
        nq_tab, ym_tab, gc_tab, cl_tab, fx_6e_tab, fx_6j_tab = st.tabs(
            ["NQ — Nasdaq", "YM — Dow", "GC — Gold", "CL — Crude", "6E — Euro FX", "6J — Yen FX"]
        )
        with nq_tab:
            _show_instrument_section("NQ")
        with ym_tab:
            _show_instrument_section("YM")
        with gc_tab:
            _show_instrument_section("GC")
        with cl_tab:
            _show_instrument_section("CL")
        with fx_6e_tab:
            _show_instrument_section("6E")
        with fx_6j_tab:
            _show_instrument_section("6J")

    # ═════════════════════════════════════════════════════════════════════════
    with quick_tab:
        st.markdown("### Quick Compare — Single Contract (API)")
        st.caption(
            "Fetches a small date range via the Massive REST API for spot-checking. "
            "Use the Contract Manager tab for bulk historical downloads."
        )

        with controls.expander("mas_config", "⚙️ Config", expanded=False):
            col_ticker, col_d1, col_d2 = st.columns([1, 1, 1])
            ticker = col_ticker.text_input(
                "Ticker",
                value=st.session_state.get("mas_ticker", "ESM6"),
                help="Massive contract ticker e.g. ESM6, ESZ5",
            )
            date_start = col_d1.text_input(
                "Start Date", value=st.session_state.get("mas_date_start", "2026-06-12"),
            )
            date_end = col_d2.text_input(
                "End Date", value=st.session_state.get("mas_date_end", "2026-06-13"),
            )
            st.session_state["mas_ticker"]     = ticker
            st.session_state["mas_date_start"] = date_start
            st.session_state["mas_date_end"]   = date_end

            if st.button("🔎 Look up contract info"):
                try:
                    info    = fetch_massive_contract_info(_API_KEY, ticker)
                    c_cat   = CATALOG_BY_TICKER.get(ticker)
                    nt_name = c_cat.nt_name if c_cat else ticker
                    st.info(
                        f"**{ticker}** · {info['first_trade_date']} → {info['last_trade_date']}  \n"
                        f"NT name: `{nt_name}`  |  tick size: {info.get('tick_size', '—')}"
                    )
                except Exception as e:
                    st.error(f"Lookup failed: {e}")

        st.markdown("#### Data")
        col_t, col_a, col_n, col_nn = st.columns(4)

        tick_bars      = st.session_state.get("mas_tick_bars")
        agg_bars       = st.session_state.get("mas_agg_bars")
        nt_bars        = st.session_state.get("mas_nt_bars")
        nt_native_bars = st.session_state.get("mas_nt_native_bars")

        def _status_box(bars, label):
            if bars is not None:
                d = bars["DateTime"].dt.date
                st.success(f"✅ **{label}**  \n{d.nunique()} days · {d.min()} → {d.max()}")
            else:
                st.info(f"{label} — not loaded")

        with col_t:
            _status_box(tick_bars, "Flat-file bars")
            has_parquet = _bars_path(ticker).exists()
            has_cache   = any(
                (_GZ_CACHE_DIR / f"{(date.fromisoformat(date_start) + timedelta(days=i)).isoformat()}.csv.gz").exists()
                for i in range((date.fromisoformat(date_end) - date.fromisoformat(date_start)).days + 1)
            )
            src_label = "contract parquet" if has_parquet else ("gzip cache" if has_cache else "API")
            if st.button(f"📥 Build Bars  ({src_label})",
                         help="Uses local flat-file cache if available, otherwise falls back to Massive API."):
                try:
                    bars = bars_from_cache(ticker, date_start, date_end)
                    if bars.empty:
                        st.warning("Not in local cache — falling back to API…")
                        with st.spinner(f"Fetching {ticker} ticks from API…"):
                            ticks = fetch_massive_trades(_API_KEY, ticker, date_start, date_end)
                        bars = resample_ticks_to_bars(ticks)
                        st.session_state["mas_tick_ticks"] = ticks
                    st.session_state["mas_tick_bars"] = bars
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed: {e}")

        with col_a:
            _status_box(agg_bars, "Massive agg bars")
            if st.button("📊 Fetch Agg Bars",
                         help="Fetches Massive pre-built 5M bars as a reference."):
                try:
                    with st.spinner(f"Fetching {ticker} agg bars…"):
                        bars = fetch_massive_aggs(_API_KEY, ticker, date_start, date_end)
                    st.session_state["mas_agg_bars"] = bars
                    st.rerun()
                except Exception as e:
                    st.error(f"Fetch failed: {e}")

        with col_n:
            _status_box(nt_bars, "NT ES_MAS bars")
            nt_file = st.file_uploader(
                "Upload NT ES_MAS 5M export", type=["txt", "csv"], key="mas_nt_upload",
            )
            if nt_file:
                _key = f"{nt_file.name}_{nt_file.size}"
                if st.session_state.get("mas_nt_key") != _key:
                    with st.spinner("Parsing…"):
                        df = parse_ohlc_from_upload(nt_file)
                    st.session_state["mas_nt_bars"] = df
                    st.session_state["mas_nt_key"]  = _key
                    st.rerun()

        with col_nn:
            _status_box(nt_native_bars, "NT native bars")
            nt_native_file = st.file_uploader(
                "Upload NT native 5M export", type=["txt", "csv"], key="mas_nt_native_upload",
            )
            if nt_native_file:
                _key = f"{nt_native_file.name}_{nt_native_file.size}"
                if st.session_state.get("mas_nt_native_key") != _key:
                    with st.spinner("Parsing…"):
                        df = parse_ohlc_from_upload(nt_native_file)
                    st.session_state["mas_nt_native_bars"] = df
                    st.session_state["mas_nt_native_key"]  = _key
                    st.rerun()

        if st.button("🗑️ Clear cache",
                     help="Deletes parquet cache — next fetch re-downloads from Massive API."):
            if MASSIVE_CACHE_DIR.exists():
                shutil.rmtree(MASSIVE_CACHE_DIR)
            for k in ("mas_tick_bars", "mas_tick_ticks", "mas_agg_bars",
                      "mas_nt_bars", "mas_nt_key", "mas_nt_native_bars", "mas_nt_native_key"):
                st.session_state.pop(k, None)
            st.rerun()

        st.divider()
        st.markdown("#### Comparison 1 — Tick-Built vs Massive Agg")
        st.caption("Both from Massive — should be identical if bar builder is correct.")
        if tick_bars is not None and agg_bars is not None:
            _show_comparison(build_comparison(tick_bars, agg_bars), "Tick", "Agg")
        else:
            st.info(f"Needs: {', '.join(l for l, d in [('Tick-built', tick_bars), ('Agg', agg_bars)] if d is None)}")

        st.divider()
        st.markdown("#### Comparison 2 — Tick-Built vs NT ES_MAS")
        st.caption("Validates round-trip: Massive ticks → NT import → OHLCExporter → bars.")
        if tick_bars is not None and nt_bars is not None:
            _show_comparison(build_comparison(tick_bars, nt_bars), "Tick", "NT_MAS")
        else:
            st.info(f"Needs: {', '.join(l for l, d in [('Tick-built', tick_bars), ('NT ES_MAS', nt_bars)] if d is None)}")

        st.divider()
        st.markdown("#### Comparison 3 — Tick-Built vs NT Native")
        st.caption("Cross-checks Massive tick data against NT's native Rithmic feed.")
        if tick_bars is not None and nt_native_bars is not None:
            _show_comparison(build_comparison(tick_bars, nt_native_bars), "Tick", "NT_Native")
        else:
            st.info(f"Needs: {', '.join(l for l, d in [('Tick-built', tick_bars), ('NT Native', nt_native_bars)] if d is None)}")
