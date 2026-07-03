import re
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.graph_objects as go
from data_loader import (CONTRACTS, bar_num_from_dt,
                         parse_ohlc_from_upload,
                         load_csv_cache, save_csv_cache,
                         load_csv_manifest, save_csv_manifest, clear_csv_cache,
                         apply_data_slot,
                         load_excluded_dates, save_excluded_dates)
import bar_analysis
import ama_setups
import portfolio
import massive
import validation
import wfa as wfa_mod
import continuous_chart
import extras
import prop_sim
import auction_tab
import er_lookahead_tab
import qs_tab
import leg_labeler_tab
import ui_controls as controls

# ── Global display rule for st.dataframe (DISPLAY only — calc precision intact) ─
# One wrapper instead of editing ~35 call sites (and it catches future ones).
# Money/PnL columns → whole dollars (0 dp); ratios/percentages/everything else
# → max 2 dp. Uses Streamlit column_config for plain DataFrames (cheap, no Styler
# overhead on big trade-log tables) and Styler.format for already-styled tables.
# Columns that genuinely need 3 dp (R-grid values like 0.625) are passed as
# pre-formatted strings at their call site, so they're object dtype and untouched.
import re as _re
from pandas.io.formats.style import Styler as _Styler

_ORIG_DATAFRAME = st.dataframe
_MONEY_RE = _re.compile(r'(\$|net|gross|pnl|p&l|profit|loss|slippage|commission|dollar|cost|equity|drawdown|\bdd\b|margin)', _re.I)
_RATIO_RE = _re.compile(r'(/|ratio|factor|\bpf\b|prom|wfe|pct|%|kurt|sqn|win|\br\b)', _re.I)


def _col_dp(name) -> int:
    """0 dp for money/PnL columns, 2 dp for ratios/percentages/everything else."""
    n = str(name)
    if _RATIO_RE.search(n):
        return 2
    if _MONEY_RE.search(n):
        return 0
    return 2


def _dataframe_2dp(data=None, *args, **kwargs):
    try:
        if isinstance(data, _Styler):
            fmt = {c: ("{:,.0f}" if _col_dp(c) == 0 else "{:.2f}")
                   for c in data.data.select_dtypes(include="floating").columns}
            if fmt:
                data = data.format(fmt, na_rep="—")
        elif isinstance(data, pd.DataFrame):
            cfg = dict(kwargs.get("column_config") or {})
            for c in data.select_dtypes(include="floating").columns:
                if c in cfg:
                    continue
                cfg[c] = st.column_config.NumberColumn(
                    format="%.0f" if _col_dp(c) == 0 else "%.2f")
            if cfg:
                kwargs["column_config"] = cfg
    except Exception:
        pass
    return _ORIG_DATAFRAME(data, *args, **kwargs)


st.dataframe = _dataframe_2dp

st.set_page_config(
    page_title="ES Futures — 5-Min RTH Bars",
    page_icon="📈",
    layout="wide",
)
st.markdown("""
<style>
    .block-container { padding-top: 1.5rem; padding-bottom: 1rem; }
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
    [data-testid="stMetricValue"] { font-size: 1.5rem !important; }
    [data-testid="stMetricLabel"] { font-size: 0.72rem !important; }
</style>
""", unsafe_allow_html=True)


# ── Data slot helper ──────────────────────────────────────────────────────────

_apply_data_slot = apply_data_slot  # alias — shared implementation lives in data_loader.py


# ── Chart builder ─────────────────────────────────────────────────────────────

