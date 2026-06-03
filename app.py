import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path

st.set_page_config(
    page_title="ESM6 5-Min RTH Bars",
    page_icon="📈",
    layout="wide",
)

DATA_FILE = Path(__file__).parent / "data/raw/ESM6.CME_BarData.txt"

RTH_START = "08:30:00"
RTH_END = "15:15:00"

# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(show_spinner="Loading tick data — first run takes a few minutes…")
def load_bars() -> pd.DataFrame:
    """
    Read raw tick file in chunks, filter to RTH, resample to 5-minute OHLCV bars.
    Cached after first run so subsequent page interactions are instant.
    """
    chunks = []
    chunk_iter = pd.read_csv(
        DATA_FILE,
        skipinitialspace=True,
        usecols=["Date", "Time", "Last", "Volume"],
        chunksize=500_000,
        dtype={"Date": str, "Time": str, "Last": float, "Volume": "int32"},
    )
    for chunk in chunk_iter:
        # Fast string filter before any datetime parsing
        mask = (chunk["Time"] >= RTH_START) & (chunk["Time"] < RTH_END)
        chunk = chunk.loc[mask]
        if chunk.empty:
            continue
        chunk = chunk.copy()
        chunk["datetime"] = pd.to_datetime(
            chunk["Date"] + " " + chunk["Time"],
            format="mixed",
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

    # Drop any bins that spilled outside RTH (can happen at boundary)
    bars = bars[
        (bars.index.time >= pd.Timestamp(RTH_START).time())
        & (bars.index.time < pd.Timestamp(RTH_END).time())
    ]
    return bars.reset_index().rename(columns={"datetime": "DateTime"})


# ── Chart builder ─────────────────────────────────────────────────────────────

def make_candlestick(df: pd.DataFrame, date_str: str) -> go.Figure:
    colors = dict(increasing_line_color="#26a69a", decreasing_line_color="#ef5350")
    fig = go.Figure(
        go.Candlestick(
            x=df["DateTime"],
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="ESM6",
            **colors,
        )
    )
    fig.update_layout(
        title=f"ESM6 — 5-Min RTH Bars  ({date_str})",
        xaxis_title="Time (CT)",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        xaxis=dict(
            tickformat="%H:%M",
            dtick=15 * 60 * 1000,
            tickangle=-45,
        ),
        yaxis=dict(autorange=True),
        height=520,
        margin=dict(l=50, r=20, t=60, b=60),
        template="plotly_white",
    )
    return fig


# ── Main layout ───────────────────────────────────────────────────────────────

def main():
    st.title("ESM6 CME Futures — 5-Minute RTH Bars")
    st.caption("Regular Trading Hours 08:30 – 15:15 CT  |  5-minute bars  |  All times Central")

    if not DATA_FILE.exists():
        st.error(f"Data file not found: `{DATA_FILE}`")
        st.stop()

    bars = load_bars()
    bars["Date"] = bars["DateTime"].dt.date
    dates = sorted(bars["Date"].unique())

    with st.sidebar:
        st.header("Filters")
        selected_date = st.selectbox(
            "Trading Date",
            options=dates,
            index=len(dates) - 1,
            format_func=lambda d: d.strftime("%A %b %d, %Y"),
        )

    day = bars[bars["Date"] == selected_date].drop(columns="Date").reset_index(drop=True)

    if day.empty:
        st.warning("No RTH data found for this date.")
        return

    # Summary metrics row
    day_open = day.iloc[0]["Open"]
    day_close = day.iloc[-1]["Close"]
    day_high = day["High"].max()
    day_low = day["Low"].min()
    day_vol = day["Volume"].sum()
    chg = day_close - day_open
    chg_pct = chg / day_open * 100

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Open", f"{day_open:.2f}")
    m2.metric("High", f"{day_high:.2f}")
    m3.metric("Low", f"{day_low:.2f}")
    m4.metric("Close", f"{day_close:.2f}")
    m5.metric("Change", f"{chg:+.2f}", f"{chg_pct:+.2f}%")
    m6.metric("Total Volume", f"{day_vol:,.0f}")

    # Candlestick chart
    date_str = selected_date.strftime("%B %d, %Y")
    st.plotly_chart(make_candlestick(day, date_str), use_container_width=True)

    # Bar table
    st.subheader("5-Minute Bar Table")
    display = day.copy()
    display["Time"] = display["DateTime"].dt.strftime("%H:%M")
    display = display[["Time", "Open", "High", "Low", "Close", "Volume"]]
    st.dataframe(
        display.style.format({
            "Open": "{:.2f}",
            "High": "{:.2f}",
            "Low": "{:.2f}",
            "Close": "{:.2f}",
            "Volume": "{:,.0f}",
        }),
        use_container_width=True,
        hide_index=True,
        height=min(35 * len(display) + 38, 600),
    )


main()
