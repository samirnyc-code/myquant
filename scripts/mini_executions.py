"""mini_executions.py — each XSP mini fill with the TICK-EXACT per-leg bid/ask captured at
execution (from xsp_fills.csv), the total spread paid per trade, and a live fly-vs-condor
execution-cost breakdown — so you can watch WHERE the mini bleeds (the ATM flies) vs where
it tracks clean (the OTM condor wings).

Falls back to the ~10s tape (chain_XSP) only if xsp_fills.csv is empty. Writes
data/options_sim/mini_executions.html (auto-refresh 30s) and prints inline.

    python scripts/mini_executions.py [--date 2026-08-25] [--open]
"""
from __future__ import annotations
import argparse, datetime as dt, json, webbrowser
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
LOG = ROOT / "data" / "options_log"


def _kind(strat):
    s = str(strat)
    if "fly" in s:
        return "FLY (ATM)"
    if "ic" in s:
        return "condor"
    if s.startswith("gx"):
        return "wall"
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    day = a.date.replace("-", "")

    ff = LOG / "xsp_fills.csv"
    if not ff.exists() or len(pd.read_csv(ff)) == 0:
        print("no tick-exact fills yet (xsp_fills.csv empty) — mirror hasn't filled today")
        return
    f = pd.read_csv(ff)
    f = f[f.ts.astype(str).str.startswith(a.date) & (f.kind == "entry")].copy()
    if not len(f):
        print(f"no entry fills on {a.date}")
        return
    f["spread"] = pd.to_numeric(f["spread"], errors="coerce")
    f["kindg"] = f["strategy"].map(_kind)

    # per-trade total spread paid
    per_trade = f.groupby(["trade_id", "strategy", "kindg"]).agg(
        legs=("leg", list), spreads=("spread", list),
        total_spread=("spread", "sum"), fill=("combo_fill", "first")).reset_index()

    # fly vs condor summary
    summ = f.groupby("kindg").agg(n_legs=("leg", "size"),
                                  avg_spread=("spread", "mean"),
                                  max_spread=("spread", "max")).reset_index()

    print(f"XSP tick-exact executions — {a.date}  (bid/ask AT the fill)")
    print("=" * 62)
    print("  execution-cost by structure (avg per-leg spread):")
    for _, s in summ.iterrows():
        print(f"    {s['kindg']:<11} avg spread {s['avg_spread']:.3f}  (max {s['max_spread']:.2f}, {int(s['n_legs'])} legs)")
    print("\n  per trade:")
    for _, r in per_trade.iterrows():
        legs = " ".join(f"{l}[{sp:.2f}]" for l, sp in zip(r["legs"], r["spreads"]))
        print(f"    {r['strategy']:<10} {r['kindg']:<11} fill {r['fill']:<6} total spread {r['total_spread']:.2f}  |  {legs}")

    # ---- html ----
    def sumrow(s):
        hot = "neg" if s["avg_spread"] > 0.1 else "pos"
        return (f"<tr><td><b>{s['kindg']}</b></td><td class='n {hot}'>{s['avg_spread']:.3f}</td>"
                f"<td class=n>{s['max_spread']:.2f}</td><td class=n>{int(s['n_legs'])}</td></tr>")
    trows = []
    for _, r in per_trade.iterrows():
        lg = "".join(
            f"<tr><td>{l}</td><td class='n {'neg' if sp>0.1 else ''}'>{sp:.2f}</td></tr>"
            for l, sp in zip(r["legs"], r["spreads"]))
        hot = "neg" if r["total_spread"] > 0.15 else ""
        trows.append(
            f"<div class=trade><div class=th><b>{r['strategy']}</b> · {r['kindg']} · fill {r['fill']} · "
            f"total spread paid <b class='{hot}'>{r['total_spread']:.2f}</b></div>"
            f"<table><tr><th>leg</th><th>spread</th></tr>{lg}</table></div>")
    html = f"""<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=30><title>XSP executions</title>
<style>body{{background:#0b0d12;color:#e8ebf0;font:13px/1.5 system-ui,Segoe UI;padding:22px;max-width:780px;margin:auto}}
h1{{font-size:18px;margin:0 0 2px}}.sub{{color:#7d8697;font-size:12px;margin-bottom:14px}}
.card{{background:#12151c;border:1px solid #232833;border-radius:10px;padding:12px 14px;margin-bottom:14px}}
.trade{{background:#12151c;border:1px solid #232833;border-radius:9px;padding:9px 13px;margin-bottom:9px}}
.th{{margin-bottom:5px}}table{{width:100%;border-collapse:collapse}}
th,td{{text-align:right;padding:4px 8px;border-bottom:1px solid #1c212b}}th{{color:#7d8697;font-size:11px}}
td:first-child,th:first-child{{text-align:left}}.n{{font-variant-numeric:tabular-nums}}
.pos{{color:#2fbf8f}}.neg{{color:#f0555f;font-weight:700}}</style>
<h1>💹 XSP Execution Cost — {a.date}</h1>
<div class=sub>tick-exact bid/ask at each fill · red = wide spread (&gt;0.10/leg) = where the mini bleeds · updates 30s</div>
<div class=card><b>By structure — the fly-vs-condor gap</b>
<table><tr><th>structure</th><th>avg spread/leg</th><th>max</th><th>legs</th></tr>{''.join(sumrow(s) for _, s in summ.iterrows())}</table></div>
<b style="font-size:13px">Per trade — spread paid at execution</b>
{''.join(trows)}"""
    out = SIM / "mini_executions.html"
    out.write_text(html, encoding="utf-8")
    print(f"\nsaved -> {out.relative_to(ROOT)}")
    if a.open:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