def make_candlestick(df: pd.DataFrame, date_str: str,
                     show_bar_nums: bool = False,
                     show_volume: bool = False,
                     excl_first_n: int = 0, excl_last_min: int = 0,
                     contract: str = "ES",
                     signals: "pd.DataFrame | None" = None,
                     show_trades: bool = True,
                     ama_detected: "pd.DataFrame | None" = None) -> go.Figure:
    # NT8 neutral: white body + black border/wicks (bull), solid black (bear)
    candle = go.Candlestick(
        x=df["DateTime"],
        open=df["Open"], high=df["High"],
        low=df["Low"],   close=df["Close"],
        name=contract,
        increasing=dict(line=dict(color="#000000", width=1), fillcolor="#FFFFFF"),
        decreasing=dict(line=dict(color="#000000", width=1), fillcolor="#000000"),
        showlegend=False,
    )

    if show_volume:
        from plotly.subplots import make_subplots
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            row_heights=[0.75, 0.25],
            vertical_spacing=0.02,
        )
        fig.add_trace(candle, row=1, col=1)
        vol_colors = [
            "#26a69a" if c >= o else "#ef5350"
            for o, c in zip(df["Open"], df["Close"])
        ]
        fig.add_trace(
            go.Bar(x=df["DateTime"], y=df["Volume"],
                   marker_color=vol_colors, showlegend=False, name="Volume"),
            row=2, col=1,
        )
        fig.update_layout(
            title=f"{contract} — 5-Min RTH Bars  ({date_str})",
            xaxis_rangeslider_visible=False,
            xaxis2=dict(tickformat="%H:%M", dtick=15 * 60 * 1000, tickangle=-45),
            yaxis=dict(autorange=True, title="Price"),
            yaxis2=dict(tickformat=",d", title="Vol"),
            height=640,
            margin=dict(l=50, r=20, t=60, b=60),
            template="plotly_dark",
            plot_bgcolor="#9E9E9E",
            paper_bgcolor="#9E9E9E",
        )
    else:
        fig = go.Figure(candle)
        fig.update_layout(
            title=f"{contract} — 5-Min RTH Bars  ({date_str})",
            xaxis_title="Time (CT)",
            yaxis_title="Price",
            xaxis_rangeslider_visible=False,
            xaxis=dict(tickformat="%H:%M", dtick=15 * 60 * 1000, tickangle=-45),
            yaxis=dict(autorange=True),
            height=520,
            margin=dict(l=50, r=20, t=60, b=60),
            template="plotly_dark",
            plot_bgcolor="#9E9E9E",
            paper_bgcolor="#9E9E9E",
        )

    half  = pd.Timedelta(minutes=2, seconds=30)
    shade = dict(fillcolor="rgba(180,180,180,0.15)", line_width=0, layer="below")
    if excl_first_n > 0 and excl_first_n <= len(df):
        fig.add_vrect(x0=df.iloc[0]["DateTime"] - half,
                      x1=df.iloc[min(excl_first_n, len(df)) - 1]["DateTime"] + half, **shade)
    if excl_last_min > 0:
        cutoff_total = 15 * 60 + 15 - excl_last_min
        cutoff_str   = f"{cutoff_total // 60:02d}:{cutoff_total % 60:02d}"
        cutoff_bars  = df[df["DateTime"].dt.strftime("%H:%M") >= cutoff_str]
        if not cutoff_bars.empty:
            fig.add_vrect(x0=cutoff_bars.iloc[0]["DateTime"] - half,
                          x1=df.iloc[-1]["DateTime"] + half, **shade)
    if show_bar_nums:
        labeled = sorted(set(range(0, len(df), 3)) | {len(df) - 1})
        for i in labeled:
            fig.add_annotation(
                x=df.iloc[i]["DateTime"], xref="x",
                y=df.iloc[i]["Low"], yref="y",
                yshift=-6,
                text=str(bar_num_from_dt(df.iloc[i]["DateTime"])),
                showarrow=False,
                font=dict(size=12),
                xanchor="center",
                yanchor="top",
            )

    _has_sigs = signals is not None and not signals.empty
    _has_ama  = ama_detected is not None and not ama_detected.empty

    if _has_sigs or _has_ama:
        bar_hi = df.set_index("DateTime")["High"]
        bar_lo = df.set_index("DateTime")["Low"]
        bar_cl = df.set_index("DateTime")["Close"]
        offset = df["High"].max() * 0.0003
        row_kw = {"row": 1, "col": 1} if show_volume else {}

        df_day = df.copy()
        df_day["DateTime"] = pd.to_datetime(df_day["DateTime"])
        df_day = df_day.sort_values("DateTime").reset_index(drop=True)

        wins = losses = i1r_total = 0
        net_pts = 0.0
        type_stats: dict = {}

        # (fill_color, line_color) → set of bar DateTimes
        _bar_paints: dict[tuple, set] = {}

        def _paint(fill: str, line: str, dt) -> None:
            _bar_paints.setdefault((fill, line), set()).add(pd.Timestamp(dt))

        # --- AMA bar painting from raw detected — exact NT8 match ---
        # Paint every bar whose Signal != 0, applying FT override exactly as NT8
        # (NT8 line 1385: FT color is suppressed when abs(Signal) == 5 BigBO).
        if _has_ama:
            for _, _det in ama_detected.iterrows():
                _sig = int(_det["Signal"])
                _ft  = int(_det["FTflag"])
                if _sig == 0:
                    continue
                _dt   = pd.to_datetime(_det["DateTime"])
                _long = _sig > 0
                _abs  = abs(_sig)
                _ft_c = "#00FFFF" if _long else "#DC143C"   # Cyan / Crimson
                _bo_c = "#1E90FF" if _long else "#8B0000"   # DodgerBlue / DarkRed
                _ob_c = "#008000" if _long else "#FF8C00"   # Green / DarkOrange
                if _ft != 0 and _abs != 5:
                    # FT bar (not BigBO): Cyan / Crimson
                    _paint(_ft_c, _ft_c, _dt)
                elif _abs == 5:
                    # BigBO: Plum fill + direction-colored outline
                    _paint("#DDA0DD", _bo_c, _dt)
                elif _abs == 4:
                    # Doji OB: Magenta
                    _paint("#FF00FF", "#FF00FF", _dt)
                elif _abs == 3:
                    # OB: Green (bull) / DarkOrange (bear)
                    _paint(_ob_c, _ob_c, _dt)
                elif _abs == 2:
                    # CX: DarkOrchid fill + direction-colored outline
                    _paint("#9932CC", _bo_c, _dt)
                else:
                    # BO (abs == 1): DodgerBlue / DarkRed
                    _paint(_bo_c, _bo_c, _dt)

        if _has_sigs:
          for _, s in signals.iterrows():
            sig_dt      = pd.to_datetime(s["SignalDateTime"])
            bo_start    = sig_dt - pd.Timedelta(minutes=5)
            setup_end   = sig_dt + pd.Timedelta(minutes=5)
            entry_dt    = setup_end
            is_long     = s["Direction"] == "Long"
            is_cx       = s["SignalType"] == "CX"
            is_bigbo    = s["SignalType"] == "BigBO"
            is_ob       = s["SignalType"] in ("OB", "OB_Doji", "OB+FT")
            stype       = s["SignalType"]
            stop_px     = s["StopPrice"]
            tgt_px      = (s["SignalPrice"] + s["TargetPoints"] if is_long
                           else s["SignalPrice"] - s["TargetPoints"])
            target_mode = s.get("TargetMode", "BarRange")

            # Hover data (used in the colored candlestick customdata)
            ft_hi  = bar_hi.get(sig_dt, float("nan"))
            ft_lo  = bar_lo.get(sig_dt, float("nan"))
            ft_cl  = bar_cl.get(sig_dt, float("nan"))
            ft_ibs = round((ft_cl - ft_lo) / (ft_hi - ft_lo) * 100) if (ft_hi - ft_lo) > 0 else 0
            pr_hi  = bar_hi.get(bo_start, float("nan"))
            pr_lo  = bar_lo.get(bo_start, float("nan"))
            ft_zscore = s.get("ZScore", float("nan"))
            z_str     = f"{ft_zscore:.2f}" if not pd.isna(ft_zscore) else "n/a"

            # Build hover text for this signal bar
            if is_cx:
                if is_long:
                    bo_up = ft_hi - pr_hi
                    bo_dn = ft_lo - pr_lo
                    cx_ratio = bo_up / max(bo_dn, 0.01)
                    _hover = (f"CX Long  HH:{bo_up:.2f} LL:{bo_dn:.2f}  ratio:{cx_ratio:.1f}x  IBS:{ft_ibs}")
                else:
                    bo_dn = pr_lo - ft_lo
                    bo_up = ft_hi - pr_hi
                    _hover = (f"CX Short  LL:{bo_dn:.2f} HH:{bo_up:+.2f}  pure bear  IBS:{ft_ibs}")
            elif is_bigbo:
                _hover = f"Big {'Long' if is_long else 'Short'}  Z:{z_str}  IBS:{ft_ibs}"
            else:
                _hover = (f"{stype} {s['Direction']}<br>"
                          f"Entry:{s['SignalPrice']:.2f}  Stop:{stop_px:.2f}  Tgt:+{s['TargetPoints']:.2f}<br>"
                          f"IBS:{ft_ibs}  Z:{z_str}")

            # Invisible scatter for custom hover on signal bar
            fig.add_trace(go.Scatter(
                x=[sig_dt], y=[(ft_hi + ft_lo) / 2],
                mode="markers", marker=dict(size=1, opacity=0),
                hovertext=[_hover], hoverinfo="text", showlegend=False,
            ), **row_kw)

            if not show_trades:
                continue

            # Walk forward from entry bar to find exit (stop or target hit)
            fwd = df_day[df_day["DateTime"] >= entry_dt].reset_index(drop=True)
            entry_px = fwd.iloc[0]["Open"] if not fwd.empty else s["SignalPrice"]
            exit_dt = exit_px = result = None

            for _, bar in fwd.iterrows():
                hit_tgt  = bar["High"] >= tgt_px  if is_long else bar["Low"]  <= tgt_px
                hit_stop = bar["Low"]  <= stop_px if is_long else bar["High"] >= stop_px
                if hit_stop and hit_tgt:
                    exit_dt = bar["DateTime"]
                    exit_px = stop_px
                    result  = stop_px - entry_px if is_long else entry_px - stop_px
                    break
                elif hit_tgt:
                    exit_dt = bar["DateTime"]
                    exit_px = tgt_px
                    result  = tgt_px - entry_px if is_long else entry_px - tgt_px
                    break
                elif hit_stop:
                    exit_dt = bar["DateTime"]
                    exit_px = stop_px
                    result  = stop_px - entry_px if is_long else entry_px - stop_px
                    break

            if exit_dt is None and not fwd.empty:
                last    = fwd.iloc[-1]
                exit_dt = last["DateTime"]
                exit_px = last["Close"]
                result  = (exit_px - entry_px) if is_long else (entry_px - exit_px)
            elif exit_dt is None:
                exit_dt = sig_dt + pd.Timedelta(minutes=10)
                exit_px = s["SignalPrice"]
                result  = 0.0

            # Stop line (red): BO bar → exit bar
            fig.add_shape(type="line",
                x0=bo_start, x1=exit_dt,
                y0=stop_px, y1=stop_px,
                line=dict(color="#DC143C", width=1.5, dash="dot"),
                opacity=0.7, **row_kw)

            # Target line (cyan): BO bar → exit bar
            fig.add_shape(type="line",
                x0=bo_start, x1=exit_dt,
                y0=tgt_px, y1=tgt_px,
                line=dict(color="#00FFFF", width=1.5, dash="dot"),
                opacity=0.7, **row_kw)

            # Price path: direct dotted line entry → exit (yellow)
            fig.add_shape(type="line",
                x0=entry_dt, x1=exit_dt,
                y0=entry_px, y1=exit_px,
                line=dict(color="#FFD600", width=2.5, dash="dot"),
                opacity=0.9, **row_kw)

            # Setup range lines — single bar for CX/BigBO, two bars for BO+FT
            _sb = sig_dt if (is_cx or is_bigbo) else bo_start
            bo_row = df_day[df_day["DateTime"] == _sb]
            ft_row = df_day[df_day["DateTime"] == sig_dt]
            if not bo_row.empty and not ft_row.empty:
                bo_r = bo_row.iloc[0]
                ft_r = ft_row.iloc[0]
                # BarRange: H and L of combined setup bars
                for y in (max(bo_r["High"], ft_r["High"]),
                          min(bo_r["Low"],  ft_r["Low"])):
                    fig.add_shape(type="line",
                        x0=bo_start, x1=setup_end,
                        y0=y, y1=y,
                        line=dict(color="#00FFFF", width=1, dash="dot"),
                        opacity=0.4, **row_kw)
                if target_mode == "BodyRange":
                    # Additional lines for combined body extents
                    for y in (max(bo_r["Open"], bo_r["Close"],
                                  ft_r["Open"], ft_r["Close"]),
                              min(bo_r["Open"], bo_r["Close"],
                                  ft_r["Open"], ft_r["Close"])):
                        fig.add_shape(type="line",
                            x0=bo_start, x1=setup_end,
                            y0=y, y1=y,
                            line=dict(color="#00FFFF", width=1, dash="dot"),
                            opacity=0.25, **row_kw)

            # I1R: target filled on the entry bar itself
            is_i1r = (exit_dt is not None
                      and exit_dt == entry_dt
                      and exit_px is not None
                      and abs(exit_px - tgt_px) < 1e-6)

            # Accumulate day stats
            if result is not None:
                if stype not in type_stats:
                    type_stats[stype] = {"w": 0, "l": 0, "pts": 0.0, "i1r": 0}
                if result > 0:
                    wins += 1
                    type_stats[stype]["w"] += 1
                else:
                    losses += 1
                    type_stats[stype]["l"] += 1
                net_pts += result
                type_stats[stype]["pts"] += result
                if is_i1r:
                    i1r_total += 1
                    type_stats[stype]["i1r"] += 1

            # I1R label — tight to the entry bar (EB), same offset style as the setup marker
            if is_i1r:
                eb_ref = bar_lo.get(entry_dt, exit_px) if is_long else bar_hi.get(entry_dt, exit_px)
                i1r_y  = eb_ref - offset if is_long else eb_ref + offset
                fig.add_annotation(
                    x=entry_dt, y=i1r_y,
                    text="I1R",
                    showarrow=False,
                    font=dict(size=8, color="#FFD700", family="monospace"),
                    xanchor="center",
                    yanchor="top" if is_long else "bottom",
                    **row_kw,
                )

            # Result annotation at exit bar
            if result is not None:
                sign      = "+" if result > 0 else ""
                ann_color = "#00FFFF" if result > 0 else "#DC143C"
                fig.add_annotation(
                    x=exit_dt, y=exit_px,
                    text=f"{sign}{result:.2f}",
                    showarrow=False,
                    font=dict(size=9, color=ann_color, family="monospace"),
                    xanchor="left",
                    yanchor="bottom" if is_long else "top",
                    **row_kw,
                )

        # Paint signal bars — pass full datetime index with NaN for non-signal
        # bars so Plotly uses identical bar width as the base candle trace.
        for (fill, line), _dts in _bar_paints.items():
            _mask = df_day["DateTime"].isin(_dts)
            if not _mask.any():
                continue
            _nan = float("nan")
            fig.add_trace(go.Candlestick(
                x=df_day["DateTime"],
                open=df_day["Open"].where(_mask, _nan),
                high=df_day["High"].where(_mask, _nan),
                low=df_day["Low"].where(_mask, _nan),
                close=df_day["Close"].where(_mask, _nan),
                increasing=dict(line=dict(color=line, width=1), fillcolor=fill),
                decreasing=dict(line=dict(color=line, width=1), fillcolor=fill),
                showlegend=False, name="",
            ), **row_kw)

        # Legend — derive from ama_detected when available (exact NT8 paint match),
        # fall back to signals for non-AMA overlays.
        if _has_ama:
            _sigs_a = ama_detected["Signal"].to_numpy(int)
            _ft_a   = ama_detected["FTflag"].to_numpy(int)
            _lbo = bool((_sigs_a == 1).any())
            _bbo = bool((_sigs_a == -1).any())
            _lft = bool(((_ft_a == 1)  & (_sigs_a != 5)).any())
            _bft = bool(((_ft_a == -1) & (_sigs_a != -5)).any())
            _lob = bool((_sigs_a == 3).any())
            _bob = bool((_sigs_a == -3).any())
            _cx  = bool((abs(_sigs_a) == 2).any())
            _bbo5 = bool((abs(_sigs_a) == 5).any())
        elif _has_sigs:
            _seen_types = {r["SignalType"] for _, r in signals.iterrows()}
            _lbo  = any(r["Direction"] == "Long"  and r["SignalType"] in ("BO", "BO+FT") for _, r in signals.iterrows())
            _bbo  = any(r["Direction"] == "Short" and r["SignalType"] in ("BO", "BO+FT") for _, r in signals.iterrows())
            _lft  = any(r["Direction"] == "Long"  and r["SignalType"] in ("BO+FT", "OB+FT", "CX", "BigBO") for _, r in signals.iterrows())
            _bft  = any(r["Direction"] == "Short" and r["SignalType"] in ("BO+FT", "OB+FT", "CX", "BigBO") for _, r in signals.iterrows())
            _lob  = any(r["Direction"] == "Long"  and r["SignalType"] in ("OB", "OB_Doji", "OB+FT") for _, r in signals.iterrows())
            _bob  = any(r["Direction"] == "Short" and r["SignalType"] in ("OB", "OB_Doji", "OB+FT") for _, r in signals.iterrows())
            _cx   = "CX"    in _seen_types
            _bbo5 = "BigBO" in _seen_types
        else:
            _lbo = _bbo = _lft = _bft = _lob = _bob = _cx = _bbo5 = False
        _legend_defs = [
            ("BO long",  "square", "#1E90FF", _lbo),
            ("BO bear",  "square", "#8B0000", _bbo),
            ("FT long",  "square", "#00FFFF", _lft),
            ("FT bear",  "square", "#DC143C", _bft),
            ("OB long",  "square", "#008000", _lob),
            ("OB bear",  "square", "#FF8C00", _bob),
            ("CX",       "square", "#9932CC", _cx),
            ("BigBO",    "square", "#DDA0DD", _bbo5),
        ]
        for leg_name, leg_sym, leg_col, _show in _legend_defs:
            if not _show:
                continue
            fig.add_trace(go.Scatter(
                x=[None], y=[None],
                mode="markers",
                marker=dict(symbol=leg_sym, size=10, color=leg_col),
                name=leg_name,
                showlegend=True,
            ), **row_kw)
        fig.update_layout(
            showlegend=True,
            legend=dict(
                x=0.01, y=0.01,
                xanchor="left", yanchor="bottom",
                bgcolor="rgba(15,15,15,0.65)",
                borderwidth=0,
                font=dict(size=10, color="#CCCCCC", family="monospace"),
            ),
        )

        # Combined info + stats box — only shown when tradeable signals are present
        if _has_sigs:
            s0   = signals.iloc[0]
            tm   = s0.get("TargetMode", "BarRange")
            tmul = float(s0.get("TargetMult", 1.0))
            sm   = s0.get("StopMode",   "BarExtreme")
            soff = s0.get("StopOffset", 1)
            lime = "#FFD700"

            def _fmt(pts: float, pnl: float) -> str:
                p = f"+{pts:.2f}" if pts >= 0 else f"{pts:.2f}"
                d = f"+${pnl:,.0f}" if pnl >= 0 else f"-${abs(pnl):,.0f}"
                return f"{p}pts  {d}"

            box_lines = [f"Tgt: {tm} ×{tmul:.2f}  |  Stop: {sm} +{int(soff)}t"]
            for stype, st in sorted(type_stats.items()):
                if st["w"] + st["l"] == 0:
                    continue
                i1r_tag = f"  {st['i1r']}I1R" if st.get("i1r", 0) else ""
                box_lines.append(f"{stype}  {st['w']}W-{st['l']}L  {_fmt(st['pts'], st['pts']*50)}{i1r_tag}")
            net_pnl = net_pts * 50
            box_lines.append(f"Total  {wins}W-{losses}L  {_fmt(net_pts, net_pnl)}")
            total_traded = wins + losses
            if i1r_total and total_traded:
                pct = i1r_total / total_traded * 100
                box_lines.append(f"I1R: {i1r_total}/{total_traded} ({pct:.0f}%)")

            fig.add_annotation(
                x=0.99, y=0.99,
                xref="paper", yref="paper",
                text="<br> <br>".join(box_lines),
                showarrow=False,
                bgcolor="rgba(15,15,15,0.75)",
                borderwidth=0,
                font=dict(size=11, color=lime, family="monospace"),
                align="left",
                xanchor="right",
                yanchor="top",
            )

    return fig


