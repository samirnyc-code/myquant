"""Mine the FULL local GexLog archive (2026-04 .. present) for value — no scraping.
Quantifies their track record and dumps the complete narrative corpus for reading.

Outputs:
  data/options_sim/gexlog_mine_stats.txt   — quantified patterns
  data/options_sim/gexlog_corpus.md        — every narrative/playbook/guidance, dated
"""
import glob, json, re
from collections import Counter, defaultdict
from pathlib import Path

RAW = Path(r"C:\Users\Admin\Desktop\gexlog\data\raw")
OUT = Path(r"c:\Users\Admin\myquant\data\options_sim")

def g(d, *p, default=None):
    for k in p:
        d = d.get(k) if isinstance(d, dict) else None
        if d is None: return default
    return d

morn = {Path(f).name[:10]: json.load(open(f, encoding="utf-8"))
        for f in glob.glob(str(RAW / "*_morning.json"))}
even = {Path(f).name[:10]: json.load(open(f, encoding="utf-8"))
        for f in glob.glob(str(RAW / "*_evening.json"))}
dates = sorted(set(morn) & set(even))

L = []
L.append(f"GEXLOG ARCHIVE MINE — {len(morn)} morning, {len(even)} evening, {len(dates)} paired days "
         f"({dates[0]}..{dates[-1]})\n")

# 1) forecast accuracy by morning SIGNAL
sig_acc = defaultdict(lambda: [0, 0])   # signal -> [accurate, total]
sig_emhit = defaultdict(lambda: [0, 0])
sess_by_sig = defaultdict(Counter)
for dt in dates:
    sig = (g(morn[dt], "guidance", "signal") or "?").upper()[:4]
    acc = g(even[dt], "session_analysis", "forecast_accurate")
    emh = g(even[dt], "session_analysis", "expected_move_hit")
    st = g(even[dt], "session_analysis", "session_type") or "?"
    if acc is not None: sig_acc[sig][1] += 1; sig_acc[sig][0] += int(bool(acc))
    if emh is not None: sig_emhit[sig][1] += 1; sig_emhit[sig][0] += int(bool(emh))
    sess_by_sig[sig][st.split()[0]] += 1

L.append("=== FORECAST ACCURACY by morning signal (their self-scored) ===")
for s in ("GO", "CAUT", "WAIT", "?"):
    if sig_acc[s][1]:
        a, t = sig_acc[s]; e2, t2 = sig_emhit[s]
        L.append(f"  {s:5} n={t:3}  forecast-accurate {100*a/t:3.0f}%  EM-held {100*e2/t2 if t2 else 0:3.0f}%  "
                 f"sessions={dict(sess_by_sig[s].most_common(4))}")

# 2) overall forecast/EM hit + session_type distribution
allacc = [int(bool(g(even[d],'session_analysis','forecast_accurate'))) for d in dates if g(even[d],'session_analysis','forecast_accurate') is not None]
allemh = [int(bool(g(even[d],'session_analysis','expected_move_hit'))) for d in dates if g(even[d],'session_analysis','expected_move_hit') is not None]
L.append(f"\n=== OVERALL ===")
L.append(f"  forecast accurate: {100*sum(allacc)/len(allacc):.0f}% (n={len(allacc)})   EM held: {100*sum(allemh)/len(allemh):.0f}% (n={len(allemh)})")
sess = Counter((g(even[d],'session_analysis','session_type') or '?').split()[0] for d in dates)
L.append(f"  realized session types: {dict(sess.most_common())}")

# 3) morning forecast_type distribution + how often each was right
ft_acc = defaultdict(lambda: [0, 0])
for dt in dates:
    ft = (g(morn[dt], "forecast", "type") or "?")
    acc = g(even[dt], "session_analysis", "forecast_accurate")
    if acc is not None: ft_acc[ft][1] += 1; ft_acc[ft][0] += int(bool(acc))
L.append(f"\n=== MORNING forecast_type -> accuracy ===")
for ft, (a, t) in sorted(ft_acc.items(), key=lambda x:-x[1][1]):
    L.append(f"  {ft:22} n={t:3}  right {100*a/t:3.0f}%")

# 4) wall-hold: did SPX close inside [putWall, callWall]?  (needs evening close = current)
wall_hold = [0, 0]
for dt in dates:
    pw, cw = g(morn[dt],"levels","putWall"), g(morn[dt],"levels","callWall")
    close = g(even[dt],"levels","current")
    if pw and cw and close:
        wall_hold[1] += 1; wall_hold[0] += int(pw <= close <= cw)
if wall_hold[1]:
    L.append(f"\n=== WALL CONTAINMENT (close within morning put/call wall) ===")
    L.append(f"  {100*wall_hold[0]/wall_hold[1]:.0f}% of {wall_hold[1]} days")

# 5) recurring GUIDANCE phrases + playbook structure recommendations
guide_notes = Counter()
pb_struct = Counter()
for dt in dates:
    n = (g(morn[dt],"guidance","notes") or "")
    for phrase in ["wait", "wider wing", "reduce", "reduced size", "flat overnight", "size", "avoid"]:
        if phrase in n.lower(): guide_notes[phrase] += 1
    for scen, v in (g(morn[dt],"playbook",default={}) or {}).items():
        if isinstance(v, dict):
            bias = (v.get("bias") or "").lower()
            for st in ["iron condor","credit spread","call credit","put credit","debit spread","butterfly","bull call","bear call","bull put","bear put"]:
                if st in bias: pb_struct[st] += 1
L.append(f"\n=== recurring GUIDANCE phrases (morning notes) ===")
for p, c in guide_notes.most_common(): L.append(f"  '{p}': {c} days")
L.append(f"\n=== playbook STRUCTURE recommendations (across scenarios) ===")
for p, c in pb_struct.most_common(): L.append(f"  {p}: {c} mentions")

(OUT / "gexlog_mine_stats.txt").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L))

# 6) full narrative corpus for reading
C = ["# GexLog full narrative corpus (local archive)\n"]
for dt in dates:
    e = even[dt]; m = morn[dt]
    C.append(f"\n\n===== {dt} =====")
    C.append(f"morning: signal {g(m,'guidance','signal')} · forecast {g(m,'forecast','type')} · conf {g(m,'forecast','confidence')}")
    C.append(f"evening verdict: {g(e,'session_analysis','session_type')} · accurate {g(e,'session_analysis','forecast_accurate')} · EM-hit {g(e,'session_analysis','expected_move_hit')}")
    C.append("--- morning guidance ---\n" + str(g(m,'guidance','notes') or ''))
    for scen, v in (g(m,'playbook',default={}) or {}).items():
        if isinstance(v,dict): C.append(f"--- playbook {scen}: {v.get('scenario')} ---\n{v.get('bias','')}")
    C.append("--- evening narrative ---\n" + str(e.get('notes') or ''))
(OUT / "gexlog_corpus.md").write_text("\n".join(C), encoding="utf-8")
print(f"\ncorpus -> data/options_sim/gexlog_corpus.md ({len(''.join(C))//1000}KB)")
