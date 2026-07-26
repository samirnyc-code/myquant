"""book_review_prep.py — generate the per-day review data the forward-reveal tool (mark_setups.py)
consumes for THIS book: two-sided 2E + SMA20 gate + skip-after-trend-day. One JSON per trade-day
(2021-2026) with everything the reviewer overlays (all toggleable in the UI):

  bars      : 5M RTH [idx,time,o,h,l,c]
  regime    : phase-machine segments [{from,to,mode}] (BULL/BEAR/NEUTRAL) for shading
  trades    : this book's setups {entry_bar, dir, entry_px, stop, exit_bar, exit_px, net,
              pass_sma20, pass_skipTD, pass_gap, pass_window, with_trend} -- + filter verdicts
  prior     : prior session last-bar OHLC, prior HLC, prior 20-day SMA, gap {pts,pct,vs_range}
  ib        : today's initial balance (08:30-09:30) hi/lo

Causal: everything from prior sessions / prior closes; SMA20 = prior-day 20-day SMA of closes.
Uses Databento 5m + 1m pseudo-ticks (matches the book numbers).

  python scripts/book_review_prep.py [--limit N]
Output: data/annotations/book_review/<date>.json  (+ index.json)
"""
import sys, json, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
KFADE = 2; FADE_STOP = 4.0                                   # fade: fail within 2 bars, fixed 4pt stop
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT / "scripts"))
from regime_second_entry_study import phase_transitions as pt_old   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402
from regime_2e_tickproxy_fidelity import proxy_ticks                # noqa: E402
OUT = WT / "data" / "annotations" / "book_review"
GOOD = {9, 10, 11, 12, 13}


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    OUT.mkdir(parents=True, exist_ok=True)
    b = pd.read_parquet(DATA / "bars" / "_db_es_5m_rth.parquet"); b["DateTime"] = pd.to_datetime(b["DateTime"]); b["Date"] = b["DateTime"].dt.date.astype(str)
    b = b.sort_values("DateTime").reset_index(drop=True)
    b["ema20i"] = b["Close"].ewm(span=20, adjust=False).mean()   # continuous 5M EMA20 (carries across sessions)
    alldates = sorted(b["Date"].unique())
    prior_date = {alldates[i]: alldates[i - 1] for i in range(1, len(alldates))}
    bydate = {d: x.sort_values("DateTime").reset_index(drop=True) for d, x in b.groupby("Date")}
    m1 = pd.read_parquet(DATA / "bars" / "_db_es_1m_rth.parquet"); m1["DateTime"] = pd.to_datetime(m1["DateTime"]); m1["Date"] = m1["DateTime"].dt.date.astype(str)
    m1g = {d: x.sort_values("DateTime").reset_index(drop=True) for d, x in m1.groupby("Date")}
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index().sort_values("Date").reset_index(drop=True)
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100)
    dly["sma20"] = dly.dC.rolling(20).mean().shift(1)
    dly["rng"] = dly.dH - dly.dL
    dly["trendday"] = (dly.rng > 1.6 * dly.adr10)
    dly["skipTD"] = dly.trendday.shift(1).fillna(False)
    dly["pH"] = dly.dH.shift(1); dly["pL"] = dly.dL.shift(1); dly["pC"] = dly.dC.shift(1)
    gm = dly.set_index("Date")
    days = [d for d in sorted(b["Date"].unique()) if d >= "2021-01-01"]
    if limit:
        days = days[:limit]
    index = []; t0 = time.time()
    for di, dstr in enumerate(days):
        if dstr not in gm.index or dstr not in m1g:
            continue
        row = gm.loc[dstr]; adr = row.adr10
        if not np.isfinite(adr):
            continue
        g = b[b.Date == dstr].sort_values("DateTime").reset_index(drop=True)
        if len(g) < 30:
            continue
        m1day = m1g[dstr]; m1day = m1day[m1day.DateTime >= g["DateTime"].values[0]]
        if len(m1day) < 30:
            continue
        H, L, C, O = g.High.values, g.Low.values, g.Close.values, g.Open.values
        n = len(g); gapPct = float(row.gap) if np.isfinite(row.gap) else None
        sma20 = float(row.sma20) if np.isfinite(row.sma20) else None
        pass_gap = (gapPct is None) or (abs(gapPct) <= 0.54)
        skipTD = bool(row.skipTD)
        EMA = g.ema20i.values
        bars = [[i, pd.Timestamp(g.DateTime.values[i]).strftime("%H:%M"),
                 round(float(O[i]), 2), round(float(H[i]), 2), round(float(L[i]), 2), round(float(C[i]), 2),
                 round(float(EMA[i]), 2)] for i in range(n)]
        pdte = prior_date.get(dstr)
        ptail = []
        if pdte and pdte in bydate:
            ptdf = bydate[pdte].tail(20)
            ptail = [[round(float(r.Open), 2), round(float(r.High), 2), round(float(r.Low), 2),
                      round(float(r.Close), 2), round(float(r.ema20i), 2),
                      pd.Timestamp(r.DateTime).strftime("%H:%M")] for r in ptdf.itertuples()]
        # regime segments + pivots (phase-machine trace)
        tP, tbar = proxy_ticks(g, m1day)
        tr = {}
        trans = pt_old(H, L, n, tP, tbar, trace=tr); tr_ix = [t for (t, _) in trans]; tr_md = [mm for (_, mm) in trans]
        seg = []
        for i in range(n):
            z = int(np.searchsorted(tbar, i, "right"))
            mode = tr_md[bisect_right(tr_ix, z - 1) - 1] if z else "NEUTRAL"
            if seg and seg[-1]["mode"] == mode:
                seg[-1]["to"] = i
            else:
                seg.append({"from": i, "to": i, "mode": mode})
        pivots = [{"b": int(p["bar"]), "side": p["side"], "tag": p["tag"],
                   "lab": (p["majlab"] or p["disp"] or p["tag"]).upper(),
                   "major": p["major"] is not None}
                  for p in tr.get("piv", []) if 0 <= p["bar"] < n]
        for _s in ("H", "L"):                              # opening regime swing H / L
            _f = next((q for q in pivots if q["side"] == _s), None)
            if _f:
                _f["lab"] = "O" + _s; _f["open"] = True; _f["major"] = True
        obs = [i for i in range(1, n) if H[i] >= H[i - 1] and L[i] <= L[i - 1] and (H[i] > H[i - 1] or L[i] < L[i - 1])]
        ibs = [i for i in range(1, n) if H[i] <= H[i - 1] and L[i] >= L[i - 1]]
        # trades: WITH-TREND book (2EL/2ES, retest, 0.30xADR) + FADES (f2EL short / f2ES long, stop-entry, 4pt)
        wide = max(round(0.30 * adr / TICK) * TICK, FLOOR); trades = []
        for (fb, sb, dr, cnt, trig) in detect_entries_causal(g, tP, tbar):
            if cnt != 2:
                continue
            short = dr == "S"; want = "BEAR" if short else "BULL"
            a = np.searchsorted(tbar, fb, "left"); zz = np.searchsorted(tbar, fb, "right")
            hit = np.nonzero(tP[a:zz] <= trig)[0] if short else np.nonzero(tP[a:zz] >= trig)[0]
            if not len(hit):
                continue
            jf = a + int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf) - 1]
            if reg == want:
                # ---- WITH-TREND 2E book ----
                lim = trig + 6 * TICK if short else trig - 6 * TICK; s0 = tP[jf:]
                jl = np.nonzero(s0 > lim)[0] if short else np.nonzero(s0 < lim)[0]
                if not len(jl):
                    continue
                jfl = jf + int(jl[0]); fb2 = int(tbar[jfl])
                if fb2 - fb > 6:
                    continue
                hr = int(pd.Timestamp(g.DateTime.values[min(fb2, n - 1)]).hour)
                stop = lim + wide if short else lim - wide; segp = tP[jfl:]
                js = np.nonzero(segp >= stop)[0] if short else np.nonzero(segp <= stop)[0]
                ex = stop if len(js) else segp[-1]
                exbar = int(tbar[min(jfl + (int(js[0]) if len(js) else len(segp) - 1), len(tbar) - 1)])
                net = round(((lim - ex) if short else (ex - lim)) * PT - COMM - SLIP, 1)
                pass_sma = (sma20 is not None) and (lim > sma20)
                trades.append({"setup": "2E" + dr, "book": "2E", "is_fade": False, "entry_bar": fb2, "sig_bar": int(sb),
                               "dir": dr, "trigger": round(float(trig), 2), "entry_px": round(float(lim), 2),
                               "stop": round(float(stop), 2), "exit_bar": exbar, "exit_px": round(float(ex), 2),
                               "net": net, "with_trend": True, "pass_sma20": bool(pass_sma),
                               "pass_skipTD": (not skipTD), "pass_gap": bool(pass_gap), "pass_window": hr in GOOD,
                               "in_book": bool(pass_sma and (not skipTD) and pass_gap and (hr in GOOD))})
            else:
                # ---- FADE book (f2EL=short/f2ES=long): stop-entry beyond signal-bar extreme, 4pt stop ----
                fade_short = not short; need = "BEAR" if fade_short else "BULL"
                if reg != need:
                    continue                                          # neutral regime -> not a fade
                sb_ext = L[sb] if fade_short else H[sb]
                fail_px = sb_ext - TICK if fade_short else sb_ext + TICK
                zlim = np.searchsorted(tbar, fb + KFADE + 1, "left"); segf = tP[jf:zlim]
                w = np.nonzero(segf <= fail_px)[0] if fade_short else np.nonzero(segf >= fail_px)[0]
                if not len(w):
                    continue
                jx = jf + int(w[0]); fb2 = int(tbar[min(jx, len(tbar) - 1)])
                hr = int(pd.Timestamp(g.DateTime.values[min(fb2, n - 1)]).hour)
                fill = fail_px - TICK if fade_short else fail_px + TICK
                stop = fill + FADE_STOP if fade_short else fill - FADE_STOP; seg2 = tP[jx:]
                jsx = np.nonzero(seg2 >= stop)[0] if fade_short else np.nonzero(seg2 <= stop)[0]
                ex = stop if len(jsx) else seg2[-1]
                exbar = int(tbar[min(jx + (int(jsx[0]) if len(jsx) else len(seg2) - 1), len(tbar) - 1)])
                net = round(((fill - ex) if fade_short else (ex - fill)) * PT - COMM - SLIP, 1)
                fdir = "S" if fade_short else "L"
                trades.append({"setup": "f2E" + dr, "book": "fade", "is_fade": True, "entry_bar": fb2, "sig_bar": int(sb),
                               "dir": fdir, "trigger": round(float(fail_px), 2), "entry_px": round(float(fill), 2),
                               "stop": round(float(stop), 2), "exit_bar": exbar, "exit_px": round(float(ex), 2),
                               "net": net, "with_trend": False, "pass_sma20": None, "pass_skipTD": None,
                               "pass_gap": bool(pass_gap), "pass_window": hr in GOOD,
                               "fade_tradeable": bool(fade_short),   # f2EL tradeable; f2ES DEAD
                               "in_book": bool(fade_short and pass_gap and (hr in GOOD))})
        ib = g[g.DateTime.dt.hour.isin([8, 9]) & (g.DateTime.dt.strftime("%H:%M") < "09:30")]
        rec = {
            "date": dstr, "bars": bars, "regime": seg, "trades": trades, "prior_tail": ptail,
            "pivots": pivots, "obs": obs, "ibs": ibs, "today_open": round(float(O[0]), 2),
            "sma20": round(sma20, 2) if sma20 else None,
            "prior": {"H": round(float(row.pH), 2) if np.isfinite(row.pH) else None,
                      "L": round(float(row.pL), 2) if np.isfinite(row.pL) else None,
                      "C": round(float(row.pC), 2) if np.isfinite(row.pC) else None,
                      "gap_pts": round(float(row.dO - row.pC), 2) if np.isfinite(row.pC) else None,
                      "gap_pct": round(gapPct, 3) if gapPct is not None else None},
            "ib": {"hi": round(float(ib.High.max()), 2), "lo": round(float(ib.Low.min()), 2)} if len(ib) else None,
            "skipTD": skipTD, "adr10": round(float(adr), 2),
        }
        (OUT / f"{dstr}.json").write_text(json.dumps(rec))
        index.append({"date": dstr, "n_trades": len(trades), "n_in_book": sum(t["in_book"] for t in trades),
                      "net": round(sum(t["net"] for t in trades if t["in_book"]), 1), "skipTD": skipTD})
        del g, m1day, tP, tbar; gc.collect()
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] {len(index)} days ({time.time()-t0:.0f}s)", flush=True)
    (OUT / "index.json").write_text(json.dumps(index))
    print(f"\nDONE {time.time()-t0:.0f}s — {len(index)} day files -> {OUT}")
    print(f"  total book trades: {sum(x['n_in_book'] for x in index)}  net ${sum(x['net'] for x in index):+,.0f}")


if __name__ == "__main__":
    main()