# ── Bar Viewer tab ────────────────────────────────────────────────────────────

def show_bar_viewer(sc_file: str = "", contract: str = "ES"):
    bars = st.session_state.get("data_sc_5m")

    if bars is None:
        st.info("Build the continuous series in the **📂 Massive** tab to begin.")
        return

    bars["Date"] = bars["DateTime"].dt.date
    dates = sorted(bars["Date"].unique())

    if "bar_viewer_idx" not in st.session_state:
        st.session_state.bar_viewer_idx = len(dates) - 1
    st.session_state.bar_viewer_idx = max(0, min(st.session_state.bar_viewer_idx, len(dates) - 1))

    c_prev, c_next, c_sel = st.columns([1, 1, 14])
    if c_prev.button("‹", help="Previous date"):
        st.session_state.bar_viewer_idx = max(0, st.session_state.bar_viewer_idx - 1)
    if c_next.button("›", help="Next date"):
        st.session_state.bar_viewer_idx = min(len(dates) - 1, st.session_state.bar_viewer_idx + 1)

    selected_date = c_sel.selectbox(
        "Trading Date",
        options=dates,
        index=st.session_state.bar_viewer_idx,
        format_func=lambda d: d.strftime("%A %b %d, %Y"),
    )
    st.session_state.bar_viewer_idx = dates.index(selected_date)

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

    cb1, cb2, cb3 = st.columns(3)
    show_bar_nums  = cb1.checkbox("Show bar numbers", value=False,
                                   help="Labels every 3rd bar (1, 4, 7…) below the x-axis.")
    show_volume    = cb2.checkbox("Show volume", value=False,
                                   help="Adds a colour-coded volume panel below the price chart.")
    show_trades    = cb3.checkbox("Show trades/lines", value=True,
                                   help="Toggle stop, target, price-path lines and result annotations.")
    excl_first_n  = st.session_state.get("excl_first_n",  0)
    excl_last_min = st.session_state.get("excl_last_min", 0)

    # Signal overlay selector
    _ama_sigs   = st.session_state.get("ba_signals_ama")
    _revft_sigs = st.session_state.get("ba_signals_revft")
    _mc_sigs    = st.session_state.get("ba_signals_mc")
    _overlay_opts = ["None"]
    if _ama_sigs   is not None and not _ama_sigs.empty:   _overlay_opts.append("AMA")
    if _revft_sigs is not None and not _revft_sigs.empty: _overlay_opts.append("RevFT")
    if _mc_sigs    is not None and not _mc_sigs.empty:    _overlay_opts.append("MC")
    _overlay_choice = st.selectbox(
        "Signal overlay", _overlay_opts,
        index=min(1, len(_overlay_opts) - 1),
        key="bar_viewer_overlay",
    ) if len(_overlay_opts) > 1 else "None"

    def _adapt_parse_signals(sigs, date):
        """Convert parse_signals() schema (DateTime=close) to AMA schema (SignalDateTime=open)."""
        day = sigs[pd.to_datetime(sigs["DateTime"]).dt.date == date].copy()
        if day.empty:
            return None
        day = day.rename(columns={"DateTime": "_close_dt"})
        day["SignalDateTime"] = pd.to_datetime(day["_close_dt"]) - pd.Timedelta(minutes=5)
        day["TargetPoints"]   = (day["SignalPrice"] - day["StopPrice"]).abs()
        day["TargetMode"]     = "1R"
        day["ZScore"]         = float("nan")
        return day

    _overlay = None
    if _overlay_choice == "AMA" and _ama_sigs is not None:
        _day = _ama_sigs[pd.to_datetime(_ama_sigs["SignalDateTime"]).dt.date == selected_date]
        _overlay = _day if not _day.empty else None
    elif _overlay_choice == "RevFT" and _revft_sigs is not None:
        _overlay = _adapt_parse_signals(_revft_sigs, selected_date)
    elif _overlay_choice == "MC" and _mc_sigs is not None:
        _overlay = _adapt_parse_signals(_mc_sigs, selected_date)

    # AMA raw detected for bar painting (exact NT8 match)
    _ama_det_day = None
    _ama_det_full = st.session_state.get("ba_ama_detected")
    if _ama_det_full is not None:
        _det_mask = pd.to_datetime(_ama_det_full["DateTime"]).dt.date == selected_date
        _ama_det_day = _ama_det_full[_det_mask].reset_index(drop=True)
        if _ama_det_day.empty:
            _ama_det_day = None

    st.plotly_chart(
        make_candlestick(day, selected_date.strftime("%B %d, %Y"),
                         show_bar_nums=show_bar_nums,
                         show_volume=show_volume,
                         excl_first_n=excl_first_n, excl_last_min=excl_last_min,
                         contract=contract,
                         signals=_overlay,
                         show_trades=show_trades,
                         ama_detected=_ama_det_day),
        use_container_width=True,
    )

    with controls.expander("data_bartable", "5-Minute Bar Table", expanded=False):
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


