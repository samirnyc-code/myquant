import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from data_loader import load_sc_bars, SC_FILE
import validation

st.set_page_config(
    page_title="ESM6 5-Min RTH Bars",
    page_icon="📈",
    layout="wide",
)


# ── Chart builder ─────────────────────────────────────────────────────────────

def make_candlestick(df: pd.DataFrame, date_str: str, show_bar_nums: bool = False) -> go.Figure:
    fig = go.Figure(
        go.Candlestick(
            x=df["DateTime"],
            open=df["Open"],
            high=df["High"],
            low=df["Low"],
            close=df["Close"],
            name="ESM6",
            increasing_line_color="#26a69a",
            decreasing_line_color="#ef5350",
        )
    )
    bottom_margin = 90 if show_bar_nums else 60
    fig.update_layout(
        title=f"ESM6 — 5-Min RTH Bars  ({date_str})",
        xaxis_title="Time (CT)",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
        xaxis=dict(tickformat="%H:%M", dtick=15 * 60 * 1000, tickangle=-45),
        yaxis=dict(autorange=True),
        height=520,
        margin=dict(l=50, r=20, t=60, b=bottom_margin),
        template="plotly_white",
    )
    if show_bar_nums:
        for i in range(0, len(df), 3):
            fig.add_annotation(
                x=df.iloc[i]["DateTime"], xref="x",
                y=0, yref="paper", yshift=-48,
                text=str(i + 1),
                showarrow=False,
                font=dict(size=8, color="#999"),
                xanchor="center",
            )
    return fig


# ── Bar Viewer tab ────────────────────────────────────────────────────────────

def show_bar_viewer():
    bars = load_sc_bars()
    bars["Date"] = bars["DateTime"].dt.date
    dates = sorted(bars["Date"].unique())

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

    day_open  = day.iloc[0]["Open"]
    day_close = day.iloc[-1]["Close"]
    day_high  = day["High"].max()
    day_low   = day["Low"].min()
    day_vol   = day["Volume"].sum()
    chg       = day_close - day_open
    chg_pct   = chg / day_open * 100

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Open",         f"{day_open:.2f}")
    m2.metric("High",         f"{day_high:.2f}")
    m3.metric("Low",          f"{day_low:.2f}")
    m4.metric("Close",        f"{day_close:.2f}")
    m5.metric("Change",       f"{chg:+.2f}", f"{chg_pct:+.2f}%")
    m6.metric("Total Volume", f"{day_vol:,.0f}")

    show_bar_nums = st.checkbox("Show bar numbers", value=False,
                                help="Labels every 3rd bar (1, 4, 7…) below the x-axis.")
    st.plotly_chart(
        make_candlestick(day, selected_date.strftime("%B %d, %Y"), show_bar_nums=show_bar_nums),
        use_container_width=True,
    )

    st.subheader("5-Minute Bar Table")
    display = day.copy()
    display["Time"] = display["DateTime"].dt.strftime("%H:%M")
    display = display[["Time", "Open", "High", "Low", "Close", "Volume"]]
    st.dataframe(
        display.style.format({
            "Open": "{:.2f}", "High": "{:.2f}",
            "Low":  "{:.2f}", "Close": "{:.2f}",
            "Volume": "{:,.0f}",
        }),
        use_container_width=True,
        hide_index=True,
        height=min(35 * len(display) + 38, 600),
    )


# ── App entry point ───────────────────────────────────────────────────────────

def main():
    st.title("ESM6 CME Futures — 5-Minute RTH Bars")
    st.caption("Regular Trading Hours 08:30 – 15:15 CT  |  5-minute bars  |  All times Central")

    with st.sidebar:
        st.markdown("---")
        if st.button("🔄 Reload Data", help="Clears all cached data and reloads from disk. Use after updating data files."):
            st.cache_data.clear()
            st.rerun()

    if not SC_FILE.exists():
        st.error(f"SC data file not found: `{SC_FILE}`")
        st.stop()

    tab1, tab2 = st.tabs(["📊 Bar Viewer", "🔍 Bar Validation"])

    with tab1:
        show_bar_viewer()

    with tab2:
        validation.show_validation_tab()


main()
