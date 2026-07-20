"""Trade-card chart (S75) — an annotated 5M RTH snapshot of a trade at OPEN and CLOSE.

Generalized 2026-07-20 (was a GW0-butterfly prototype): works for every structure the
desk trades — vertical credit/debit spreads, butterflies, straddles. Renders:

  * 5M RTH candles built from the realtime parity tape (+ dim overnight ES-adj line)
  * every MenthorQ level + the trade's strikes + computed breakevens, all labeled
  * shaded WIN / LOSS zones from the actual expiry payoff (not hand-drawn)
  * ENTRY marker at the fill (interpolated tape price at order time); on --when close
    also the EXIT marker, realized P&L and the daemon's close reason
  * metrics header: credit/debit, max gain/loss, POP, P(max loss), EV, 1-sigma
  * a WHY box (fire reason + grade basis, straight from the gameplan) and, at close,
    an OUTCOME box (what ended it and what it cost/made)
  * generic payoff tent sharing the price axis

Auto-called by options_trigger_daemon at fire and at close. Manual:
  .venv/Scripts/python.exe scripts/trade_chart.py --trade auto_20260720_090212 --when open
"""
import argparse
import datetime as dt
import json
import math
import re
import sys
import textwrap
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    sys.stdout.reconfigure(encoding="utf-8")   # console is cp1252; we print sigma etc.
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
GOOD, CRIT, WARN = "#0ca30c", "#d03b3b", "#fab219"
PRICE = "#3987e5"
NIGHT = "#5f6f8a"
WING = "#e8ebf0"           # OUR strikes (neutral white — not an MQ level)
UP, DN = "#26a69a", "#ef5350"   # candle bodies
MQ = {"cr": "#e34948", "cr0": "#e34948", "ps": "#1baf7a", "ps0": "#1baf7a",
      "hvl": "#3987e5", "gw0": "#eda100", "d1": "#fab219", "gex": "#9085e9"}


# ---- structure model ----------------------------------------------------------
def struct_legs(trig):
    """[(qty, right, strike)] with sign: +long / -short. Prefers ACTUAL filled legs
    (the straddle's ATM strike only exists at fill); falls back to the plan."""
    fl = trig.get("filled_legs")
    if fl:
        return [((1 if l.get("side", "buy") == "buy" else -1) * l.get("qty", 1),
                 l["right"], float(l["strike"])) for l in fl]
    st = trig["structure"]
    k = st.get("kind")
    if k == "vertical":
        return [(-1, st["right"], float(st["short"])), (1, st["right"], float(st["long"]))]
    if k == "butterfly":
        r = st.get("right", "C")
        return [(1, r, float(st["lower"])), (-2, r, float(st["center"])),
                (1, r, float(st["upper"]))]
    raise SystemExit(f"no legs derivable for structure {st}")


def payoff_pts(legs, net, S):
    """Expiry P&L in POINTS at underlying S. net: +credit received / -debit paid."""
    v = sum(q * (max(S - k, 0) if r == "C" else max(k - S, 0)) for q, r, k in legs)
    return v + net


def breakevens(legs, net, lo, hi):
    """Zero crossings of the payoff on [lo, hi], found on a 0.25pt grid."""
    bes, step = [], 0.25
    prev_s, prev_p = lo, payoff_pts(legs, net, lo)
    s = lo + step
    while s <= hi:
        p = payoff_pts(legs, net, s)
        if (prev_p < 0) != (p < 0):
            bes.append(prev_s + step * abs(prev_p) / (abs(prev_p) + abs(p) + 1e-12))
        prev_s, prev_p = s, p
        s += step
    return bes


# ---- data ---------------------------------------------------------------------
def load_trade(trade_id, date):
    """The daemon spawns this renderer right at fire time, possibly BEFORE it has
    persisted the gameplan with the new trade_id — retry briefly instead of dying."""
    import time
    for _ in range(6):
        gp = json.loads((SIM / f"gameplan_{date}.json").read_text(encoding="utf-8"))
        trig = next((t for t in gp["triggers"] if t.get("trade_id") == trade_id), None)
        if trig:
            return gp, trig
        time.sleep(5)
    raise SystemExit(f"trade {trade_id} not in gameplan_{date}.json")


