"""Sim v3 — new regime (as v2) PLUS the new entry logic:
IGNORE_IB (legs/structure ignore inside bars; entries arm off the bar BEFORE the
IB = triangle) and ALLOW_LOOSE (loose IB/OB with one equal-tick side count as
IB/OB). Same dates/trade rules/$5 RT/1 ES as v1/v2 so results are comparable.
3rd (wedge) entries are NOT traded (count capped at 2).
"""
import sys, gc, time
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0
IGNORE_IB = True; ALLOW_LOOSE = True
NO_3RD = True                         # do not trade 3rd+ entries
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
import massive

START, END = "2025-07-08", "2026-07-07"
b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous.parquet")
b["Date"] = b["DateTime"].dt.date.astype(str)
days = sorted(d for d in b["Date"].unique() if START <= d <= END)


def run_day(g, tP, tbar):
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)
    rng = (H - L).astype(float)
    IBS = np.where(rng > 0, (C - L) / np.maximum(rng, 1e-9) * 100.0, 50.0)
    ABR = np.array([rng[max(0, i-10):i].mean() if i > 0 else rng[0] for i in range(n)])
    K = 12
    ER = np.zeros(n)
    for i in range(n):
        if i >= K:
            den = np.abs(np.diff(C[i-K:i+1])).sum()
            ER[i] = abs(C[i] - C[i-K]) / den if den > 0 else 0.0
    ema = pd.Series(C).ewm(span=20, adjust=False).mean().values      # EMA20 on closes
    eslope = np.zeros(n)                                             # signed slope in ABR units/bar
    for i in range(n):
        if i >= 3:
            eslope[i] = (ema[i] - ema[i-3]) / 3.0 / max(ABR[i], TICK)

    def btype(i, p):
        eqH = H[i] == H[p]; eqL = L[i] == L[p]
        inH = H[i] < H[p]; inL = L[i] > L[p]
        outH = H[i] > H[p]; outL = L[i] < L[p]
        if inH and inL: return "IB"
        if outH and outL: return "OB"
        if eqH and eqL: return "IB"
        if ALLOW_LOOSE:
            if (eqH and inL) or (eqL and inH): return "IB"
            if (eqH and outL) or (eqL and outH): return "OB"
        return "N"

    is_ib = np.zeros(n, dtype=bool); prev = np.zeros(n, dtype=int)
    if IGNORE_IB:
        _ref = 0
        for i in range(1, n):
            if btype(i, _ref) == "IB": is_ib[i] = True; prev[i] = _ref
            else: prev[i] = _ref; _ref = i
    else:
        for i in range(1, n):
            prev[i] = i-1; is_ib[i] = btype(i, i-1) == "IB"

    def tick_slice(i):
        a = np.searchsorted(tbar, i, "left"); z = np.searchsorted(tbar, i, "right")
        return a, z

    def ob_cont_first(i, up):
        p = prev[i]; a, z = tick_slice(i); s = tP[a:z]
        if up: c_ = np.nonzero(s > H[p])[0]; k_ = np.nonzero(s < L[p])[0]
        else:  c_ = np.nonzero(s < L[p])[0]; k_ = np.nonzero(s > H[p])[0]
        tc = c_[0] if len(c_) else np.inf; tb = k_[0] if len(k_) else np.inf
        return tc < tb

    def boft_up(i):
        if i < 2: return False
        bo, ft = i-1, i
        return (H[bo] > H[bo-1] and IBS[bo] >= 69 and IBS[ft] >= 69
                and (rng[bo] > ABR[bo] or rng[ft] > ABR[ft]))

    def boft_dn(i):
        if i < 2: return False
        bo, ft = i-1, i
        return (L[bo] < L[bo-1] and IBS[bo] <= 31 and IBS[ft] <= 31
                and (rng[bo] > ABR[bo] or rng[ft] > ABR[ft]))

    # legs (IGNORE_IB + loose)
    piv = []
    d = 1 if H[1] >= H[0] else -1
    ext_i = 0; pj = 0
    for i in range(1, n):
        if is_ib[i]: continue
        p = prev[i]
        if btype(i, p) == "OB":
            up = (d == 1); cf = ob_cont_first(i, up)
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
            if L[i] < L[pj]:
                piv.append((ext_i, H[ext_i], "H", i)); d = -1; ext_i = i
        else:
            if L[i] <= L[ext_i]: ext_i = i
            if H[i] > H[pj]:
                piv.append((ext_i, L[ext_i], "L", i)); d = 1; ext_i = i
        pj = i
    piv.append((ext_i, H[ext_i] if d == 1 else L[ext_i], "H" if d == 1 else "L", n-1))
    piv_at_conf = {}
    for (pb, prc, typ, cb) in piv:
        piv_at_conf.setdefault(cb, []).append((pb, prc, typ))

    # structure
    sw = [[idx, prc, typ, ""] for (idx, prc, typ, cb) in piv]
    events = []
    refH = refL = None
    for k, (idx, prc, typ, _) in enumerate(sw):
        if typ == "L":
            if refL is None: refL = prc
            elif prc < refL:
                sw[k][3] = "LL"; refL = prc
                lows = [j for j, s in enumerate(sw[:k]) if s[2] == "L"]; j0 = lows[-1] if lows else -1
                seg = [s for s in sw[j0+1:k] if s[2] == "H"]
                if seg:
                    lh = max(seg, key=lambda s: s[1])
                    if not lh[3] and (refH is None or lh[1] < refH):
                        lh[3] = "LH"; refH = lh[1]; events.append((idx, "LL", lh[0], lh[1]))
        else:
            if refH is None: refH = prc
            elif prc > refH:
                sw[k][3] = "HH"; refH = prc
                highs = [j for j, s in enumerate(sw[:k]) if s[2] == "H"]; j0 = highs[-1] if highs else -1
                seg = [s for s in sw[j0+1:k] if s[2] == "L"]
                if seg:
                    hl = min(seg, key=lambda s: s[1])
                    if not hl[3] and (refL is None or hl[1] > refL):
                        hl[3] = "HL"; refL = hl[1]; events.append((idx, "HH", hl[0], hl[1]))
    ev_by_bar = {}
    for e in events:
        ev_by_bar.setdefault(e[0], []).append(e)

    # ---- one pass: new regime + TRIANGLE entries (IGNORE_IB) ----
    entries = []
    regime = 0; opened = False
    conf_LH = conf_HL = None
    ecS = 0; refS = None; refSb = None; orgS = None
    ecL = 0; refLo = None; refLb = None; orgL = None
    armed_bull = armed_bear = False; arm_bar = None
    last_sh = last_sl = None
    rev_sh = rev_sh_bar = rev_ref_lo = None
    rev_sl = rev_sl_bar = rev_ref_hi = None
    refS_kind = refL_kind = "N"           # how the armed level was set: IB / OB / N
    flip_pending = False                  # next entry is the first after a flip
    regime_start_bar = 0; _pr = 0         # regime age tracking

    for i in range(n):
        es_fired = el_fired = False
        for (ebar, kind, lb, lp) in ev_by_bar.get(i, []):
            if kind == "LL":
                conf_LH = (lb, lp)
                if regime == 0 and not opened:
                    regime = -1; opened = True; ecL = 0; refLo = refLb = orgL = None; ecS = 0
            else:
                conf_HL = (lb, lp)
                if regime == 0 and not opened:
                    regime = 1; opened = True; ecS = 0; refS = refSb = orgS = None; ecL = 0
        for (pb, prc, typ) in piv_at_conf.get(i, []):
            if typ == "H":
                if armed_bull and arm_bar is not None and pb > arm_bar and rev_sh is None:
                    rev_sh = prc; rev_sh_bar = pb; rev_ref_lo = last_sl
                last_sh = prc
            else:
                if armed_bear and arm_bar is not None and pb > arm_bar and rev_sl is None:
                    rev_sl = prc; rev_sl_bar = pb; rev_ref_hi = last_sh
                last_sl = prc

        # inside-bar triangle arming (arm off the bar before the IB)
        if i >= 1 and is_ib[i]:
            p = prev[i]
            if regime <= 0:
                if orgS is None: orgS = L[p]
                refS = L[p]; refSb = p; refS_kind = "IB"
            if regime >= 0:
                if orgL is None: orgL = H[p]
                refLo = H[p]; refLb = p; refL_kind = "IB"

        if i >= 1 and not is_ib[i]:
            p = prev[i]
            is_ob = btype(i, p) == "OB"
            if regime == 1:
                ecS = 0; refS = refSb = orgS = None
            else:
                if refS is not None and L[i] < refS - TICK/2:
                    ecS += 1; es_fired = True
                    entries.append((i, refSb, "S", min(ecS, 3), refS - TICK, refS_kind, int(flip_pending),
                                    i/n, ER[i], int(C[i] < O[0]), i - regime_start_bar, eslope[i]))
                    flip_pending = False
                    if regime == 0 and not opened:
                        regime = -1; opened = True; ecL = 0; refLo = refLb = orgL = None; ecS = 0
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
            if regime == -1:
                ecL = 0; refLo = refLb = orgL = None
            else:
                if refLo is not None and H[i] > refLo + TICK/2:
                    ecL += 1; el_fired = True
                    entries.append((i, refLb, "L", min(ecL, 3), refLo + TICK, refL_kind, int(flip_pending),
                                    i/n, ER[i], int(C[i] > O[0]), i - regime_start_bar, eslope[i]))
                    flip_pending = False
                    if regime == 0 and not opened:
                        regime = 1; opened = True; ecS = 0; refS = refSb = orgS = None; ecL = 0
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
            regime = 0; conf_LH = None; armed_bull = True; armed_bear = False; arm_bar = i
            rev_sh = rev_sh_bar = rev_ref_lo = None
            ecS = 0; refS = refSb = orgS = None; ecL = 0; refLo = refLb = orgL = None
        elif regime == 1 and conf_HL is not None and L[i] < conf_HL[1]:
            regime = 0; conf_HL = None; armed_bear = True; armed_bull = False; arm_bar = i
            rev_sl = rev_sl_bar = rev_ref_hi = None
            ecS = 0; refS = refSb = orgS = None; ecL = 0; refLo = refLb = orgL = None

        if armed_bull and es_fired:
            regime = -1; armed_bull = False; rev_sh = rev_sh_bar = rev_ref_lo = None; flip_pending = True
        elif armed_bear and el_fired:
            regime = 1; armed_bear = False; rev_sl = rev_sl_bar = rev_ref_hi = None; flip_pending = True
        if armed_bull and boft_up(i):
            regime = 1; armed_bull = False; rev_sh = rev_sh_bar = rev_ref_lo = None; flip_pending = True
        elif armed_bear and boft_dn(i):
            regime = -1; armed_bear = False; rev_sl = rev_sl_bar = rev_ref_hi = None; flip_pending = True
        if armed_bull and rev_sh is not None and rev_ref_lo is not None:
            if H[i] > rev_sh and L[rev_sh_bar:i+1].min() > rev_ref_lo:
                regime = 1; armed_bull = False; flip_pending = True
        elif armed_bear and rev_sl is not None and rev_ref_hi is not None:
            if L[i] < rev_sl and H[rev_sl_bar:i+1].max() < rev_ref_hi:
                regime = -1; armed_bear = False; flip_pending = True

        if regime != _pr:                              # regime age tracking
            if regime != 0: regime_start_bar = i
            _pr = regime

    # ---- STOP x TARGET matrix (exact tick order) ----
    STOPS = [("SB", None), ("A1", 1.0), ("A1.5", 1.5), ("A2", 2.0)]   # None=signal bar; else xABR
    TGTS = [("t3", 3.0), ("t5", 5.0), ("t8", 8.0), ("t12", 12.0), ("EOD", None)]

    def first(cond):
        return int(np.argmax(cond)) if cond.any() else 10**9

    out = []
    for (fb, sb, dr, cnt, trig, setup, pf, frac, er, withday, regage, eslp) in entries:
        if NO_3RD and cnt >= 3:
            continue
        short = dr == "S"
        a, z = tick_slice(fb); s = tP[a:z]
        hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
        if not len(hit):
            continue
        jf = a + int(hit[0])
        fill = trig - TICK if short else trig + TICK
        sbR = (H[sb] + TICK - fill) if short else (fill - (L[sb] - TICK))
        if sbR <= 0:
            continue
        seg = tP[jf:]
        abr_e = max(ABR[fb], TICK)
        sbibs = IBS[sb] if not short else (100 - IBS[sb])
        wslope = int((eslp < 0) if short else (eslp > 0))          # trade agrees with EMA slope
        aslope = round(abs(eslp), 3)

        def adv_first(x):    # adverse move of x pts from fill
            return first((seg >= fill + x) if short else (seg <= fill - x))

        def fav_first(x):    # favorable move of x pts from fill
            return first((seg <= fill - x) if short else (seg >= fill + x))

        jstop = {}
        for sn, mult in STOPS:
            sd = sbR if mult is None else mult * abr_e
            jstop[sn] = (adv_first(sd), sd)
        jtgt = {}
        for tn, td in TGTS:
            jtgt[tn] = ((10**9, None) if td is None else (fav_first(td), td))
        finpts = (fill - seg[-1]) if short else (seg[-1] - fill)
        for sn, (js, sd) in jstop.items():
            for tn, (jt, td) in jtgt.items():
                if js < jt:
                    exp = -sd
                elif td is not None and jt < 10**9:
                    exp = td
                else:
                    exp = finpts
                out.append((dr, cnt, setup, int(withday), round(frac, 3), round(sbibs, 1),
                            wslope, aslope, sn, tn, exp / sd, exp * PT - COMM))
            for rk in (1.0, 2.0, 3.0):                 # R-multiple targets (RR relative to THIS stop)
                jr = fav_first(rk * sd)
                if js < jr:
                    exp = -sd
                elif jr < 10**9:
                    exp = rk * sd
                else:
                    exp = finpts
                out.append((dr, cnt, setup, int(withday), round(frac, 3), round(sbibs, 1),
                            wslope, aslope, sn, f"{int(rk)}R", exp / sd, exp * PT - COMM))
        # BE management on the swing (A2) stop: move stop to fill after +be pts, hold to EOD
        swing = 2.0 * abr_e; t_sw = adv_first(swing)
        for be in (1.0, 2.0):
            t_tr = fav_first(be)
            if t_sw < t_tr:
                exp = -swing
            else:
                after = seg[t_tr:]
                back = first((after >= fill) if short else (after <= fill))   # return to BE
                exp = 0.0 if back < 10**9 else finpts
            out.append((dr, cnt, setup, int(withday), round(frac, 3), round(sbibs, 1),
                        wslope, aslope, "A2", f"BE{int(be)}", exp / swing, exp * PT - COMM))
    return out


