"""Tick-accurate sim for MyReversals (RevFT) signals exported from the NT8 indicator.

Signal source = the indicator's own export (ground truth at default settings):
  data/signals/All MyReversals Signal Export ... 1850 Days.txt
  cols: Counter Type Direction DD/MM/YYYY HH:MM:SS(CT, = FT bar CLOSE) BarNo BTC Stop

Trade model (reuses the tick discipline of research/scalp_swing/engine_ticks):
  - side from Direction; risk = |BTC - Stop|.
  - ENTRY (selectable): 'market' = first tick at/after signal time (next bar);
    'retest' = limit at BTC, fill if price returns to BTC before Stop is hit (else DEAD);
    'stopbeyond' = stop-entry 1t beyond FT extreme in trade dir (needs bars).
  - EXIT: first of {Stop, Target} on the tick path; Target = BTC + side*RR*risk;
    if hold_eod, no fixed target -> exit at last RTH tick. Stop always active.
  - 1 position at a time, no opposing (skip signals while in a trade). $30 RT, $50/pt.
All fills on raw ticks in time order -> no phantom fills.
"""
import sys, re
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(r"c:\Users\Admin\myquant"); sys.path.insert(0, str(ROOT / "research" / "scalp_swing"))
import engine_ticks as E   # reuse _load_ticks, metrics, by_year

PT = 50.0; COST = 30.0; TICK = 0.25
DEFAULT_TXT = ROOT / "data" / "signals" / "All MyReversals Signal Export - ES SEP26 - Nymex Energy RTH - 5 Minute from 02.07.2026 - 1850 Days.txt"


def parse_signals(path=DEFAULT_TXT):
    rows = []
    for ln in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        p = ln.split()
        if len(p) < 8 or p[2] not in ("Long", "Short"):
            continue
        try:
            cnt = int(p[0])
        except ValueError:
            continue
        date = pd.to_datetime(p[3], format="%d/%m/%Y").date()
        t = pd.to_datetime(f"{p[3]} {p[4]}", format="%d/%m/%Y %H:%M:%S")
        entry = float(p[6].replace(",", "")); stop = float(p[7].replace(",", ""))
        rows.append(dict(cnt=cnt, rev=p[1], side=1 if p[2] == "Long" else -1,
                         Date=str(date), time=t, barno=int(p[5]), entry=entry, stop=stop))
    df = pd.DataFrame(rows).sort_values("time").reset_index(drop=True)
    return df


def sim(sigs, entry="market", rr=2.0, hold_eod=False, min_rr=0.0,
        gate=None, sma=None, tod=None, retest_expiry_min=25):
    """sigs: parsed DataFrame (optionally pre-filtered by type/dir). Returns trades df.
    gate: None | 'above' | 'below'  (price vs SMA20-D at signal, needs sma map).
    tod: None | (lo_hhmm, hi_hhmm) restrict signal time-of-day (CT), e.g. (830,1300)."""
    trades = []
    for date, day in sigs.groupby("Date", sort=True):
        try:
            tt, tp = E._load_ticks(date)
        except FileNotFoundError:
            continue
        if len(tt) == 0:
            continue
        sess_end = tt[-1]
        L = sma.get(date, np.nan) if sma is not None else np.nan
        ptr = tt[0]
        for _, s in day.iterrows():
            st = np.datetime64(s["time"])
            if st < ptr:
                continue
            side = int(s["side"]); btc = s["entry"]; stop = s["stop"]
            risk = abs(btc - stop)
            if risk <= 0:
                continue
            # time-of-day gate
            if tod is not None:
                hm = s["time"].hour * 100 + s["time"].minute
                if not (tod[0] <= hm <= tod[1]):
                    continue
            # regime gate
            if gate is not None and np.isfinite(L):
                if gate == "above" and not (btc > L): continue
                if gate == "below" and not (btc < L): continue
            # entry window starts at signal time (next-bar ticks)
            e0 = np.searchsorted(tt, st, side="left")
            if e0 >= len(tt):
                continue
            if entry == "market":
                efill = e0
            elif entry == "retest":
                # limit at BTC; fill if price reaches BTC before Stop; DEAD else
                wend = np.searchsorted(tt, st + np.timedelta64(retest_expiry_min, "m"), side="right")
                seg = tp[e0:wend]
                if seg.size == 0:
                    continue
                if side > 0:
                    reachB = seg <= btc; hitS = seg <= stop
                else:
                    reachB = seg >= btc; hitS = seg >= stop
                iB = np.argmax(reachB) if reachB.any() else -1
                iS = np.argmax(hitS) if hitS.any() else -1
                if iB < 0:
                    continue
                if iS >= 0 and iS < iB:
                    continue  # stopped before fill -> DEAD
                efill = e0 + iB
            else:
                efill = e0
            fpx = btc if entry == "retest" else tp[efill]
            ftime = tt[efill]
            target = btc + side * rr * risk
            if abs(target - fpx) < min_rr * risk - 1e-9:
                pass  # min_rr handled by choosing rr; keep
            # exit scan on ticks after fill
            xseg = tp[efill + 1:]
            xt = tt[efill + 1:]
            if xseg.size == 0:
                continue
            if side > 0:
                sc = xseg <= stop; tc = xseg >= target
            else:
                sc = xseg >= stop; tc = xseg <= target
            si = np.argmax(sc) if sc.any() else -1
            ti = (np.argmax(tc) if tc.any() else -1) if not hold_eod else -1
            cand = [c for c in [(si, "stop"), (ti, "target")] if c[0] >= 0]
            if cand:
                xi, reason = min(cand, key=lambda c: c[0])
                xpx = stop if reason == "stop" else target
                xtime = xt[xi]
            else:
                xpx = xseg[-1]; xtime = xt[-1]; reason = "eod"
            pnl_pts = (xpx - fpx) * side
            trades.append(dict(Date=date, rev=s["rev"], side=side, entry=round(fpx, 2),
                               stop=stop, target=round(target, 2), exitpx=round(xpx, 2),
                               reason=reason, risk_pts=round(risk, 2), pnl_pts=round(pnl_pts, 2),
                               pnl=round(pnl_pts * PT - COST, 2), etime=ftime, xtime=xtime))
            ptr = xtime
    return pd.DataFrame(trades)


