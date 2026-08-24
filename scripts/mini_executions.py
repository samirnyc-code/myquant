"""mini_executions.py — each XSP mini trade with the per-leg BID/ASK at execution, so you
can see exactly how wide XSP's spreads were and where you filled vs the market.

The mirror logs the combo fill but not per-leg quotes, so we reconstruct the bid/ask from
the recorded XSP chain tape (chain_XSP_YYYYMMDD.csv — every strike's NBBO every ~10s) at
the snapshot nearest each trade's entry time. Accuracy ~ the tape cadence (~10s of the
fill), not the exact tick. Prints inline and writes data/options_sim/mini_executions.html.

    python scripts/mini_executions.py [--date 2026-08-24] [--open]
"""
from __future__ import annotations
import argparse, datetime as dt, json, webbrowser
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
LOG = ROOT / "data" / "options_log"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    day = a.date.replace("-", "")

    xf = LOG / "trades_xsp.parquet"
    tape_f = SIM / f"chain_XSP_{day}.csv"
    if not xf.exists():
        print("no XSP mirror book yet"); return
    x = pd.read_parquet(xf)
    x = x[x.entry_dt.astype(str).str.startswith(a.date)].copy()
    if not len(x):
        print(f"no XSP trades on {a.date}"); return
    tape = pd.read_csv(tape_f) if tape_f.exists() else pd.DataFrame(columns=["ts_et", "strike", "right", "bid", "ask"])
    if len(tape):
        tape["t"] = pd.to_datetime(tape["ts_et"])

    def quote_at(strike, right, entry_et):
        """Nearest tape snapshot to entry_et for this (strike,right)."""
        if not len(tape):
            return None, None, None
        sub = tape[(tape.strike == float(strike)) & (tape.right == right)]
        if not len(sub):
            return None, None, None
        i = (sub.t - entry_et).abs().idxmin()
        r = sub.loc[i]
        return r.bid, r.ask, r.t

    rows_html = []
    print(f"XSP mini executions — {a.date}  (bid/ask from the XSP tape at ~execution time)")
    for _, tr in x.sort_values("entry_dt").iterrows():
        legs = tr["legs"] if isinstance(tr["legs"], list) else json.loads(tr["legs"])
        entry_ct = pd.to_datetime(tr["entry_dt"])
        entry_et = entry_ct + pd.Timedelta(hours=1)     # CT -> ET to match the tape
        print(f"\n  {tr['strategy_id']}  entry {entry_ct:%H:%M} CT  | fill credit {tr.get('credit')}  "
              f"| pnl {tr.get('pnl')}")
        leg_html = []
        for l in legs:
            b, ak, qt = quote_at(l["strike"], l["right"], entry_et)
            if b is None:
                line = f"    {l['side']:>4} {int(l['strike'])}{l['right']}: (no tape quote)"
                spread = mid = "—"
            else:
                mid = round((b + ak) / 2, 3)
                spread = round(ak - b, 3)
                line = (f"    {l['side']:>4} {int(l['strike'])}{l['right']}: "
                        f"bid {b} / ask {ak}  (mid {mid}, spread {spread})  @ {qt:%H:%M:%S} ET")
            print(line)
            leg_html.append(f"<tr><td>{l['side']}</td><td>{int(l['strike'])}{l['right']}</td>"
                            f"<td class=n>{b if b is not None else '—'}</td><td class=n>{ak if b is not None else '—'}</td>"
                            f"<td class=n>{mid}</td><td class=n>{spread}</td></tr>")
        rows_html.append(
            f"<div class=trade><div class=th><b>{tr['strategy_id']}</b> · entry {entry_ct:%H:%M} CT · "
            f"fill credit <b>{tr.get('credit')}</b> · pnl {tr.get('pnl')}</div>"
            f"<table><tr><th>side</th><th>leg</th><th>bid</th><th>ask</th><th>mid</th><th>spread</th></tr>"
            f"{''.join(leg_html)}</table></div>")

    html = f"""<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=30><title>XSP executions</title>
<style>body{{background:#0b0d12;color:#e8ebf0;font:13px/1.5 system-ui,Segoe UI;padding:22px;max-width:820px;margin:auto}}
h1{{font-size:18px;margin:0 0 2px}}.sub{{color:#7d8697;font-size:12px;margin-bottom:16px}}
.trade{{background:#12151c;border:1px solid #232833;border-radius:10px;padding:10px 14px;margin-bottom:12px}}
.th{{margin-bottom:6px}}table{{width:100%;border-collapse:collapse}}
th,td{{text-align:right;padding:4px 8px;border-bottom:1px solid #1c212b}}th{{color:#7d8697;font-size:11px}}
td:first-child,td:nth-child(2),th:first-child,th:nth-child(2){{text-align:left}}.n{{font-variant-numeric:tabular-nums}}</style>
<h1>💹 XSP Mini Executions — {a.date}</h1>
<div class=sub>per-leg bid/ask from the recorded XSP tape at ~execution time · fill credit = actual paper combo fill</div>
{''.join(rows_html)}"""
    out = SIM / "mini_executions.html"
    out.write_text(html, encoding="utf-8")
    print(f"\nsaved -> {out.relative_to(ROOT)}")
    if a.open:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
