"""Regime x SECOND-ENTRY sweeps — S83 stage 2 (worktree branch regime/indep).

Runs AFTER regime_second_entry_study.py. One chronological tick pass produces:

  A) data/regime/second_entries_features_20260723.csv — one row per traded entry
     (counts 1+2; 2E is the study focus) with:
       - regime labels under THREE machines:
           base   : phase machine v4 (tick break starts/terminations)
           sticky : NEUTRAL inherits the prior trend until an OPPOSITE start (relabel)
           closec : starts/terminations require a bar CLOSE beyond the level
       - features at signal: EMA20 dist, ER10, ADX14, stoch %K/%D, zerolag osc,
         IB (first hour) position, fill time (machine-tz, raw), bar index
       - day features: VIX prior close, prior-day range%, 10d ADR%, gap%,
         prior-day VAH/VAL/POC (70% value area from prior-day tick profile),
         ETH overnight high/low position
       - base-sim results (T1/T2 nets) for convenience
  B) data/regime/second_entries_stop_target_sweep_20260723.csv — long format:
     entry x stop-variant x target-variant -> R, net$  (first-hit tick semantics,
     EOD flat, $5 RT, 1 ES). Stop variants: sigbar+1t (base), sigbar+4t, fixed
     2/3/4pt. Targets: 0.5/1/1.5/2/3/4 R, fixed 2/4/6pt, EOD hold.

NOT included (coverage too thin for 5yr, flagged not silently dropped):
  gamma regime (gamma.db starts 2026-07-10), MenthorQ levels (2025+).

Usage:  python scripts/regime_2e_sweeps.py [--limit N]
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0
WT_ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")          # main-repo data, read-only
sys.path.insert(0, str(WT_ROOT / "scripts"))
from regime_second_entry_study import phase_transitions, load_day  # noqa: E402

OUT_F = WT_ROOT / "data" / "regime" / "second_entries_features_20260723.csv"
OUT_S = WT_ROOT / "data" / "regime" / "second_entries_stop_target_sweep_20260723.csv"
BARS = DATA / "bars" / "_continuous.parquet"
TICKD = DATA / "ticks_continuous"

STOPS = [("sb1", "sig", 1), ("sb4", "sig", 4),
         ("fx2p", "fix", 8), ("fx3p", "fix", 12), ("fx4p", "fix", 16)]
TGT_R = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0]
TGT_FIX = [8, 16, 24]            # ticks: 2/4/6 pt
# target ids: r05..r40, f2p/f4p/f6p, eod


# ============ close-confirm phase machine (v4 copy; regime changes on CLOSE) ============
def phase_transitions_closec(H, L, C, n, tP, tbar):
    """Identical to phase_transitions EXCEPT trend starts and terminations fire only
    when a completed bar CLOSES beyond the level (race level / standing major).
    Pivot formation, candidate contest and running-extreme updates stay tick-driven."""
    piv = []
    prevH = prevL = 0
    first_pivot_done = False
    mode = "NEUTRAL"
    standing = None
    run_b = None; run_px = None
    cand = None
    hi_p = None; lo_p = None
    lsh = None; lsl = None
    has_hl = False; has_lh = False
    struct_hl = None; struct_lh = None
    d = None; leg_px = None; leg_bar = None

    def add_pivot(bar, side, emit):
        nonlocal prevH, prevL, first_pivot_done, hi_p, lo_p, lsh, lsl
        nonlocal has_hl, has_lh, cand, struct_hl, struct_lh
        if side == "H":
            t = "hh" if H[bar] > H[prevH] else ("lh" if H[bar] < H[prevH] else "dh"); prevH = bar
        else:
            t = "hl" if L[bar] > L[prevL] else ("ll" if L[bar] < L[prevL] else "dl"); prevL = bar
        disp = side if not first_pivot_done else t
        first_pivot_done = True
        p = dict(bar=bar, side=side, tag=t, disp=disp, major=None, majlab=None)
        piv.append(p)
        if mode == "NEUTRAL":
            if side == "H":
                lsh = p
                if hi_p is None or H[bar] > H[hi_p["bar"]]: hi_p = p
                if t == "lh" or len(disp) == 1: has_lh = True; struct_lh = p
            else:
                lsl = p
                if lo_p is None or L[bar] < L[lo_p["bar"]]: lo_p = p
                if t == "hl" or len(disp) == 1: has_hl = True; struct_hl = p
        elif mode == "BULL" and side == "L":
            if cand is None or L[bar] < L[cand["p"]["bar"]]:
                cand = dict(p=p, ref_px=run_px)
        elif mode == "BEAR" and side == "H":
            if cand is None or H[bar] > H[cand["p"]["bar"]]:
                cand = dict(p=p, ref_px=run_px)
        return p

    def start_trend(up, b, px):
        nonlocal mode, standing, run_b, run_px, cand
        partner = struct_hl if up else struct_lh
        standing = None
        if partner is not None:
            standing = (partner["bar"], L[partner["bar"]] if up else H[partner["bar"]])
        run_b, run_px = b, px
        mode = "BULL" if up else "BEAR"; cand = None

    def terminate(b):
        nonlocal mode, standing, run_b, run_px, cand, d, leg_px, leg_bar
        nonlocal hi_p, lo_p, lsh, lsl, has_hl, has_lh, struct_hl, struct_lh, prevH, prevL
        mode = "NEUTRAL"
        cand = None; standing = None; run_b = run_px = None
        hi_p = lo_p = lsh = lsl = None; has_hl = has_lh = False
        struct_hl = struct_lh = None
        prevH = b; prevL = b
        d = None; leg_px = leg_bar = None

    def close_checks(pb, _t):
        """Evaluate regime conditions on completed bar pb's close (at tick _t)."""
        nonlocal mode
        cpx = C[pb]
        if mode == "NEUTRAL":
            if lsh is not None and cpx > H[lsh["bar"]] and has_hl:
                start_trend(True, pb, cpx)
            elif lsl is not None and cpx < L[lsl["bar"]] and has_lh:
                start_trend(False, pb, cpx)
        elif standing is not None:
            if (mode == "BULL" and cpx < standing[1]) or (mode == "BEAR" and cpx > standing[1]):
                terminate(pb)

    transitions = [(0, "NEUTRAL")]
    cur_bar = -1
    up_done = dn_done = True
    for _t in range(len(tP)):
        b = int(tbar[_t])
        if b < 1 or b >= n:
            continue
        px = tP[_t]
        if b != cur_bar:
            if cur_bar >= 1:
                close_checks(cur_bar, _t)          # prior bar completed -> close rules
            cur_bar = b
            up_done = dn_done = False
        if d == 1 and (leg_px is None or px > leg_px): leg_px, leg_bar = px, b
        if d == -1 and (leg_px is None or px < leg_px): leg_px, leg_bar = px, b
        if not up_done and px > H[b - 1]:
            up_done = True
            if d == -1:
                add_pivot(leg_bar, "L", b)
                d = 1; leg_px, leg_bar = px, b
            elif d is None:
                d = 1; leg_px, leg_bar = px, b
        if not dn_done and px < L[b - 1]:
            dn_done = True
            if d == 1:
                add_pivot(leg_bar, "H", b)
                d = -1; leg_px, leg_bar = px, b
            elif d is None:
                d = -1; leg_px, leg_bar = px, b
        if mode != "NEUTRAL":
            if cand is not None and cand["ref_px"] is not None:
                hit = px > cand["ref_px"] if mode == "BULL" else px < cand["ref_px"]
                if hit:
                    q = cand["p"]
                    standing = (q["bar"], L[q["bar"]] if mode == "BULL" else H[q["bar"]])
                    cand = None
            if mode == "BULL" and px > run_px: run_b, run_px = b, px
            if mode == "BEAR" and px < run_px: run_b, run_px = b, px
        if transitions[-1][1] != mode:
            transitions.append((_t, mode))
    if cur_bar >= 1:
        close_checks(cur_bar, len(tP) - 1)
        if transitions[-1][1] != mode:
            transitions.append((len(tP) - 1, mode))
    return transitions