def sim_day(date, tt, tp, day, cfg, sma_L=np.nan):
    """One day, preloaded ticks + that day's (already type/dir-filtered) signals + cfg dict.
    cfg keys: entry, rr, hold_eod, gate, tod, retest_expiry_min. Returns list of trade dicts."""
    out = []; sess_end = tt[-1]; ptr = tt[0]
    entry = cfg.get("entry", "market"); rr = cfg.get("rr", 2.0)
    hold_eod = cfg.get("hold_eod", False); gate = cfg.get("gate")
    tod = cfg.get("tod"); rexp = cfg.get("retest_expiry_min", 25)
    for _, s in day.iterrows():
        st = np.datetime64(s["time"])
        if st < ptr:
            continue
        side = int(s["side"]); btc = s["entry"]; stop = s["stop"]; risk = abs(btc - stop)
        if risk <= 0:
            continue
        if tod is not None:
            hm = s["time"].hour * 100 + s["time"].minute
            if not (tod[0] <= hm <= tod[1]):
                continue
        if gate is not None and np.isfinite(sma_L):
            if gate == "above" and not (btc > sma_L): continue
            if gate == "below" and not (btc < sma_L): continue
        e0 = np.searchsorted(tt, st, side="left")
        if e0 >= len(tt):
            continue
        if entry == "retest":
            wend = np.searchsorted(tt, st + np.timedelta64(rexp, "m"), side="right")
            seg = tp[e0:wend]
            if seg.size == 0:
                continue
            if side > 0:
                reachB = seg <= btc; hitS = seg <= stop
            else:
                reachB = seg >= btc; hitS = seg >= stop
            iB = np.argmax(reachB) if reachB.any() else -1
            iS = np.argmax(hitS) if hitS.any() else -1
            if iB < 0 or (iS >= 0 and iS < iB):
                continue
            efill = e0 + iB; fpx = btc
        else:
            efill = e0; fpx = tp[efill]
        ftime = tt[efill]; target = btc + side * rr * risk
        xseg = tp[efill + 1:]; xt = tt[efill + 1:]
        if xseg.size == 0:
            continue
        if side > 0:
            sc = xseg <= stop; tc = xseg >= target
        else:
            sc = xseg >= stop; tc = xseg <= target
        si = np.argmax(sc) if sc.any() else -1
        ti = (np.argmax(tc) if tc.any() else -1) if not hold_eod else -1
        cand = [c for c in [(si, "stop"), (ti, "target")] if c[0] >= 0]
        if cand:
            xi, reason = min(cand, key=lambda c: c[0])
            xpx = stop if reason == "stop" else target; xtime = xt[xi]
        else:
            xpx = xseg[-1]; xtime = xt[-1]; reason = "eod"
        pnl_pts = (xpx - fpx) * side
        out.append(dict(Date=date, rev=s["rev"], side=side, entry=round(fpx, 2), stop=stop,
                        target=round(target, 2), exitpx=round(xpx, 2), reason=reason,
                        risk_pts=round(risk, 2), pnl_pts=round(pnl_pts, 2),
                        pnl=round(pnl_pts * PT - COST, 2), etime=ftime, xtime=xtime))
        ptr = xtime
    return out


def run_configs(sigs, configs, sma=None):
    """configs: list of (name, filter_fn(sig_df)->sub_df, cfg_dict). Loop days once."""
    acc = {name: [] for name, _, _ in configs}
    filt_cache = {name: fn(sigs) for name, fn, _ in configs}
    for date, day_all in sigs.groupby("Date", sort=True):
        try:
            tt, tp = E._load_ticks(date)
        except FileNotFoundError:
            continue
        if len(tt) == 0:
            continue
        L = sma.get(date, np.nan) if sma is not None else np.nan
        for name, _, cfg in configs:
            sub = filt_cache[name]
            day = sub[sub.Date == date]
            if len(day) == 0:
                continue
            acc[name].extend(sim_day(date, tt, tp, day, cfg, L))
    return {n: pd.DataFrame(r) for n, r in acc.items()}


if __name__ == "__main__":
    sg = parse_signals()
    print(f"parsed {len(sg)} signals  {sg.Date.min()}..{sg.Date.max()}")
    print(sg.rev.value_counts().to_string())
    # clip to tick coverage
    sg = sg[sg.Date >= "2021-06-18"]
    print(f"\nBASELINE: all types, market entry, EOD hold")
    tr = sim(sg, entry="market", hold_eod=True)
    tr["d"] = pd.to_datetime(tr["Date"])
    print("ALL  ", E.metrics(tr))
    print("TRAIN", E.metrics(tr[tr.d < "2024-01-01"]))
    print("OOS  ", E.metrics(tr[tr.d >= "2024-01-01"]))
    print(E.by_year(tr).to_string())
