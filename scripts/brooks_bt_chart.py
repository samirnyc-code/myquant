"""Render a single Brooks setup trade on a clean, readable 5m chart.

Big fonts, non-overlapping labels, EMA20, signal bar highlighted, entry/stop/
target/exit lines, and a PnL box. Auto-opens the PNG in VSCode.

Usage (programmatic): render_trade(g, f, sig, book, setup_name, out_png)
"""
import subprocess
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from brooks_bt_core import TICK, PT_MES, COMM

GREEN = "#128a3a"; RED = "#c0261a"; BLUE = "#1f5fbf"; ORANGE = "#e08a00"
STOPC = "#c0261a"; TGTC = "#128a3a"; ENTRYC = "#1f5fbf"


def trade_path(f, tP, tbar, sig, book, cancel_bars=4):
    """Recompute one trade's full path for charting.
    Returns dict or None (no fill)."""
    H, L = f["H"], f["L"]
    short = sig["dir"] == "S"
    fb, sb, trig = sig["fb"], sig["sb"], sig["trig"]
    a = np.searchsorted(tbar, fb, "left")
    ze = np.searchsorted(tbar, fb + cancel_bars, "right")
    s = tP[a:ze]
    hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
    if not len(hit):
        return None
    jf = a + int(hit[0])
    entry_bar = int(tbar[jf])
    fill = trig - TICK if short else trig + TICK
    stop = H[sb] + TICK if short else L[sb] - TICK
    R = (stop - fill) if short else (fill - stop)
    if R <= 0:
        return None
    seg = tP[jf:]
    seg_bar = tbar[jf:]
    js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
    js = js_[0] if len(js_) else np.inf
    # target for the requested book
    kmap = {"1R": 1.0, "2R": 2.0, "4R": 4.0, "BE2R": 2.0}
    tgt = None
    if book in kmap:
        k = kmap[book]
        tgt = fill - k * R if short else fill + k * R
        jt_ = np.nonzero(seg <= tgt)[0] if short else np.nonzero(seg >= tgt)[0]
        jt = jt_[0] if len(jt_) else np.inf
        if js <= jt:
            ex_i = js; ex_px = stop
        elif np.isfinite(jt):
            ex_i = jt; ex_px = tgt
        else:
            ex_i = len(seg) - 1; ex_px = seg[-1]
    else:  # EOD
        if np.isfinite(js):
            ex_i = js; ex_px = stop
        else:
            ex_i = len(seg) - 1; ex_px = seg[-1]
    exit_bar = int(seg_bar[int(ex_i)])
    pnl = (fill - ex_px) if short else (ex_px - fill)
    return dict(entry_bar=entry_bar, fill=fill, stop=stop, target=tgt, exit_bar=exit_bar,
                exit_px=ex_px, R=R, pnl=pnl, Rmult=pnl / R,
                net_mes=pnl * PT_MES - COMM, dir=sig["dir"], sb=sb, m2b=sig.get("m2b"))


def _candles(ax, O, H, L, C, i0, i1):
    for i in range(i0, i1):
        up = C[i] >= O[i]
        col = GREEN if up else RED
        ax.plot([i, i], [L[i], H[i]], color=col, lw=1.4, zorder=2)
        lo, hi = (O[i], C[i]) if up else (C[i], O[i])
        ax.add_patch(Rectangle((i - 0.3, lo), 0.6, max(hi - lo, TICK / 2),
                               facecolor=col, edgecolor=col, zorder=3))