t0 = time.time(); rows = []
for di, d in enumerate(days):
    g = b[b["Date"] == d].sort_values("DateTime").reset_index(drop=True)
    if len(g) < 30:
        continue
    tk = massive.load_continuous_ticks(date.fromisoformat(d))
    if tk.empty:
        continue
    tk = tk.sort_values("DateTime")
    tP = tk["Price"].values
    tbar = np.searchsorted(g["DateTime"].values, tk["DateTime"].values, side="right") - 1
    try:
        for r in run_day(g, tP, tbar):
            rows.append((d,) + r)
    except Exception as e:
        print(d, "ERR", e)
    del tk, tP, tbar; gc.collect()
    if (di + 1) % 50 == 0:
        print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

df = pd.DataFrame(rows, columns=["Date", "dir", "count", "setup", "withday", "frac", "sbibs",
                                 "wslope", "aslope", "stop", "target", "R", "net"])
df.to_parquet(ROOT / "docs" / "living" / "brooks_sim_matrix.parquet")
ntr = len(df[(df.stop == "SB") & (df.target == "EOD")])
print(f"\nDONE {time.time()-t0:.0f}s  days={len(days)}  trades={ntr}")
STOPS = ["SB", "A1", "A1.5", "A2"]; TGTS = ["1R", "2R", "3R", "t8", "EOD", "BE1", "BE2"]


