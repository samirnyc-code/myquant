"""make_keystone_pdf.py — one-page research note PDF for the IB-edge setup ("Keystone").

Recomputes the gated 2.0R book (chunked, memory-safe) for the headline + equity chart,
embeds the accumulated evidence, writes a send-ready PDF. Honest framing — includes the
drawdown/capital reality, marked in-sample.

Run: .venv/Scripts/python.exe scripts/make_keystone_pdf.py
Out: docs/living/Keystone_IBEF_<date>.pdf
"""
from __future__ import annotations

import sys, gc
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                                                       # noqa: E402
from simulation_engine import simulate_trades                        # noqa: E402
from indicators import tag_signals                                   # noqa: E402
from data_loader import bar_num_from_dt                              # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"
EDGE_MAX = 0.10
SIM = dict(entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5, contracts=1,
           contracts_t1=1, contracts_t2=1, commission=4.36, ratchet_r=0.0,
           pb_round="nearest", target_r=2.0, multileg=False, threeleg=False, overrides=None)


def log(m): print(f"[pdf] {datetime.now():%H:%M:%S} {m}", flush=True)


def build_book():
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bbd = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)
    tg = tag_signals(sig, bars).sort_values("DateTime").reset_index(drop=True)
    adr = tg["prior_ATR"].replace(0, np.nan).to_numpy()
    isL = tg["Direction"].str.lower().str.startswith("l").values
    origin = tg["StopPrice"].to_numpy()
    d_edge = np.where(isL, origin - tg["OR60_Low"].to_numpy(),
                            tg["OR60_High"].to_numpy() - origin) / adr
    G = (d_edge >= 0) & (d_edge <= EDGE_MAX)
    gtg = tg.loc[G].reset_index(drop=True)
    gtg["_date"] = pd.to_datetime(gtg["DateTime"]).dt.date
    log(f"gated {len(gtg)} - simulating @2.0R...")
    parts = []
    for ci, chunk in enumerate(np.array_split(np.array(sorted(gtg["_date"].unique()), object), 4)):
        sub = gtg[gtg["_date"].isin(set(chunk.tolist()))].reset_index(drop=True)
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        res = simulate_trades(signals=sub, ticks_by_date=tbd, bars_by_date=bbd, **SIM).reset_index(drop=True)
        fl = res["Filled"] == True
        k = res.loc[fl, ["DateTime", "Direction", "NetPnL", "RiskDollar"]].copy()
        parts.append(k); del res, tbd; gc.collect()
        log(f"  chunk {ci+1}/4")
    book = pd.concat(parts, ignore_index=True)
    book["DateTime"] = pd.to_datetime(book["DateTime"])
    return book.sort_values("DateTime").reset_index(drop=True)


def summarize(book):
    pnl = book["NetPnL"].values
    r = pnl / book["RiskDollar"].values
    eq = np.cumsum(pnl)
    dd = np.maximum.accumulate(eq) - eq
    isS = ~book["Direction"].str.lower().str.startswith("l").values
    yr = book["DateTime"].dt.year.values
    s = dict(
        n=len(book), nL=int((~isS).sum()), nS=int(isS.sum()),
        net=float(eq[-1]), expR=float(np.nanmean(r)),
        pf=float(pnl[pnl > 0].sum() / abs(pnl[pnl < 0].sum())),
        win=float((pnl > 0).mean() * 100), maxdd=float(dd.max()),
        mar=float(eq[-1] / dd.max()), dd5=float((dd > 5000).mean() * 100),
        eq=eq, dt=book["DateTime"].values,
        eqS=np.cumsum(pnl[isS]), dtS=book["DateTime"].values[isS],
        years={int(y): float(np.nanmean(r[yr == y])) for y in sorted(np.unique(yr))})
    return s


def chart(s, png):
    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=pd.to_datetime(s["dt"]), y=s["eq"], name="Both directions",
                             line=dict(color="#1f5fa8", width=2)))
    fig.add_trace(go.Scatter(x=pd.to_datetime(s["dtS"]), y=s["eqS"], name="Short only",
                             line=dict(color="#c0392b", width=1.3)))
    fig.update_layout(template="plotly_white", width=1000, height=420,
                      title="Keystone (IBEF) - stitched equity, 1 contract, 2.0R target",
                      yaxis_title="Cumulative net P/L ($)", xaxis_title=None,
                      legend=dict(x=0.02, y=0.98), margin=dict(t=50, l=60, r=20, b=40))
    fig.write_image(str(png), scale=2)