# ── Data tab ──────────────────────────────────────────────────────────────────

def show_data_tab():
    st.caption(
        "Set once here — these same filters (holidays, day-of-week, session boundaries, "
        "economic events) automatically apply to the Massive continuous-series comparison "
        "and to Bar Analysis. No need to set them twice."
    )
    validation.render_filters("shared")

    st.divider()
    st.markdown("### Data Sources")
    st.caption(
        "Massive bars/ticks (built in the 📂 Massive tab) drive Bar Viewer and all trade analysis. "
        "NT is only used as a continuous-contract upload in the Massive tab, for matching — "
        "it doesn't need anything here. This panel is a manual override if you ever need to "
        "load a different ES_MAS 5M export by hand."
    )

    _sc5m = st.session_state.get("data_sc_5m")
    if _sc5m is not None:
        _lbl  = st.session_state.get("data_sc_5m_label", "")
        _days = _sc5m["DateTime"].dt.date.nunique()
        _min  = _sc5m["DateTime"].dt.date.min()
        _max  = _sc5m["DateTime"].dt.date.max()
        st.success(f"✅ **ES_MAS 5M** — {_lbl}  |  {_days:,} days  |  {_min} → {_max}")
    else:
        st.info("ES_MAS 5M — not loaded")

    sc_5m_file = st.file_uploader(
        "Upload ES_MAS 5M bars (.txt / .csv) — overrides the Massive continuous series",
        type=["txt", "csv"], key="dt_sc5m",
        help="OHLCExporter TXT from the ES_MAS chart in NT",
    )
    if sc_5m_file:
        _key = f"{sc_5m_file.name}_{sc_5m_file.size}"
        if st.session_state.get("data_sc_5m_key") != _key:
            _cached = load_csv_cache("sc_5m", sc_5m_file.name, sc_5m_file.size)
            if _cached is not None:
                _df = _cached
            else:
                with st.spinner("Parsing ES_MAS 5M data…"):
                    _df = parse_ohlc_from_upload(sc_5m_file)
                save_csv_cache(_df, "sc_5m", sc_5m_file.name, sc_5m_file.size)
                _mf = load_csv_manifest()
                _mf["sc_5m"] = {"name": sc_5m_file.name, "size": sc_5m_file.size}
                save_csv_manifest(_mf)
            _apply_data_slot("sc_5m", _df, sc_5m_file.name, _key)
            st.rerun()

    # ── Manually excluded dates ───────────────────────────────────────────────
    st.divider()
    with controls.expander("data_excluded", "🚫 Manually Excluded Dates", expanded=False):
        st.caption(
            "Dates flagged here are dropped everywhere in the app — comparisons, Bar Viewer, "
            "and trade simulation/WFA — because the underlying data for that day is known to be bad "
            "(feed gap, capture artifact, etc), not a real price discrepancy."
        )
        excluded = load_excluded_dates()

        ec1, ec2, ec3 = st.columns([2, 3, 1])
        new_date   = ec1.date_input("Date", key="excl_date_input")
        new_reason = ec2.text_input("Reason", key="excl_reason_input", placeholder="e.g. NT capture gap")
        if ec3.button("Add", key="excl_date_add"):
            excluded[str(new_date)] = new_reason or "—"
            save_excluded_dates(excluded)
            st.rerun()

        if excluded:
            for d in sorted(excluded):
                rc1, rc2, rc3 = st.columns([2, 5, 1])
                rc1.write(d)
                rc2.write(excluded[d])
                if rc3.button("🗑️", key=f"excl_remove_{d}"):
                    excluded.pop(d, None)
                    save_excluded_dates(excluded)
                    st.rerun()
        else:
            st.info("No dates excluded.")

    # ── Cache management ──────────────────────────────────────────────────────
    st.divider()
    if st.button("🗑️ Clear all cached data", help="Deletes Parquet cache files and resets session."):
        clear_csv_cache()
        for k in list(st.session_state.keys()):
            if k.startswith("data_") or k in (
                "uploaded_ohlc_bars", "uploaded_ohlc_key",
                "bv_sc5m_bars", "bv_sc5m_key", "bv_nt5m_bars", "bv_nt5m_key",
            ):
                st.session_state.pop(k, None)
        st.rerun()


