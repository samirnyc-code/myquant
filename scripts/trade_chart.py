"""Trade-card chart (S75) — an annotated snapshot of a trade at OPEN and CLOSE.

Renders the intraday underlying with the strategy's strikes, breakevens, shaded
profit/loss zones, the MenthorQ levels, the projected EOD price paths, the intended
exit, and OUTCOME PROBABILITIES (from the MQ 1-day expected-move range) — as a dark,
labeled PNG (archival, dropped in the tradelog) AND an interactive Plotly HTML.

Price series (see chat): SPX is a cash index (RTH only), so "PA to the left" comes
from ES futures overnight, basis-adjusted into SPX terms (basis = median ES−SPX over
the RTH overlap). Annotation layer is delay-immune; price is finalized bars.

Prototype entry (today's fired GW0 butterfly):
  .venv/Scripts/python.exe scripts/trade_chart.py --trade auto_20260716_090122 --when open
"""
import argparse
import datetime as dt
import json
import math
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    sys.stdout.reconfigure(encoding="utf-8")   # console is cp1252; we print σ, ±, −
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
SCRATCH = ROOT / "scratchpad"
CARDS = ROOT / "data" / "options_log" / "cards"
CT = ZoneInfo("America/Chicago")

# ---- palette (dataviz reference, dark surface) --------------------------------
BG, SURF = "#0d0d0d", "#1a1a19"
INK, INK2, MUT = "#ffffff", "#c3c2b7", "#898781"
GRID, AXLINE = "#2c2c2a", "#383835"
GOOD, CRIT, WARN = "#0ca30c", "#d03b3b", "#fab219"   # status: profit / loss / caution
PRICE = "#3987e5"        # series-1 blue — SPX (RTH)
NIGHT = "#5f6f8a"        # dimmer — overnight ES (basis-adj)
WING = "#e8ebf0"         # OUR long-wing strikes (neutral white — not an MQ level)
PATH_A, PATH_C = "#199e70", "#d55181"  # aqua / magenta — projected paths

# ---- MenthorQ level color coding (PROPOSED — confirm/adjust) -------------------
# CR call-resistance=red · PS put-support=green · HVL=blue · GW gamma-wall=gold ·
# GEX=violet · 1D expected range=amber. (No color codes shipped in the MQ API/scrape.)
MQ = {"cr": "#e34948", "cr0": "#e34948", "ps": "#1baf7a", "ps0": "#1baf7a",
      "hvl": "#3987e5", "gw0": "#eda100", "d1": "#fab219", "gex": "#9085e9"}
PIN = MQ["gw0"]          # short×2 sits on GW0/CR0 (the wall/pin the fly targets)


def _decollide(items, min_gap):
    """items: list of [y, ...]. Nudge y's apart (in order) so adjacent ≥ min_gap.
    Returns new y's preserving order. Prevents label text overlap (req: never overlap)."""
    ys = sorted(range(len(items)), key=lambda i: items[i][0])
    out = list(items)
    prev = None
    for idx in ys:
        y = items[idx][0]
        if prev is not None and y - prev < min_gap:
            y = prev + min_gap
        out[idx] = (y,) + tuple(items[idx][1:])
        prev = y
    return out


def load_trade(trade_id, date):
    gp = json.loads((SIM / f"gameplan_{date}.json").read_text(encoding="utf-8"))
    trig = next((t for t in gp["triggers"] if t.get("trade_id") == trade_id), None)
    if not trig:
        raise SystemExit(f"trade {trade_id} not in gameplan_{date}.json")
    return gp, trig


def butterfly_payoff(lo, ctr, hi, debit, S):
    """Long call fly P&L (points) at expiry for underlying S."""
    return (max(S - lo, 0) - 2 * max(S - ctr, 0) + max(S - hi, 0)) - debit


def load_series():
    """Combined overnight(ES-adj) + RTH(SPX) price in SPX terms."""
    f = SCRATCH / "pa_today.json"
    if not f.exists():
        return [], [], [], []
    d = json.loads(f.read_text())
    on = [(dt.datetime.fromisoformat(p["t"]), p["c"]) for p in d["series"] if p["src"] == "ES_adj"]
    rt = [(dt.datetime.fromisoformat(p["t"]), p["c"]) for p in d["series"] if p["src"] in ("SPX", "TAPE")]
    return ([x for x, _ in on], [y for _, y in on], [x for x, _ in rt], [y for _, y in rt])