def load_log_row(trade_id):
    try:
        import pandas as pd
        d = pd.read_parquet(ROOT / "data" / "options_log" / "trades.parquet")
        r = d[d["trade_id"] == trade_id]
        return r.iloc[-1].to_dict() if len(r) else {}
    except Exception:
        return {}


def load_series(date):
    """RTH SPX tape from the sim daemon's live quote log (underlying_YYYYMMDD.csv,
    ts on the exchange clock). Replaces the stale pa_today.json prototype source —
    which froze on 2026-07-16 and silently fed every chart a 4-day-old price."""
    f = SIM / f"underlying_{date}.csv"
    if not f.exists():
        return [], [], [], []
    xr, yr = [], []
    day = dt.datetime.strptime(date, "%Y%m%d").date()
    for ln in f.read_text().splitlines()[1:]:
        try:
            ts, px = ln.split(",")
            h, m, s = (int(v) for v in ts.split(":"))
            xr.append(dt.datetime.combine(day, dt.time(h, m, s), tzinfo=CT))
            yr.append(float(px))
        except Exception:
            continue
    return [], [], xr, yr          # no overnight leg from this source


def bars_5m(xr, yr):
    """5-minute OHLC from a (time, price) series: [(t_open, o, h, l, c)]."""
    out = {}
    for t, p in sorted(zip(xr, yr)):
        b = t.replace(minute=t.minute - t.minute % 5, second=0, microsecond=0)
        if b not in out:
            out[b] = [p, p, p, p]
        else:
            o = out[b]
            o[1] = max(o[1], p); o[2] = min(o[2], p); o[3] = p
    return [(b, v[0], v[1], v[2], v[3]) for b, v in sorted(out.items())]


