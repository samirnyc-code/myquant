"""KILL-RULE BACKTEST (Samir's last gate, 2026-07-25).
The proposed live kill-rule: if a SIDE (long book / short book) posts PF < 1.0 for
TWO CONSECUTIVE quarters, disable that side starting the next quarter. Concern: shorts
were weak in 2023 -> the rule could disable shorts right before the best years.

Applied CAUSALLY to the book's own history: enabled[q] uses only completed prior
quarters (shadow-tracked, so a side auto-re-enables once it recovers). Compares:
  BASELINE (both sides always on)  vs  KILL-RULE (2-consecutive-quarter)  vs  1-quarter variant.
Primary = the SHIPPING with-trend book (WT: 2EL long + 2ES short). Also shows three-book.

  python scripts/regime_2e_killrule_backtest.py
"""
from pathlib import Path
import numpy as np, pandas as pd

WT = Path(__file__).resolve().parent.parent
ts = pd.read_csv(WT / "data" / "regime" / "two_sleeves_20260724.csv")


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum(); return gp/gl if gl else (np.inf if gp > 0 else 0)


def run(book_df, label):
    d = book_df.copy(); d["q"] = pd.PeriodIndex(pd.to_datetime(d.Date), freq="Q")
    d["side"] = np.where(d.dir == "L", "LONG", "SHORT")
    quarters = sorted(d.q.unique())
    # shadow quarterly PF per side (as if always on)
    qpf = {sd: {q: pf(d[(d.side == sd) & (d.q == q)].net) for q in quarters} for sd in ("LONG", "SHORT")}
    qn = {sd: {q: len(d[(d.side == sd) & (d.q == q)]) for q in quarters} for sd in ("LONG", "SHORT")}

    print(f"\n===== {label} — per-side quarterly PF (n) =====")
    print(f"{'quarter':9}{'LONG':>16}{'SHORT':>16}")
    for q in quarters:
        lp, sp = qpf['LONG'][q], qpf['SHORT'][q]
        print(f"{str(q):9}{lp:>8.2f} (n{qn['LONG'][q]:<3}){sp:>8.2f} (n{qn['SHORT'][q]:<3})")

    def enabled(sd, qi, k):                       # causal: prior k quarters all < 1.0 -> disabled
        if qi < k:
            return True
        return not all(qpf[sd][quarters[qi-j-1]] < 1.0 for j in range(k))

    res = {}
    for k, name in [(99, "BASELINE (never kill)"), (2, "KILL 2-consec-Q"), (1, "KILL 1-Q")]:
        net = 0.0; killed = []
        for qi, q in enumerate(quarters):
            for sd in ("LONG", "SHORT"):
                on = enabled(sd, qi, k) if k < 99 else True
                seg = d[(d.side == sd) & (d.q == q)].net
                if on:
                    net += seg.sum()
                elif len(seg):
                    killed.append((str(q), sd, round(seg.sum())))
        res[name] = (net, killed)
    print(f"\n{label} — rule comparison:")
    base = res["BASELINE (never kill)"][0]
    for name, (net, killed) in res.items():
        tag = "" if name.startswith("BASELINE") else f"  vs baseline {net-base:+,.0f}"
        print(f"  {name:22}: net ${net:+,.0f}{tag}")
        for (q, sd, amt) in killed:
            print(f"       disabled {sd} in {q}: gave up ${amt:+,}")
    return res


# shipping book = WT (2EL long + 2ES short)
run(ts[ts.sleeve == "WT"], "SHIPPING with-trend book (2EL long + 2ES short)")
# three-book (add f2EL fade to SHORT side)
tb = ts[(ts.sleeve == "WT") | ((ts.sleeve == "FADE") & (ts.dir == "S"))]
run(tb, "Three-book (2EL + 2ES + f2EL fade)")