def norm_cdf(x, mu, sigma):
    return 0.5 * (1 + math.erf((x - mu) / (sigma * math.sqrt(2))))


def price_at(xr, yr, t):
    """Price on the tape AT time t (interpolated) — NOT the last tape point.
    Fixes the fill-marker bug: the fill sits on the price when the order was placed."""
    if not xr:
        return None
    pairs = sorted(zip(xr, yr))
    if t <= pairs[0][0]:
        return pairs[0][1]
    prev = pairs[0]
    for x, y in pairs[1:]:
        if x >= t:
            frac = (t - prev[0]) / (x - prev[0])
            return prev[1] + frac * (y - prev[1])
        prev = (x, y)
    return pairs[-1][1]


def compute(gp, trig):
    st = trig["structure"]
    lo, ctr, hi = st["lower"], st["center"], st["upper"]
    debit = -trig["fill"]["net"]                 # net negative for a debit
    be_lo, be_hi = lo + debit, hi - debit
    max_gain = (ctr - lo - debit) * 100
    max_loss = debit * 100
    fill_ct = dt.datetime.strptime(gp["date"] + " " + trig["fill"]["at"],
                                   "%Y%m%d %H:%M:%S").replace(tzinfo=CT)

    # spot AT FILL (interpolated from the realtime tape) — the price when the order
    # was placed, not the last tape point. Drives the fill marker AND the probabilities.
    _, _, xr, yr = load_series()
    spot = price_at(xr, yr, fill_ct) if yr else gp.get("spot_preopen", ctr)
    d1lo, d1hi = gp.get("d1_min"), gp.get("d1_max")
    sigma_full = (d1hi - d1lo) / 2 if (d1lo and d1hi) else 55.0   # ±1σ ≈ half the exp range
    close_ct = dt.datetime.strptime(gp["date"] + " 15:00", "%Y%m%d %H:%M").replace(tzinfo=CT)
    open_ct = dt.datetime.strptime(gp["date"] + " 08:30", "%Y%m%d %H:%M").replace(tzinfo=CT)
    frac = max(0.05, (close_ct - fill_ct) / (close_ct - open_ct))
    sigma = sigma_full * math.sqrt(frac)         # scale to time-to-close

    pop = norm_cdf(be_hi, spot, sigma) - norm_cdf(be_lo, spot, sigma)
    p_maxloss = norm_cdf(lo, spot, sigma) + (1 - norm_cdf(hi, spot, sigma))
    p_pin = norm_cdf(ctr + 10, spot, sigma) - norm_cdf(ctr - 10, spot, sigma)
    # expected value: numeric integral of payoff($) × normal pdf
    ev = 0.0
    step = 1.0
    for S in range(int(spot - 4 * sigma), int(spot + 4 * sigma), int(step)):
        pdf = math.exp(-0.5 * ((S - spot) / sigma) ** 2) / (sigma * math.sqrt(2 * math.pi))
        ev += butterfly_payoff(lo, ctr, hi, debit, S) * 100 * pdf * step

    return dict(lo=lo, ctr=ctr, hi=hi, debit=debit, be_lo=be_lo, be_hi=be_hi,
               max_gain=max_gain, max_loss=max_loss, levels=gp["levels"], fill_ct=fill_ct,
               grade=trig.get("projected_grade"), name=trig["name"], regime=gp.get("regime"),
               width=st["width"], spot=spot, sigma=sigma, d1lo=d1lo, d1hi=d1hi,
               pop=pop, p_maxloss=p_maxloss, p_pin=p_pin, ev=ev)


