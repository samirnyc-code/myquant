from pathlib import Path
import re
import struct
import numpy as np
import pandas as pd
import streamlit as st
import exchange_calendars as xcals

DATA_DIR  = Path(__file__).parent / "data" / "raw"

RTH_START     = "08:30:00"
RTH_END       = "15:15:00"
TICK_SIZE     = 0.25
RTH_START_MIN = 8 * 60 + 30   # 510


def apply_data_slot(slot: str, df: pd.DataFrame, label: str, key: str) -> None:
    """Push a 5M bar DataFrame into a named session-state slot used by the Bar Viewer / validation."""
    st.session_state[f"data_{slot}"]       = df
    st.session_state[f"data_{slot}_label"] = label
    st.session_state[f"data_{slot}_key"]   = key

    if slot == "sc_5m":
        st.session_state["bv_sc5m_bars"] = df
        st.session_state["bv_sc5m_key"]  = key
    elif slot == "nt_5m":
        st.session_state["bv_nt5m_bars"]       = df
        st.session_state["bv_nt5m_key"]        = key
        st.session_state["uploaded_ohlc_bars"] = df
        st.session_state["uploaded_ohlc_key"]  = key

# ── Contract registry ─────────────────────────────────────────────────────────
# Add new contracts here. sc_file must be a SC BarData tick file.
# nt_file must be a NinjaTrader semicolon-delimited OHLC export.

CONTRACTS = {
    "ESM6 — 2026": {
        "sc_file": DATA_DIR / "ESM6.CME_BarData.txt",
        "nt_file": DATA_DIR / "NinjaScript Output 03_06_2026 23_08.txt",
    },
    "ESH21 — 2021": {
        "sc_file": DATA_DIR / "ESH21-CME.txt",
        "nt_file": DATA_DIR / "NinjaScript Output 2021.txt",
    },
}

# Keep legacy path constants so any import that uses SC_FILE / NT_FILE still compiles.
SC_FILE = CONTRACTS["ESM6 — 2026"]["sc_file"]
NT_FILE = CONTRACTS["ESM6 — 2026"]["nt_file"]