# ── App entry point ───────────────────────────────────────────────────────────

@st.cache_data(show_spinner="Detecting AMA signals…")
def _run_ama(
    bars: pd.DataFrame,
    stop_offset: int,
    target_mode: str,
    target_mult: float,
    types_key: str,
    ob_requires_ft: bool,
    # 01. BO, OB, CX
    show_blbo: int,
    show_brbo: int,
    show_outside_bars: int,
    strict_ob: int,
    show_cx: int,
    cx_factor: float,
    show_bigbo: int,
    big_bo_range_factor: float,
    # 02. Z score
    big_bo_by_zscore: int,
    compare_range2range: int,
    compare_body2body: int,
    z_length: int,
    # 03. Range Filter
    range_filter: float,
    range_lookback: int,
    do_not_range_limit_ob: int,
    # 04. IBS Filters
    bl_signal_ibs: int,
    br_signal_ibs: int,
    bl_ft_ibs: int,
    br_ft_ibs: int,
    do_not_ibs_filter_ob: int,
    # 05. Signal/Output Control
    paint_ft_bar: int,
    ft_color_same_as_bo: int,
    ft_must_close_beyond: int,
    ft_bar_must_bo: int,
    ft_bar_not_range_limited: int,
    ft_after_ob: int,
    ignore_open_gap: int,
) -> pd.DataFrame:
    """Run AMA detect + to_signal_rows on `bars`. Cached by all params."""
    cfg = ama_setups.AMAConfig(
        show_blbo=show_blbo,
        show_brbo=show_brbo,
        show_outside_bars=show_outside_bars,
        strict_ob=strict_ob,
        show_cx=show_cx,
        cx_factor=cx_factor,
        show_bigbo=show_bigbo,
        big_bo_range_factor=big_bo_range_factor,
        big_bo_by_zscore=big_bo_by_zscore,
        compare_range2range=compare_range2range,
        compare_body2body=compare_body2body,
        z_length=z_length,
        range_filter=range_filter,
        range_lookback=range_lookback,
        do_not_range_limit_ob=do_not_range_limit_ob,
        bl_signal_ibs=bl_signal_ibs,
        br_signal_ibs=br_signal_ibs,
        bl_ft_bar_ibs=bl_ft_ibs,
        br_ft_bar_ibs=br_ft_ibs,
        do_not_ibs_filter_ob=do_not_ibs_filter_ob,
        paint_ft_bar=paint_ft_bar,
        ft_color_same_as_bo=ft_color_same_as_bo,
        ft_bar_must_close_beyond=ft_must_close_beyond,
        ft_bar_must_bo=ft_bar_must_bo,
        ft_bar_not_range_limited=ft_bar_not_range_limited,
        ft_after_ob=ft_after_ob,
        ignore_open_gap=ignore_open_gap,
    )
    tp = ama_setups.AMATradeParams(
        stop_offset_ticks=stop_offset,
        target_mode=target_mode,
        target_mult=target_mult,
    )
    types_set  = set(types_key.split(","))
    include_ft = "BO" in types_set or "FT" in types_set
    codes: list[int] = []
    if "BO" in types_set or "FT" in types_set: codes += [1, -1]
    if "OB"    in types_set: codes += [3, -3, 4]
    if show_bigbo: codes += [5, -5]   # display-only marker, always injected when show flag is on
    if show_cx:    codes += [2, -2]   # display-only marker, always injected when show flag is on
    bars = bars.drop(columns=["Contract"], errors="ignore")
    detected  = ama_setups.detect(bars, cfg)
    signals   = ama_setups.to_signal_rows(
        detected, bars, tp,
        signal_types=tuple(set(codes)),
        include_ft=include_ft,
        ob_requires_ft=ob_requires_ft,
        include_flip=False,
    )
    # Join ZScore from detect() output so hover can show it
    z_lookup = detected.set_index("DateTime")["ZScore"]
    signals["ZScore"] = pd.to_datetime(signals["SignalDateTime"]).map(z_lookup).round(2)
    return signals, detected


def _render_status_strip():
    """A compact load-status row: price, continuous series, and signal sets.
    Checkmarks reflect current session state (continuous self-corrects on the
    next rerun after the Massive tab builds it)."""
    def _has(x):
        return x is not None and not getattr(x, "empty", False)

    def _chk(ok):
        return "✅" if ok else "⬜"

    price = st.session_state.get("data_sc_5m")
    cont  = st.session_state.get("mas_continuous")
    mc    = st.session_state.get("ba_signals_mc")
    rev   = st.session_state.get("ba_signals_revft")
    ama   = st.session_state.get("ba_signals_ama")

    s1, s2, s3, s4, s5 = st.columns(5)
    if _has(price):
        d0, d1 = price["DateTime"].min().date(), price["DateTime"].max().date()
        s1.markdown(f"{_chk(True)} **Price** · {len(price):,} bars · {d0} → {d1}")
    else:
        s1.markdown(f"{_chk(False)} **Price** — none loaded")
    s2.markdown(f"{_chk(_has(cont))} **Continuous** "
                + (f"· {len(cont):,} bars" if _has(cont) else "— not built"))
    s3.markdown(f"{_chk(_has(mc))} **MC signals** "
                + (f"· {len(mc)}" if _has(mc) else "— none"))
    s4.markdown(f"{_chk(_has(rev))} **RevFT signals** "
                + (f"· {len(rev)}" if _has(rev) else "— none"))
    s5.markdown(f"{_chk(_has(ama))} **AMA signals** "
                + (f"· {len(ama)}" if _has(ama) else "— none"))