# ---- PNG (matplotlib) ---------------------------------------------------------
def render_png(gp, trig, c, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    date = gp["date"]
    close_ct = dt.datetime.strptime(date + " 15:00", "%Y%m%d %H:%M").replace(tzinfo=CT)
    xon, yon, xrt, yrt = load_series()
    x_start = xon[0] if xon else (xrt[0] if xrt else c["fill_ct"])

    fig = plt.figure(figsize=(15, 7.8), facecolor=BG)
    gs = fig.add_gridspec(1, 2, width_ratios=[4.6, 1.05], wspace=0.04)
    ax = fig.add_subplot(gs[0]); axp = fig.add_subplot(gs[1])
    for a in (ax, axp):
        a.set_facecolor(SURF)
        for s in a.spines.values():
            s.set_color(AXLINE)
        a.tick_params(colors=MUT, labelsize=9)

    ylo, yhi = 7500, 7660
    ax.set_xlim(x_start, close_ct); ax.set_ylim(ylo, yhi)

    # profit / loss zones (faint backgrounds; MQ level lines carry the color)
    ax.axhspan(c["be_lo"], c["be_hi"], color=GOOD, alpha=0.08, zorder=0)
    ax.axhspan(ylo, c["be_lo"], color=CRIT, alpha=0.06, zorder=0)
    ax.axhspan(c["be_hi"], yhi, color=CRIT, alpha=0.06, zorder=0)

    # ---- horizontal lines (MQ color coding) --------------------------------
    lv = c["levels"]
    linespec = [   # (y, color, lw, linestyle)
        (c["d1lo"], MQ["d1"], 0.9, (0, (5, 4))), (c["d1hi"], MQ["d1"], 0.9, (0, (5, 4))),
        (lv.get("hvl"), MQ["hvl"], 1.3, ":"), (lv.get("ps0"), MQ["ps0"], 1.5, "-"),
        (c["lo"], WING, 1.4, "-"), (c["hi"], WING, 1.4, "-"),
        (c["be_lo"], INK2, 1.0, "--"), (c["be_hi"], INK2, 1.0, "--"),
        (c["ctr"], MQ["gw0"], 2.4, "-"),
    ]
    for y, col, lw, ls in linespec:
        if y and ylo < y < yhi:
            ax.axhline(y, color=col, lw=lw, ls=ls, alpha=0.85, zorder=2)

    # labels: right-edge, staggered LEFT within a cluster so text NEVER overlaps
    labels = [(c["d1lo"], f"1D min {c['d1lo']:.0f}", MQ["d1"], False),
              (lv.get("hvl"), f"HVL {lv.get('hvl'):.0f}", MQ["hvl"], False) if lv.get("hvl") else None,
              (lv.get("ps0"), f"PS0 {lv.get('ps0'):.0f}", MQ["ps0"], False) if lv.get("ps0") else None,
              (c["lo"], f"long {c['lo']:.0f}", WING, False),
              (c["be_lo"], f"BE {c['be_lo']:.2f}", INK2, False),
              (c["ctr"], f"GW0·CR0 {c['ctr']:.0f} · short×2", MQ["gw0"], True),
              (c["be_hi"], f"BE {c['be_hi']:.2f}", INK2, False),
              (c["hi"], f"long {c['hi']:.0f}", WING, False),
              (c["d1hi"], f"1D max {c['d1hi']:.0f}", MQ["d1"], False)]
    labels = [l for l in labels if l and l[0] and ylo < l[0] < yhi]
    labels.sort(key=lambda t: t[0])
    span_min = (close_ct - x_start).total_seconds() / 60
    LEFT_Y = 7576   # levels at/below here → LEFT gutter (clear space below the overnight line);
    col_i, last = 0, None   # upper levels → RIGHT, staggered. Split keeps text off the price/fill.
    for y, text, col, bold in labels:
        if y <= LEFT_Y:
            ax.text(x_start + dt.timedelta(minutes=0.01 * span_min), y, " " + text, color=col,
                    va="center", ha="left", fontsize=8, fontweight="bold" if bold else "normal",
                    zorder=9, bbox=dict(boxstyle="round,pad=0.16", fc=BG, ec="none", alpha=0.92))
            continue
        col_i = col_i + 1 if (last is not None and y - last < 4.6) else 0
        lx = close_ct - dt.timedelta(minutes=(0.02 + col_i * 0.11) * span_min)
        ax.text(lx, y, text + " ", color=col, va="center", ha="right",
                fontsize=8, fontweight="bold" if bold else "normal", zorder=9,
                bbox=dict(boxstyle="round,pad=0.16", fc=BG, ec="none", alpha=0.92))
        last = y

    # ---- price: overnight (ES-adj) dim, RTH (realtime tape) bright ----------
    if xon:
        ax.plot(xon, yon, color=NIGHT, lw=1.4, zorder=4, label="overnight (ES→SPX)")
    if xrt:
        ax.plot(xrt, yrt, color=PRICE, lw=2.4, zorder=5, label="SPX realtime (parity tape)")
    fy = c["spot"]   # price AT fill (interpolated tape), not last point

    ax.scatter([c["fill_ct"]], [fy], s=95, color=PRICE, edgecolor=INK, lw=1.4, zorder=7)
    ax.annotate(f"FILL {c['fill_ct']:%H:%M} · {fy:.0f} · debit {c['debit']:.2f}",
                (c["fill_ct"], fy), xytext=(14, -34), textcoords="offset points",
                color=INK, fontsize=8.5, fontweight="bold", zorder=10,
                arrowprops=dict(arrowstyle="-", color=MUT, lw=0.8),
                bbox=dict(boxstyle="round,pad=0.25", fc=SURF, ec=AXLINE, alpha=0.92))

    for col, tgt, nm in [(PATH_A, c["ctr"], "path A · grind to wall"),
                         (PATH_C, c["ctr"] - 6, "path C · pin (base)")]:
        ax.plot([c["fill_ct"], close_ct], [fy, tgt], color=col, lw=1.8, ls="--",
                alpha=0.9, zorder=4, label=nm)

    ax.axvline(close_ct, color=WARN, lw=1.2, ls=":", alpha=0.8, zorder=3)
    ax.text(close_ct, 7524, "EXIT 15:00 · cash-settle ", color=WARN, fontsize=8,
            ha="right", va="center", fontweight="bold", zorder=9,
            bbox=dict(boxstyle="round,pad=0.16", fc=BG, ec="none", alpha=0.92))

    # ---- reasoning box (req 6): why this fired — matches the gameplan -------
    reasons = [f"Regime {trig.get('arm', {}).get('regime', '?')} — spot ≥ HVL {lv.get('hvl'):.0f}",
               f"Fired ≥ {trig.get('fire', {}).get('not_before', '?')} CT (filled {trig['fill']['at']})",
               f"In window {'–'.join(trig.get('window', ['?', '?']))} CT",
               f"Grade {c['grade']}: {trig.get('grade_basis', '')}"]
    box = "WHY THIS TRADE  (per gameplan)\n" + "\n".join(f"✓  {r}" for r in reasons)
    ax.text(0.014, 0.975, box, transform=ax.transAxes, va="top", ha="left",
            fontsize=8.4, color=INK, linespacing=1.5, zorder=10,
            bbox=dict(boxstyle="round,pad=0.5", fc="#12140f", ec=GOOD, alpha=0.94))

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%d %H:%M", tz=CT))
    ax.set_ylabel("SPX (index terms)", color=INK2, fontsize=10)
    ax.grid(color=GRID, lw=0.6, alpha=0.5)
    ax.legend(loc="lower left", bbox_to_anchor=(0.63, 0.0), facecolor=SURF, edgecolor=AXLINE,
              labelcolor=INK2, fontsize=8, framealpha=0.92)

    # --- payoff tent (right), shares price y-axis, $ increments ---
    axp.set_ylim(ylo, yhi)
    Sgrid = list(range(ylo, yhi + 1, 1))
    pnl = [butterfly_payoff(c["lo"], c["ctr"], c["hi"], c["debit"], s) * 100 for s in Sgrid]
    axp.plot(pnl, Sgrid, color=INK2, lw=1.6, zorder=5)
    axp.fill_betweenx(Sgrid, 0, pnl, where=[p >= 0 for p in pnl], color=GOOD, alpha=0.35)
    axp.fill_betweenx(Sgrid, 0, pnl, where=[p < 0 for p in pnl], color=CRIT, alpha=0.30)
    axp.axvline(0, color=AXLINE, lw=1)
    xt = list(range(-500, 2501, 500))
    axp.set_xticks(xt)
    axp.set_xticklabels([("+" if t > 0 else "") + f"${t:,}" if t else "$0" for t in xt],
                        fontsize=7.2, rotation=45)
    axp.set_xlim(-600, 2600)
    axp.set_xlabel("P&L @ expiry", color=MUT, fontsize=8.5)
    axp.tick_params(labelleft=False)
    axp.grid(color=GRID, lw=0.5, alpha=0.4, axis="x")
    axp.text(c["max_gain"], c["ctr"], f" +\\${c['max_gain']:,.0f}", color=GOOD,
             fontsize=8.5, fontweight="bold", va="bottom")
    axp.text(-c["max_loss"], ylo + 6, f"-\\${c['max_loss']:,.0f}", color=CRIT, fontsize=8)

    # header + probabilities
    fig.suptitle(f"{c['name']}   ·   {gp['date']}   ·   grade {c['grade']}   ·   {c['regime']}",
                 color=INK, fontsize=15, fontweight="bold", x=0.5, y=0.985)
    sub = (f"debit {c['debit']:.2f}     max gain +\\${c['max_gain']:,.0f}     "
           f"max loss -\\${c['max_loss']:,.0f}     BE {c['be_lo']:.2f}–{c['be_hi']:.2f}     width {c['width']}")
    fig.text(0.5, 0.945, sub, color=INK2, fontsize=10.5, ha="center")
    ev_col = GOOD if c["ev"] >= 0 else CRIT
    prob = (f"POP {c['pop']*100:.0f}%        P(max loss) {c['p_maxloss']*100:.0f}%        "
            f"P(±10 of pin) {c['p_pin']*100:.0f}%")
    fig.text(0.5, 0.912, prob, color=INK, fontsize=11, ha="center", fontweight="bold")
    fig.text(0.5, 0.884, f"EV {'+' if c['ev']>=0 else '−'}\\${abs(c['ev']):,.0f}     ·     "
             f"1σ to close ±{c['sigma']:.0f} pts  (from MQ 1-day expected range)",
             color=ev_col, fontsize=9.5, ha="center")

    CARDS.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    return out


# ---- HTML (plotly) ------------------------------------------------------------
def render_html(gp, trig, c, out):
    import plotly.graph_objects as go
    date = gp["date"]
    close_ct = dt.datetime.strptime(date + " 15:00", "%Y%m%d %H:%M").replace(tzinfo=CT)
    xon, yon, xrt, yrt = load_series()
    x_start = xon[0] if xon else (xrt[0] if xrt else c["fill_ct"])
    fy = c["spot"]   # price AT fill (interpolated tape), not last point
    ylo, yhi = 7500, 7660

    fig = go.Figure()
    fig.add_hrect(y0=c["be_lo"], y1=c["be_hi"], fillcolor=GOOD, opacity=0.10, line_width=0)
    fig.add_hrect(y0=ylo, y1=c["be_lo"], fillcolor=CRIT, opacity=0.08, line_width=0)
    fig.add_hrect(y0=c["be_hi"], y1=yhi, fillcolor=CRIT, opacity=0.08, line_width=0)
    for v, lbl in [(c["d1lo"], "1D exp min"), (c["d1hi"], "1D exp max")]:
        if v:
            fig.add_hline(y=v, line=dict(color=WARN, width=1, dash="dash"),
                          annotation_text=f"{lbl} {v:.0f}", annotation_font_color=WARN)
    for key, lbl in [("hvl", "HVL"), ("ps0", "PS0")]:
        v = c["levels"].get(key)
        if v:
            fig.add_hline(y=v, line=dict(color=MUT, width=1, dash="dot"),
                          annotation_text=f"{lbl} {v:.0f}", annotation_font_color=MUT)
    fig.add_hline(y=c["ctr"], line=dict(color=PIN, width=2.4),
                  annotation_text=f"short×2 {c['ctr']:.0f} (GW0)", annotation_font_color=PIN)
    for v in (c["lo"], c["hi"]):
        fig.add_hline(y=v, line=dict(color=WING, width=1.6),
                      annotation_text=f"long {v:.0f}", annotation_font_color=WING)
    for v in (c["be_lo"], c["be_hi"]):
        fig.add_hline(y=v, line=dict(color=INK2, width=1, dash="dash"),
                      annotation_text=f"BE {v:.2f}", annotation_font_color=INK2)
    if xon:
        fig.add_trace(go.Scatter(x=xon, y=yon, mode="lines", name="overnight (ES, adj)",
                                 line=dict(color=NIGHT, width=1.4),
                                 hovertemplate="%{x|%m/%d %H:%M}  %{y:.1f}<extra>ES-adj</extra>"))
    if xrt:
        fig.add_trace(go.Scatter(x=xrt, y=yrt, mode="lines", name="SPX (RTH)",
                                 line=dict(color=PRICE, width=2.6),
                                 hovertemplate="%{x|%H:%M}  %{y:.2f}<extra>SPX</extra>"))
    fig.add_trace(go.Scatter(x=[c["fill_ct"]], y=[fy], mode="markers+text", name="fill",
                             text=[f"FILL {c['fill_ct']:%H:%M} · debit {c['debit']:.2f}"],
                             textposition="bottom right", textfont=dict(color=INK),
                             marker=dict(color=PRICE, size=13, line=dict(color=INK, width=1.5))))
    for col, tgt, nm in [(PATH_A, c["ctr"], "path A · grind"),
                         (PATH_C, c["ctr"] - 6, "path C · pin")]:
        fig.add_trace(go.Scatter(x=[c["fill_ct"], close_ct], y=[fy, tgt], mode="lines",
                                 name=nm, line=dict(color=col, width=2, dash="dash")))
    fig.add_vline(x=close_ct.timestamp() * 1000, line=dict(color=WARN, width=1.2, dash="dot"),
                  annotation_text="EXIT 15:00 · cash-settle", annotation_font_color=WARN)

    ev_txt = f"{'+' if c['ev']>=0 else '−'}${abs(c['ev']):,.0f}"
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=SURF,
        title=dict(text=(f"<b>{c['name']}</b> · {date} · grade {c['grade']} · {c['regime']}<br>"
                         f"<span style='font-size:13px;color:{INK2}'>debit {c['debit']:.2f} · "
                         f"max gain +${c['max_gain']:,.0f} · max loss -${c['max_loss']:,.0f} · "
                         f"BE {c['be_lo']:.2f}–{c['be_hi']:.2f}</span><br>"
                         f"<span style='font-size:13px;color:#fab219'>POP {c['pop']*100:.0f}% · "
                         f"P(max loss) {c['p_maxloss']*100:.0f}% · P(±10 pin) {c['p_pin']*100:.0f}% · "
                         f"EV {ev_txt} · 1σ ±{c['sigma']:.0f}</span>"), font_color=INK),
        xaxis=dict(range=[x_start, close_ct], gridcolor=GRID, title="Exchange time (CT)"),
        yaxis=dict(range=[ylo, yhi], gridcolor=GRID, title="SPX (index terms)"),
        legend=dict(bgcolor=SURF, bordercolor=AXLINE, borderwidth=1),
        margin=dict(l=60, r=30, t=120, b=50), height=700)
    CARDS.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(out), include_plotlyjs="cdn")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trade", default="auto_20260716_090122")
    ap.add_argument("--date", default="20260716")
    ap.add_argument("--when", default="open", choices=["open", "close"])
    args = ap.parse_args()

    gp, trig = load_trade(args.trade, args.date)
    c = compute(gp, trig)
    png = CARDS / f"{args.trade}_{args.when}.png"
    html = CARDS / f"{args.trade}_{args.when}.html"
    render_png(gp, trig, c, png)
    render_html(gp, trig, c, html)
    print(f"PNG  -> {png}")
    print(f"HTML -> {html}")
    print(f"  {c['name']} | debit {c['debit']:.2f} | maxG +${c['max_gain']:,.0f} "
          f"maxL -${c['max_loss']:,.0f} | BE {c['be_lo']:.2f}-{c['be_hi']:.2f}")
    print(f"  POP {c['pop']*100:.0f}% | P(maxloss) {c['p_maxloss']*100:.0f}% | "
          f"P(pin±10) {c['p_pin']*100:.0f}% | EV {'+' if c['ev']>=0 else '-'}${abs(c['ev']):,.0f} "
          f"| 1σ ±{c['sigma']:.0f} (spot {c['spot']:.1f})")


if __name__ == "__main__":
    main()
