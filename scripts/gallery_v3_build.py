"""GALLERY v3 — INTERACTIVE (Plotly): candles + native zoom + click/box-select annotation.
Same look as the v2 matplotlib slides (full-day 5M candles, regime shading, EMA20, prior bar,
gap chip, right-side level gutter) but interactive: drag-to-zoom, and an Annotate mode to select
a bar/range and attach a note (stored to localStorage + exportable JSON; P2 wires to committed JSON).
Exit zoom fixed: EOD exit shows NO stop, y auto-scales (no more bunching).
  python scripts/gallery_v3_build.py
"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gallery_v2_proto import find_trade

OUTD = Path(__file__).resolve().parent.parent / "docs" / "living" / "trade_review"


def _np(o):
    if isinstance(o, np.integer): return int(o)
    if isinstance(o, np.floating): return float(o)
    raise TypeError(str(type(o)))


def main():
    r = find_trade()
    if r is None: print("no trade"); return
    t, g, tP, tbar, trace, ema, pbar = r
    n = len(g); gdt = pd.to_datetime(g.DateTime); iso = [d.isoformat() for d in gdt]
    O, H, L, C = (list(map(float, g[c])) for c in ["Open","High","Low","Close"])

    # regime segments -> x-time spans
    bounds = sorted([(s_,"start",sd) for (s_,sd,_) in trace["starts"]] +
                    [(bb,"term",None) for (_,_,bb,_) in trace["terms"]])
    cur="neutral"; x0=0; segs=[]
    for (xb,ktp,sd) in bounds: segs.append((x0,xb,cur)); x0=xb; cur=sd if ktp=="start" else "neutral"
    segs.append((x0,n-1,cur))
    regime=[{"x0":iso[max(aa,0)], "x1":iso[min(bb,n-1)], "mode":sdv} for (aa,bb,sdv) in segs]

    prior={"x":(gdt.iloc[0]-pd.Timedelta("5min")).isoformat(),
           "o":float(pbar.Open),"h":float(pbar.High),"l":float(pbar.Low),"c":float(pbar.Close)}

    def zoom(center, levels, w=260):
        i0=max(0,center-w); i1=min(len(tP),center+w)
        return {"x":list(range(i1-i0)), "y":list(map(float,tP[i0:i1])),
                "mark_x":int(center-i0), "levels":levels}
    entry=zoom(t["jfl"], [{"y":t["trig"],"l":"2EL trigger","c":"#d98a2b"},
                          {"y":t["sb_lo"],"l":"SB low","c":"#8a8f94"},
                          {"y":t["fill"],"l":"Entry (fill)","c":"#2a78d6"}])
    exlv=[{"y":t["ex"],"l":f"Exit ({t['extype']})","c":"#2e8b57"}]
    if t["extype"]=="stop": exlv.append({"y":t["stop"],"l":"Stop","c":"#b23a2e"})
    exitz=zoom(t["exi"], exlv)

    trade={"date":t["Date"],"book":"2EL long (BULL)","net":t["net"],"trigger":t["trig"],
           "sb_lo":t["sb_lo"],"fill":t["fill"],"stop":t["stop"],"ex":round(float(t["ex"]),2),
           "extype":t["extype"],"pc":round(float(t["pc"]),2),"gap":round(float(t["gap"]),2),
           "adr":round(float(t["adr"]),1),"verified":t["verified"],
           "entry_mark":iso[t["fill_bar"]],"exit_mark":iso[t["exit_bar"]],"sig_mark":iso[t["sb"]]}
    data={"trade":trade,"candles":{"x":iso,"o":O,"h":H,"l":L,"c":C},
          "ema20":list(map(float,ema)),"regime":regime,"prior":prior,"entry":entry,"exit":exitz}
    OUTD.mkdir(parents=True, exist_ok=True)
    tpl=(OUTD/"v3_template.html").read_text(encoding="utf-8")
    (OUTD/"v3.html").write_text(tpl.replace("__DATA__", json.dumps(data, default=_np)), encoding="utf-8")
    print(f"built v3.html — {trade['date']} net ${trade['net']} verified={trade['verified']}")


if __name__ == "__main__":
    main()
