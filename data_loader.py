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
