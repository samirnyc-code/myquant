"""mini_stats.py — a standalone view of the XSP (Mini-SPX) mirror book until the full
mini dashboard tab lands. Answers the one question the mirror exists to answer:

    how much of the SPX edge survives at 1/10 size in XSP?  (XSP*10 / SPX)

Reads both books (trades_xsp.parquet = mirror, trades.parquet = SPX), prints the
comparison inline, and writes data/options_sim/mini_stats.html you can open in the
browser. While the mirror is in --dry mode the XSP fills are just SPX/10, so the ratio
is ~1.0 by construction; from Monday's LIVE paper fills it becomes the real penalty.

    python scripts/mini_stats.py [--open]
"""
from __future__ import annotations
import argparse
import datetime as dt
import webbrowser
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
LOG = ROOT / "data" / "options_log"


def _stats(df):
    df = df[df.pnl.notna()]
    if not len(df):
        return dict(n=0, total=0.0, win=0.0, pf=None)
    p = df.pnl.astype(float)
    pf = (p[p > 0].sum() / -p[p < 0].sum()) if (p < 0).any() else float("inf")
    return dict(n=len(p), total=round(p.sum(), 2), win=round(100 * (p > 0).mean()),
                pf=(round(pf, 2) if pf != float("inf") else "∞"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()

    # TODAY headline (realized closed + open unrealized from marks_xsp = live mini net)
    import datetime as _dt
    from zoneinfo import ZoneInfo as _ZI
    today = _dt.datetime.now(_ZI("America/Chicago")).strftime("%Y-%m-%d")
    _xf = LOG / "trades_xsp.parquet"
    t_real = t_unreal = 0.0
    n_open = n_closed = 0
    if _xf.exists():
        _x = pd.read_parquet(_xf)
        _x = _x[_x.entry_dt.astype(str).str.startswith(today)] if len(_x) else _x
        _cl = _x[_x.exit_dt.notna()]; _op = _x[_x.exit_dt.isna()]
        n_closed, n_open = len(_cl), len(_op)
        t_real = float(_cl.pnl.sum()) if len(_cl) else 0.0
        _mf = LOG / "marks_xsp.csv"
        if _mf.exists() and len(_op):
            _mk = pd.read_csv(_mf).groupby("trade_id").last()
            _u = [_mk.unreal_pnl.get(x) for x in _op.trade_id]
            t_unreal = float(sum(v for v in _u if v == v))
    t_net = t_real + t_unreal

    xf, sf = LOG / "trades_xsp.parquet", LOG / "trades.parquet"
    xsp = pd.read_parquet(xf) if xf.exists() else pd.DataFrame(columns=["trade_id", "strategy_id", "pnl", "fill_model"])
    spx = pd.read_parquet(sf) if sf.exists() else pd.DataFrame(columns=["trade_id", "strategy_id", "pnl"])
    dry = bool(len(xsp)) and (xsp.get("fill_model", pd.Series(dtype=str)) == "dry_est").any()

    # MATCH each XSP mirror to its SPX PARENT by trade_id (xsp_<parent>), so the comparison
    # is like-for-like over the SAME trades — never XSP-few-days vs SPX-all-days.
    xsp = xsp.copy()
    xsp["parent"] = xsp.trade_id.astype(str).str.replace("^xsp_", "", regex=True)
    m = xsp.merge(spx[["trade_id", "pnl"]].rename(columns={"pnl": "spx_pnl"}),
                  left_on="parent", right_on="trade_id", how="inner", suffixes=("", "_s"))
    m = m[m.pnl.notna() & m.spx_pnl.notna()]

    xs = _stats(xsp)
    ss = dict(total=round(float(m.spx_pnl.sum()), 2)) if len(m) else dict(total=0.0)
    surv = ((m.pnl.astype(float).sum() * 10) / m.spx_pnl.sum()) if len(m) and m.spx_pnl.sum() else None

    # per-strategy comparison over MATCHED pairs only: SPX vs XSP*10
    rows = []
    for sid in sorted(set(m.strategy_id)) if len(m) else []:
        sub = m[m.strategy_id == sid]
        xp = sub.pnl.astype(float).sum(); sp = sub.spx_pnl.astype(float).sum()
        ratio = (xp * 10 / sp) if sp else None
        rows.append((sid, round(sp), round(xp, 2), round(xp * 10), (round(ratio, 2) if ratio is not None else "—")))

    # ---- inline ----
    print("=" * 68)
    print(f"XSP MINI BOOK  {'(DRY estimates — SPX/10; live fills Monday)' if dry else '(LIVE paper fills)'}")
    print("=" * 68)
    print(f"  TODAY net ${t_net:+,.2f}  (realized ${t_real:+,.0f} / {n_closed} closed + open ${t_unreal:+,.0f} / {n_open} live)")
    print(f"  XSP closed: {xs['n']} (of {n_open + n_closed} mirrored) | realized ${xs['total']:,.2f} | win {xs['win']}% | PF {xs['pf']}")
    print(f"  SPX (same strategies): P&L ${ss['total']:,.0f}")
    print(f"  edge survival  XSP*10 / SPX = {round(surv,2) if surv else '—'}   (1.0 = mini keeps the full SPX edge)")
    print(f"\n  {'strategy':>10} {'SPX$':>8} {'XSP$':>8} {'XSP*10':>8} {'ratio':>7}")
    for sid, sp, xp, x10, r in rows:
        print(f"  {sid:>10} {sp:>8} {xp:>8} {x10:>8} {str(r):>7}")

    # ---- html ----
    trs = "".join(
        f"<tr><td>{sid}</td><td class='n'>{sp:+}</td><td class='n'>{xp:+.2f}</td>"
        f"<td class='n'>{x10:+}</td><td class='n'>{r}</td></tr>" for sid, sp, xp, x10, r in rows)
    banner = ("⚠ DRY estimates (SPX/10) — real XSP paper fills begin Monday"
              if dry else "LIVE XSP paper fills")
    ncls = 'pos' if t_net >= 0 else 'neg'
    html = f"""<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=30><title>XSP Mini Book</title>
<style>body{{background:#0b0d12;color:#e8ebf0;font:14px/1.5 system-ui,Segoe UI;padding:24px;max-width:760px;margin:auto}}
h1{{font-size:19px;margin:0 0 2px}}.sub{{color:#7d8697;font-size:12.5px;margin-bottom:16px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:18px}}
.tile{{background:#171b23;border:1px solid #232833;border-radius:12px;padding:12px 14px}}
.tl{{color:#7d8697;font-size:11px;text-transform:uppercase;letter-spacing:.04em}}
.tv{{font-size:20px;font-weight:750;margin-top:4px}}.pos{{color:#2fbf8f}}.neg{{color:#f0555f}}
table{{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}}
th,td{{text-align:right;padding:7px 10px;border-bottom:1px solid #1c212b}}th{{color:#7d8697;font-size:11px;text-transform:uppercase}}
td:first-child,th:first-child{{text-align:left}}.n{{font-weight:600}}
.warn{{background:#2a2410;border:1px solid #6b5a1e;color:#e6c65b;padding:8px 12px;border-radius:8px;font-size:12.5px;margin-bottom:16px}}</style>
<h1>💹 XSP Mini Book <span style="color:#5b9dd9">(1/10 SPX)</span></h1>
<div class=sub>the same strategy at 1/10 size — how much edge survives XSP's spreads. generated {dt.datetime.now():%Y-%m-%d %H:%M} machine-time</div>
<div class=warn>{banner}</div>
<div class=kpis style="margin-bottom:10px">
 <div class=tile style="grid-column:span 2"><div class=tl>TODAY net (realized + open)</div><div class="tv {ncls}" style="font-size:26px">${t_net:+,.2f}</div>
   <div class=tl style="margin-top:4px">realized ${t_real:+,.0f} ({n_closed} closed) · open ${t_unreal:+,.0f} ({n_open} live)</div></div>
</div>
<div class=kpis>
 <div class=tile><div class=tl>mirrored today</div><div class=tv>{n_open + n_closed}</div><div class=tl style="margin-top:3px">{n_closed} closed · {n_open} open</div></div>
 <div class=tile><div class=tl>XSP P&L</div><div class="tv {'pos' if xs['total']>=0 else 'neg'}">${xs['total']:,.2f}</div></div>
 <div class=tile><div class=tl>win rate</div><div class=tv>{xs['win']}%</div></div>
 <div class=tile><div class=tl>PF</div><div class=tv>{xs['pf']}</div></div>
 <div class=tile><div class=tl>edge survival<br>XSP×10 / SPX</div><div class="tv {'pos' if (surv or 0)>=0.9 else 'neg'}">{round(surv,2) if surv else '—'}</div></div>
</div>
<b style="font-size:13px">Per-strategy — SPX vs XSP×10</b>
<table><tr><th>strategy</th><th>SPX $</th><th>XSP $</th><th>XSP×10</th><th>ratio</th></tr>{trs}</table>
<p style="color:#7d8697;font-size:12px;margin-top:14px">ratio ≈ 1.0 = XSP keeps the full SPX edge at 1/10 the capital. &lt;1 = the wider XSP spread is eating it. Margin: XSP ties up ~1/10 of SPX.</p>"""
    out = SIM / "mini_stats.html"
    out.write_text(html, encoding="utf-8")
    print(f"\nsaved -> {out.relative_to(ROOT)}")
    if a.open:
        webbrowser.open(out.as_uri())


if __name__ == "__main__":
    main()
