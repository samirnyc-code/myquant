"""Chart one day of the REALISTIC regime system: candles, regime shading,
structure labels, and the taken trades (entry, swing stop, exit-at-flip).
Reuses the engine from brooks_sim_regime (guarded import)."""
import sys, random
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
import massive
import importlib.util
spec = importlib.util.spec_from_file_location("bsr", ROOT / "scripts" / "brooks_sim_regime.py")
# we only want run_day-like internals; re-implement a thin day runner here instead.

TICK = 0.25; IGNORE_IB = True; ALLOW_LOOSE = True; STOPMULT = 2.0
b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous.parquet")
b["Date"] = b["DateTime"].dt.date.astype(str)
alld = sorted(b["Date"].unique())
DAY = sys.argv[1] if len(sys.argv) > 1 else random.choice([d for d in alld if 40 < (b["Date"] == d).sum() < 200])

g = b[b["Date"] == DAY].sort_values("DateTime").reset_index(drop=True)
O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"]); n = len(g)
tk = massive.load_continuous_ticks(date.fromisoformat(DAY)).sort_values("DateTime")
tP = tk["Price"].values
tbar = np.searchsorted(g["DateTime"].values, tk["DateTime"].values, side="right") - 1
rng = (H - L).astype(float)
IBS = np.where(rng > 0, (C - L) / np.maximum(rng, 1e-9) * 100.0, 50.0)
ABR = np.array([rng[max(0, i-10):i].mean() if i > 0 else rng[0] for i in range(n)])


def btype(i, p):
    eqH = H[i] == H[p]; eqL = L[i] == L[p]; inH = H[i] < H[p]; inL = L[i] > L[p]
    outH = H[i] > H[p]; outL = L[i] < L[p]
    if inH and inL: return "IB"
    if outH and outL: return "OB"
    if eqH and eqL: return "IB"
    if ALLOW_LOOSE:
        if (eqH and inL) or (eqL and inH): return "IB"
        if (eqH and outL) or (eqL and outH): return "OB"
    return "N"


is_ib = np.zeros(n, bool); prev = np.zeros(n, int); _ref = 0
for i in range(1, n):
    if btype(i, _ref) == "IB": is_ib[i] = True; prev[i] = _ref
    else: prev[i] = _ref; _ref = i


def tslice(i):
    return np.searchsorted(tbar, i, "left"), np.searchsorted(tbar, i, "right")


def ob_cf(i, up):
    p = prev[i]; a, z = tslice(i); s = tP[a:z]
    if up: c_ = np.nonzero(s > H[p])[0]; k_ = np.nonzero(s < L[p])[0]
    else: c_ = np.nonzero(s < L[p])[0]; k_ = np.nonzero(s > H[p])[0]
    return (c_[0] if len(c_) else np.inf) < (k_[0] if len(k_) else np.inf)


def bup(i):
    return i >= 2 and H[i-1] > H[i-2] and IBS[i-1] >= 69 and IBS[i] >= 69 and (rng[i-1] > ABR[i-1] or rng[i] > ABR[i])


def bdn(i):
    return i >= 2 and L[i-1] < L[i-2] and IBS[i-1] <= 31 and IBS[i] <= 31 and (rng[i-1] > ABR[i-1] or rng[i] > ABR[i])


# legs
piv = []; d = 1 if H[1] >= H[0] else -1; ext_i = 0; pj = 0
for i in range(1, n):
    if is_ib[i]: continue
    p = prev[i]
    if btype(i, p) == "OB":
        up = (d == 1); cf = ob_cf(i, up)
        if up:
            if cf:
                if H[i] >= H[ext_i]: ext_i = i
                piv.append((ext_i, H[ext_i], "H", i)); d = -1; ext_i = i
            else:
                piv.append((ext_i, H[ext_i], "H", i)); piv.append((i, L[i], "L", i)); d = 1; ext_i = i
        else:
            if cf:
                if L[i] <= L[ext_i]: ext_i = i
                piv.append((ext_i, L[ext_i], "L", i)); d = 1; ext_i = i
            else:
                piv.append((ext_i, L[ext_i], "L", i)); piv.append((i, H[i], "H", i)); d = -1; ext_i = i
        pj = i; continue
    if d == 1:
        if H[i] >= H[ext_i]: ext_i = i
        if L[i] < L[pj]: piv.append((ext_i, H[ext_i], "H", i)); d = -1; ext_i = i
    else:
        if L[i] <= L[ext_i]: ext_i = i
        if H[i] > H[pj]: piv.append((ext_i, L[ext_i], "L", i)); d = 1; ext_i = i
    pj = i
