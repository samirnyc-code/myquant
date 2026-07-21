"""First sim of the S61 Brooks entry engine (spec as locked with user 2026-07-08).

Engine: strict legs (IB ignored, OB tick-resolved), direct-travel structure,
neutral open + first-entry regime adoption + close-through flips, origin-reset
entry counting (1ES/2ES/3ES-wedge, mirrored longs).

Trade: stop entry 1t beyond the tracked break level (fill = trigger with 1t
slip), stop 1t beyond signal bar's opposite extreme, targets 1R and 2R
(separate books), EOD flat, $5 RT, 1 contract ES.
"""
import sys, gc, time
from pathlib import Path
from datetime import date
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0
ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(ROOT))
import massive

START, END = "2025-07-08", "2026-07-07"

b = pd.read_parquet(ROOT / "data" / "bars" / "_continuous.parquet")
b["Date"] = b["DateTime"].dt.date.astype(str)
days = sorted(d for d in b["Date"].unique() if START <= d <= END)


def run_day(g, tP, tbar):
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

    # legs
    piv = []
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
                    piv.append((ext_i, H[ext_i], "H")); d = -1; ext_i = i
                else:
                    piv.append((ext_i, H[ext_i], "H")); piv.append((i, L[i], "L")); d = 1; ext_i = i
            else:
                if cf:
                    if L[i] <= L[ext_i]: ext_i = i
                    piv.append((ext_i, L[ext_i], "L")); d = 1; ext_i = i
                else:
                    piv.append((ext_i, L[ext_i], "L")); piv.append((i, H[i], "H")); d = -1; ext_i = i
            pj = i; continue
        if d == 1:
            if H[i] >= H[ext_i]: ext_i = i
            if L[i] < L[pj]:
                piv.append((ext_i, H[ext_i], "H")); d = -1; ext_i = i
        else:
            if L[i] <= L[ext_i]: ext_i = i
            if H[i] > H[pj]:
                piv.append((ext_i, L[ext_i], "L")); d = 1; ext_i = i
        pj = i
    piv.append((ext_i, H[ext_i] if d == 1 else L[ext_i], "H" if d == 1 else "L"))

    # structure vs last labeled extreme
    sw = [[idx, prc, typ, ""] for (idx, prc, typ) in piv]
    events = []
    refH = refL = None
    for k, (idx, prc, typ, _) in enumerate(sw):
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
                        events.append((idx, "LL", lh[0], lh[1]))
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
                        events.append((idx, "HH", hl[0], hl[1]))
    ev_by_bar = {}
    for e in events:
        ev_by_bar.setdefault(e[0], []).append(e)

    # one pass: regime + trackers; collect fired entries
    entries = []   # (fire_bar, sig_bar, dir, count, trigger)
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
        # reg not stored; not needed further

    # ---- trade the fired entries on ticks ----
    out = []
    for (fb, sb, dr, cnt, trig) in entries:
        if cnt >= 3:                       # do not trade 3rd+ entries
            continue
        short = dr == "S"
        a, z = tick_slice(fb)
        s = tP[a:z]
        hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
        if not len(hit):
            continue
        jf = a + int(hit[0])
        fill = trig - TICK if short else trig + TICK        # 1t slip
        stop = H[sb] + TICK if short else L[sb] - TICK
        R = (stop - fill) if short else (fill - stop)
        if R <= 0:
            continue
        seg = tP[jf:]
        js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
        js = js_[0] if len(js_) else np.inf
        for k, book in ((1.0, "T1"), (2.0, "T2")):
            tgt = fill - k * R if short else fill + k * R
            jt_ = np.nonzero(seg <= tgt)[0] if short else np.nonzero(seg >= tgt)[0]
            jt = jt_[0] if len(jt_) else np.inf
            if js <= jt:
                ex = stop
            elif np.isfinite(jt):
                ex = tgt
            else:
                ex = tP[-1]
            pnl = (fill - ex) if short else (ex - fill)
            out.append((dr, cnt, book, pnl / R, pnl * PT - COMM, R))
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
        print(f"[{di+1}/{len(days)}] trades={len(rows)//2} ({time.time()-t0:.0f}s)", flush=True)

df = pd.DataFrame(rows, columns=["Date", "dir", "count", "book", "R", "net", "Rpts"])
df.to_parquet(ROOT / "docs" / "living" / "brooks_sim_trades.parquet")
print(f"\nDONE {time.time()-t0:.0f}s  days={len(days)}  trades/book={len(df)//2}")
for book in ["T1", "T2"]:
    d2 = df[df.book == book]
    ci = 1.96 * d2["R"].std() / np.sqrt(len(d2))
    print(f"\n== target {book} ({'1R' if book=='T1' else '2R'}) ==  n={len(d2)}  "
          f"meanR {d2['R'].mean():+.3f} ±{ci:.3f}  win {(d2['R']>0).mean()*100:.1f}%  "
          f"net ${d2['net'].sum():,.0f}  medR {d2['Rpts'].median():.2f}pts")
    t = d2.groupby(["dir", "count"]).agg(n=("R", "size"), meanR=("R", "mean"),
                                         win=("R", lambda s: (s > 0).mean() * 100),
                                         net=("net", "sum")).round(3)
    print(t.to_string())
