from pathlib import Path
import pandas as pd
import streamlit as st

DATA_DIR  = Path(__file__).parent / "data" / "raw"
SC_FILE   = DATA_DIR / "ESM6.CME_BarData.txt"
NT_FILE   = DATA_DIR / "NinjaScript Output 03_06_2026 23_08.txt"

RTH_START = "08:30:00"
RTH_END   = "15:15:00"
TICK_SIZE = 0.25


@st.cache_data(show_spinner="Loading SC tick data — first run takes a few minutes…")
def load_sc_bars() -> pd.DataFrame:
    chunks = []
    for chunk in pd.read_csv(
        SC_FILE,
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


@st.cache_data(show_spinner="Loading NT bar data…")
def load_nt_bars() -> pd.DataFrame:
    df = pd.read_csv(
        NT_FILE,
        sep=";",
        header=None,
        names=["DateTime", "Open", "High", "Low", "Close", "Volume"],
        dtype={"Open": float, "High": float, "Low": float, "Close": float, "Volume": float},
    )
    # Berlin close times → Chicago open times
    # CEST (UTC+2) → CDT (UTC-5) = −7 h, then −5 min close→open
    df["DateTime"] = (
        pd.to_datetime(df["DateTime"], format="%d/%m/%Y %H:%M:%S")
        .dt.tz_localize("Europe/Berlin")
        .dt.tz_convert("America/Chicago")
        .dt.tz_localize(None)
        - pd.Timedelta(minutes=5)
    )
    df = df.dropna(subset=["Open"])  # rows with no price are unusable
    df["NullVol"] = df["Volume"].isna()
    df["Volume"]  = df["Volume"].fillna(0)
    t = df["DateTime"].dt.time
    df = df[
        (t >= pd.Timestamp(RTH_START).time()) &
        (t <  pd.Timestamp(RTH_END).time())
    ]
    return df.sort_values("DateTime").reset_index(drop=True)