piv.append((ext_i, H[ext_i] if d == 1 else L[ext_i], "H" if d == 1 else "L", n-1))
piv_conf = {}
for (pb, prc, typ, cb) in piv: piv_conf.setdefault(cb, []).append((pb, prc, typ))

sw = [[idx, prc, typ, ""] for (idx, prc, typ, cb) in piv]; events = []; refH = refL = None
for k, (idx, prc, typ, _) in enumerate(sw):
    if typ == "L":
        if refL is None: refL = prc
        elif prc < refL:
            sw[k][3] = "LL"; refL = prc
            lows = [j for j, s in enumerate(sw[:k]) if s[2] == "L"]; j0 = lows[-1] if lows else -1
            seg = [s for s in sw[j0+1:k] if s[2] == "H"]
            if seg:
                lh = max(seg, key=lambda s: s[1])
                if not lh[3] and (refH is None or lh[1] < refH): lh[3] = "LH"; refH = lh[1]; events.append((idx, "LL", lh[0], lh[1]))
    else:
        if refH is None: refH = prc
        elif prc > refH:
            sw[k][3] = "HH"; refH = prc
            highs = [j for j, s in enumerate(sw[:k]) if s[2] == "H"]; j0 = highs[-1] if highs else -1
            seg = [s for s in sw[j0+1:k] if s[2] == "L"]
            if seg:
                hl = min(seg, key=lambda s: s[1])
                if not hl[3] and (refL is None or hl[1] > refL): hl[3] = "HL"; refL = hl[1]; events.append((idx, "HH", hl[0], hl[1]))
ev = {}
for e in events: ev.setdefault(e[0], []).append(e)

