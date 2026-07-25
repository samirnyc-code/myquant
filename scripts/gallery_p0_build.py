"""P0 PROTOTYPE — one 2EL trade, lightweight-charts, the NEW rendering to approve the look:
 - NO entry arrows (dotted price lines only) · all prices in a clean side LEVEL GUTTER w/ leader ticks
 - EMA20 · prior-session last bar (ghost) + prior-close line · gap-stats chip · regime shading
 - context (5M) chart + tick-granularity zoom with a big green check when the trade verifies
Self-contained HTML (references vendored lib; DATA inlined) -> docs/living/trade_review/p0.html

  python scripts/gallery_p0_build.py
"""
import sys, json
from pathlib import Path
from bisect import bisect_right
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from regime_second_entry_study import phase_transitions, load_day
from regime_2e_causal_check import detect_entries_causal

TICK = 0.25; PT = 50.0; FLOOR = 8 * TICK; GOOD = {"09", "10", "11", "12", "13"}
WT = Path(__file__).resolve().parent.parent
OUT = WT / "docs" / "living" / "trade_review"
DATA = Path(r"C:/Users/Admin/myquant/data")


def epoch(ts):
    return int(pd.Timestamp(ts).value // 10**9)


def find_and_extract():
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet"); b["Date"] = b.DateTime.dt.date.astype(str)
    b["ema20"] = b.Close.ewm(span=20, adjust=False).mean()          # continuous EMA20
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100)
    dly["pc"] = dly.dC.shift(1)
    gm = dly.set_index("Date")
    days = [d for d in sorted(b.Date.unique()) if d >= "2024-03-01"]   # recent, clean
    for dstr in days:
        if dstr not in gm.index:
            continue
        adr, gapv, pc = gm.loc[dstr, "adr10"], gm.loc[dstr, "gap"], gm.loc[dstr, "pc"]
        if not np.isfinite(adr) or abs(gapv) > 0.54:
            continue
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        H, L, C = g.High.values, g.Low.values, g.Close.values; n = len(g); gdt = g.DateTime.values
        try:
            trans = phase_transitions(H, L, n, tP, tbar); entries = detect_entries_causal(g, tP, tbar)
        except Exception:
            continue
        tix = [t for (t, _) in trans]; tmd = [m for (_, m) in trans]
        sd = max(round(0.30 * adr / TICK) * TICK, FLOOR)
        for (fb, sb, dr, cnt, trig) in entries:
            if cnt != 2 or dr != "L":
                continue
            a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
            hit = np.nonzero(tP[a:z] >= trig)[0]
            if not len(hit):
                continue
            jf = a + int(hit[0]); reg = tmd[bisect_right(tix, jf) - 1]
            if reg != "BULL":
                continue
            lim = trig - 6 * TICK; seg0 = tP[jf:]
            jl = np.nonzero(seg0 < lim)[0]
            if not len(jl):
                continue
            jfl = jf + int(jl[0]); fillbar = int(tbar[jfl])
            if fillbar - fb > 6 or pd.Timestamp(gdt[min(fillbar, n-1)]).strftime("%H") not in GOOD:
                continue
            fill = lim; stop = fill - sd; seg = tP[jfl:]
            js = np.nonzero(seg <= stop)[0]
            if len(js):
                exi = jfl + int(js[0]); ex = stop; extype = "stop"
            else:
                exi = len(tP) - 1; ex = tP[-1]; extype = "EOD"
            net = round((ex - fill) * PT - 5 - 12.5, 1)
            if net < 400:                                   # a clean winner for the prototype
                continue
            # ---- verify (independent replay) ----
            v_entry = bool(np.any(tP[jf:jfl+1] < lim))
            v_exit = (extype == "stop" and ex == stop) or (extype == "EOD")
            verified = v_entry and v_exit
            # ---- build series ----
            cndl = [{"time": epoch(gdt[i]), "open": float(g.Open.values[i]), "high": float(H[i]),
                     "low": float(L[i]), "close": float(C[i])} for i in range(n)]
            ema = [{"time": epoch(gdt[i]), "value": round(float(g.ema20.values[i]), 2)} for i in range(n)]
            # regime spans -> per-bar mode
            barmode = []
            for i in range(n):
                ti = np.searchsorted(tbar, i, "right") - 1
                barmode.append(tmd[bisect_right(tix, max(ti, 0)) - 1] if tix else "NEUTRAL")
            spans = []
            s0 = 0
            for i in range(1, n+1):
                if i == n or barmode[i] != barmode[s0]:
                    spans.append({"from": epoch(gdt[s0]), "to": epoch(gdt[min(i, n-1)]), "mode": barmode[s0]})
                    s0 = i
            # prior bar (last bar of prior session)
            pidx = b.index[b.Date == dstr][0]
            pbar = b.iloc[pidx-1]
            prior = {"time": epoch(gdt[0]) - 300, "open": float(pbar.Open), "high": float(pbar.High),
                     "low": float(pbar.Low), "close": float(pbar.Close)}
            # zoom tick window: 2 bars before signal -> 1 bar after exit
            zi0 = int(np.searchsorted(tbar, max(sb-2, 0), "left")); zi1 = int(min(exi + 400, len(tP)-1))
            step = max(1, (zi1 - zi0) // 4000)              # cap ~4000 pts
            path = [{"i": int(k - zi0), "value": float(tP[k])} for k in range(zi0, zi1, step)]
            fill_i = int(jfl - zi0); exit_i = int(exi - zi0)
            zt = {int(k - zi0): pd.Timestamp(gdt[min(int(tbar[k]), n-1)]).strftime("%H:%M") for k in range(zi0, zi1, max(step, 200))}
            trade = {
                "date": dstr, "book": "2EL long (with-trend BULL)", "dir": "LONG", "net": net,
                "trigger": float(trig), "sb_low": float(L[sb]), "entry": float(fill), "stop": float(stop),
                "exit": round(float(ex), 2), "exit_type": extype, "prior_close": round(float(pc), 2),
                "gap_pct": round(float(gapv), 2), "adr10": round(float(adr), 1),
                "verified": verified, "verify_reason": "entry traded through limit; exit at " + extype,
                "sig_time": pd.Timestamp(gdt[sb]).strftime("%H:%M"),
                "entry_time": pd.Timestamp(gdt[fillbar]).strftime("%H:%M"),
            }
            return {"trade": trade, "context": {"candles": cndl, "ema20": ema, "spans": spans, "prior": prior,
                    "entry_time": epoch(gdt[fillbar]), "sig_time": epoch(gdt[sb])},
                    "zoom": {"path": path, "fill_i": fill_i, "exit_i": exit_i, "tlabels": zt}}
    return None


d = find_and_extract()
if d is None:
    print("no trade found"); sys.exit(1)
OUT.mkdir(parents=True, exist_ok=True)
def _np(o):
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, np.floating): return float(o)
    raise TypeError(str(type(o)))
tpl = (OUT / "p0_template.html").read_text(encoding="utf-8")
(OUT / "p0.html").write_text(tpl.replace("__DATA__", json.dumps(d, default=_np)), encoding="utf-8")
print(f"built docs/living/trade_review/p0.html — trade {d['trade']['date']} {d['trade']['book']} "
      f"net ${d['trade']['net']} verified={d['trade']['verified']}")