def main():
    # ── Auto-load from CSV Parquet cache on first run ─────────────────────────
    if "data_sc_5m" not in st.session_state and "data_nt_5m" not in st.session_state:
        _mf = load_csv_manifest()
        for _slot in ("sc_5m", "nt_5m"):
            _info = _mf.get(_slot)
            if _info:
                _df = load_csv_cache(_slot, _info["name"], _info["size"])
                if _df is not None:
                    _apply_data_slot(
                        _slot, _df, _info["name"],
                        f"{_info['name']}_{_info['size']}",
                    )

    st.title("ES Futures — 5-Minute RTH Bars")

    hdr_l, hdr_r = st.columns([8, 2])
    hdr_l.caption("Regular Trading Hours 08:30 – 15:15 CT  |  5-minute bars  |  All times Central")

    # Positioned here but filled at the END of main(), so it reflects state that
    # the tab blocks populate later (continuous series, signals, sc_5m bridge).
    status_ph = st.container()

    from pathlib import Path
    contract_keys = [k for k, v in CONTRACTS.items() if Path(v["sc_file"]).exists()]

    if len(contract_keys) > 1:
        selected_key = hdr_r.selectbox(
            "Contract", contract_keys,
            index=0, key="active_contract", label_visibility="collapsed",
        )
    elif len(contract_keys) == 1:
        selected_key = contract_keys[0]
    else:
        selected_key = None

    sc_file = str(CONTRACTS[selected_key]["sc_file"]) if selected_key else ""
    nt_file = str(CONTRACTS[selected_key]["nt_file"]) if selected_key else ""

    _rl_col, _fr_col, _ = st.columns([1, 1.6, 9])
    if _rl_col.button("🔄 Reload", help="Clears session data (cache files are preserved)."):
        st.cache_data.clear()
        for k in list(st.session_state.keys()):
            if k.startswith("data_") or k in (
                "uploaded_ohlc_bars", "uploaded_ohlc_key",
                "bv_sc5m_bars", "bv_sc5m_key", "bv_nt5m_bars", "bv_nt5m_key",
                "ba_signals", "ba_signals_key",
            ):
                st.session_state.pop(k, None)
        st.rerun()
    if _fr_col.button(
        "♻️ Full Restart",
        help="Resets ALL session state + caches and re-derives everything from disk "
             "(continuous series, defaults, widgets). The in-app equivalent of relaunching — "
             "use after code changes. Cache files on disk are preserved.",
    ):
        st.cache_data.clear()
        try:
            st.cache_resource.clear()
        except Exception:
            pass
        st.session_state.clear()
        st.rerun()

    # Tab bar is built dynamically: the 🎛️ Master tab (first, never hideable) lets
    # the user switch whole tabs on/off, so disabled tabs are simply omitted from
    # the st.tabs() label list. Tabs are referenced by key via the T dict below.
    # st.tabs always opens tab 0, so a one-time JS click further down makes Bar
    # Analysis the default-active tab.
    controls.load_state()
    _visible_keys = ["master"] + [k for k in controls.TAB_ORDER[1:] if controls.tab_visible(k)]
    _tab_objs = st.tabs([controls.TAB_LABELS[k] for k in _visible_keys])
    T = dict(zip(_visible_keys, _tab_objs))

    # Auto-select Bar Analysis once per browser session — guarded so it does NOT
    # re-fire on every rerun and yank you off a tab you navigated to. Tabs are now
    # built dynamically (the Master tab can hide tabs), so we match the button by
    # its label text rather than a fixed index.
    components.html(
        """
        <script>
        (function () {
          if (window.sessionStorage.getItem('ba_default_done')) return;
          const doc = window.parent.document;
          const tabs = doc.querySelectorAll('button[data-baseweb="tab"]');
          for (const t of tabs) {
            if (t.innerText && t.innerText.indexOf('Bar Analysis') !== -1) {
              t.click();
              window.sessionStorage.setItem('ba_default_done', '1');
              break;
            }
          }
        })();
        </script>
        """,
        height=0,
    )

    contract_label = selected_key.split(" — ")[0] if selected_key else "ES"

    with T["master"]:
        controls.render_master_tab()

    with controls.tab_ctx(T, "massive"):
        massive.show_massive_tab()

    if st.session_state.get("data_sc_5m") is None and st.session_state.get("mas_continuous") is not None:
        mas_cont = st.session_state["mas_continuous"]
        apply_data_slot("sc_5m", mas_cont.drop(columns=["Contract"], errors="ignore"),
                         "Massive Continuous (auto)", "mas_continuous_auto")

    with controls.tab_ctx(T, "data"):
        show_data_tab()

    with controls.tab_ctx(T, "bar_viewer"):
        show_bar_viewer(sc_file, contract=contract_label)

    with controls.tab_ctx(T, "chart"):
        continuous_chart.show_continuous_chart_tab()

    with controls.tab_ctx(T, "bar_analysis"):
        # Signals upload lives here (price data is in the Data tab)
        _SIGNALS_DIR = Path(__file__).parent / "saved_signals"
        _SIGNALS_DIR.mkdir(exist_ok=True)

        def _signal_uploader(label: str, upload_key: str, state_prefix: str):
            _disk_path = _SIGNALS_DIR / f"{state_prefix}.parquet"
            with controls.expander(state_prefix, label, expanded=False):
                sig_file = st.file_uploader(
                    "Signals (.txt/.csv)", type=["txt", "csv"], key=upload_key,
                    help="Space-delimited: Num Type Dir DD/MM/YYYY HH:MM:SS BarNum Price Stop",
                )
                if sig_file is not None:
                    sig_key = f"{sig_file.name}_{sig_file.size}"
                    if st.session_state.get(f"{state_prefix}_key") != sig_key:
                        raw    = sig_file.read().decode("utf-8", errors="replace")
                        parsed = bar_analysis.parse_signals(raw)
                        if parsed is None or parsed.empty:
                            st.error("Could not parse signals.")
                        else:
                            st.session_state[state_prefix]           = parsed
                            st.session_state[f"{state_prefix}_key"]  = sig_key
                            parsed.to_parquet(_disk_path, index=False)
                    if st.session_state.get(state_prefix) is not None:
                        n_sig = len(st.session_state[state_prefix])
                        st.caption(f"✅ {sig_file.name}  |  {n_sig} signals")
                else:
                    if state_prefix not in st.session_state and _disk_path.exists():
                        st.session_state[state_prefix] = pd.read_parquet(_disk_path)
                    if st.session_state.get(state_prefix) is not None:
                        n_sig = len(st.session_state[state_prefix])
                        st.caption(f"✅ (auto-loaded from disk)  |  {n_sig} signals")

        _signal_uploader("📊 MC Signals",   "upload_signals",       "ba_signals_mc")
        _signal_uploader("🔁 RevFT Signals", "upload_signals_revft", "ba_signals_revft")

        # AMA Signals — generated directly from loaded bar data, no upload needed
        with st.expander("🔶 AMA Breakouts Signals", expanded=False):
            _cont = st.session_state.get("mas_continuous")
            _sc   = st.session_state.get("data_sc_5m")
            _ama_bars = _cont if (_cont is not None and not _cont.empty) else _sc
            if _ama_bars is None:
                st.info("Load bar data first (Data tab or Massive tab).")
            else:
                # ── Signal types (what to TRADE) ──────────────────────────────
                st.markdown("**Signal types**")
                _tc1, _tc2 = st.columns(2)
                _inc_boft = _tc1.checkbox("BO+FT", value=True, key="ama_inc_boft")
                _inc_ob   = _tc2.checkbox("OB+FT", value=True, key="ama_inc_ob")
                _selected_types = ",".join(t for t, on in [
                    ("BO", _inc_boft), ("OB", _inc_ob),
                ] if on)

                # ── Trade geometry ─────────────────────────────────────────────
                st.markdown("**Trade geometry**")
                _ag1, _ag2, _ag3 = st.columns(3)
                _ama_stop_off = _ag1.number_input("Stop offset (ticks)", min_value=0,
                                                   max_value=10, value=1, step=1,
                                                   key="ama_stop_offset")
                _ama_tgt_mode = _ag2.selectbox("Target mode", ["BarRange", "BodyRange"],
                                                key="ama_target_mode")
                _ama_tgt_mult = _ag3.number_input("Target mult", min_value=0.1,
                                                   max_value=5.0, value=1.0, step=0.1,
                                                   format="%.1f", key="ama_target_mult")

                # ── Indicator settings (exact NT8 AMA_Breakouts_PB §01–05 parity) ──
                with st.expander("AMA indicator settings", expanded=False):
                    # 01. BO, OB, CX  — identical to NT8 §01 order
                    st.markdown("**01. BO, OB, CX**")
                    _r1a, _r1b, _r1c, _r1d = st.columns(4)
                    _show_blbo = _r1a.checkbox("_ShowBLBO",          value=True,  key="ama_show_blbo")
                    _show_brbo = _r1b.checkbox("_ShowBRBO",          value=True,  key="ama_show_brbo")
                    _show_bbo  = _r1c.checkbox("_ShowBigBO",         value=False, key="ama_show_bigbo")
                    _bbo_fact  = _r1d.number_input("_BigBORangeFactor", min_value=0.5, max_value=5.0,
                                                    value=1.05, step=0.05, format="%.2f",
                                                    key="ama_bbo_factor")
                    _r2a, _r2b, _r2c, _r2d = st.columns(4)
                    _show_ob   = _r2a.checkbox("_ShowOutsideBars",   value=True,  key="ama_show_outside")
                    _strict    = _r2b.checkbox("_StrictOB",          value=True,  key="ama_strict_ob")
                    _show_cx   = _r2c.checkbox("_ShowCX",            value=False, key="ama_show_cx")
                    _cx_factor = _r2d.number_input("_CXfactor",      min_value=0.5, max_value=5.0,
                                                    value=1.8, step=0.1, format="%.1f",
                                                    key="ama_cx_factor")
                    _ob_ft     = st.checkbox("OB requires FT  (app-only, not in NT8)",
                                              value=True, key="ama_ob_req_ft")

                    # 02. Z score
                    st.markdown("**02. Z score**")
                    _z1, _z2, _z3, _z4 = st.columns(4)
                    _bbo_zscore = _z1.checkbox("BigBO by Z-score", value=True,  key="ama_bbo_zscore")
                    _cmp_r2r   = _z2.checkbox("Range vs Range Z", value=True,  key="ama_cmp_r2r")
                    _cmp_b2b   = _z3.checkbox("Body vs Body Z",   value=False, key="ama_cmp_b2b")
                    _z_len     = _z4.number_input("Z length",     min_value=5,
                                                   max_value=100, value=20, step=1,
                                                   key="ama_z_length")

                    # 03. Range filter
                    st.markdown("**03. Range filter** (0 = off)")
                    _rf1, _rf2, _rf3 = st.columns(3)
                    _rng_filt  = _rf1.number_input("Range filter mult", min_value=0.0,
                                                    max_value=3.0, value=0.0, step=0.1,
                                                    format="%.1f", key="ama_range_filter")
                    _rng_lb    = _rf2.number_input("Range lookback",    min_value=2,
                                                    max_value=50, value=8, step=1,
                                                    key="ama_range_lookback")
                    _no_rng_ob = _rf3.checkbox("Don't range-limit OB", value=False,
                                                key="ama_no_rng_ob")

                    # 04. IBS Filters
                    st.markdown("**04. IBS filters** (−1 = off)")
                    _ib1, _ib2, _ib3, _ib4, _ib5 = st.columns(5)
                    _bl_ibs    = _ib1.number_input("Bull BO min IBS",  min_value=-1, max_value=100,
                                                    value=69, step=1, key="ama_bl_ibs")
                    _br_ibs    = _ib2.number_input("Bear BO max IBS",  min_value=-1, max_value=100,
                                                    value=31, step=1, key="ama_br_ibs")
                    _bl_ft     = _ib3.number_input("Bull FT min IBS",  min_value=-1, max_value=100,
                                                    value=40, step=1, key="ama_bl_ft_ibs")
                    _br_ft     = _ib4.number_input("Bear FT max IBS",  min_value=-1, max_value=100,
                                                    value=60, step=1, key="ama_br_ft_ibs")
                    _no_ibs_ob = _ib5.checkbox("Don't IBS-filter OB", value=True,
                                                key="ama_no_ibs_ob")

                    # 05. Signal/Output Control
                    st.markdown("**05. Signal/Output Control**")
                    _s1, _s2, _s3, _s4 = st.columns(4)
                    _paint_ft       = _s1.checkbox("Paint FT bar",        value=True,  key="ama_paint_ft")
                    _ft_must_bo     = _s2.checkbox("FT must BO",          value=True,  key="ama_ft_must_bo")
                    _ft_no_rng      = _s3.checkbox("FT not range-limited",value=True,  key="ama_ft_no_rng")
                    _ft_after_ob    = _s4.checkbox("FT after OB",         value=False, key="ama_ft_after_ob")
                    _s5, _s6, _s7   = st.columns(3)
                    _ft_close       = _s5.selectbox("FT must close beyond", [1, 0],
                                                     format_func=lambda x: "Yes" if x else "No",
                                                     key="ama_ft_close_beyond")
                    _ft_color_same  = _s6.checkbox("FT color same as BO", value=False, key="ama_ft_color_same")
                    _ign_gap        = _s7.checkbox("Ignore open gap",      value=True,  key="ama_ign_gap")

                st.divider()
                if st.button("Generate AMA Signals", key="ama_generate"):
                    if not _selected_types and not _show_bbo and not _show_cx:
                        st.warning("Select at least one signal type (BO+FT / OB+FT) or enable BigBO/CX in §01.")
                    else:
                        _ama_sig, _ama_det = _run_ama(
                            _ama_bars,
                            int(_ama_stop_off),
                            _ama_tgt_mode,
                            float(_ama_tgt_mult),
                            _selected_types,
                            ob_requires_ft=bool(_ob_ft),
                            # 01
                            show_blbo=int(_show_blbo),
                            show_brbo=int(_show_brbo),
                            show_outside_bars=int(_show_ob),
                            strict_ob=int(_strict),
                            show_cx=int(_show_cx),
                            cx_factor=float(_cx_factor),
                            show_bigbo=int(_show_bbo),
                            big_bo_range_factor=float(_bbo_fact),
                            # 02
                            big_bo_by_zscore=int(_bbo_zscore),
                            compare_range2range=int(_cmp_r2r),
                            compare_body2body=int(_cmp_b2b),
                            z_length=int(_z_len),
                            # 03
                            range_filter=float(_rng_filt),
                            range_lookback=int(_rng_lb),
                            do_not_range_limit_ob=int(_no_rng_ob),
                            # 04
                            bl_signal_ibs=int(_bl_ibs),
                            br_signal_ibs=int(_br_ibs),
                            bl_ft_ibs=int(_bl_ft),
                            br_ft_ibs=int(_br_ft),
                            do_not_ibs_filter_ob=int(_no_ibs_ob),
                            # 05
                            paint_ft_bar=int(_paint_ft),
                            ft_color_same_as_bo=int(_ft_color_same),
                            ft_must_close_beyond=int(_ft_close),
                            ft_bar_must_bo=int(_ft_must_bo),
                            ft_bar_not_range_limited=int(_ft_no_rng),
                            ft_after_ob=int(_ft_after_ob),
                            ignore_open_gap=int(_ign_gap),
                        )
                        # Compute session-relative BarNum (1-based intra-day index).
                        # bar_analysis.py expects BarNum in 1…81 range, not absolute position.
                        _bn_bars = _ama_bars.copy()
                        _bn_bars["_Date"] = pd.to_datetime(_bn_bars["DateTime"]).dt.date
                        _bn_bars["BarNum"] = _bn_bars.groupby("_Date").cumcount() + 1
                        _bn_lookup = _bn_bars.set_index("DateTime")["BarNum"]
                        _ama_sig["BarNum"] = (
                            pd.to_datetime(_ama_sig["SignalDateTime"])
                            .map(_bn_lookup)
                            .fillna(0).astype(int)
                        )

                        st.session_state["ba_signals_ama"]    = _ama_sig
                        st.session_state["ba_ama_detected"]   = _ama_det
                        st.success(f"Generated {len(_ama_sig):,} signals.")

                if st.session_state.get("ba_signals_ama") is not None:
                    _n = len(st.session_state["ba_signals_ama"])
                    st.caption(f"✅ {_n:,} signals ready  "
                               f"({_ama_stop_off}t offset · {_ama_tgt_mode} ×{_ama_tgt_mult:.1f})")

        # ZLO overlay data
        _ZLO_DISK = _SIGNALS_DIR / "ba_zlo_overlay.parquet"
        with controls.expander("ba_zlo", "📈 ZLO Overlay (optional)", expanded=False):
            zlo_file = st.file_uploader(
                "ZLO Export (.csv)", type=["csv"], key="upload_zlo",
                help="CSV from NT ZerolagExporter: DateTime,Open,High,Low,Close,Oscillator,BaseTrend,TrendState,signals…",
            )
            if zlo_file is not None:
                zlo_key = f"{zlo_file.name}_{zlo_file.size}"
                if st.session_state.get("ba_zlo_key") != zlo_key:
                    zlo_df = pd.read_csv(zlo_file, parse_dates=["DateTime"])
                    st.session_state["ba_zlo"] = zlo_df
                    st.session_state["ba_zlo_key"] = zlo_key
                    zlo_df.to_parquet(_ZLO_DISK, index=False)
                if st.session_state.get("ba_zlo") is not None:
                    st.caption(f"✅ {zlo_file.name}  |  {len(st.session_state['ba_zlo'])} bars")
            else:
                if "ba_zlo" not in st.session_state and _ZLO_DISK.exists():
                    st.session_state["ba_zlo"] = pd.read_parquet(_ZLO_DISK)
                if st.session_state.get("ba_zlo") is not None:
                    st.caption(f"✅ (auto-loaded from disk)  |  {len(st.session_state['ba_zlo'])} bars")

        # Always In (AID) flip-state overlay
        _AI_DISK = _SIGNALS_DIR / "ba_alwaysin_overlay.parquet"
        with controls.expander("ba_alwaysin", "🧭 Always In State (optional)", expanded=False):
            ai_file = st.file_uploader(
                "AlwaysIn flips (.csv)", type=["csv"], key="upload_alwaysin",
                help="CSV from the NT AlwaysIn indicator: Event,BarTime,BarNum,NewDir,…  (flip rows)",
            )
            if ai_file is not None:
                ai_key = f"{ai_file.name}_{ai_file.size}"
                if st.session_state.get("ba_alwaysin_key") != ai_key:
                    ai_df = pd.read_csv(ai_file, parse_dates=["BarTime"])
                    st.session_state["ba_alwaysin"] = ai_df
                    st.session_state["ba_alwaysin_key"] = ai_key
                    ai_df.to_parquet(_AI_DISK, index=False)
                if st.session_state.get("ba_alwaysin") is not None:
                    st.caption(f"✅ {ai_file.name}  |  {len(st.session_state['ba_alwaysin'])} flips")
            else:
                if "ba_alwaysin" not in st.session_state and _AI_DISK.exists():
                    st.session_state["ba_alwaysin"] = pd.read_parquet(_AI_DISK)
                if st.session_state.get("ba_alwaysin") is not None:
                    st.caption(f"✅ (auto-loaded from disk)  |  {len(st.session_state['ba_alwaysin'])} flips")

        # Stochastic (%K/%D) overlay
        _STOCH_DISK = _SIGNALS_DIR / "ba_stoch_overlay.parquet"
        with controls.expander("ba_stoch", "📊 Stochastic Overlay (optional)", expanded=False):
            stoch_file = st.file_uploader(
                "Stochastic export (.csv)", type=["csv"], key="upload_stoch",
                help="CSV from NT MyStochasticExporter: DateTime,Open,High,Low,Close,K,D,KSignalUp,KSignalDn,ZoneSignal",
            )
            if stoch_file is not None:
                stoch_key = f"{stoch_file.name}_{stoch_file.size}"
                if st.session_state.get("ba_stoch_key") != stoch_key:
                    stoch_df = pd.read_csv(stoch_file, parse_dates=["DateTime"])
                    st.session_state["ba_stoch"] = stoch_df
                    st.session_state["ba_stoch_key"] = stoch_key
                    stoch_df.to_parquet(_STOCH_DISK, index=False)
                if st.session_state.get("ba_stoch") is not None:
                    st.caption(f"✅ {stoch_file.name}  |  {len(st.session_state['ba_stoch'])} bars")
            else:
                if "ba_stoch" not in st.session_state and _STOCH_DISK.exists():
                    st.session_state["ba_stoch"] = pd.read_parquet(_STOCH_DISK)
                if st.session_state.get("ba_stoch") is not None:
                    st.caption(f"✅ (auto-loaded from disk)  |  {len(st.session_state['ba_stoch'])} bars")

        active_set = st.radio(
            "Active Signal Set",
            ["MC Signals", "RevFT Signals", "AMA Signals"],
            key="ba_active_signal_set",
            horizontal=True,
        )
        st.session_state["ba_signals"] = {
            "MC Signals":   st.session_state.get("ba_signals_mc"),
            "RevFT Signals": st.session_state.get("ba_signals_revft"),
            "AMA Signals":  st.session_state.get("ba_signals_ama"),
        }.get(active_set)

        bar_analysis.show_bar_analysis(sc_file=sc_file, contract=contract_label, nt_file=nt_file)

    with controls.tab_ctx(T, "portfolio"):
        portfolio.show_portfolio()

    with controls.tab_ctx(T, "wfa"):
        wfa_mod.show_wfa_tab()

    with controls.tab_ctx(T, "extras"):
        extras.show_extras_tab()

    with controls.tab_ctx(T, "prop"):
        prop_sim.show_prop_sim_tab()

    with controls.tab_ctx(T, "auction"):
        auction_tab.show_auction_tab()

    with controls.tab_ctx(T, "erc"):
        er_lookahead_tab.show_er_lookahead_tab()

    with controls.tab_ctx(T, "qs"):
        qs_tab.show_qs_tab()

    with controls.tab_ctx(T, "legs"):
        leg_labeler_tab.show_labeler_tab()

    # Render the status strip now that all tabs have populated session state.
    with status_ph:
        _render_status_strip()


main()