# regime + entries (same as sim)
entries = []; reg = np.zeros(n, int); regime = 0; opened = False
conf_LH = conf_HL = None
ecS = refS = refSb = orgS = None; ecS = 0
ecL = refLo = refLb = orgL = None; ecL = 0
armed_bull = armed_bear = False; arm_bar = None
last_sh = last_sl = None; rev_sh = rev_sh_bar = rev_ref_lo = None; rev_sl = rev_sl_bar = rev_ref_hi = None
refS_kind = refL_kind = "N"; regime_start_bar = 0; _pr = 0
for i in range(n):
    es_fired = el_fired = False
    for (eb, kind, lb, lp) in ev.get(i, []):
        if kind == "LL":
            conf_LH = (lb, lp)
            if regime == 0 and not opened: regime = -1; opened = True; ecL = 0; refLo = refLb = orgL = None; ecS = 0
        else:
            conf_HL = (lb, lp)
            if regime == 0 and not opened: regime = 1; opened = True; ecS = 0; refS = refSb = orgS = None; ecL = 0
    for (pb, prc, typ) in piv_conf.get(i, []):
        if typ == "H":
            if armed_bull and arm_bar is not None and pb > arm_bar and rev_sh is None: rev_sh = prc; rev_sh_bar = pb; rev_ref_lo = last_sl
            last_sh = prc
        else:
            if armed_bear and arm_bar is not None and pb > arm_bar and rev_sl is None: rev_sl = prc; rev_sl_bar = pb; rev_ref_hi = last_sh
            last_sl = prc
    if i >= 1 and is_ib[i]:
        p = prev[i]
        if regime <= 0:
            if orgS is None: orgS = L[p]
            refS = L[p]; refSb = p; refS_kind = "IB"
        if regime >= 0:
            if orgL is None: orgL = H[p]
            refLo = H[p]; refLb = p; refL_kind = "IB"
    if i >= 1 and not is_ib[i]:
        p = prev[i]; is_ob = btype(i, p) == "OB"
        if regime == 1: ecS = 0; refS = refSb = orgS = None
        else:
            if refS is not None and L[i] < refS - TICK/2:
                ecS += 1; es_fired = True
                entries.append((i, refSb, "S", min(ecS, 3), refS - TICK, refS_kind, i - regime_start_bar))
                if regime == 0 and not opened: regime = -1; opened = True; ecL = 0; refLo = refLb = orgL = None; ecS = 0
                refS = None; refSb = None
                if is_ob and H[i] > H[p]: refS = L[i]; refSb = i; refS_kind = "OB"
                if orgS is not None and L[i] < orgS - TICK/2: ecS = 0; orgS = None
            elif orgS is not None and L[i] < orgS - TICK/2: ecS = 0; orgS = None
            if regime <= 0:
                if is_ob:
                    if orgS is None: orgS = L[i]
                    refS = L[i]; refSb = i; refS_kind = "OB"
                elif H[i] > H[p] or L[i] >= L[p] - TICK/2:
                    if refS is None and orgS is None: orgS = L[p]
                    refS = L[i]; refSb = i; refS_kind = "N"
        if regime == -1: ecL = 0; refLo = refLb = orgL = None
        else:
            if refLo is not None and H[i] > refLo + TICK/2:
                ecL += 1; el_fired = True
                entries.append((i, refLb, "L", min(ecL, 3), refLo + TICK, refL_kind, i - regime_start_bar))
                if regime == 0 and not opened: regime = 1; opened = True; ecS = 0; refS = refSb = orgS = None; ecL = 0
                refLo = None; refLb = None
                if is_ob and L[i] < L[p]: refLo = H[i]; refLb = i; refL_kind = "OB"
                if orgL is not None and H[i] > orgL + TICK/2: ecL = 0; orgL = None
            elif orgL is not None and H[i] > orgL + TICK/2: ecL = 0; orgL = None
            if regime >= 0:
                if is_ob:
                    if orgL is None: orgL = H[i]
                    refLo = H[i]; refLb = i; refL_kind = "OB"
                elif L[i] < L[p] or H[i] <= H[p] + TICK/2:
                    if refLo is None and orgL is None: orgL = H[p]
                    refLo = H[i]; refLb = i; refL_kind = "N"
    if regime == -1 and conf_LH is not None and H[i] > conf_LH[1]:
        regime = 0; conf_LH = None; armed_bull = True; armed_bear = False; arm_bar = i; rev_sh = rev_sh_bar = rev_ref_lo = None
        ecS = 0; refS = refSb = orgS = None; ecL = 0; refLo = refLb = orgL = None
    elif regime == 1 and conf_HL is not None and L[i] < conf_HL[1]:
        regime = 0; conf_HL = None; armed_bear = True; armed_bull = False; arm_bar = i; rev_sl = rev_sl_bar = rev_ref_hi = None
        ecS = 0; refS = refSb = orgS = None; ecL = 0; refLo = refLb = orgL = None
    if armed_bull and es_fired: regime = -1; armed_bull = False; rev_sh = rev_sh_bar = rev_ref_lo = None
    elif armed_bear and el_fired: regime = 1; armed_bear = False; rev_sl = rev_sl_bar = rev_ref_hi = None
    if armed_bull and bup(i): regime = 1; armed_bull = False; rev_sh = rev_sh_bar = rev_ref_lo = None
    elif armed_bear and bdn(i): regime = -1; armed_bear = False; rev_sl = rev_sl_bar = rev_ref_hi = None
    if armed_bull and rev_sh is not None and rev_ref_lo is not None and H[i] > rev_sh and L[rev_sh_bar:i+1].min() > rev_ref_lo:
        regime = 1; armed_bull = False
    elif armed_bear and rev_sl is not None and rev_ref_hi is not None and L[i] < rev_sl and H[rev_sl_bar:i+1].max() < rev_ref_hi:
        regime = -1; armed_bear = False
    if regime != _pr:
        if regime != 0: regime_start_bar = i
        _pr = regime
    reg[i] = regime