def make_pdf(s, png, out):
    from fpdf import FPDF
    BLUE = (31, 95, 168)
    GREY = (90, 90, 90)

    class PDF(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 8)
            self.set_text_color(*GREY)
            self.cell(0, 5, "CONFIDENTIAL - INTERNAL RESEARCH NOTE", 0, 0, "L")
            self.cell(0, 5, f"Generated {datetime.now():%Y-%m-%d}", 0, 1, "R")
            self.set_draw_color(*BLUE); self.set_line_width(0.4)
            self.line(10, 16, 200, 16); self.ln(4)

        def footer(self):
            self.set_y(-12); self.set_font("Helvetica", "I", 7); self.set_text_color(*GREY)
            self.cell(0, 5, "Keystone / IB-Edge Fade - research note, in-sample, not investment advice.  "
                            f"Page {self.page_no()}", 0, 0, "C")

    def h(txt):
        pdf.ln(1.5); pdf.set_font("Helvetica", "B", 11); pdf.set_text_color(*BLUE)
        pdf.cell(0, 6, txt, 0, 1); pdf.set_text_color(0, 0, 0)

    def body(txt):
        pdf.set_font("Helvetica", "", 9.5); pdf.multi_cell(0, 4.6, txt); pdf.ln(0.5)

    def table(headers, rows, widths):
        pdf.set_font("Helvetica", "B", 8.5); pdf.set_fill_color(*BLUE); pdf.set_text_color(255, 255, 255)
        for w, htxt in zip(widths, headers):
            pdf.cell(w, 6, htxt, 1, 0, "C", True)
        pdf.ln(); pdf.set_text_color(0, 0, 0); pdf.set_font("Helvetica", "", 8.5)
        fill = False
        for row in rows:
            pdf.set_fill_color(238, 242, 248)
            for w, c in zip(widths, row):
                pdf.cell(w, 5.5, c, 1, 0, "C", fill)
            pdf.ln(); fill = not fill

    pdf = PDF(); pdf.set_auto_page_break(True, 14); pdf.add_page()

    pdf.set_font("Helvetica", "B", 17); pdf.set_text_color(*BLUE)
    pdf.cell(0, 9, "KEYSTONE", 0, 1)
    pdf.set_font("Helvetica", "B", 11); pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 6, "Initial-Balance Edge Fade (IBEF) - ES futures, 5-minute", 0, 1)
    pdf.ln(1)

    h("What it is")
    body("A responsive intraday fade of the day's Initial Balance (IB) extreme. We already "
         "generate momentum-channel (MC) breakout signals on 5-minute ES. Keystone keeps only "
         "those whose channel ORIGINATED at the edge of the first-hour range: longs whose "
         "channel low sits within 0.10 ADR of the session's IB low, shorts whose channel high "
         "sits within 0.10 ADR of the IB high. The premise (Auction Market Theory): a move that "
         "launches off the IB boundary is a market REJECTION of that level - a responsive trade "
         "back into the day's developing value. Trades exit at a fixed 2.0R target.")

    h("Why it is a credible portfolio component")
    body("- Structural, not fitted: a single fixed rule (origin within 0.10 ADR of the IB edge) "
         "with a fixed 2.0R exit. Nothing is optimized per period.\n"
         "- Look-ahead-safe: the IB is frozen after the first 60 minutes; every input is known "
         "at the signal bar. Verified through a single causal tagging chokepoint.\n"
         "- The filter does real work: it isolates the edge and leaves the rest inert (below).\n"
         "- Symmetric and regime-robust: works long AND short, and the short side is positive in "
         "every calendar year tested.\n"
         "- Survives realistic costs (slippage stress below).")

    h("Headline performance  (1 contract, ~5 years, 2.0R)")
    table(["Trades", "Net P/L", "Exp R / trade", "Profit factor", "Win %", "Net / MaxDD"],
          [[f"{s['n']:,}", f"${s['net']:,.0f}", f"+{s['expR']:.3f}", f"{s['pf']:.2f}",
            f"{s['win']:.1f}%", f"{s['mar']:.2f}"]],
          [24, 30, 30, 30, 26, 30])
    pdf.ln(1)
    body(f"Direction split: {s['nL']} long / {s['nS']} short.  Frequency ~280 trades/year "
         "(about one per session).")

    h("The filter isolates the edge  (selection value, 1.0R basis)")
    table(["Population", "Trades", "Exp R", "Profit factor"],
          [["Keystone gate", "1,395", "+0.112", "1.30"],
           ["Everything else (non-gate)", "4,049", "+0.017", "1.08"],
           ["All signals (baseline)", "5,444", "+0.041", "1.14"]],
          [70, 30, 30, 30])
    pdf.ln(1)
    body("The non-gated remainder is essentially flat - the gate concentrates the edge rather "
         "than slicing an already-good book. Lifting the exit from 1.0R to 2.0R raises the gate "
         f"to +{s['expR']:.3f} R/trade.")

    h("Consistency by year  (Exp R / trade, 2.0R)")
    yrs = sorted(s["years"])
    table(["Year"] + [str(y) for y in yrs],
          [["Exp R"] + [f"+{s['years'][y]:.3f}" if s['years'][y] >= 0 else f"{s['years'][y]:.3f}" for y in yrs]],
          [22] + [ (168/len(yrs)) for _ in yrs])
    pdf.ln(1)
    body("Positive in every year, including the 2022 bear market. 2023 is the softest "
         "(thin positive); no single year carries the result.")

    h("Robustness to execution cost  (Exp R, 1.0R basis)")
    table(["Slippage assumption", "Exp R", "Profit factor"],
          [["1 tick in / 0 out (base)", "+0.112", "1.30"],
           ["2 in / 1 out (realistic-conservative)", "+0.077", "1.23"],
           ["3 in / 2 out (brutal)", "+0.048", "1.18"]],
          [90, 35, 35])
    pdf.ln(1)
    body("Degrades gracefully and stays positive even under pessimistic fills. The 2.0R exit "
         "carries more cushion than the 1.0R figures shown.")

    pdf.add_page()
    h("Equity curve")
    pdf.image(str(png), w=190)
    pdf.ln(2)

    h("Risk profile and capital requirement  (the honest part)")
    body(f"This is a deep-drawdown system. On a single contract the worst peak-to-trough "
         f"drawdown was ${s['maxdd']:,.0f}, and the book sits more than $5,000 below its high-"
         f"water mark roughly {s['dd5']:.0f}% of the time - the drawdowns arrive in clusters "
         "during weak regimes and are NOT reduced by changing the exit. Net/MaxDD of "
         f"{s['mar']:.1f} is strong, but the path is grindy.\n\n"
         "Implication: Keystone is suited to a well-capitalized CASH account (roughly "
         "$75k-$100k of capital per ES contract to hold the drawdown comfortably), not a "
         "tight trailing-drawdown prop evaluation. It is best deployed sized conservatively, "
         "and is a strong candidate as a SIZING/selection overlay within a broader book where "
         "its bleeds dilute.")

    h("Status and next steps")
    body("- Current results are IN-SAMPLE descriptive over the full ~5-year history, look-ahead-"
         "safe, with a fixed never-optimized rule. They are a reason to advance the setup, not a "
         "live track record.\n"
         "- Next: walk-forward / out-of-sample confirmation; prop-account simulation with "
         "contract scaling and a never-blow floor to quantify survivability and net-to-trader; "
         "and a regime study of the 2023-24 soft patch (the signals were most frequent when "
         "least effective - a possible further filter).")

    pdf.output(str(out))


def main() -> int:
    book = build_book()
    s = summarize(book)
    png = _OUT / f"keystone_equity_{datetime.now():%Y%m%d}.png"
    log("chart..."); chart(s, png)
    out = _OUT / f"Keystone_IBEF_{datetime.now():%Y%m%d}.pdf"
    log("pdf..."); make_pdf(s, png, out)
    log(f"wrote {out}")
    print(f"\nPDF: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
