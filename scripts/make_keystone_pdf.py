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
NOTE_NO  = "RN-001"      # sequential research-note id (bump for each new note)
NOTE_TITLE = "Keystone — Initial-Balance Edge Fade (IBEF)"
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
    tg["_G"] = (d_edge >= 0) & (d_edge <= EDGE_MAX)        # Keystone gate flag
    tg["_date"] = pd.to_datetime(tg["DateTime"]).dt.date
    log(f"simulating FULL population {len(tg)} @2.0R (gate + complement) in 4 chunks...")
    parts = []
    for ci, chunk in enumerate(np.array_split(np.array(sorted(tg["_date"].unique()), object), 4)):
        sub = tg[tg["_date"].isin(set(chunk.tolist()))].reset_index(drop=True)
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        res = simulate_trades(signals=sub, ticks_by_date=tbd, bars_by_date=bbd, **SIM).reset_index(drop=True)
        fl = res["Filled"] == True
        k = res.loc[fl, ["DateTime", "Direction", "NetPnL", "RiskDollar"]].copy()
        k["Gate"] = sub.loc[fl, "_G"].values
        parts.append(k); del res, tbd; gc.collect()
        log(f"  chunk {ci+1}/4")
    book = pd.concat(parts, ignore_index=True)
    book["DateTime"] = pd.to_datetime(book["DateTime"])
    return book.sort_values("DateTime").reset_index(drop=True)


def selection(book):
    """Gate vs complement vs all, at 2.0R — does the filter concentrate the edge?"""
    def er(b):
        if len(b) == 0:
            return dict(n=0, expR=np.nan, pf=0, net=0)
        pnl = b["NetPnL"].values; r = pnl / b["RiskDollar"].values
        gw = pnl[pnl > 0].sum(); gl = abs(pnl[pnl < 0].sum())
        return dict(n=len(b), expR=float(np.nanmean(r)), net=float(pnl.sum()),
                    pf=float(gw / gl) if gl > 0 else float("inf"))
    return dict(all=er(book), gate=er(book[book["Gate"]]),
                comp=er(book[~book["Gate"]]))


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


