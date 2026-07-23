"""CAUSALITY AUDIT of the S61 entry engine, before any live port.

In brooks_entry_sim (and every S83 script that copied it), structure events are
keyed by the PIVOT'S OWN BAR (`events.append((idx, ...))` consumed at i == idx),
but a pivot only becomes KNOWABLE at its confirmation (the later flip bar). The
engine's internal regime therefore saw some structure early. A live port can't.

This script re-runs the HEADLINE book (WT | h09-13 | retest 4t THROUGH-fill |
4pt stop | EOD) with events keyed at the CAUSAL bar (the flip bar where the
pivot was appended) and compares against the recorded backtest
(data/regime/headline_trades_detail_20260723.csv).

  python scripts/regime_2e_causal_check.py
Output: data/regime/causal_check_20260723.csv + stdout verdict.
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0
WT_ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT_ROOT / "scripts"))
from regime_second_entry_study import phase_transitions, load_day  # noqa: E402

GOOD_HOURS = {"09", "10", "11", "12", "13"}


def detect_entries_causal(g, tP, tbar):
    """detect_entries with structure events keyed at their KNOWABLE bar."""
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)

    def tick_slice(i):
        a = np.searchsorted(tbar, i, "left"); z = np.searchsorted(tbar, i, "right")
        return a, z

    def ob_cont_first(i, up):
        a, z = tick_slice(i); s = tP[a:z]
        if up:
            c_ = np.nonzero(s > H[i-1])[0]; k_ = np.nonzero(s < L[i-1])[0]
        else:
            c_ = np.nonzero(s < L[i-1])[0]; k_ = np.nonzero(s > H[i-1])[0]
        tc = c_[0] if len(c_) else np.inf
        tb = k_[0] if len(k_) else np.inf
        return tc < tb

    piv = []                      # (idx, price, typ, cb)  cb = append (flip) bar
    d = 1 if H[1] >= H[0] else -1
    ext_i = 0; pj = 0
    for i in range(1, n):
        if H[i] < H[i-1] and L[i] > L[i-1]:
            continue
        if H[i] > H[i-1] and L[i] < L[i-1]:
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
    piv.append((ext_i, H[ext_i] if d == 1 else L[ext_i], "H" if d == 1 else "L", n - 1))

    sw = [[idx, prc, typ, "", cb] for (idx, prc, typ, cb) in piv]
    events = []
    refH = refL = None
    for k, (idx, prc, typ, _, cb) in enumerate(sw):
        if typ == "L":
            if refL is None:
                refL = prc
            elif prc < refL:
                sw[k][3] = "LL"; refL = prc
                lows = [j for j, s in enumerate(sw[:k]) if s[2] == "L"]
                j0 = lows[-1] if lows else -1
                seg = [s for s in sw[j0+1:k] if s[2] == "H"]
                if seg:
                    lh = max(seg, key=lambda s: s[1])
                    if not lh[3] and (refH is None or lh[1] < refH):
                        lh[3] = "LH"; refH = lh[1]
                        events.append((cb, "LL", lh[0], lh[1]))       # CAUSAL key: cb
        else:
            if refH is None:
                refH = prc
            elif prc > refH:
                sw[k][3] = "HH"; refH = prc
                highs = [j for j, s in enumerate(sw[:k]) if s[2] == "H"]
                j0 = highs[-1] if highs else -1
                seg = [s for s in sw[j0+1:k] if s[2] == "L"]
                if seg:
                    hl = min(seg, key=lambda s: s[1])
                    if not hl[3] and (refL is None or hl[1] > refL):
                        hl[3] = "HL"; refL = hl[1]
                        events.append((cb, "HH", hl[0], hl[1]))       # CAUSAL key: cb
    ev_by_bar = {}
    for e in events:
        ev_by_bar.setdefault(e[0], []).append(e)

    entries = []
    regime = 0
    conf_LH = conf_HL = None
    ecS = 0; refS = None; refSb = None; orgS = None
    ecL = 0; refLo = None; refLb = None; orgL = None
    for i in range(n):
        for (ebar, kind, lb, lp) in ev_by_bar.get(i, []):
            if kind == "LL":
                conf_LH = (lb, lp)
                if regime == 0:
                    regime = -1; ecL = 0; refLo = None; refLb = None; orgL = None; ecS = 0
            else:
                conf_HL = (lb, lp)
                if regime == 0:
                    regime = 1; ecS = 0; refS = None; refSb = None; orgS = None; ecL = 0
        if i >= 1:
            is_ob = H[i] > H[i-1] and L[i] < L[i-1]
            if regime == 1:
                ecS = 0; refS = None; refSb = None; orgS = None
            else:
                if refS is not None and L[i] < refS - TICK/2:
                    ecS += 1
                    entries.append((i, refSb, "S", min(ecS, 3), refS - TICK))
                    if regime == 0:
                        regime = -1; ecL = 0; refLo = None; refLb = None; orgL = None; ecS = 0
                    refS = None; refSb = None
                    if is_ob and H[i] > H[i-1]:
                        refS = L[i]; refSb = i
                    if orgS is not None and L[i] < orgS - TICK/2:
                        ecS = 0; orgS = None
                elif orgS is not None and L[i] < orgS - TICK/2:
                    ecS = 0; orgS = None
                if regime <= 0:
                    if is_ob:
                        if orgS is None: orgS = L[i]
                        refS = L[i]; refSb = i
                    elif H[i] > H[i-1] or L[i] >= L[i-1] - TICK/2:
                        if refS is None and orgS is None: orgS = L[i-1]
                        refS = L[i]; refSb = i
            if regime == -1:
                ecL = 0; refLo = None; refLb = None; orgL = None
            else:
                if refLo is not None and H[i] > refLo + TICK/2:
                    ecL += 1
                    entries.append((i, refLb, "L", min(ecL, 3), refLo + TICK))
                    if regime == 0:
                        regime = 1; ecS = 0; refS = None; refSb = None; orgS = None; ecL = 0
                    refLo = None; refLb = None
                    if is_ob and L[i] < L[i-1]:
                        refLo = H[i]; refLb = i
                    if orgL is not None and H[i] > orgL + TICK/2:
                        ecL = 0; orgL = None
                elif orgL is not None and H[i] > orgL + TICK/2:
                    ecL = 0; orgL = None
                if regime >= 0:
                    if is_ob:
                        if orgL is None: orgL = H[i]
                        refLo = H[i]; refLb = i
                    elif L[i] < L[i-1] or H[i] <= H[i-1] + TICK/2:
                        if refLo is None and orgL is None: orgL = H[i-1]
                        refLo = H[i]; refLb = i
        if regime == -1 and conf_LH is not None and C[i] > conf_LH[1]:
            regime = 1; conf_LH = None
            ecS = 0; refS = None; refSb = None; orgS = None; ecL = 0
        elif regime == 1 and conf_HL is not None and C[i] < conf_HL[1]:
            regime = -1; conf_HL = None
            ecL = 0; refLo = None; refLb = None; orgL = None; ecS = 0
    return entries


def main():
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
    b["Date"] = b["DateTime"].dt.date.astype(str)
    days = sorted(b["Date"].unique())
    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g)
        try:
            transitions = phase_transitions(H, L, n, tP, tbar)
            entries = detect_entries_causal(g, tP, tbar)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
            continue
        tr_ix = [t for (t, _) in transitions]; tr_md = [m for (_, m) in transitions]
        g_dt = g["DateTime"].values
        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 2:
                continue
            short = dr == "S"
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            s = tP[a:z]
            hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
            if not len(hit):
                continue
            jf = a + int(hit[0])
            regime = tr_md[bisect_right(tr_ix, jf) - 1]
            if (short and regime != "BEAR") or (not short and regime != "BULL"):
                continue
            lim = trig + 4 * TICK if short else trig - 4 * TICK
            seg0 = tP[jf:]
            jl_ = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
            if not len(jl_):
                continue
            jfl = jf + int(jl_[0])
            fill = lim; fill_bar = int(tbar[jfl])
            hh_ = pd.Timestamp(g_dt[min(fill_bar, n - 1)]).strftime("%H")
            if hh_ not in GOOD_HOURS:
                continue
            stop = fill + 16 * TICK if short else fill - 16 * TICK
            seg = tP[jfl:]
            js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
            ex = stop if len(js_) else seg[-1]
            pnl = ((fill - ex) if short else (ex - fill)) * PT - COMM
            rows.append((dstr, dr, fb + 1, round(pnl, 1)))
        del tP, tbar; gc.collect()
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] n={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    ca = pd.DataFrame(rows, columns=["Date", "dir", "fire_bar", "net"])
    ca.to_csv(WT_ROOT / "data" / "regime" / "causal_check_20260723.csv", index=False)

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return gp / gl if gl > 0 else float("inf")

    det = pd.read_csv(WT_ROOT / "data" / "regime" / "headline_trades_detail_20260723.csv")
    print("\n== CAUSAL vs RECORDED (headline strict book) ==")
    print(f"recorded: n={len(det)}  net {det.net.sum():+,.0f}  PF {pf(det.net):.3f}")
    print(f"causal  : n={len(ca)}  net {ca.net.sum():+,.0f}  PF {pf(ca.net):.3f}")
    a = set(zip(det.Date, det["dir"], det.fill_bar))   # fill_bar vs fire_bar differ; compare counts/day
    per_day = pd.concat([det.groupby("Date").size().rename("rec"),
                         ca.groupby("Date").size().rename("cau")], axis=1).fillna(0)
    same = (per_day.rec == per_day.cau).mean()
    print(f"days with identical trade count: {same*100:.1f}%")


if __name__ == "__main__":
    main()