def render(g, f, sig, path, book, setup_name, out_png, pad_left=14, pad_right=10,
           open_vscode=True, sig_label=None):
    O, H, L, C, ema, n = f["O"], f["H"], f["L"], f["C"], f["ema"], f["n"]
    sb, fb = sig["sb"], sig["fb"]
    ex_bar = path["exit_bar"]
    i0 = max(0, min(sb, fb) - pad_left)
    i1 = min(n, max(fb, ex_bar) + pad_right)

    plt.rcParams.update({"font.size": 15})
    fig, ax = plt.subplots(figsize=(19, 10.5), dpi=120)
    _candles(ax, O, H, L, C, i0, i1)
    ax.plot(range(i0, i1), ema[i0:i1], color=ORANGE, lw=2.4, label="EMA 20", zorder=4)

    # highlight signal bar
    ax.add_patch(Rectangle((sb - 0.45, L[sb] - TICK), 0.9, (H[sb] - L[sb]) + 2 * TICK,
                           fill=False, edgecolor=BLUE, lw=2.6, ls="-", zorder=6))
    long = sig["dir"] == "L"
    ylo, yhi = L[i0:i1].min(), H[i0:i1].max()
    yr = yhi - ylo
    # entry / stop / target lines across the trade duration
    xa, xb = fb - 0.5, ex_bar + 0.5
    ax.hlines(path["fill"], xa, xb, color=ENTRYC, lw=2.4, ls=(0, (5, 2)), zorder=5)
    ax.hlines(path["stop"], xa, xb, color=STOPC, lw=2.4, ls=(0, (5, 2)), zorder=5)
    if path["target"] is not None:
        ax.hlines(path["target"], xa, xb, color=TGTC, lw=2.4, ls=(0, (5, 2)), zorder=5)
    # exit marker
    ax.scatter([ex_bar], [path["exit_px"]], s=180, marker="X",
               color="black", zorder=8)

    # entry arrow at signal bar
    ay = L[sb] - yr * 0.06 if long else H[sb] + yr * 0.06
    deflab = "H2\nsignal" if long else "L2\nsignal"
    ax.annotate(sig_label or deflab, (sb, ay),
                ha="center", va="top" if long else "bottom", fontsize=15, fontweight="bold",
                color=BLUE)

    # right-edge, staggered price labels (no overlap)
    xr = i1 - 0.5
    def lab(y, txt, color):
        ax.annotate(txt, (xr, y), xytext=(8, 0), textcoords="offset points",
                    va="center", ha="left", fontsize=15, fontweight="bold", color=color,
                    bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=color, lw=1.6))
    # stagger if lines are close
    lab(path["fill"], f"ENTRY {path['fill']:.2f}", ENTRYC)
    lab(path["stop"], f"STOP {path['stop']:.2f}", STOPC)
    if path["target"] is not None:
        lab(path["target"], f"TARGET {path['target']:.2f}", TGTC)

    # PnL / stats box (top-left, big)
    won = path["pnl"] > 0
    res = f"WIN +{path['Rmult']:.2f}R" if won else f"LOSS {path['Rmult']:.2f}R"
    box = (f"{res}\n"
           f"P&L (1 MES, 5 dol RT): {path['net_mes']:+,.0f} USD\n"
           f"Risk (R): {path['R']:.2f} pts   Exit: {path['exit_px']:.2f}\n"
           f"Mgmt: {book}   {'M2B (EMA touch)' if path.get('m2b') else 'non-M2B'}")
    ax.text(0.012, 0.985, box, transform=ax.transAxes, va="top", ha="left",
            fontsize=16, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.5", fc="#f4f7ff",
                      ec=GREEN if won else RED, lw=2.4))

    # x ticks as times
    times = g["DateTime"].dt.strftime("%H:%M").values
    step = max(1, (i1 - i0) // 12)
    xt = list(range(i0, i1, step))
    ax.set_xticks(xt); ax.set_xticklabels([times[t] for t in xt], fontsize=13)
    ax.set_xlim(i0 - 1, i1 + 6)
    ax.set_ylim(ylo - yr * 0.10, yhi + yr * 0.10)
    ax.set_ylabel("ES price", fontsize=15)
    ax.grid(True, alpha=0.25, zorder=0)
    dirw = "LONG" if long else "SHORT"
    ax.set_title(f"{setup_name}  —  {dirw}  —  {g['Date'].iloc[0]}",
                 fontsize=21, fontweight="bold", pad=14)
    ax.legend(loc="lower left", fontsize=14, framealpha=0.9)
    fig.tight_layout()
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, bbox_inches="tight")
    plt.close(fig)
    if open_vscode:
        try:
            subprocess.run(["code", "-r", str(out_png)], shell=True, timeout=20)
        except Exception:
            pass
    return out_png