# ============ entry detection (verbatim from regime_second_entry_study.run_day) ============
def detect_entries(g, tP, tbar):
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
    return entries


# ================================ indicators ================================
def ema(x, n):
    a = 2.0 / (n + 1)
    out = np.empty_like(x, dtype=float); out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def zlema(x, n):
    lag = (n - 1) // 2
    adj = 2 * x - np.roll(x, lag); adj[:lag] = x[:lag]
    return ema(adj, n)


def wilder_adx(H, L, C, n=14):
    m = len(C)
    tr = np.zeros(m); pdm = np.zeros(m); ndm = np.zeros(m)
    for i in range(1, m):
        tr[i] = max(H[i] - L[i], abs(H[i] - C[i-1]), abs(L[i] - C[i-1]))
        up = H[i] - H[i-1]; dn = L[i-1] - L[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        ndm[i] = dn if (dn > up and dn > 0) else 0.0
    atr = np.zeros(m); spd = np.zeros(m); snd = np.zeros(m); adx = np.full(m, np.nan)
    atr[n] = tr[1:n+1].sum(); spd[n] = pdm[1:n+1].sum(); snd[n] = ndm[1:n+1].sum()
    dx = np.full(m, np.nan)
    for i in range(n + 1, m):
        atr[i] = atr[i-1] - atr[i-1] / n + tr[i]
        spd[i] = spd[i-1] - spd[i-1] / n + pdm[i]
        snd[i] = snd[i-1] - snd[i-1] / n + ndm[i]
        pdi = 100 * spd[i] / atr[i] if atr[i] > 0 else 0
        ndi = 100 * snd[i] / atr[i] if atr[i] > 0 else 0
        dx[i] = 100 * abs(pdi - ndi) / (pdi + ndi) if (pdi + ndi) > 0 else 0
    st = 2 * n
    if m > st:
        adx[st] = np.nanmean(dx[n+1:st+1])
        for i in range(st + 1, m):
            adx[i] = (adx[i-1] * (n - 1) + dx[i]) / n
    return adx


def stoch_kd(H, L, C, n=14, k_s=3, d_s=3):
    m = len(C)
    raw = np.full(m, 50.0)
    for i in range(m):
        a = max(0, i - n + 1)
        hh = H[a:i+1].max(); ll = L[a:i+1].min()
        raw[i] = 100 * (C[i] - ll) / (hh - ll) if hh > ll else 50.0
    k = pd.Series(raw).rolling(k_s, min_periods=1).mean().values
    dv = pd.Series(k).rolling(d_s, min_periods=1).mean().values
    return k, dv


def er10(C):
    m = len(C); out = np.full(m, np.nan)
    dif = np.abs(np.diff(C, prepend=C[0]))
    for i in range(10, m):
        den = dif[i-9:i+1].sum()
        out[i] = abs(C[i] - C[i-10]) / den if den > 0 else 0.0
    return out


def value_area(tkP, tkV):
    """POC + 70% value area from a day's tick volume-at-price."""
    px = np.round(tkP / TICK).astype(np.int64)
    vp = {}
    for p_, v_ in zip(px, tkV):
        vp[p_] = vp.get(p_, 0) + v_
    if not vp:
        return None
    keys = sorted(vp)
    vols = np.array([vp[k] for k in keys], dtype=float)
    tot = vols.sum(); poc_i = int(vols.argmax())
    lo = hi = poc_i; acc = vols[poc_i]
    while acc < 0.70 * tot and (lo > 0 or hi < len(keys) - 1):
        vlo = vols[lo - 1] if lo > 0 else -1
        vhi = vols[hi + 1] if hi < len(keys) - 1 else -1
        if vhi >= vlo:
            hi += 1; acc += vols[hi]
        else:
            lo -= 1; acc += vols[lo]
    return keys[poc_i] * TICK, keys[lo] * TICK, keys[hi] * TICK   # POC, VAL, VAH


# ================================ driver ================================
def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    b = pd.read_parquet(BARS)
    b["Date"] = b["DateTime"].dt.date.astype(str)
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]

    # day-level context from bars (daily agg) + VIX + ETH levels
    dly = b.groupby("Date").agg(dO=("Open", "first"), dH=("High", "max"),
                                dL=("Low", "min"), dC=("Close", "last")).reset_index()
    dly["rng_pct"] = (dly.dH - dly.dL) / dly.dC * 100
    dly["adr10"] = dly["rng_pct"].rolling(10).mean().shift(1)   # prior 10d avg
    dly["prev_rng_pct"] = dly["rng_pct"].shift(1)
    dly["prev_C"] = dly["dC"].shift(1)
    dly = dly.set_index("Date")

    vix = pd.read_csv(WT_ROOT / "data" / "VIX_History.csv")
    vix["Date"] = pd.to_datetime(vix["DATE"]).dt.date.astype(str)
    vix = vix.set_index("Date")["CLOSE"].sort_index()

    eth = pd.read_parquet(DATA / "eth_levels.parquet")
    eth["Date"] = eth["Date"].astype(str)
    eth = eth.set_index("Date")

    frows = []; srows = []
    prev_profile = {}          # date -> (POC, VAL, VAH) of that date
    prev_day = None
    t0 = time.time(); ndone = 0
    for di, dstr in enumerate(days):
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        tk_v = pd.read_parquet(TICKD / f"{dstr}.parquet", columns=["Volume"])["Volume"].values \
            if (TICKD / f"{dstr}.parquet").exists() else None
        O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
        n = len(g)
        try:
            trans_b = phase_transitions(H, L, n, tP, tbar)
            trans_c = phase_transitions_closec(H, L, C, n, tP, tbar)
            entries = detect_entries(g, tP, tbar)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
            prev_day = dstr
            continue

        # indicators on 5-min bars
        e20 = ema(C, 20)
        zl = zlema(C, 12) - zlema(C, 26)
        adx = wilder_adx(H, L, C, 14)
        kK, kD = stoch_kd(H, L, C)
        er = er10(C)
        ibN = min(12, n)
        ib_hi = H[:ibN].max(); ib_lo = L[:ibN].min()
        atr10 = pd.Series(H - L).rolling(10, min_periods=1).mean().values

        dd = dly.loc[dstr]
        vix_prev = vix[vix.index < dstr]
        vix_v = float(vix_prev.iloc[-1]) if len(vix_prev) else np.nan
        gap = (O[0] - dd.prev_C) / dd.prev_C * 100 if pd.notna(dd.prev_C) else np.nan
        pva = prev_profile.get(prev_day)
        eth_row = eth.loc[dstr] if dstr in eth.index else None
        times = g["DateTime"].dt.strftime("%H:%M").values

        tr_ix_b = [t for (t, _) in trans_b]; tr_md_b = [m for (_, m) in trans_b]
        tr_ix_c = [t for (t, _) in trans_c]; tr_md_c = [m for (_, m) in trans_c]

        def lab(ix, md, jf):
            return md[bisect_right(ix, jf) - 1]

        def sticky(jf):
            k = bisect_right(tr_ix_b, jf) - 1
            for q in range(k, -1, -1):
                if tr_md_b[q] != "NEUTRAL":
                    return tr_md_b[q]
            return "NEUTRAL"

        for (fb, sb, dr, cnt, trig) in entries:
            if cnt >= 3:
                continue
            short = dr == "S"
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            s = tP[a:z]
            hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
            if not len(hit):
                continue
            jf = a + int(hit[0])
            fill = trig - TICK if short else trig + TICK
            seg = tP[jf:]
            eid = f"{dstr}_{fb+1}{dr}{cnt}"

            # ---- stop/target grid ----
            base_R = None; base_nets = {}
            for (sid, skind, sticks) in STOPS:
                if skind == "sig":
                    stop = (H[sb] + sticks * TICK) if short else (L[sb] - sticks * TICK)
                else:
                    stop = (fill + sticks * TICK) if short else (fill - sticks * TICK)
                R = (stop - fill) if short else (fill - stop)
                if R <= 0:
                    continue
                js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
                js = js_[0] if len(js_) else np.inf
                tgts = [("r%02d" % int(r_ * 10), r_ * R) for r_ in TGT_R] + \
                       [("f%dp" % (tk_ // 4), tk_ * TICK) for tk_ in TGT_FIX] + \
                       [("eod", None)]
                for (tid, dist) in tgts:
                    if dist is None:
                        ex = stop if np.isfinite(js) else seg[-1]
                    else:
                        tgt = fill - dist if short else fill + dist
                        jt_ = np.nonzero(seg <= tgt)[0] if short else np.nonzero(seg >= tgt)[0]
                        jt = jt_[0] if len(jt_) else np.inf
                        if js <= jt:
                            ex = stop
                        elif np.isfinite(jt):
                            ex = tgt
                        else:
                            ex = seg[-1]
                    pnl = (fill - ex) if short else (ex - fill)
                    net = pnl * PT - COMM
                    srows.append((eid, dstr, dr, cnt, sid, tid, pnl / max(R, 1e-9), net))
                    if sid == "sb1":
                        if tid == "r10": base_nets["T1"] = net
                        if tid == "r20": base_nets["T2"] = net; base_R = R

            # ---- features ----
            ema_d = (fill - e20[fb]) / max(atr10[fb], TICK)     # EMA dist in ATR10 units
            ib_pos = "above" if fill > ib_hi else ("below" if fill < ib_lo else "inside")
            if pva:
                poc, val, vah = pva
                va_pos = "above" if fill > vah else ("below" if fill < val else "inside")
            else:
                poc = val = vah = np.nan; va_pos = ""
            if eth_row is not None:
                eth_pos = ("above" if fill > eth_row.ETH_High
                           else ("below" if fill < eth_row.ETH_Low else "inside"))
            else:
                eth_pos = ""
            frows.append(dict(
                entry_id=eid, Date=dstr, dir=dr, count=cnt, fire_bar=fb + 1,
                sig_bar=sb + 1, fill=fill, R_base=base_R,
                netT1=base_nets.get("T1", np.nan), netT2=base_nets.get("T2", np.nan),
                reg_base=lab(tr_ix_b, tr_md_b, jf), reg_sticky=sticky(jf),
                reg_closec=lab(tr_ix_c, tr_md_c, jf),
                bar_time=times[fb], ema20_atr=round(ema_d, 3),
                er10=round(float(er[fb]), 3) if np.isfinite(er[fb]) else np.nan,
                adx14=round(float(adx[fb]), 1) if np.isfinite(adx[fb]) else np.nan,
                stochK=round(float(kK[sb]), 1), stochD=round(float(kD[sb]), 1),
                zl_osc=round(float(zl[fb]), 2), zl_sign=int(np.sign(zl[fb])),
                ib_pos=ib_pos, va_pos=va_pos, eth_pos=eth_pos,
                vix=vix_v, gap_pct=round(gap, 3) if np.isfinite(gap) else np.nan,
                prev_rng_pct=round(float(dd.prev_rng_pct), 3) if pd.notna(dd.prev_rng_pct) else np.nan,
                adr10_pct=round(float(dd.adr10), 3) if pd.notna(dd.adr10) else np.nan))

        if tk_v is not None and len(tk_v) == len(tP):
            va = value_area(tP, tk_v)
            if va:
                prev_profile = {dstr: va}
        prev_day = dstr
        ndone += 1
        del tP, tbar; gc.collect()
        if (di + 1) % 50 == 0:
            print(f"[{di+1}/{len(days)}] entries={len(frows)} ({time.time()-t0:.0f}s)", flush=True)

    fdf = pd.DataFrame(frows)
    sdf = pd.DataFrame(srows, columns=["entry_id", "Date", "dir", "count",
                                       "stop", "target", "R", "net"])
    fdf.to_csv(OUT_F, index=False)
    sdf.to_csv(OUT_S, index=False)
    print(f"\nDONE {time.time()-t0:.0f}s days={ndone} entries={len(fdf)} sweep_rows={len(sdf)}")
    print("->", OUT_F)
    print("->", OUT_S)


if __name__ == "__main__":
    main()