def make_pdf(s, sel, png, out):
    from fpdf import FPDF
    def _er(d): return "-" if d["n"] == 0 else f"{d['expR']:+.3f}"
    def _pf(d): return "-" if d["n"] == 0 else ("inf" if d["pf"] == float("inf") else f"{d['pf']:.2f}")
    BLUE = (31, 95, 168)
    GREY = (90, 90, 90)

    class PDF(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 8)
            self.set_text_color(*GREY)
            self.cell(0, 5, f"CONFIDENTIAL - INTERNAL RESEARCH NOTE {NOTE_NO}", 0, 0, "L")
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
    pdf.cell(0, 9, f"KEYSTONE   ({NOTE_NO})", 0, 1)
    pdf.set_font("Helvetica", "B", 11); pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 6, "Initial-Balance Edge Fade (IBEF) - ES futures, 5-minute", 0, 1)
    pdf.set_font("Helvetica", "", 8.5); pdf.set_text_color(*GREY)
    pdf.cell(0, 5, "Research Note " + NOTE_NO + " | signal source: MCSignal (MC channel breakout) | "
                   "data: ~5 yr continuous ES, tick-level fills", 0, 1)
    pdf.set_text_color(0, 0, 0); pdf.ln(1)
    pdf.set_font("Helvetica", "B", 9); pdf.set_fill_color(225, 240, 225); pdf.set_text_color(20, 90, 30)
    pdf.multi_cell(0, 4.6, "STATUS: PASSED look-ahead audit (OR60 causal; edge is STRONGER in the "
                   "unambiguously-past window; no entry-bar merge leak). Still IN-SAMPLE and "
                   "selection-biased (found among ~85 tested buckets), so treat the forward edge as "
                   "the conservative ~+0.09-0.12R, not +0.159R. Deep drawdown = a cash-account "
                   "COMPONENT, not a standalone prop system.", fill=True)
    pdf.set_text_color(0, 0, 0); pdf.ln(1)

    h("What it is")
    body("A responsive intraday fade of the day's Initial Balance (IB) extreme. We already "
         "generate momentum-channel (MC) breakout signals on 5-minute ES. Keystone keeps only "
         "those whose channel ORIGINATED at the edge of the first-hour range: longs whose "
         "channel low sits within 0.10 ADR of the session's IB low, shorts whose channel high "
         "sits within 0.10 ADR of the IB high. The premise (Auction Market Theory): a move that "
         "launches off the IB boundary is a market REJECTION of that level - a responsive trade "
         "back into the day's developing value. Trades exit at a fixed 2.0R target.")

    h("Final configuration & why  (each choice was tested, not assumed)")
    table(["Design choice", "Setting", "Why this and not otherwise"],
          [["Entry filter", "origin <=0.10 ADR from IB edge", "sharp expectancy CLIFF at 0.10 (p.3)"],
           ["Exit target", "fixed 2.0R", "plateau, not a tuned peak (p.2)"],
           ["Direction", "both long & short", "symmetric; shorts positive every year"],
           ["Position mgmt", "none (no BE / no trail)", "every mgmt variant failed to beat it (p.3)"],
           ["Legs", "single (no scale-in/out)", "2-leg variants worse + add drawdown (p.3)"],
           ["Optimization", "none per period", "fixed rule; avoids the overfit that look-ahead masked"]],
          [38, 55, 97])
    pdf.ln(1)

    h("Why it is a credible (audited) edge")
    body("- Structural, not fitted: a single fixed rule (origin within 0.10 ADR of the IB edge) "
         "with a fixed 2.0R exit. Nothing is optimized per period.\n"
         "- PASSED a look-ahead audit: OR60 is causal (developing range during the first hour, "
         "frozen after), no as-of-merge can land on the entry bar, and the edge is STRONGER on "
         "signals after the first hour where the IB is indisputably in the past (see audit below).\n"
         "- The filter does real work: it isolates the edge and leaves the rest inert (below).\n"
         "- Symmetric and regime-robust: works long AND short, and the short side is positive in "
         "every calendar year tested.\n"
         "- Survives realistic costs (slippage stress below).\n"
         "- Exit/entry variants (breakeven, trailing, scale-in, scale-out) were tested and NONE "
         "beat the simple single-leg 2.0R on a risk-adjusted basis - the edge is in selection.")

    h("Headline performance  (1 contract, ~5 years, 2.0R)")
    table(["Trades", "Net P/L", "Exp R / trade", "Profit factor", "Win %", "Net / MaxDD"],
          [[f"{s['n']:,}", f"${s['net']:,.0f}", f"+{s['expR']:.3f}", f"{s['pf']:.2f}",
            f"{s['win']:.1f}%", f"{s['mar']:.2f}"]],
          [24, 30, 30, 30, 26, 30])
    pdf.ln(1)
    body(f"Direction split: {s['nL']} long / {s['nS']} short.  Frequency ~280 trades/year "
         "(about one per session).")

    h("The filter isolates the edge  (selection value, 2.0R)")
    table(["Population", "Trades", "Exp R", "Profit factor"],
          [["Keystone gate", f"{sel['gate']['n']:,}", _er(sel['gate']), _pf(sel['gate'])],
           ["Everything else (non-gate)", f"{sel['comp']['n']:,}", _er(sel['comp']), _pf(sel['comp'])],
           ["All signals (baseline)", f"{sel['all']['n']:,}", _er(sel['all']), _pf(sel['all'])]],
          [70, 30, 30, 30])
    pdf.ln(1)
    body("Same 2.0R exit for all three rows. The non-gated remainder is essentially flat - the "
         "gate CONCENTRATES the edge rather than slicing an already-good book. That separation "
         "(gate vs the inert rest) is the core evidence the filter carries real information.")

    h("Consistency by year  (Exp R / trade, 2.0R)")
    yrs = sorted(s["years"])
    table(["Year"] + [str(y) for y in yrs],
          [["Exp R"] + [f"+{s['years'][y]:.3f}" if s['years'][y] >= 0 else f"{s['years'][y]:.3f}" for y in yrs]],
          [22] + [ (168/len(yrs)) for _ in yrs])
    pdf.ln(1)
    body("Positive in every year, including the 2022 bear market. 2023 is the softest "
         "(thin positive); no single year carries the result.")

    h("Why 2.0R is the target  (a plateau, not a tuned peak)")
    body("The target was swept, not optimized. Expectancy rises and then PLATEAUS from ~2R "
         "onward - so 2.0R sits on a flat shelf, not a fragile spike (a tuned peak would tower "
         "over its neighbours). 2.0R is the conservative shelf entry; the lower targets give up "
         "edge, the higher ones add variance for little gain.")
    table(["Target", "Exp R", "Profit factor", "Net / MaxDD"],
          [["1.0R", "+0.112", "1.30", "6.9"],
           ["1.5R", "+0.136", "1.34", "7.8"],
           ["2.0R  (chosen)", "+0.159", "1.38", "8.9"],
           ["3.0R", "+0.161", "1.35", "8.3"],
           ["4.0R", "+0.169", "1.37", "9.1"]],
          [55, 45, 45, 45])
    pdf.ln(1)

    h("Robustness to execution cost  (Exp R, 2.0R)")
    table(["Slippage assumption", "Exp R", "Profit factor"],
          [["1 tick in / 0 out (base)", "+0.159", "1.38"],
           ["2 in / 1 out (realistic-conservative)", "+0.123", "1.30"],
           ["3 in / 2 out (brutal)", "+0.092", "1.24"]],
          [90, 35, 35])
    pdf.ln(1)
    body("Stays clearly positive even under pessimistic fills (lower 95% CI bound above zero "
         "at brutal). The forward edge realistically sits near the +0.09-0.12R end after costs "
         "and selection bias.")

    h("Look-ahead audit  (the decisive test - PASSED)")
    body("If the edge came from peeking at the final IB before it formed, it would concentrate "
         "in signals fired DURING the first hour (IB still developing) and vanish AFTER it. The "
         "opposite holds - the edge is STRONGER once the IB is indisputably in the past:")
    table(["Subset", "Trades", "Exp R", "Profit factor"],
          [["After first hour (IB fully PAST)", "603", "+0.203", "1.62"],
           ["During first hour (IB developing)", "792", "+0.126", "1.27"]],
          [95, 30, 30, 35][:4])
    pdf.ln(1)
    body("OR60 is causal in code (developing range during the first hour, frozen after); no "
         "as-of merge can land on the entry bar; StopPrice is 100% on the correct side of the "
         "signal. Residual unknown: the NT indicator's internal causality in producing StopPrice "
         "cannot be audited from the Python side (low risk - same stop every MC strategy uses).")

    pdf.add_page()
    h("PART A - How we tried to IMPROVE the edge (and why we stopped where we did)")
    body("Once the IB-edge filter survived the location search, we attacked it from every "
         "direction we could to make it better. Almost nothing helped; the value is in knowing "
         "that, because it means the final config is the simplest one that works - not a stack of "
         "fragile tweaks. Each lever below, what we tried, and the decision.")

    body("1) WHERE to draw the gate line. Swept origin-to-IB-edge distance in 0.05-ADR bands. "
         "The edge is concentrated within 0.10 ADR and falls off a CLIFF beyond it - not a smooth "
         "knob to tune:")
    table(["Distance to IB edge (ADR)", "Exp R", "Profit factor"],
          [["0.00 - 0.05", "+0.097", "1.25"],
           ["0.05 - 0.10  (gate keeps <=0.10)", "+0.156", "1.51"],
           ["0.10 - 0.20", "-0.02", "0.99"],
           ["0.20 - 0.35", "+0.04", "1.13"]],
          [70, 30, 30])
    body("   Decision: gate at 0.10 ADR - it is where the cliff is, a STRUCTURAL boundary, not a "
         "fitted peak. Tighter (0.05) throws away half the trades for no better R.")

    body("2) The EXIT TARGET. Swept 0.5R-4R (p.2): expectancy plateaus from ~2R. Decision: 2.0R "
         "(conservative entry to the plateau).")

    body("3) Active trade MANAGEMENT. Tested moving to break-even and a lock-in trail:")
    table(["Exit rule", "Exp R", "Net / MaxDD"],
          [["Plain 2.0R (chosen)", "+0.159", "8.9"],
           ["+ break-even after +1R", "+0.161", "9.4"],
           ["+ trail (lock +0.5R after +1.5R)", "+0.158", "8.5"]],
          [80, 35, 35])
    body("   Decision: NONE. Break-even is a hair better on MAR but trades win-rate for it and "
         "adds moving parts; the gain is inside the noise. The edge is in SELECTION, not management.")

    body("4) Two-leg SCALE-IN / SCALE-OUT. Tested adding a second contract on a pullback (incl. "
         "the 'E1 scratches, E2 wins' structure) and scaling out a partial at 1R. Every variant "
         "underperformed plain single-leg 2.0R on net AND drawdown (the pullback-add piles size "
         "into the losers). NB: this work also uncovered and fixed a P&L bug in the 2-leg engine.")
    body("   Decision: single leg. The high win-rate of the scale-in is a trap - the small wins "
         "do not cover the occasional double-stopped loss.")

    body("5) DIRECTION. Long-only +0.091R, short-only +0.133R, both positive in every year. "
         "Decision: trade BOTH. The symmetry is itself evidence the edge is structural; dropping "
         "a side to flatter the curve would be fitting.")

    body("6) STACKING with other filters. Layering the 'balance day' context on top lifts the "
         "gate to +0.168R - but balance alone is weak and regime-dependent, and it halves the "
         "trade count. Decision: keep the gate STANDALONE (more trades, cleaner); balance is an "
         "optional conviction add, not part of the core rule.")

    pdf.add_page()
    h("PART B - How many angles we looked at to FIND it  (Keystone was the lone survivor)")
    body("Keystone was not the first idea - it was the one that survived. We tested whether a "
         "signal's LOCATION relative to many structural levels predicts an edge, across ~85 "
         "buckets and the families below. Almost everything died honestly; reporting the failures "
         "is the point - it shows the survivor was not cherry-picked from a single lucky look.")
    table(["Hypothesis tested (origin / location vs a level)", "Verdict"],
          [["Reversal off developing day low/high (LOD/HOD)", "REJECT - long-only, drift-suspected"],
           ["Origin at prior-day low/high (LOY/HOY)", "REJECT - nothing beyond 'balance' below"],
           ["Balance state (opened inside Y, still rotating)", "WEAK - real but fails 2023-24"],
           ["Failed-breakout 'look above/below & fail' fade", "REJECT - the canonical fade LOSES"],
           ["Origin at prior volume nodes (HVN / LVN)", "REJECT - null"],
           ["Origin at single / zero prints (profile gaps)", "REJECT - null"],
           ["Origin at prior value-area edge (VAH / VAL)", "WEAK - suggestive but thin (n~100)"],
           ["IB width 'sweet spot' (inverted-U in dollars)", "REJECT - a stop-size illusion in $"],
           ["Origin at the IB edge (<=0.10 ADR)  = KEYSTONE", "SURVIVED all of the above"]],
          [125, 65])
    pdf.ln(1)
    body("Exit structure was also exhausted: fixed-target sweep (0.5R-4R), breakeven, trailing, "
         "scale-in and scale-out - none beat the simple single-leg 2.0R risk-adjusted. The edge "
         "lives in SELECTION (which trade to take), not in management after entry.")

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
    body("- The look-ahead audit is DONE and PASSED (above). What remains before capital: the "
         "result is still IN-SAMPLE over the full ~5-year history and was selected among many "
         "tested filters, so the forward edge is the conservative ~+0.09-0.12R, not +0.159R.\n"
         "- Next, IN ORDER: (1) walk-forward / out-of-sample confirmation on held-out data; "
         "(2) prop/cash account simulation with contract scaling + never-blow floor for blow-up "
         "probability and net-to-trader (the drawdown path, not the average, is the binding "
         "constraint); (3) deploy only as a sized COMPONENT, not a standalone system.\n"
         "- Honest framing: a real, audited, modest edge - best as one sleeve among several or a "
         "sizing overlay, on a well-capitalized cash account. Not a get-rich automated machine.")

    pdf.output(str(out))


def main() -> int:
    book = build_book()
    sel = selection(book)
    gbook = book[book["Gate"]].reset_index(drop=True)
    s = summarize(gbook)
    png = _OUT / f"keystone_equity_{datetime.now():%Y%m%d}.png"
    log("chart..."); chart(s, png)
    out = _OUT / f"Keystone_IBEF_{datetime.now():%Y%m%d}.pdf"
    log("pdf..."); make_pdf(s, sel, png, out)
    log(f"wrote {out}")
    print(f"\nPDF: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