# one position per regime, exit at flip
trades = []; traded = set()
for (fb, sb, dr, cnt, trig, setup, regage) in entries:
    if setup not in ("IB", "OB"): continue
    epx = fb - regage
    if epx in traded: continue
    short = dr == "S"; a, z = tslice(fb); s = tP[a:z]
    hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
    if not len(hit): continue
    traded.add(epx); jf = a + int(hit[0])
    fill = trig - TICK if short else trig + TICK
    swing = STOPMULT * max(ABR[fb], TICK)
    stop = fill + swing if short else fill - swing
    dsign = -1 if short else 1; ex_bar = n - 1
    for bb in range(fb + 1, n):
        if reg[bb] != dsign: ex_bar = bb; break
    z_ex = np.searchsorted(tbar, ex_bar, "right"); seg = tP[jf:max(z_ex, jf+1)]
    adv = (seg >= stop) if short else (seg <= stop)
    if adv.any(): expx = -swing; exprice = stop; kind = "stop"
    else: expx = (fill - seg[-1]) if short else (seg[-1] - fill); exprice = seg[-1]; kind = "flip" if ex_bar < n-1 else "eod"
    trades.append((fb, sb, ex_bar, dr, setup, fill, stop, exprice, expx / swing, kind))

# ---- chart ----
fig, ax = plt.subplots(figsize=(26, 12))
i0 = 0
for i in range(1, n+1):
    if i == n or reg[i] != reg[i0]:
        c = "#ffe5e5" if reg[i0] == -1 else ("#e3f4e3" if reg[i0] == 1 else "#f0f0f0")
        ax.axvspan(i0-0.5, i-0.5, color=c, alpha=0.6, zorder=0); i0 = i
for i in range(n):
    col = "#26a69a" if C[i] >= O[i] else "#ef5350"
    ax.plot([i, i], [L[i], H[i]], color=col, lw=1.2, zorder=2)
    ax.add_patch(plt.Rectangle((i-0.34, min(O[i], C[i])), 0.68, max(abs(C[i]-O[i]), .02), facecolor=col, edgecolor="black", lw=0.4, zorder=3))
seq = {"HH": 0, "HL": 0, "LH": 0, "LL": 0}
for (idx, prc, typ, lbl) in sw:
    if not lbl: continue
    seq[lbl] += 1; dy = 2.0 if typ == "H" else -2.0
    ax.text(idx, prc+dy, f"{lbl}{seq[lbl]}", ha="center", va="bottom" if typ == "H" else "top",
            fontsize=7, fontweight="bold", color="darkgreen" if lbl in ("HH", "HL") else "darkred", zorder=7)
for (fb, sb, ex_bar, dr, setup, fill, stop, exprice, R, kind) in trades:
    short = dr == "S"; c = "green" if R > 0 else "red"
    ax.annotate("", xy=(fb, fill), xytext=(fb, fill + (3 if short else -3)),
                arrowprops=dict(arrowstyle="-|>", color="blue", lw=2.5), zorder=9)
    ax.text(fb, fill + (3.4 if short else -3.4), f"{'SHORT' if short else 'LONG'}·{setup}", ha="center",
            va="bottom" if short else "top", fontsize=7.5, color="blue", fontweight="bold", zorder=9)
    ax.plot([fb, ex_bar], [stop, stop], color="red", ls="--", lw=1.3, zorder=6)          # swing stop
    ax.plot([fb, ex_bar], [fill, fill], color="blue", ls=":", lw=1.0, zorder=6)           # entry
    ax.plot([ex_bar], [exprice], marker="o", ms=9, mfc=c, mec="black", zorder=10)         # exit
    ax.text(ex_bar, exprice, f" {kind} {R:+.1f}R", fontsize=7, color=c, fontweight="bold", va="center", zorder=10)
ax.set_xticks(range(0, n, 2)); ax.set_xticklabels(range(0, n, 2), fontsize=7); ax.grid(alpha=0.25)
tot = sum(t[8] for t in trades)
ax.set_title(f"{DAY} — regime system: one position/regime, exit at flip, swing 2xABR stop "
             f"| {len(trades)} trades, {tot:+.1f}R", fontsize=13, fontweight="bold")
fig.tight_layout()
out = ROOT / "docs" / "living" / f"regime_day_{DAY.replace('-','')}.png"
fig.savefig(out, dpi=115); print("saved", out)
print("trades:", [(t[0], t[3], t[4], f"{t[8]:+.1f}R", t[9]) for t in trades])