def matrix(sub, title):
    print(f"\n===== {title}  (n={len(sub)//(len(STOPS)*len(TGTS))}) =====")
    for metric in ("win%", "avgR", "net$", "PF"):
        print(f"  [{metric}]   " + "  ".join(f"{t:>7}" for t in TGTS))
        for sn in STOPS:
            cells = []
            for tn in TGTS:
                c = sub[(sub.stop == sn) & (sub.target == tn)]
                if metric == "win%": v = f"{(c.R>0).mean()*100:6.1f}"
                elif metric == "avgR": v = f"{c.R.mean():+6.3f}"
                elif metric == "net$": v = f"{c.net.sum():7.0f}"
                else:
                    gp = c.net[c.net > 0].sum(); gl = -c.net[c.net < 0].sum()
                    v = f"{(gp/gl if gl else 9):6.2f}"
                cells.append(f"{v:>7}")
            print(f"  {sn:5s}      " + "  ".join(cells))


IBOB = df[df.setup.isin(["IB", "OB"])]
matrix(IBOB, "IB+OB (all day)")
matrix(IBOB[IBOB.frac < 0.33], "IB+OB MORNING")
matrix(IBOB[(IBOB.frac < 0.33) & (IBOB.sbibs >= 60)], "IB+OB MORNING + SB-IBS>=60")
