"""gameplan_charts.py — one well-labeled chart per price path and per trade idea.

Daily requirement (S75V, 2026-07-20): the gameplan JSON says WHAT is armed; these charts
show WHY — the dealer-mechanics reasoning behind each scenario and the structure, zones
and grade logic behind each trade. Rendered from data/options_sim/gameplan_YYYYMMDD.json,
so they can never drift from what the desk is actually running.

    python scripts/gameplan_charts.py                 # today's gameplan
    python scripts/gameplan_charts.py --date 20260720
    python scripts/gameplan_charts.py --no-open       # don't open tabs in VSCode
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"

# dark theme to match Mission Control
BG, PANEL, FG, MUT = "#0d1117", "#161b22", "#e6edf3", "#8b949e"
GRN, RED, AMB, BLU, PUR = "#3fb950", "#f85149", "#d29922", "#58a6ff", "#bc8cff"
LEVEL_STYLE = {  # name -> (color, label)
    "cr":  (RED, "CR  call resistance — upper gamma wall"),
    "cr0": (RED, "CR0 0DTE call resistance"),
    "gw0": (PUR, "GW0 0DTE gamma wall (pin candidate)"),
    "hvl": (AMB, "HVL hedging-vol line — regime flip level"),
    "ps0": (GRN, "PS0 0DTE put support"),
    "ps":  (GRN, "PS  put support — last gamma support"),
}
GRADE_COLOR = {"A": GRN, "B": BLU, "C": AMB, "D": "#f0883e", "F": RED}


def _fig(title: str, sub: str):
    fig = plt.figure(figsize=(12.8, 7.2), facecolor=BG)
    fig.text(0.02, 0.965, title, color=FG, fontsize=15, fontweight="bold", va="top")
    fig.text(0.02, 0.925, sub, color=MUT, fontsize=9.5, va="top")
    return fig


def _levels_backdrop(ax, g, ylim, spot_label=True):
    """Horizontal gamma levels + expected range + pre-open spot on any price axis."""
    lv = g["levels"]
    ax.set_facecolor(PANEL)
    ax.axhspan(g["d1_min"], g["d1_max"], color=BLU, alpha=0.08,
               label=f"1-day expected range {g['d1_min']:.0f}–{g['d1_max']:.0f}")
    drawn = set()
    for k, (color, label) in LEVEL_STYLE.items():
        v = lv.get(k)
        if v is None or not (ylim[0] <= v <= ylim[1]) or v in drawn:
            continue
        drawn.add(v)
        # GW0 and CR0 sit on the same price today - one line, joint tag
        names = [n.upper() for n in lv if lv[n] == v]
        ax.axhline(v, color=color, lw=1.4, alpha=0.9)
        ax.annotate(f"{'/'.join(names)}  {v:.0f}", xy=(0.99, v), xycoords=("axes fraction", "data"),
                    xytext=(0, 4), textcoords="offset points", color=color, fontsize=9,
                    fontweight="bold", ha="right", va="bottom")
    spot = g["spot_preopen"]
    if spot_label and ylim[0] <= spot <= ylim[1]:
        ax.scatter([0.06], [spot], transform=ax.get_yaxis_transform(),
                   color=FG, zorder=5, s=45)
        ax.annotate(f"spot {spot:.0f} ({g['spot_source']})", xy=(0.06, spot),
                    xycoords=("axes fraction", "data"), xytext=(10, 8),
                    textcoords="offset points", color=FG, fontsize=9.5, fontweight="bold")
    ax.set_ylim(*ylim)
    ax.set_xlim(0, 1)
    ax.set_xticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_xticklabels(["08:30", "10:00", "11:30", "13:00", "15:00 CT"],
                       color=MUT, fontsize=8.5)
    ax.tick_params(colors=MUT, labelsize=8.5)
    for s in ax.spines.values():
        s.set_color("#30363d")


def _text_panel(fig, blocks, x=0.66):
    """Right-hand reasoning column: list of (heading, body, color)."""
    y = 0.86
    for head, body, color in blocks:
        fig.text(x, y, head, color=color, fontsize=10.5, fontweight="bold", va="top")
        y -= 0.045
        for line in textwrap.wrap(body, 46):
            fig.text(x, y, line, color=FG, fontsize=9.5, va="top")
            y -= 0.037
        y -= 0.025


def _arrow(ax, pts, color):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), color=color, lw=2.6,
                                     arrowstyle="-|>", mutation_scale=18, alpha=0.95))


def _path_geometry(sid, g):
    """Schematic trajectory (x in axes 0-1, y in price) + zone shading per scenario."""
    lv, spot = g["levels"], g["spot_preopen"]
    if sid == "A":
        return [[(0.10, spot), (0.45, lv["hvl"]), (0.80, lv["hvl"] + 25)]], \
               [(lv["hvl"], g["d1_max"] + 30, GRN, "above HVL: +gamma, premium-sells re-arm")]
    if sid == "B":
        return [[(0.10, spot), (0.40, lv["ps0"]), (0.85, lv["ps"] + 40)]], \
               [(lv["ps"], lv["ps0"], RED, "-gamma slide zone: dealers sell weakness")]
    if sid == "C":
        return [[(0.10, spot), (0.55, lv["hvl"] + 45)],
                [(0.10, spot), (0.55, lv["ps0"] - 55)]], \
               [(lv["ps0"], lv["hvl"], MUT, "7490-7540: leaving this box = expansion")]
    # D
    return [[(0.10, spot), (0.45, lv["ps"]), (0.85, lv["ps"] - 60)]], \
           [(lv["ps"] - 120, lv["ps"], RED, "below PS: nothing structural beneath")]


def render_path(g, s, out: Path):
    fig = _fig(f"PATH {s['id']} — {s['name']}",
               f"{g['date']}  ·  regime {g['regime'].replace('_', ' ').upper()}  ·  {g['regime_detail']}")
    ax = fig.add_axes([0.06, 0.08, 0.55, 0.78])
    lo = min(g["levels"]["ps"], g["d1_min"]) - 140
    hi = max(g["levels"]["cr"], g["d1_max"]) + 60
    _levels_backdrop(ax, g, (lo, hi))
    paths, zones = _path_geometry(s["id"], g)
    for y0, y1, color, label in zones:
        ax.axhspan(y0, y1, color=color, alpha=0.13)
        ax.annotate(label, xy=(0.30, (y0 + y1) / 2), xycoords=("axes fraction", "data"),
                    color=color, fontsize=8.5, style="italic")
    for pts in paths:
        _arrow(ax, pts, FG)
    _text_panel(fig, [
        ("THE PATH", s["path"], BLU),
        ("WHAT IT MEANS (dealer mechanics)", s["means"], AMB),
        ("WHAT WE DO", s["acts"], GRN),
        ("WHY THIS REASONING", _path_why(s["id"], g), MUT),
    ])
    fig.savefig(out, dpi=110, facecolor=BG)
    plt.close(fig)


def _path_why(sid, g):
    lv = g["levels"]
    return {
        "A": (f"HVL {lv['hvl']:.0f} is where net dealer gamma flips sign. Above it dealers "
              "are LONG gamma: they sell rallies and buy dips, which dampens movement and "
              "pins price — the environment premium selling needs. Reclaiming it turns the "
              "day's character from trend back to chop."),
        "B": (f"Below HVL dealers are SHORT gamma: falling prices force them to SELL more "
              f"to stay hedged, feeding the move. PS0 {lv['ps0']:.0f} is the first 0DTE put "
              f"wall; if it breaks with dealers chasing, there is little to slow price "
              f"until PS {lv['ps']:.0f}. That is why support must NOT be faded into momentum."),
        "C": (f"Negative gamma does not mean 'down' — it means AMPLIFIED. Whichever way "
              f"price leaves the {lv['ps0']:.0f}–{lv['hvl']:.0f} box, hedging flow pushes it "
              "further. Direction is unknown, expansion is the bet: that is a long-straddle "
              "day, and short-premium stays off."),
        "D": (f"PS {lv['ps']:.0f} is the LAST major put wall. Below it there is no gamma "
              "support left to lean on — fades have no structural argument, so the only "
              "position that makes sense is already-held long volatility."),
        "TR": (f"Two-sided rotation between {lv['ps0']:.0f} and {lv['hvl']:.0f} — neither edge "
               "is accepted, so price rejects both and chops. The negative-gamma break has not "
               "happened yet (statistically the most common intraday start). Fade the edges with "
               "tight risk until one side is accepted."),
    }.get(sid, "See the gameplan for this path's mechanics.")


# ---------------------------------------------------------------- trades
def _fire_text(t):
    f = t["fire"]
    k = f.get("type")
    if k == "touch":
        return f"first touch of {f['level']} {f['dir'].replace('_', ' ')}"
    if k == "first_of":
        return f"tag {f['touch']['level']} or {f.get('not_before', '')} (whichever first)"
    if k == "time_at":
        return f"at {f.get('not_before', '?')} CT"
    if k == "signal_1559":
        return f"15:59 ET signal: {f.get('cond', '')}"
    return json.dumps(f)


def _trade_zones(t, spot):
    """(ylim, [(y0,y1,color,label)], [strike lines]) for the structure."""
    st = t["structure"]
    k = st["kind"]
    if k == "vertical":
        s, l = st["short"], st.get("long")
        if isinstance(s, str) or l is None:   # STMR: strike picked at 14:59 (~30 delta)
            return None, None, None
        pad = st["width"] * 2.5
        if st["right"] == "P":
            zones = [(s, s + pad, GRN, "WIN: price stays ABOVE short strike"),
                     (l, s, AMB, "between strikes: partial loss"),
                     (l - pad * 0.6, l, RED, "MAX LOSS: below long strike")]
        else:
            zones = [(s - pad, s, GRN, "WIN: price stays BELOW short strike"),
                     (s, l, AMB, "between strikes: partial loss"),
                     (l, l + pad * 0.6, RED, "MAX LOSS: above long strike")]
        lo, hi = min(l, s) - pad, max(l, s) + pad
        return (lo, hi), zones, [(s, "short " + str(s)), (l, "long " + str(l))]
    if k == "butterfly":
        c, lo_w, hi_w = st["center"], st["lower"], st["upper"]
        pad = st["width"] * 1.8
        zones = [(lo_w, hi_w, GRN, f"profit tent — max payoff AT {c} (the pin)"),
                 (hi_w, hi_w + pad * 0.6, RED, "beyond wings: fly expires worthless"),
                 (lo_w - pad * 0.6, lo_w, RED, "beyond wings: fly expires worthless")]
        return (lo_w - pad, hi_w + pad), zones, \
               [(lo_w, f"wing {lo_w}"), (c, f"CENTER {c}"), (hi_w, f"wing {hi_w}")]
    if k == "straddle":
        pad = 120
        zones = [(spot - pad, spot - 35, GRN, "WIN: big move DOWN (beyond premium)"),
                 (spot + 35, spot + pad, GRN, "WIN: big move UP (beyond premium)"),
                 (spot - 35, spot + 35, RED, "LOSS zone: day stays quiet near ATM")]
        return (spot - pad, spot + pad), zones, [(spot, f"ATM ~{spot:.0f}")]
    return None, None, None


def render_trade(g, t, out: Path):
    grade = str(t["projected_grade"])[0].upper()
    gc = GRADE_COLOR.get(grade, MUT)
    status = t["status"].upper() + (" — " + t.get("disarmed_reason", "") if t["status"] == "disarmed" else "")
    fig = _fig(t["name"],
               f"{g['date']}  ·  path {t['path']}  ·  window {t['window'][0]}–{t['window'][1]} CT"
               f"  ·  fires on {_fire_text(t)}")
    # grade badge
    fig.text(0.955, 0.955, f" {t['projected_grade']} ", color=BG, fontsize=14,
             fontweight="bold", ha="right", va="top",
             bbox=dict(boxstyle="round,pad=0.35", fc=gc, ec="none"))

    ylim, zones, strikes = _trade_zones(t, g["spot_preopen"])
    ax = fig.add_axes([0.06, 0.08, 0.55, 0.78])
    if ylim:
        _levels_backdrop(ax, g, ylim)
        for y0, y1, color, label in zones:
            ax.axhspan(y0, y1, color=color, alpha=0.14)
            ax.annotate(label, xy=(0.28, (y0 + y1) / 2), xycoords=("axes fraction", "data"),
                        color=color, fontsize=9, fontweight="bold", va="center")
        for y, lab in strikes:
            ax.axhline(y, color=FG, lw=1.6, ls="--", alpha=0.85)
            ax.annotate(lab, xy=(0.015, y), xycoords=("axes fraction", "data"),
                        xytext=(0, 5), textcoords="offset points", color=FG, fontsize=9,
                        fontweight="bold")
    else:  # STMR: strike unknown until 14:59 - schematic text chart
        ax.set_facecolor(PANEL)
        ax.set_xticks([]); ax.set_yticks([])
        for s in ax.spines.values():
            s.set_color("#30363d")
        ax.text(0.5, 0.62, "strike chosen AT 14:59 CT (~30Δ put)", color=FG,
                ha="center", fontsize=12, fontweight="bold")
        ax.text(0.5, 0.45, f"width {t['structure'].get('width')}pt · {t['structure'].get('dte')} DTE",
                color=MUT, ha="center", fontsize=11)
        ax.text(0.5, 0.30, "no chart until the signal computes the strike", color=MUT,
                ha="center", fontsize=9.5, style="italic")

    why = _trade_why(t, g)
    _text_panel(fig, [
        ("STATUS", status, GRN if t["status"] == "armed" else RED),
        ("GRADE REASONING", t["grade_basis"], gc),
        ("HOW THE TRADE WORKS", why[0], BLU),
        ("WHY THIS GRADE TODAY", why[1], MUT),
    ])
    fig.savefig(out, dpi=110, facecolor=BG)
    plt.close(fig)


def _trade_why(t, g):
    st, neg = t["structure"], g["regime"] == "negative_gamma"
    k, setup = st["kind"], t["setup"]
    if setup == "bps_stmr":
        return ("Sell a ~30-delta put spread on the 15:59 ET oversold signal (%K8<15) while "
                "the larger trend is still up (spot>SMA100): selling a short-term panic "
                "inside an uptrend, defined risk, 14 DTE.",
                "The one setup with a validated historical edge; it does not depend on "
                "today's gamma regime, which is why it grades A/B regardless of the -gamma tape.")
    if k == "vertical" and setup.startswith("sell"):
        side = "put" if st["right"] == "P" else "call"
        wall = "PS0" if st["right"] == "P" else "CR0"
        return (f"Collect credit selling the {side} spread AT the {wall} wall. Max profit if the "
                f"wall holds into expiry; the long strike caps risk at width - credit.",
                "Premium selling is a POSITIVE-gamma trade: it needs dealers pinning price. "
                f"Today is {'negative' if neg else 'positive'} gamma, so the pin argument is "
                f"{'absent - hence the low grade / disarm' if neg else 'present'}.")
    if k == "vertical":  # touch fades
        side = "put" if st["right"] == "P" else "call"
        return (f"On the FIRST touch of the wall, sell the {side} spread against it: first "
                "touches are where a wall's hedging flow is strongest, before it is absorbed.",
                "In -gamma the momentum INTO the level is dealer-fed, so the wall is more "
                "likely to break than hold: fading it is fighting the tape - graded D, small size only.")
    if k == "butterfly":
        return ("Buy the wings, sell 2x the center at the gamma wall: a pin bet whose max "
                "payoff lands exactly at the wall on the close, for small defined cost.",
                "A pin needs positive gamma to attract price. On a -gamma trend day the wall "
                "repels instead of attracts - that is a structural F, kept only for the ledger.")
    if k == "straddle":
        return ("Buy the ATM call AND put: direction-agnostic. Profits if the day RANGE "
                "expands beyond the combined premium; loses only if price sits still.",
                "This is THE negative-gamma structure (path C/D is the base case). Gap-armed: "
                "the HVL break happened pre-open, so it fires on state at 09:00, not on a cross.")
    return ("", "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYYMMDD (default: today CT)")
    ap.add_argument("--no-open", action="store_true", help="skip opening tabs in VSCode")
    a = ap.parse_args()
    from zoneinfo import ZoneInfo
    date = a.date or dt.datetime.now(ZoneInfo("America/Chicago")).strftime("%Y%m%d")
    gp = SIM / f"gameplan_{date}.json"
    if not gp.exists():
        print(f"no gameplan for {date}: {gp}")
        return 1
    g = json.loads(gp.read_text(encoding="utf-8"))
    outdir = SIM / "gameplan_charts" / date
    outdir.mkdir(parents=True, exist_ok=True)

    made = []
    for i, s in enumerate(g.get("scenarios", []), 1):
        f = outdir / f"path_{s['id']}.png"
        render_path(g, s, f)
        made.append(f)
    for i, t in enumerate(g.get("triggers", []), 1):
        f = outdir / f"trade_{i}_{t['id']}.png"
        render_trade(g, t, f)
        made.append(f)
    for f in made:
        print(f"  wrote {f.relative_to(ROOT)}")
    if not a.no_open:
        for f in made:
            subprocess.run(["code", str(f)], shell=True, creationflags=0x08000000)
    print(f"{len(made)} charts -> {outdir.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
