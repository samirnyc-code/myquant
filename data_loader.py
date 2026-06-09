from pathlib import Path
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

_SCID_CHUNK_RECS = 262_144  # ~10 MB per chunk (262144 * 40 bytes)


# ── Parquet cache helpers ─────────────────────────────────────────────────────

def save_scid_cache(ticks: pd.DataFrame, quarters: list[str]) -> None:
    """Persist ticks to Parquet so the next app start loads instantly."""
    import json
    SCID_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ticks.to_parquet(SCID_CACHE_DIR / "ticks.parquet", index=False, compression="snappy")
    meta = {
        "quarters": sorted(quarters),
        "n_ticks":  len(ticks),
        "saved_at": pd.Timestamp.now().isoformat(timespec="seconds"),
    }
    (SCID_CACHE_DIR / "meta.json").write_text(json.dumps(meta))


def load_scid_cache() -> tuple:
    """Load cached ticks from Parquet. Returns (ticks_df, meta_dict) or (None, None)."""
    import json
    meta_path  = SCID_CACHE_DIR / "meta.json"
    ticks_path = SCID_CACHE_DIR / "ticks.parquet"
    if not meta_path.exists() or not ticks_path.exists():
        return None, None
    meta  = json.loads(meta_path.read_text())
    ticks = pd.read_parquet(ticks_path)
    return ticks, meta


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
    """Read a SCID file from disk in ~10 MB chunks.
    Keeps only RTH ticks whose quarter (YYYYQN) is in `quarters`.
    progress: optional callable(fraction 0-1).
    Returns DataFrame: DateTime (CT, tz-naive), Price, Volume."""
    with open(path, "rb") as f:
        hdr_bytes = f.read(56)
        hdr = struct.unpack_from("<I", hdr_bytes, 4)[0]
        rec = struct.unpack_from("<I", hdr_bytes, 8)[0]
        file_size = f.seek(0, 2)

    if rec != 40:
        raise ValueError(f"Unsupported SCID record size {rec}")

    total_recs = (file_size - hdr) // rec
    chunks_out = []

    with open(path, "rb") as f:
        f.seek(hdr)
        recs_read = 0
        while True:
            raw = f.read(_SCID_CHUNK_RECS * rec)
            if not raw:
                break
            n = len(raw) // rec
            records = np.frombuffer(raw[: n * rec], dtype=_SCID_DTYPE)
            valid = records["DateTime"] > 0
            records = records[valid]
            if len(records) == 0:
                recs_read += n
                if progress and total_recs:
                    progress(min(recs_read / total_recs, 0.99))
                continue

            dt_ct = _scid_us_to_ct(records["DateTime"])
            t_str = dt_ct.strftime("%H:%M:%S")
            q_str = pd.PeriodIndex(dt_ct, freq="Q").strftime("%YQ%q")

            rth_mask = (t_str >= RTH_START) & (t_str <= RTH_END)
            q_mask   = np.isin(q_str, list(quarters))
            keep     = rth_mask & q_mask

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
    """Parse NT8 bar_export OHLC file: DD/MM/YYYY HH:MM:SS;O;H;L;C;V
    Timestamps are CT bar CLOSE times → subtract 5 min → CT bar OPEN times.
    Non-data rows (dashes, headers) are silently dropped."""
    uploaded_file.seek(0)
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
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)
    df["NullVol"] = df["Volume"].isna()

    # Try DD/MM/YYYY first; fall back to MM/DD/YYYY
    dt_parsed = pd.to_datetime(df["DateTime"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    if dt_parsed.isna().mean() > 0.5:
        dt_parsed = pd.to_datetime(df["DateTime"], format="%m/%d/%Y %H:%M:%S", errors="coerce")

    # Auto-detect timezone format from median hour of valid rows:
    # CT close times cluster around 08:35–15:15 (median ≈ 11–12)
    # Berlin close times cluster around 15:35–22:15 (median ≈ 18–19)
    valid_hours = dt_parsed.dropna().dt.hour
    is_berlin = valid_hours.median() > 14 if not valid_hours.empty else False

    if is_berlin:
        df["DateTime"] = (
            dt_parsed
            .dt.tz_localize("Europe/Berlin")
            .dt.tz_convert("America/Chicago")
            .dt.tz_localize(None)
            - pd.Timedelta(minutes=5)
        )
    else:
        # CT close times — just subtract 5 min to get open times
        df["DateTime"] = dt_parsed - pd.Timedelta(minutes=5)

    df = df.dropna(subset=["DateTime", "Open"])
    t = df["DateTime"].dt.time
    df = df[
        (t >= pd.Timestamp(RTH_START).time()) &
        (t <  pd.Timestamp(RTH_END).time())
    ]
    return df.sort_values("DateTime").reset_index(drop=True)


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
