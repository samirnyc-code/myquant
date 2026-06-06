from pathlib import Path
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


def parse_nt_ticks_from_upload(uploaded_file) -> pd.DataFrame:
    """Parse NT8 tick export: YYYYMMDD HHMMSS SUBSEC100NS;Price;Bid;Ask;Volume
    No header row. SUBSEC is in 100-nanosecond units.
    RTH ticks only (08:30–15:15 CT). Returns DataFrame: DateTime, Price, Volume."""
    uploaded_file.seek(0)
    chunks = []
    # Use C engine with semicolon — first column is "YYYYMMDD HHMMSS SUBSEC" (space-joined)
    for chunk in pd.read_csv(
        uploaded_file,
        sep=";",
        header=None,
        names=["ts", "price", "bid", "ask", "volume"],
        dtype=str,
        na_filter=False,
        chunksize=500_000,
        on_bad_lines="skip",
    ):
        # Split "YYYYMMDD HHMMSS SUBSEC" on whitespace
        ts_parts = chunk["ts"].str.strip().str.split(expand=True)
        if ts_parts.shape[1] < 3:
            continue
        time_s = ts_parts[1]
        # RTH filter using HHMMSS string comparison
        rth_start_s = RTH_START.replace(":", "")   # "083000"
        rth_end_s   = RTH_END.replace(":", "")     # "151500"
        mask = (time_s >= rth_start_s) & (time_s <= rth_end_s)
        if not mask.any():
            continue
        date_s   = ts_parts[0][mask]
        time_s   = time_s[mask]
        subsec   = ts_parts[2][mask]
        base_dt  = pd.to_datetime(date_s + time_s, format="%Y%m%d%H%M%S", errors="coerce")
        subsec_ns = pd.to_numeric(subsec, errors="coerce").fillna(0) * 100
        dt = base_dt + pd.to_timedelta(subsec_ns, unit="ns")
        price  = pd.to_numeric(chunk["price"][mask],  errors="coerce")
        volume = pd.to_numeric(chunk["volume"][mask], errors="coerce").fillna(0).astype("int32")
        chunks.append(pd.DataFrame({"DateTime": dt.values, "Price": price.values, "Volume": volume.values}))
    if not chunks:
        return pd.DataFrame(columns=["DateTime", "Price", "Volume"])
    return (pd.concat(chunks, ignore_index=True)
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


def parse_ohlc_from_upload(uploaded_file) -> pd.DataFrame:
    """Parse bar_export OHLC file: DD/MM/YYYY HH:MM:SS;O;H;L;C;V (same layout as NT file on disk).
    Timestamps are Berlin close times → converted to CT open times (−7h −5min).
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

    # Try DD/MM/YYYY first (NinjaScript Output format); fall back to MM/DD/YYYY
    dt_parsed = pd.to_datetime(df["DateTime"], format="%d/%m/%Y %H:%M:%S", errors="coerce")
    if dt_parsed.isna().mean() > 0.5:
        dt_parsed = pd.to_datetime(df["DateTime"], format="%m/%d/%Y %H:%M:%S", errors="coerce")

    df["DateTime"] = (
        dt_parsed
        .dt.tz_localize("Europe/Berlin")
        .dt.tz_convert("America/Chicago")
        .dt.tz_localize(None)
        - pd.Timedelta(minutes=5)
    )
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