def bar_num_from_dt(dt) -> int:
    """Return 1-indexed RTH bar number for any timestamp.
    Bar N opens at RTH_START + (N-1)*5 min. Uses hour+minute only."""
    ts = pd.Timestamp(dt)
    return int((ts.hour * 60 + ts.minute - RTH_START_MIN) // 5) + 1


@st.cache_data(show_spinner="Loading SC bars…")
def load_sc_bars(sc_file_path: str = str(SC_FILE)) -> pd.DataFrame:
    chunks = []
    for chunk in pd.read_csv(
        sc_file_path,
        skipinitialspace=True,
        usecols=["Date", "Time", "Last", "Volume"],
        chunksize=500_000,
        dtype={"Date": str, "Time": str, "Last": float, "Volume": "int32"},
    ):
        mask = (chunk["Time"] >= RTH_START) & (chunk["Time"] < RTH_END)
        chunk = chunk.loc[mask]
        if chunk.empty:
            continue
        chunk = chunk.copy()
        chunk["datetime"] = pd.to_datetime(
            chunk["Date"] + " " + chunk["Time"], format="mixed"
        )
        chunks.append(chunk[["datetime", "Last", "Volume"]])

    df = pd.concat(chunks, ignore_index=True).sort_values("datetime")
    df.set_index("datetime", inplace=True)

    bars = (
        df.resample("5min", closed="left", label="left")
        .agg(
            Open=("Last", "first"),
            High=("Last", "max"),
            Low=("Last", "min"),
            Close=("Last", "last"),
            Volume=("Volume", "sum"),
        )
        .dropna(subset=["Open"])
    )
    bars = bars[
        (bars.index.time >= pd.Timestamp(RTH_START).time()) &
        (bars.index.time <  pd.Timestamp(RTH_END).time())
    ]
    return bars.reset_index().rename(columns={"datetime": "DateTime"})


@st.cache_data(show_spinner="Loading SC tick data (tick-level)…")
def load_sc_ticks(sc_file_path: str = str(SC_FILE)) -> pd.DataFrame:
    """Return all RTH ticks as DataFrame: DateTime, Price, Volume.
    Includes ticks through 15:15:00 (session end) for session-exit pricing."""
    chunks = []
    for chunk in pd.read_csv(
        sc_file_path,
        skipinitialspace=True,
        usecols=["Date", "Time", "Last", "Volume"],
        chunksize=500_000,
        dtype={"Date": str, "Time": str, "Last": float, "Volume": "int32"},
    ):
        mask = (chunk["Time"] >= RTH_START) & (chunk["Time"] <= RTH_END)
        chunk = chunk.loc[mask]
        if chunk.empty:
            continue
        chunk = chunk.copy()
        chunk["DateTime"] = pd.to_datetime(chunk["Date"] + " " + chunk["Time"], format="mixed")
        chunks.append(chunk[["DateTime", "Last", "Volume"]].rename(columns={"Last": "Price"}))
    df = pd.concat(chunks, ignore_index=True).sort_values("DateTime").reset_index(drop=True)
    return df


# ── Upload parsers (no cache — data comes from Streamlit UploadedFile) ────────

def resample_ticks_to_bars(ticks: pd.DataFrame) -> pd.DataFrame:
    """Build 5-min RTH bars from a (DateTime, Price, Volume) ticks DataFrame."""
    if ticks.empty:
        return pd.DataFrame(columns=["DateTime", "Open", "High", "Low", "Close", "Volume"])
    df = ticks.set_index("DateTime").rename(columns={"Price": "Last"})
    bars = (
        df.resample("5min", closed="left", label="left")
        .agg(Open=("Last", "first"), High=("Last", "max"),
             Low=("Last", "min"),  Close=("Last", "last"), Volume=("Volume", "sum"))
        .dropna(subset=["Open"])
    )
    bars = bars[
        (bars.index.time >= pd.Timestamp(RTH_START).time()) &
        (bars.index.time <  pd.Timestamp(RTH_END).time())
    ]
    return bars.reset_index()


def resample_1s_ohlcv_to_5m(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate 1s OHLCV bars (SC export) into 5-min RTH bars.
    Input columns: DateTime, Open, High, Low, Close, Volume"""
    if df.empty:
        return pd.DataFrame(columns=["DateTime", "Open", "High", "Low", "Close", "Volume"])
    d = df.set_index("DateTime")
    bars = (
        d.resample("5min", closed="left", label="left")
        .agg(Open=("Open", "first"), High=("High", "max"),
             Low=("Low", "min"), Close=("Close", "last"), Volume=("Volume", "sum"))
        .dropna(subset=["Open"])
    )
    bars = bars[
        (bars.index.time >= pd.Timestamp(RTH_START).time()) &
        (bars.index.time <  pd.Timestamp(RTH_END).time())
    ]
    return bars.reset_index()


_RTH_START_S = RTH_START.replace(":", "")  # "083000"
_RTH_END_S   = RTH_END.replace(":", "")    # "151500"


def parse_nt_ticks_from_upload(uploaded_file, progress=None) -> pd.DataFrame:
    """Parse NT8 tick export: YYYYMMDD HHMMSS SUBSEC100NS;Price;Bid;Ask;Volume
    No header row. SUBSEC is in 100-nanosecond units.
    RTH ticks only (08:30–15:15 CT). Returns DataFrame: DateTime, Price, Volume.
    progress: optional callable(fraction 0–1) for UI progress updates."""
    uploaded_file.seek(0)
    file_size   = getattr(uploaded_file, "size", None)
    tick_chunks = []
    bytes_read  = 0

    for chunk in pd.read_csv(
        uploaded_file,
        sep=";",
        header=None,
        usecols=[0, 1, 4],        # skip bid (col 2) and ask (col 3)
        dtype=str,
        na_filter=False,
        chunksize=500_000,
        on_bad_lines="skip",
    ):
        chunk.columns = ["ts", "price", "volume"]

        # Split "YYYYMMDD HHMMSS SUBSEC" on whitespace
        ts_parts = chunk["ts"].str.strip().str.split(expand=True)
        if ts_parts.shape[1] < 2:
            continue
        time_s = ts_parts[1]

        mask = (time_s >= _RTH_START_S) & (time_s <= _RTH_END_S)
        if not mask.any():
            if progress and file_size:
                bytes_read += chunk.memory_usage(deep=False).sum()
                progress(min(bytes_read / file_size, 0.99))
            continue

        date_s = ts_parts[0][mask]
        time_s = time_s[mask]
        base_dt = pd.to_datetime(date_s + time_s, format="%Y%m%d%H%M%S", errors="coerce")

        if ts_parts.shape[1] >= 3:
            subsec_ns = pd.to_numeric(ts_parts[2][mask], errors="coerce").fillna(0) * 100
            dt = base_dt + pd.to_timedelta(subsec_ns, unit="ns")
        else:
            dt = base_dt

        price  = pd.to_numeric(chunk["price"][mask],  errors="coerce")
        volume = pd.to_numeric(chunk["volume"][mask], errors="coerce").fillna(0).astype("int32")
        tick_chunks.append(pd.DataFrame({
            "DateTime": dt.values, "Price": price.values, "Volume": volume.values,
        }))

        if progress and file_size:
            bytes_read += chunk.memory_usage(deep=False).sum()
            progress(min(bytes_read / file_size, 0.99))

    if not tick_chunks:
        return pd.DataFrame(columns=["DateTime", "Price", "Volume"])
    return (pd.concat(tick_chunks, ignore_index=True)
              .dropna(subset=["DateTime", "Price"])
              .sort_values("DateTime")
              .reset_index(drop=True))

def _sc_detect_sep(uploaded_file) -> str:
    """Peek at the first line to detect the delimiter (comma or tab)."""
    uploaded_file.seek(0)
    raw = uploaded_file.read(2048)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    uploaded_file.seek(0)
    first_line = raw.splitlines()[0] if raw else ""
    return "\t" if "\t" in first_line else ","


def _sc_parse_chunks(uploaded_file, rth_end_op):
    """Shared chunk iterator for SC BarData uploads. Yields (date_str, time_str, last, volume) rows."""
    sep = _sc_detect_sep(uploaded_file)
    uploaded_file.seek(0)
    for chunk in pd.read_csv(
        uploaded_file,
        sep=sep,
        skipinitialspace=True,
        chunksize=500_000,
        dtype=str,
        na_filter=False,
    ):
        chunk.columns = chunk.columns.str.strip()
        missing = [c for c in ("Date", "Time", "Last", "Volume") if c not in chunk.columns]
        if missing:
            raise ValueError(
                f"SC BarData file is missing columns: {missing}. "
                f"Found: {list(chunk.columns[:8])}. "
                "Make sure you uploaded a Sierra Charts BarData tick file."
            )
        chunk["Time"] = chunk["Time"].str.strip()
        chunk["Date"] = chunk["Date"].str.strip()
        mask = (chunk["Time"] >= RTH_START) & rth_end_op(chunk["Time"])
        chunk = chunk.loc[mask].copy()
        if chunk.empty:
            continue
        chunk["Last"]   = pd.to_numeric(chunk["Last"],   errors="coerce")
        chunk["Volume"] = pd.to_numeric(chunk["Volume"], errors="coerce").fillna(0).astype("int32")
        chunk["datetime"] = pd.to_datetime(chunk["Date"] + " " + chunk["Time"], format="mixed")
        yield chunk[["datetime", "Last", "Volume"]]


def parse_sc_bars_from_upload(uploaded_file) -> pd.DataFrame:
    """Build 5-min RTH bars from an uploaded SC BarData file (same format as load_sc_bars)."""
    chunks = list(_sc_parse_chunks(uploaded_file, lambda t: t < RTH_END))
    if not chunks:
        return pd.DataFrame()
    df = pd.concat(chunks, ignore_index=True).sort_values("datetime")
    df.set_index("datetime", inplace=True)
    bars = (
        df.resample("5min", closed="left", label="left")
        .agg(Open=("Last","first"), High=("Last","max"),
             Low=("Last","min"), Close=("Last","last"), Volume=("Volume","sum"))
        .dropna(subset=["Open"])
    )
    bars = bars[
        (bars.index.time >= pd.Timestamp(RTH_START).time()) &
        (bars.index.time <  pd.Timestamp(RTH_END).time())
    ]
    return bars.reset_index().rename(columns={"datetime": "DateTime"})


def parse_sc_ticks_from_upload(uploaded_file) -> pd.DataFrame:
    """Return RTH ticks from an uploaded SC BarData file (same format as load_sc_ticks)."""
    chunks = []
    for c in _sc_parse_chunks(uploaded_file, lambda t: t <= RTH_END):
        chunks.append(c.rename(columns={"Last": "Price", "datetime": "DateTime"}))
    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True).sort_values("DateTime").reset_index(drop=True)


_SCID_MAGIC = b"SCID"
# SCDateTimeMS is int64 microseconds since 1899-12-30 UTC (not an OLE double)
_SCID_BASE_NS = pd.Timestamp("1899-12-30", tz="UTC").value  # epoch-ns
_SCID_DTYPE = np.dtype([
    ("DateTime",    "<i8"),   # int64 us since 1899-12-30 UTC
    ("Open",        "<f4"),
    ("High",        "<f4"),
    ("Low",         "<f4"),
    ("Close",       "<f4"),
    ("NumTrades",   "<u4"),
    ("TotalVolume", "<u4"),
    ("BidVolume",   "<u4"),
    ("AskVolume",   "<u4"),
])  # 40 bytes per record


def _scid_us_to_ct(us: np.ndarray) -> pd.DatetimeIndex:
    """SCDateTimeMS (int64 us since 1899-12-30 UTC) -> tz-naive Chicago datetime."""
    ns = _SCID_BASE_NS + us * np.int64(1_000)
    return pd.DatetimeIndex(ns, tz="UTC").tz_convert("America/Chicago").tz_localize(None)


def parse_scid_ticks_from_upload(uploaded_file) -> pd.DataFrame:
    """Parse a Sierra Chart binary .scid intraday file.
    Returns RTH ticks as DataFrame: DateTime (CT, tz-naive), Price, Volume."""
    uploaded_file.seek(0)
    raw = uploaded_file.read()

    if raw[:4] != _SCID_MAGIC:
        raise ValueError("Not a valid SCID file — missing 'SCID' magic bytes")

    header_size = struct.unpack_from("<I", raw, 4)[0]
    record_size = struct.unpack_from("<I", raw, 8)[0]
    if record_size != 40:
        raise ValueError(f"Unsupported SCID record size {record_size} (expected 40)")

    rec_bytes = raw[header_size:]
    n = len(rec_bytes) // record_size
    if n == 0:
        return pd.DataFrame(columns=["DateTime", "Price", "Volume"])

    records = np.frombuffer(rec_bytes[: n * record_size], dtype=_SCID_DTYPE)
    valid = records["DateTime"] > 0   # skip filler records with timestamp == 0
    records = records[valid]
    dt_ct = _scid_us_to_ct(records["DateTime"])

    df = pd.DataFrame({
        "DateTime": dt_ct,
        "Price":    records["Close"].astype("float64"),
        "Volume":   records["TotalVolume"].astype("int32"),
    })

    t = df["DateTime"].dt.strftime("%H:%M:%S")
    df = df[(t >= RTH_START) & (t <= RTH_END)]
    return df.sort_values("DateTime").reset_index(drop=True)


SCID_DATA_DIR  = Path(r"C:\Users\Admin\Desktop\NT Code Versions\ChartMarker_Files\Data")
SCID_CACHE_DIR = SCID_DATA_DIR / "_scid_cache"

_SCID_CHUNK_RECS = 2_097_152  # ~80 MB per chunk (2M * 40 bytes)

# Integer UTC time-of-day bounds covering both CDT (UTC-5) and CST (UTC-6) RTH windows.
# CDT RTH: 08:30–15:15 CT = 13:30–20:15 UTC
# CST RTH: 08:30–15:15 CT = 14:30–21:15 UTC
# Conservative window eliminates ~65% of ETH records before any tz conversion.
_PRE_RTH_START_US = 13 * 3_600_000_000                     # 13:00 UTC in microseconds
_PRE_RTH_END_US   = 21 * 3_600_000_000 + 30 * 60_000_000   # 21:30 UTC in microseconds

_RTH_START_SEC = 8 * 3600 + 30 * 60   # 30600 — 08:30:00 CT
_RTH_END_SEC   = 15 * 3600 + 15 * 60  # 54900 — 15:15:00 CT


# ── Parquet cache helpers ─────────────────────────────────────────────────────

def save_scid_cache(ticks: pd.DataFrame, quarters: list[str]) -> None:
    """Write one Parquet file per quarter into the cache directory."""
    SCID_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not ticks.empty:
        yq_int = ticks["DateTime"].dt.year * 10 + ((ticks["DateTime"].dt.month - 1) // 3 + 1)
        for q in quarters:
            yr, qn = int(q[:4]), int(q[5])
            subset = ticks[yq_int == yr * 10 + qn].reset_index(drop=True)
            if not subset.empty:
                subset.to_parquet(SCID_CACHE_DIR / f"{q}.parquet",
                                  index=False, compression="snappy")


def save_last_selection(quarters: list[str]) -> None:
    """Persist the last quarter selection so app startup can auto-reload it."""
    import json
    SCID_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (SCID_CACHE_DIR / "last_selection.json").write_text(
        json.dumps({"quarters": sorted(quarters),
                    "saved_at": pd.Timestamp.now().isoformat(timespec="seconds")})
    )


def list_cached_quarters() -> list[str]:
    """Return sorted list of quarters that have a Parquet file in the cache."""
    if not SCID_CACHE_DIR.exists():
        return []
    return sorted(p.stem for p in SCID_CACHE_DIR.glob("????Q?.parquet"))


def load_quarters_from_cache(quarters: list[str]) -> tuple:
    """Load specific quarters from per-quarter Parquet files.
    Returns (ticks_df, meta) or (None, None) if none are cached.
    Each Parquet is already sorted; loading in quarter order means no global sort needed."""
    cached = set(list_cached_quarters())
    to_load = sorted(q for q in quarters if q in cached)
    if not to_load:
        return None, None
    dfs = [pd.read_parquet(SCID_CACHE_DIR / f"{q}.parquet") for q in to_load]
    ticks = pd.concat(dfs, ignore_index=True)
    meta = {
        "quarters": to_load,
        "n_ticks":  len(ticks),
        "saved_at": pd.Timestamp.now().isoformat(timespec="seconds"),
    }
    return ticks, meta


def build_bars_from_cache(quarters: list[str]) -> pd.DataFrame:
    """Build 5-min bars from cached quarters one at a time — never holds more than
    one quarter of ticks in memory. Use this for large quarter ranges."""
    cached = set(list_cached_quarters())
    bars_list = []
    for q in sorted(quarters):
        if q not in cached:
            continue
        ticks = pd.read_parquet(SCID_CACHE_DIR / f"{q}.parquet")
        if not ticks.empty:
            bars_list.append(resample_ticks_to_bars(ticks))
    if not bars_list:
        return pd.DataFrame(columns=["DateTime", "Open", "High", "Low", "Close", "Volume"])
    return pd.concat(bars_list, ignore_index=True).reset_index(drop=True)


def load_scid_cache() -> tuple:
    """Load the last-selected quarters from per-quarter Parquet cache.
    Falls back to the legacy single-file ticks.parquet if new format not present."""
    import json
    sel_path = SCID_CACHE_DIR / "last_selection.json"
    if sel_path.exists():
        sel = json.loads(sel_path.read_text())
        ticks, meta = load_quarters_from_cache(sel.get("quarters", []))
        if ticks is not None:
            return ticks, meta
    # Legacy fallback — single-file cache written by the old save_scid_cache
    meta_path  = SCID_CACHE_DIR / "meta.json"
    ticks_path = SCID_CACHE_DIR / "ticks.parquet"
    if meta_path.exists() and ticks_path.exists():
        return pd.read_parquet(ticks_path), json.loads(meta_path.read_text())
    return None, None


def clear_scid_cache() -> None:
    """Delete the on-disk Parquet cache."""
    import shutil
    if SCID_CACHE_DIR.exists():
        shutil.rmtree(SCID_CACHE_DIR)


def discover_scid_files() -> list[tuple[str, Path]]:
    """Return sorted (display_name, path) pairs for ES .scid files in SCID_DATA_DIR."""
    if not SCID_DATA_DIR.exists():
        return []
    return sorted(
        [(p.stem, p) for p in SCID_DATA_DIR.glob("ES*.scid")],
        key=lambda x: x[0],
    )


def _scid_sample_quarters(path: Path) -> set[str]:
    """Sample one SCID file and return the set of 'YYYYQN' quarter strings it contains."""
    with open(path, "rb") as f:
        hdr_bytes = f.read(56)
        hdr = struct.unpack_from("<I", hdr_bytes, 4)[0]
        rec = struct.unpack_from("<I", hdr_bytes, 8)[0]
        file_size = f.seek(0, 2)
    total = (file_size - hdr) // rec
    if total == 0:
        return set()

    sample_idx = np.linspace(0, total - 1, min(500, total), dtype=np.int64)
    quarters: set[str] = set()
    with open(path, "rb") as f:
        for idx in sample_idx:
            f.seek(hdr + int(idx) * rec)
            raw = f.read(8)
            if len(raw) < 8:
                continue
            us = struct.unpack_from("<q", raw)[0]
            if us <= 0:
                continue
            ns = _SCID_BASE_NS + us * 1_000
            dt = pd.Timestamp(ns, tz="UTC").tz_convert("America/Chicago").tz_localize(None)
            quarters.add(dt.to_period("Q").strftime("%YQ%q"))
    return quarters


def build_scid_quarter_map() -> dict[str, Path]:
    """Scan all ES SCID files and return a {quarter: path} mapping.
    When a quarter appears in multiple files the later contract takes precedence."""
    q_map: dict[str, Path] = {}
    for _name, path in discover_scid_files():
        for q in _scid_sample_quarters(path):
            q_map[q] = path
    return dict(sorted(q_map.items()))


def load_scid_ticks_chunked(
    path: Path,
    quarters: set[str],
    progress=None,
) -> pd.DataFrame:
    """Read a SCID file from disk in 80 MB chunks.
    Integer UTC pre-filter eliminates ~65% of ETH records before timezone conversion.
    Keeps only RTH ticks whose quarter (YYYYQN) is in `quarters`.
    progress: optional callable(fraction 0-1).
    Returns DataFrame: DateTime (CT, tz-naive), Price, Volume."""
    with open(path, "rb") as f:
        hdr_bytes = f.read(56)
        hdr      = struct.unpack_from("<I", hdr_bytes, 4)[0]
        rec      = struct.unpack_from("<I", hdr_bytes, 8)[0]
        file_size = f.seek(0, 2)

    if rec != 40:
        raise ValueError(f"Unsupported SCID record size {rec}")

    total_recs = (file_size - hdr) // rec
    chunks_out = []
    # Precompute allowed (year*10 + quarter_num) ints for vectorised quarter filter
    allowed_yq = (np.array([int(q[:4]) * 10 + int(q[5]) for q in quarters])
                  if quarters else None)

    with open(path, "rb") as f:
        f.seek(hdr)
        recs_read = 0
        while True:
            raw = f.read(_SCID_CHUNK_RECS * rec)
            if not raw:
                break
            n       = len(raw) // rec
            records = np.frombuffer(raw[: n * rec], dtype=_SCID_DTYPE)

            # drop sentinel/invalid records
            records = records[records["DateTime"] > 0]
            if len(records) == 0:
                recs_read += n
                if progress and total_recs:
                    progress(min(recs_read / total_recs, 0.99))
                continue

            # integer UTC time-of-day pre-filter — no tz conversion, drops ~65% of ETH records
            tod = records["DateTime"] % 86_400_000_000
            records = records[(tod >= _PRE_RTH_START_US) & (tod <= _PRE_RTH_END_US)]
            if len(records) == 0:
                recs_read += n
                if progress and total_recs:
                    progress(min(recs_read / total_recs, 0.99))
                continue

            # timezone conversion only on the surviving ~35%
            dt_ct = _scid_us_to_ct(records["DateTime"])

            # integer RTH check — no strftime, equivalent to >= "08:30:00" and <= "15:15:00"
            ts_sec = (dt_ct.hour.values * 3600
                      + dt_ct.minute.values * 60
                      + dt_ct.second.values)
            rth_mask = (ts_sec >= _RTH_START_SEC) & (ts_sec <= _RTH_END_SEC)

            # vectorised quarter filter
            if allowed_yq is not None:
                yq_int = dt_ct.year.values * 10 + (dt_ct.month.values - 1) // 3 + 1
                keep   = rth_mask & np.isin(yq_int, allowed_yq)
            else:
                keep = rth_mask

            if keep.any():
                chunks_out.append(pd.DataFrame({
                    "DateTime": dt_ct[keep],
                    "Price":    records["Close"][keep].astype("float64"),
                    "Volume":   records["TotalVolume"][keep].astype("int32"),
                }))

            recs_read += n
            if progress and total_recs:
                progress(min(recs_read / total_recs, 0.99))

    if progress:
        progress(1.0)
    if not chunks_out:
        return pd.DataFrame(columns=["DateTime", "Price", "Volume"])
    return (pd.concat(chunks_out, ignore_index=True)
              .sort_values("DateTime")
              .reset_index(drop=True))


def parse_ohlc_from_upload(uploaded_file) -> pd.DataFrame:
    """Parse NT OHLCExporter output — handles two formats:

    CSV:  DateTime,Open,High,Low,Close,Volume
          2025-01-02 08:30:00,6238.50,...
          DateTime is CT bar OPEN time — no shift needed.

    TXT:  DD/MM/YYYY HH:MM:SS;O;H;L;C;V  (no header)
          DateTime is CT or Berlin bar CLOSE time — kept as-is so timestamps
          match what NT charts display (bar close label = Time[0]).
    """
    uploaded_file.seek(0)
    peek = uploaded_file.read(512)
    if isinstance(peek, bytes):
        peek = peek.decode("utf-8", errors="replace")
    uploaded_file.seek(0)

    first_line = peek.splitlines()[0] if peek else ""
    is_csv = "," in first_line and ";" not in first_line

    if is_csv:
        # CSV: has header, comma-separated, DateTime already in CT open time
        df = pd.read_csv(
            uploaded_file,
            skipinitialspace=True,
            dtype=str,
            on_bad_lines="skip",
        )
        df.columns = df.columns.str.strip()
        if "DateTime" not in df.columns:
            raise ValueError("NT CSV is missing a DateTime column.")
        for col in ["Open", "High", "Low", "Close"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["Volume"]  = pd.to_numeric(df.get("Volume", 0), errors="coerce").fillna(0)
        df["NullVol"] = df["Volume"].isna()
        dt_parsed = pd.to_datetime(df["DateTime"], format="%Y-%m-%d %H:%M:%S", errors="coerce")
        if dt_parsed.isna().mean() > 0.5:
            dt_parsed = pd.to_datetime(df["DateTime"], errors="coerce")
        df["DateTime"] = dt_parsed  # already open time — no shift
    else:
        # TXT: no header, semicolon-separated, DateTime is close time
        df = pd.read_csv(
            uploaded_file,
            sep=";",
            header=None,
            names=["DateTime", "Open", "High", "Low", "Close", "Volume"],
            skipinitialspace=True,
            dtype=str,
            on_bad_lines="skip",
        )
        for col in ["Open", "High", "Low", "Close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["Volume"]  = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)
        df["NullVol"] = df["Volume"].isna()

        dt_parsed = pd.to_datetime(df["DateTime"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
        if dt_parsed.isna().mean() > 0.5:
            dt_parsed = pd.to_datetime(df["DateTime"], format="%m/%d/%Y %H:%M:%S", errors="coerce")

        valid_hours = dt_parsed.dropna().dt.hour
        is_berlin = valid_hours.median() > 14 if not valid_hours.empty else False

        if is_berlin:
            df["DateTime"] = (
                dt_parsed
                .dt.tz_localize("Europe/Berlin", ambiguous="infer", nonexistent="shift_forward")
                .dt.tz_convert("America/Chicago")
                .dt.tz_localize(None)
            )
        else:
            df["DateTime"] = dt_parsed

    df = df.dropna(subset=["DateTime", "Open"])
    t = df["DateTime"].dt.time
    if is_csv:
        # CSV has open times: include 08:30, exclude 15:15
        df = df[
            (t >= pd.Timestamp(RTH_START).time()) &
            (t <  pd.Timestamp(RTH_END).time())
        ]
    else:
        # TXT has close times: exclude 08:30 (no partial bar), include 15:15 (last bar)
        df = df[
            (t >  pd.Timestamp(RTH_START).time()) &
            (t <= pd.Timestamp(RTH_END).time())
        ]
    return df[["DateTime", "Open", "High", "Low", "Close", "Volume", "NullVol"]]\
        .sort_values("DateTime").reset_index(drop=True)


def parse_sc_ohlc_from_upload(uploaded_file) -> pd.DataFrame:
    """Parse SC 'Analysis → Export Chart Data' 5M bar CSV.
    Columns: Date (MM/DD/YYYY), Time (HH:MM), Open, High, Low, Close,
             then one of: Volume | UpVolume + DownVolume.
    Timestamps are CT bar OPEN times — no shift needed.
    Returns: DateTime, Open, High, Low, Close, Volume, NullVol"""
    sep = _sc_detect_sep(uploaded_file)
    uploaded_file.seek(0)
    df = pd.read_csv(
        uploaded_file,
        sep=sep,
        skipinitialspace=True,
        dtype=str,
        na_filter=False,
        on_bad_lines="skip",
    )
    df.columns = df.columns.str.strip()

    # SC "Export Chart Data" uses "Last" for the close price
    if "Close" not in df.columns and "Last" in df.columns:
        df = df.rename(columns={"Last": "Close"})

    missing = [c for c in ("Date", "Time", "Open", "High", "Low", "Close") if c not in df.columns]
    if missing:
        raise ValueError(
            f"SC 5M export is missing columns: {missing}. "
            f"Got: {list(df.columns)}. "
            "Export via SC Analysis → Export Chart Data → CSV."
        )

    dt_str = df["Date"].str.strip() + " " + df["Time"].str.strip()
    for fmt in ("%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S",
                "%Y/%m/%d %H:%M", "%Y/%m/%d %H:%M:%S"):
        dt = pd.to_datetime(dt_str, format=fmt, errors="coerce")
        if dt.isna().mean() <= 0.5:
            break
    else:
        dt = pd.to_datetime(dt_str, errors="coerce")
    df["DateTime"] = dt

    for col in ("Open", "High", "Low", "Close"):
        df[col] = pd.to_numeric(df[col].str.strip(), errors="coerce")

    if "Volume" in df.columns:
        df["Volume"] = pd.to_numeric(df["Volume"].str.strip(), errors="coerce").fillna(0)
    elif "UpVolume" in df.columns and "DownVolume" in df.columns:
        df["Volume"] = (
            pd.to_numeric(df["UpVolume"].str.strip(), errors="coerce").fillna(0) +
            pd.to_numeric(df["DownVolume"].str.strip(), errors="coerce").fillna(0)
        )
    else:
        df["Volume"] = 0

    df["NullVol"] = df["Volume"].isna()
    df = df.dropna(subset=["DateTime", "Open"])
    t = df["DateTime"].dt.time
    df = df[
        (t >= pd.Timestamp(RTH_START).time()) &
        (t <  pd.Timestamp(RTH_END).time())
    ]
    return (
        df[["DateTime", "Open", "High", "Low", "Close", "Volume", "NullVol"]]
        .sort_values("DateTime")
        .reset_index(drop=True)
    )


# ── CSV upload Parquet cache ───────────────────────────────────────────────────

CSV_CACHE_DIR = Path(__file__).parent / "data" / "cache"
_CSV_MANIFEST = CSV_CACHE_DIR / "manifest.json"


def _csv_cache_path(prefix: str, name: str, size: int) -> Path:
    CSV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\-.]", "_", name)
    return CSV_CACHE_DIR / f"{prefix}_{safe}_{size}.parquet"


def load_csv_cache(prefix: str, name: str, size: int) -> pd.DataFrame | None:
    p = _csv_cache_path(prefix, name, size)
    return pd.read_parquet(p) if p.exists() else None


def save_csv_cache(df: pd.DataFrame, prefix: str, name: str, size: int) -> None:
    p = _csv_cache_path(prefix, name, size)
    df.to_parquet(p, index=False)


def load_csv_manifest() -> dict:
    import json
    if _CSV_MANIFEST.exists():
        try:
            return json.loads(_CSV_MANIFEST.read_text())
        except Exception:
            pass
    return {}


def save_csv_manifest(manifest: dict) -> None:
    import json
    CSV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _CSV_MANIFEST.write_text(json.dumps(manifest, indent=2))


def clear_csv_cache() -> None:
    import shutil
    if CSV_CACHE_DIR.exists():
        shutil.rmtree(CSV_CACHE_DIR)


# ── Massive.io API ────────────────────────────────────────────────────────────

MASSIVE_BASE_URL  = "https://api.massive.com"  # confirmed from AAPL test
MASSIVE_CACHE_DIR = Path(__file__).parent / "data" / "massive_cache"
_MASSIVE_PAGE_LIMIT = 49_999
_MASSIVE_MONTH_TO_NUM = {"H": 3, "M": 6, "U": 9, "Z": 12}
# Auth: apiKey as query param (confirmed). No Authorization header needed.


def fetch_massive_contract_info(api_key: str, ticker: str) -> dict:
    """Return contract record from Massive Contracts API.
    TODO: confirm futures endpoint path (/futures/v1/ vs /v2/) with live key.
    TODO: confirm 'ticker.any_of' filter param name for futures contracts endpoint.
    """
    import requests
    resp = requests.get(
        f"{MASSIVE_BASE_URL}/futures/v1/contracts",
        params={"ticker.any_of": ticker, "apiKey": api_key},
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        raise ValueError(f"No contract found for ticker '{ticker}'")
    return results[0]


def massive_ticker_to_nt_name(ticker: str, first_trade_date: str) -> str:
    """'ESM6' + '2026-03-17' → 'ES_MAS 06-26'. Uses first_trade_date for unambiguous year."""
    month_num = _MASSIVE_MONTH_TO_NUM[ticker[2]]
    year      = int(first_trade_date[:4])
    return f"ES_MAS {month_num:02d}-{year % 100:02d}"


def fetch_massive_trades(
    api_key: str,
    ticker: str,
    date_start: str,
    date_end: str,
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Fetch RTH tick data from Massive.io Trades API for one ES contract.
    Paginates via next_url cursor. Filters: correction==0, RTH only (08:30–15:15 CT).
    Caches result to Parquet — delete cache file to force re-fetch.
    Returns DataFrame: DateTime (CT, tz-naive), Price (float64), Volume (int64).
    """
    import requests

    MASSIVE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = MASSIVE_CACHE_DIR / f"{ticker}_{date_start}_{date_end}_ticks.parquet"
    if use_cache and cache_path.exists():
        return pd.read_parquet(cache_path)

    url    = f"{MASSIVE_BASE_URL}/futures/v1/trades/{ticker}"
    # TODO: confirm futures trades endpoint path (/futures/v1/ vs /v2/) with live key.
    # TODO: confirm date filter param names for futures trades (session_end_date.gte vs timestamp.gte).
    params = {
        "session_end_date.gte": date_start,
        "session_end_date.lte": date_end,
        "limit":                _MASSIVE_PAGE_LIMIT,
        "sort":                 "asc",   # confirmed from AAPL test
        "apiKey":               api_key, # confirmed: query param, not header
    }

    rows = []
    while url:
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        body = resp.json()
        for t in body.get("results", []):
            if t.get("correction", 0) != 0:
                continue
            rows.append((int(t["timestamp"]), float(t["price"]), int(t["size"])))
        url    = body.get("next_url")
        params = {}  # next_url already encodes all params

    if not rows:
        return pd.DataFrame(columns=["DateTime", "Price", "Volume"])

    raw = pd.DataFrame(rows, columns=["timestamp_ns", "price", "size"])
    raw.sort_values("timestamp_ns", inplace=True, ignore_index=True)

    # Massive timestamps are CT (exchange local time) stored as nanoseconds since
    # Unix epoch — treat as local CT directly, do NOT convert from UTC.
    dt_ct = pd.to_datetime(raw["timestamp_ns"], unit="ns")

    df = pd.DataFrame({"DateTime": dt_ct, "Price": raw["price"], "Volume": raw["size"]})
    t  = df["DateTime"].dt.strftime("%H:%M:%S")
    df = df[(t >= RTH_START) & (t <= RTH_END)].reset_index(drop=True)

    df.to_parquet(cache_path, index=False, compression="snappy")
    return df


def fetch_massive_aggs(
    api_key: str,
    ticker: str,
    date_start: str,
    date_end: str,
    resolution: str = "5min",
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Fetch OHLCV aggregate bars from Massive.io Aggs API.
    Returns RTH bars only: DateTime (CT bar open time, tz-naive), Open, High, Low, Close, Volume.
    """
    import requests

    MASSIVE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = MASSIVE_CACHE_DIR / f"{ticker}_{date_start}_{date_end}_aggs_{resolution}.parquet"
    if use_cache and cache_path.exists():
        return pd.read_parquet(cache_path)

    url    = f"{MASSIVE_BASE_URL}/futures/v1/aggs/{ticker}"
    # TODO: confirm futures aggs endpoint path (/futures/v1/ vs /v2/aggs/ticker/{ticker}/range/5/minute/) with live key.
    # TODO: confirm date filter param names and resolution format for futures aggs.
    # TODO: confirm response field names for futures aggs (may differ from equities o/h/l/c/v/t).
    params = {
        "resolution":       resolution,
        "window_start.gte": date_start,
        "window_start.lte": date_end,
        "limit":            50_000,
        "sort":             "asc",   # confirmed from AAPL test
        "apiKey":           api_key, # confirmed: query param, not header
    }

    rows = []
    while url:
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        body = resp.json()
        for b in body.get("results", []):
            # Field names below are for equities (o/h/l/c/v/t confirmed from AAPL test).
            # Futures may use window_start/open/high/low/close/volume — update after first live call.
            rows.append({
                "DateTime": b.get("t") or b.get("window_start"),
                "Open":     float(b.get("o") or b.get("open")),
                "High":     float(b.get("h") or b.get("high")),
                "Low":      float(b.get("l") or b.get("low")),
                "Close":    float(b.get("c") or b.get("close")),
                "Volume":   int(b.get("v") or b.get("volume")),
            })
        url    = body.get("next_url")
        params = {}

    if not rows:
        return pd.DataFrame(columns=["DateTime", "Open", "High", "Low", "Close", "Volume"])

    df = pd.DataFrame(rows)

    # Timestamp: equities confirmed as Unix milliseconds (t field).
    # Futures may use ISO string (window_start) — handle both.
    if pd.api.types.is_integer_dtype(df["DateTime"]):
        dt = (pd.to_datetime(df["DateTime"], unit="ms", utc=True)
                .dt.tz_convert("America/Chicago")
                .dt.tz_localize(None))
    else:
        dt = pd.to_datetime(df["DateTime"], errors="coerce")
        if dt.dt.tz is not None:
            dt = dt.dt.tz_convert("America/Chicago").dt.tz_localize(None)

    df["DateTime"] = dt
    df = df.sort_values("DateTime").reset_index(drop=True)

    t  = df["DateTime"].dt.strftime("%H:%M:%S")
    df = df[(t >= RTH_START) & (t < RTH_END)].reset_index(drop=True)

    df.to_parquet(cache_path, index=False, compression="snappy")
    return df


@st.cache_data(show_spinner=False)
def get_market_holidays(start: str, end: str) -> set:
    """Return set of date strings ('YYYY-MM-DD') that are NYSE holidays."""
    nyse = xcals.get_calendar("XNYS")
    dates = nyse.regular_holidays.holidays(start, end)
    return set(dates.strftime("%Y-%m-%d"))


@st.cache_data(show_spinner="Loading NT bar data…")
def load_nt_bars(nt_file_path: str = str(NT_FILE)) -> pd.DataFrame:
    rows = []
    with open(nt_file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or not line[0].isdigit():
                continue
            parts = line.split(";")
            if len(parts) == 6:
                rows.append(parts)

    df = pd.DataFrame(rows, columns=["DateTime", "Open", "High", "Low", "Close", "Volume"])
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Berlin close times → Chicago open times
    # CEST (UTC+2) → CDT (UTC-5) = −7 h, then −5 min close→open
    df["DateTime"] = (
        pd.to_datetime(df["DateTime"], format="%d/%m/%Y %H:%M:%S")
        .dt.tz_localize("Europe/Berlin")
        .dt.tz_convert("America/Chicago")
        .dt.tz_localize(None)
        - pd.Timedelta(minutes=5)
    )
    df["NullVol"] = df["Volume"].isna()
    df["Volume"]  = df["Volume"].fillna(0)
    t = df["DateTime"].dt.time
    df = df[
        (t >= pd.Timestamp(RTH_START).time()) &
        (t <  pd.Timestamp(RTH_END).time())
    ]
    return df.sort_values("DateTime").reset_index(drop=True)