def es_bars_5m_spx(date, xr, yr, cutoff=None):
    """TRUE 5M RTH bars from the ES depth tape (every trade print), basis-adjusted into
    SPX terms. The SPX quote log samples ~1/min — five samples make a fake candle; the
    tape makes a real one. Basis = median(ES_trade − SPX_quote) at the quote times.
    Returns ([], reason) when the tape is unavailable so the caller can fall back."""
    day = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    hits = sorted((ROOT / "data" / "depth").glob(f"*_depth_{day}.csv"))
    if not hits:
        return [], "no depth tape"
    try:
        import pandas as pd
        d = pd.read_csv(hits[-1], usecols=["Time", "Ev", "Price"],
                        dtype={"Ev": "category", "Price": "float32"},
                        on_bad_lines="skip")
        d = d[d["Ev"] == "T"]
        d["Time"] = pd.to_datetime(d["Time"], errors="coerce")
        d = d.dropna(subset=["Time"])
        dd = dt.datetime.strptime(date, "%Y%m%d").date()
        rth = d[(d["Time"].dt.date == dd) &
                (d["Time"].dt.time >= dt.time(8, 30)) & (d["Time"].dt.time <= dt.time(15, 15))]
        if rth.empty:
            return [], "no RTH tape yet"
        ests = rth["Time"].dt.tz_localize(CT)
        if cutoff is not None:                 # entry card = the world AT the fill,
            keep = ests <= cutoff              # nothing after (forward-reveal discipline)
            ests, rth = ests[keep], rth[keep]
            if rth.empty:
                return [], "no tape before cutoff"
        # basis from the SPX quote log: nearest tape print at each quote time
        basis = 0.0
        if xr:
            t_arr = ests.astype("int64").to_numpy()
            p_arr = rth["Price"].to_numpy()
            diffs = []
            for qt, qp in zip(xr, yr):
                i = min(range(0, len(t_arr), max(1, len(t_arr) // 4000)),
                        key=lambda j: abs(t_arr[j] - qt.timestamp() * 1e9))
                diffs.append(float(p_arr[i]) - qp)
            diffs.sort()
            basis = diffs[len(diffs) // 2] if diffs else 0.0
        return bars_5m(list(ests), list(rth["Price"] - basis)), f"ES tape − basis {basis:.1f}"
    except Exception as e:
        return [], f"tape read failed: {type(e).__name__}"


def norm_cdf(x, mu, sigma):
    return 0.5 * (1 + math.erf((x - mu) / (sigma * math.sqrt(2))))


def price_at(xr, yr, t):
    """Tape price AT time t (interpolated) — the fill sits on the price when placed."""
    if not xr:
        return None
    pairs = sorted(zip(xr, yr))
    if t <= pairs[0][0]:
        return pairs[0][1]
    prev = pairs[0]
    for x, y in pairs[1:]:
        if x >= t:
            frac = (t - prev[0]) / ((x - prev[0]) or dt.timedelta(seconds=1))
            return prev[1] + frac * (y - prev[1])
        prev = (x, y)
    return pairs[-1][1]


# ---- compute ------------------------------------------------------------------
def compute(gp, trig, when, row):
    legs = struct_legs(trig)
    net = trig["fill"]["net"]                       # +credit / -debit (signed)
    fill_ct = dt.datetime.strptime(gp["date"] + " " + trig["fill"]["at"],
                                   "%Y%m%d %H:%M:%S").replace(tzinfo=CT)
    xon, yon, xr, yr = load_series(gp["date"])
    spot = price_at(xr, yr, fill_ct) or gp.get("spot_preopen") or legs[0][2]

    strikes = sorted({k for _, _, k in legs})
    d1lo, d1hi = gp.get("d1_min"), gp.get("d1_max")
    sigma_full = (d1hi - d1lo) / 2 if (d1lo and d1hi) else spot * 0.009
    close_ct = dt.datetime.strptime(gp["date"] + " 15:00", "%Y%m%d %H:%M").replace(tzinfo=CT)
    open_ct = dt.datetime.strptime(gp["date"] + " 08:30", "%Y%m%d %H:%M").replace(tzinfo=CT)
    frac = max(0.05, (close_ct - fill_ct) / (close_ct - open_ct))
    sigma = sigma_full * math.sqrt(frac)

    span = max(strikes) - min(strikes) if len(strikes) > 1 else 60
    glo, ghi = min(strikes) - max(60, span), max(strikes) + max(60, span)
    bes = breakevens(legs, net, glo, ghi)

    pnl_lo = payoff_pts(legs, net, glo) * 100
    pnl_hi = payoff_pts(legs, net, ghi) * 100
    grid = [glo + i for i in range(int(ghi - glo) + 1)]
    pnls = [payoff_pts(legs, net, s) * 100 for s in grid]
    max_gain = max(pnls)
    max_loss = -min(pnls)
    unbounded = trig["structure"].get("kind") == "straddle"

    pop = sum((norm_cdf(b, spot, sigma) if i % 2 else -norm_cdf(b, spot, sigma))
              for i, b in enumerate(sorted(bes), start=1))
    # POP = P(payoff > 0): integrate sign regions properly instead of the alternating
    # trick above (which assumes profit OUTSIDE for debit etc.) — do it numerically:
    pop = 0.0
    for i, s in enumerate(grid[:-1]):
        if pnls[i] > 0:
            pop += norm_cdf(grid[i + 1], spot, sigma) - norm_cdf(s, spot, sigma)
    if pnls[0] > 0:
        pop += norm_cdf(glo, spot, sigma)
    if pnls[-1] > 0:
        pop += 1 - norm_cdf(ghi, spot, sigma)
    p_maxloss = sum(norm_cdf(grid[i + 1], spot, sigma) - norm_cdf(grid[i], spot, sigma)
                    for i in range(len(grid) - 1) if -pnls[i] >= max_loss * 0.999)
    ev = sum(pnls[i] * (norm_cdf(grid[i + 1], spot, sigma) - norm_cdf(grid[i], spot, sigma))
             for i in range(len(grid) - 1))

    exit_ct = exit_px = None
    if when == "close" and row.get("exit_dt") not in (None, "", "NaT"):
        try:
            exit_ct = dt.datetime.strptime(str(row["exit_dt"]), "%Y-%m-%d %H:%M").replace(tzinfo=CT)
            exit_px = price_at(xr, yr, exit_ct)
        except Exception:
            pass

    return dict(legs=legs, strikes=strikes, net=net, bes=bes, grid=grid, pnls=pnls,
                max_gain=max_gain, max_loss=max_loss, unbounded=unbounded,
                levels=gp["levels"], fill_ct=fill_ct, close_ct=close_ct,
                grade=trig["fill"].get("grade", trig.get("projected_grade")),
                name=trig["name"], regime=gp.get("regime"), spot=spot, sigma=sigma,
                d1lo=d1lo, d1hi=d1hi, pop=pop, p_maxloss=p_maxloss, ev=ev,
                exit_ct=exit_ct, exit_px=exit_px, row=row,
                series=(xon, yon, xr, yr))


# ---- PNG ----------------------------------------------------------------------
def render_png(gp, trig, c, when, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.patches import Rectangle

    xon, yon, xr, yr = c["series"]
    # a snapshot shows the world AS IT LOOKED at that moment: bars stop at the fill on
    # the entry card, at the exit on the close card — never any forward reveal
    cutoff = c["fill_ct"] if when == "open" else (c["exit_ct"] or None)
    bars, bar_src = es_bars_5m_spx(gp["date"], xr, yr, cutoff)
    if not bars:                                  # honest fallback, labeled as such
        xq = [(t, p) for t, p in zip(xr, yr) if cutoff is None or t <= cutoff]
        bars, bar_src = bars_5m([t for t, _ in xq], [p for _, p in xq]), \
            "SPX quotes ~1/min (SAMPLED, not true bars)"
    open_ct = dt.datetime.strptime(gp["date"] + " 08:30", "%Y%m%d %H:%M").replace(tzinfo=CT)
    x_start = min([open_ct] + ([bars[0][0]] if bars else []))
    close_ct = c["close_ct"]

    ys = [c["spot"]] + c["strikes"] + [b for b in c["bes"]] + \
         [v for v in (c["d1lo"], c["d1hi"]) if v] + \
         ([min(b[3] for b in bars), max(b[2] for b in bars)] if bars else [])
    ylo, yhi = min(ys) - 18, max(ys) + 18

    fig = plt.figure(figsize=(15, 9.6), facecolor=BG)
    # top row: price + payoff tent · bottom row: text strip (WHY / OUTCOME) — the
    # boxes must NEVER sit on the price action (user req 2026-07-20)
    gs = fig.add_gridspec(1, 2, width_ratios=[4.6, 1.05], wspace=0.04,
                          left=0.05, right=0.985, top=0.895, bottom=0.235)
    ax = fig.add_subplot(gs[0]); axp = fig.add_subplot(gs[1])
    for a in (ax, axp):
        a.set_facecolor(SURF)
        for s in a.spines.values():
            s.set_color(AXLINE)
        a.tick_params(colors=MUT, labelsize=9)
    ax.set_xlim(x_start, close_ct); ax.set_ylim(ylo, yhi)

    # WIN/LOSS zones from the ACTUAL payoff sign — works for every structure
    seg_start, seg_sign = ylo, payoff_pts(c["legs"], c["net"], ylo) > 0
    y = ylo
    while y <= yhi + 1:
        sign = payoff_pts(c["legs"], c["net"], y) > 0
        if sign != seg_sign or y > yhi:
            ax.axhspan(seg_start, min(y, yhi), color=GOOD if seg_sign else CRIT,
                       alpha=0.10 if seg_sign else 0.07, zorder=0)
            seg_start, seg_sign = y, sign
        y += 0.5

    # ---- levels + strikes + BEs, right-edge labels, de-collided --------------
    def sq(q):
        return "short" if q < 0 else "long"
    lv = c["levels"]
    lines = [(v, MQ[k], 1.3, ":" if k == "hvl" else "-", f"{k.upper()} {v:.0f}")
             for k, v in lv.items() if v and ylo < v < yhi]
    lines += [(v, MQ["d1"], 0.9, (0, (5, 4)), f"1D {'min' if v == c['d1lo'] else 'max'} {v:.0f}")
              for v in (c["d1lo"], c["d1hi"]) if v and ylo < v < yhi]
    seen = set()
    for q, r, k in c["legs"]:
        if k in seen:
            continue
        seen.add(k)
        here = [(qq, rr) for qq, rr, kk in c["legs"] if kk == k]
        rights = "+".join(rr for _, rr in here)          # straddle: "C+P", not "C"
        qty = here[0][0] if len({qq for qq, _ in here}) == 1 else sum(q for q, _ in here)
        tag = f"{sq(qty)}{'x' + str(abs(qty)) if abs(qty) > 1 else ''} {k:.0f}{rights}"
        lines.append((k, WING, 1.6, "-", tag))
    lines += [(b, INK2, 1.0, "--", f"BE {b:.1f}") for b in c["bes"] if ylo < b < yhi]
    for yv, col, lw, ls, _ in lines:
        ax.axhline(yv, color=col, lw=lw, ls=ls, alpha=0.85, zorder=2)
    lines.sort(key=lambda t: t[0])
    min_gap = (yhi - ylo) / 34
    placed = []
    for yv, col, lw, ls, txt in lines:
        ly = yv
        if placed and ly - placed[-1] < min_gap:
            ly = placed[-1] + min_gap
        placed.append(ly)
        ax.annotate(txt + " ", xy=(1.0, ly), xycoords=("axes fraction", "data"),
                    ha="right", va="center", color=col, fontsize=8, fontweight="bold",
                    zorder=9, bbox=dict(boxstyle="round,pad=0.16", fc=BG, ec="none", alpha=0.9))

    # ---- price: dim overnight line + 5M RTH candles --------------------------
    if xon:
        ax.plot(xon, yon, color=NIGHT, lw=1.2, zorder=3, label="overnight (ES→SPX)")
    w = dt.timedelta(minutes=3.4)
    for t, o, h, l, cl in bars:
        col = UP if cl >= o else DN
        ax.plot([t + w / 2, t + w / 2], [l, h], color=col, lw=0.9, zorder=4)
        ax.add_patch(Rectangle((mdates.date2num(t), min(o, cl)), mdates.date2num(t + w) - mdates.date2num(t),
                               max(abs(cl - o), 0.05), facecolor=col, edgecolor=col, zorder=5))

    # ---- entry / exit markers ------------------------------------------------
    kind_txt = f"{'credit' if c['net'] > 0 else 'debit'} {abs(c['net']):.2f}"
    # markers on the price, labels in the BOTTOM GUTTER with a thin connector —
    # a label must never cover price action (user req 2026-07-20)
    yr_span = yhi - ylo
    ax.scatter([c["fill_ct"]], [c["spot"]], s=110, marker="^", color=GOOD,
               edgecolor=INK, lw=1.2, zorder=8)
    ax.annotate(f"ENTRY {c['fill_ct']:%H:%M} · {c['spot']:.0f} · {kind_txt}",
                (c["fill_ct"], c["spot"]), xytext=(c["fill_ct"], ylo + yr_span * 0.035),
                textcoords="data", ha="left", color=INK, fontsize=8.5, fontweight="bold",
                zorder=10, arrowprops=dict(arrowstyle="-", color=MUT, lw=0.7, alpha=0.6),
                bbox=dict(boxstyle="round,pad=0.25", fc=SURF, ec=GOOD, alpha=0.94))
    if c["exit_ct"] and c["exit_px"]:
        pnl = c["row"].get("pnl")
        pc = GOOD if (pnl or 0) >= 0 else CRIT
        ax.scatter([c["exit_ct"]], [c["exit_px"]], s=110, marker="v", color=pc,
                   edgecolor=INK, lw=1.2, zorder=8)
        ax.annotate(f"EXIT {c['exit_ct']:%H:%M} · {c['exit_px']:.0f} · {pnl:+,.0f}",
                    (c["exit_ct"], c["exit_px"]), xytext=(c["exit_ct"], ylo + yr_span * 0.105),
                    textcoords="data", ha="left", color=INK, fontsize=8.5, fontweight="bold",
                    zorder=10, arrowprops=dict(arrowstyle="-", color=MUT, lw=0.7, alpha=0.6),
                    bbox=dict(boxstyle="round,pad=0.25", fc=SURF, ec=pc, alpha=0.94))

    ax.axvline(close_ct, color=WARN, lw=1.2, ls=":", alpha=0.8, zorder=3)
    ax.text(close_ct, ylo + (yhi - ylo) * 0.03, "15:00 cash-settle ", color=WARN,
            fontsize=8, ha="right", fontweight="bold", zorder=9,
            bbox=dict(boxstyle="round,pad=0.16", fc=BG, ec="none", alpha=0.9))

    # ---- WHY / OUTCOME boxes: bottom strip, NEVER on the price action --------
    why = [f"Fired: {str(c['row'].get('commentary', trig.get('grade_basis', '')))[:230]}"]
    why += [f"Window {'–'.join(trig.get('window', ['?', '?']))} CT · filled {trig['fill']['at']}",
            f"Grade {c['grade']} · regime at entry {trig.get('entry_regime', c['regime'])}",
            f"Bars: {bar_src}"]
    box = "WHY THIS TRADE\n" + "\n".join(
        "✓  " + w for line in why for w in textwrap.wrap(line, 92))
    fig.text(0.05, 0.185, box, va="top", ha="left",
             fontsize=8.6, color=INK, linespacing=1.55,
             bbox=dict(boxstyle="round,pad=0.55", fc="#12140f", ec=GOOD, alpha=0.94))
    if when == "close" and c["row"].get("close_reason"):
        pnl = c["row"].get("pnl")
        ob = ("OUTCOME\n" + "\n".join(textwrap.wrap(str(c["row"]["close_reason"]), 52)) +
              (f"\nrealized {pnl:+,.0f}" if pnl == pnl else ""))
        fig.text(0.66, 0.185, ob, va="top", ha="left",
                 fontsize=8.6, color=INK, linespacing=1.55,
                 bbox=dict(boxstyle="round,pad=0.55", fc="#141012",
                           ec=GOOD if (pnl or 0) >= 0 else CRIT, alpha=0.94))

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=CT))
    ax.set_ylabel("SPX (index terms)", color=INK2, fontsize=10)
    ax.grid(color=GRID, lw=0.6, alpha=0.45)
    if xon:
        ax.legend(loc="lower left", facecolor=SURF, edgecolor=AXLINE,
                  labelcolor=INK2, fontsize=8, framealpha=0.92)

    # ---- payoff tent (generic) ----------------------------------------------
    axp.set_ylim(ylo, yhi)
    Sg = [s for s in c["grid"] if ylo <= s <= yhi]
    pn = [c["pnls"][c["grid"].index(s)] for s in Sg]
    axp.plot(pn, Sg, color=INK2, lw=1.6, zorder=5)
    axp.fill_betweenx(Sg, 0, pn, where=[p >= 0 for p in pn], color=GOOD, alpha=0.35)
    axp.fill_betweenx(Sg, 0, pn, where=[p < 0 for p in pn], color=CRIT, alpha=0.30)
    axp.axvline(0, color=AXLINE, lw=1)
    axp.set_xlabel("P&L @ expiry", color=MUT, fontsize=8.5)
    axp.tick_params(labelleft=False, labelsize=7.2)
    axp.grid(color=GRID, lw=0.5, alpha=0.4, axis="x")

    mg = "unbounded" if c["unbounded"] else f"+\\${c['max_gain']:,.0f}"
    fig.suptitle(f"{c['name']}   ·   {gp['date']}   ·   grade {c['grade']}   ·   {c['regime']}"
                 f"   ·   {'ENTRY' if when == 'open' else 'CLOSED'}",
                 color=INK, fontsize=15, fontweight="bold", x=0.5, y=0.985)
    sub = (f"{kind_txt}     max gain {mg}     max loss -\\${c['max_loss']:,.0f}     "
           f"BE {' / '.join(f'{b:.1f}' for b in c['bes'])}")
    fig.text(0.5, 0.945, sub, color=INK2, fontsize=10.5, ha="center")
    fig.text(0.5, 0.912, f"POP {c['pop']*100:.0f}%      P(max loss) {c['p_maxloss']*100:.0f}%      "
             f"EV {'+' if c['ev'] >= 0 else '-'}${abs(c['ev']):,.0f}      "
             f"1σ to close ±{c['sigma']:.0f} pts (MQ 1-day range)",
             color=INK, fontsize=11, ha="center", fontweight="bold")

    CARDS.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=130, facecolor=BG, bbox_inches="tight")
    plt.close(fig)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trade", required=True)
    ap.add_argument("--date", default=None, help="YYYYMMDD; default: parsed from the trade id")
    ap.add_argument("--when", default="open", choices=["open", "close"])
    args = ap.parse_args()
    if not args.date:   # auto_YYYYMMDD_HHMMSS carries its own date
        m = re.search(r"_(\d{8})_", args.trade)
        args.date = m.group(1) if m else dt.datetime.now(CT).strftime("%Y%m%d")

    gp, trig = load_trade(args.trade, args.date)
    row = load_log_row(args.trade)
    c = compute(gp, trig, args.when, row)
    png = CARDS / f"{args.trade}_{args.when}.png"
    render_png(gp, trig, c, args.when, png)
    print(f"PNG -> {png}")
    print(f"  {c['name']} | net {c['net']:+.2f} | maxL -${c['max_loss']:,.0f} | "
          f"POP {c['pop']*100:.0f}% | BE {' / '.join(f'{b:.1f}' for b in c['bes'])}")


if __name__ == "__main__":
    main()
