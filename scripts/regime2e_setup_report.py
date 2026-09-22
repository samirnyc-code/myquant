"""Per-trade stacked report from the Regime2ESetups NT8 indicator event-log CSV.

Input : Documents\\regime2e_setups_<instr>.csv (events FIRE/SKIP/FILL/EXPIRE/STOP/EOD)
Output: reports/regime2e/setup_report_<stamp>.html  (+ per-trade CSV next to it)

One card per fired setup, stacked newest-day first: side, trigger, retest limit,
fill, stop level, outcome (STOP / EOD exit / never filled), points and $ (1 ES,
$50/pt, NO fees), regime + SMA20d at fire, plus a day header and summary tiles.
SKIP events are listed per day with their reason (REG/SMA/GAP/TDY/WIN/WARM).

EOD rows exist only in indicator builds >= b11e739+1 (S118); older logs show
open-at-EOD trades as outcome "OPEN/EOD (exit not logged)".

  python scripts/regime2e_setup_report.py [path\\to\\csv] [--out DIR]
"""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

PT = 50.0
DOCS = Path.home() / "Documents"
DEFAULT_CSV = DOCS / "regime2e_setups_ES.csv"
REPO = Path(__file__).resolve().parent.parent
OUTDIR = REPO / "reports" / "regime2e"


def load(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, dtype={"reason": str}).fillna({"reason": ""})
    df["dtime"] = pd.to_datetime(df["date"] + " " + df["time"])
    return df.sort_values("dtime").reset_index(drop=True)


def build_trades(df: pd.DataFrame):
    """Stitch FIRE -> FILL -> (STOP|EOD|EXPIRE) per (date, seq)."""
    trades, skips = [], []
    # group by seq ONLY: the EOD row is written at the NEXT session's first bar,
    # so it carries the next day's date; seq is globally unique across the run.
    for seq, g in df.groupby("seq", sort=True):
        ev = {r.event: r for r in g.itertuples()}
        if "SKIP" in ev:
            r = ev["SKIP"]
            skips.append(dict(date=r.date, time=r.time, dir=r.dir, trig=r.trig,
                              regime=r.regime, reason=r.reason))
            continue
        if "FIRE" not in ev:
            continue
        f = ev["FIRE"]
        d = f.date
        t = dict(date=d, seq=seq, time=f.time, dir=f.dir, trig=f.trig, lim=f.lim,
                 regime=f.regime, sma20d=f.sma20d, filled=False, entry=None,
                 fill_time=None, stop_px=None, exit_px=None, outcome="NO FILL",
                 pts=None)
        if "FILL" in ev:
            r = ev["FILL"]
            t.update(filled=True, entry=r.lim, fill_time=r.time)
            if "STOP" in ev:
                s = ev["STOP"]
                t.update(stop_px=s.lim, exit_px=s.lim, outcome="STOP")
            elif "EOD" in ev:
                e = ev["EOD"]
                t.update(exit_px=e.lim, outcome="EOD")
            else:
                t["outcome"] = "OPEN/EOD (exit not logged)"
            if t["exit_px"] is not None:
                sgn = 1 if t["dir"] == "L" else -1
                t["pts"] = round(sgn * (t["exit_px"] - t["entry"]), 2)
        elif "EXPIRE" in ev:
            t["outcome"] = "NO FILL (expired)"
        trades.append(t)
    return trades, skips


def money(pts):
    return f"${pts * PT:+,.0f}" if pts is not None else "—"


def html_report(trades, skips, src, stamp):
    closed = [t for t in trades if t["pts"] is not None]
    wins = [t for t in closed if t["pts"] > 0]
    tot = sum(t["pts"] for t in closed)
    by_reason = pd.Series([s["reason"] for s in skips]).value_counts().to_dict() if skips else {}
    tiles = [
        ("setups fired", len(trades)), ("filled", sum(t["filled"] for t in trades)),
        ("closed w/ exit", len(closed)),
        ("win rate", f"{100 * len(wins) / len(closed):.0f}%" if closed else "—"),
        ("net pts (no fees)", f"{tot:+.2f}" if closed else "—"),
        ("net $ (1 ES, no fees)", money(tot) if closed else "—"),
        ("skipped", len(skips)),
    ]
    css = """
    body{font-family:Segoe UI,Arial,sans-serif;background:#14161a;color:#dcdfe4;margin:24px;max-width:980px}
    h1{font-size:20px} h2{font-size:15px;color:#9aa3af;border-bottom:1px solid #2a2e35;padding-bottom:4px;margin-top:28px}
    .tiles{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}
    .tile{background:#1d2127;border:1px solid #2a2e35;border-radius:8px;padding:10px 16px;min-width:110px}
    .tile b{display:block;font-size:20px;margin-top:2px}
    .card{background:#1d2127;border:1px solid #2a2e35;border-left:4px solid #4b5563;border-radius:8px;padding:10px 14px;margin:8px 0}
    .card.L{border-left-color:#2e9e5b}.card.S{border-left-color:#c0504d}
    .card .head{font-weight:600;font-size:14px;margin-bottom:6px}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:4px 18px;font-size:13px}
    .grid span{color:#9aa3af} .win b{color:#4ade80}.loss b{color:#f87171}
    .skips{font-size:12.5px;color:#9aa3af;margin:6px 0 0 2px}
    .meta{color:#6b7280;font-size:12px;margin-top:30px}
    """
    out = [f"<!doctype html><meta charset='utf-8'><title>REGIME-2E setup report {stamp}</title>",
           f"<style>{css}</style>", "<h1>REGIME-2E — per-setup report (NT8 indicator log)</h1>",
           f"<div class='tiles'>" + "".join(f"<div class='tile'>{k}<b>{v}</b></div>" for k, v in tiles) + "</div>"]
    if by_reason:
        out.append("<div class='skips'>skip reasons: " +
                   " · ".join(f"{k} {v}" for k, v in by_reason.items()) + "</div>")
    days = sorted({t["date"] for t in trades} | {s["date"] for s in skips}, reverse=True)
    for d in days:
        dt = [t for t in trades if t["date"] == d]
        ds = [s for s in skips if s["date"] == d]
        day_pts = sum(t["pts"] for t in dt if t["pts"] is not None)
        out.append(f"<h2>{d} — {len(dt)} fired, {len(ds)} skipped, {day_pts:+.2f} pts</h2>")
        for t in sorted(dt, key=lambda x: x["time"]):
            cls = "win" if (t["pts"] or 0) > 0 else ("loss" if (t["pts"] or 0) < 0 else "")
            name = "2EL" if t["dir"] == "L" else "2ES"
            out.append(
                f"<div class='card {t['dir']} {cls}'>"
                f"<div class='head'>{t['time']} — {name} — {t['outcome']}"
                + (f" — <b>{t['pts']:+.2f} pts ({money(t['pts'])})</b>" if t["pts"] is not None else "")
                + "</div><div class='grid'>"
                f"<div><span>trigger</span><br>{t['trig']}</div>"
                f"<div><span>retest limit</span><br>{t['lim']}</div>"
                f"<div><span>filled</span><br>{t['fill_time'] or '—'} @ {t['entry'] if t['entry'] is not None else '—'}</div>"
                f"<div><span>exit</span><br>{t['exit_px'] if t['exit_px'] is not None else '—'}</div>"
                f"<div><span>regime@fire</span><br>{t['regime']}</div>"
                f"<div><span>SMA20d</span><br>{t['sma20d']}</div>"
                "</div></div>")
        if ds:
            out.append("<div class='skips'>" + "<br>".join(
                f"{s['time']} — {'2EL' if s['dir'] == 'L' else '2ES'} @ {s['trig']} "
                f"skipped: <b>{s['reason']}</b> (regime {s['regime']})" for s in ds) + "</div>")
    out.append(f"<div class='meta'>source: {src} · generated {stamp} machine-time · "
               f"$ = 1 ES × $50/pt, NO commissions/slippage · indicator = Regime2ESetups (display port); "
               f"authoritative book numbers remain the python backtest (regime_2e_book_metrics.py)</div>")
    return "\n".join(out)


def print_metrics(trades):
    """Full metrics block (gross + net-of-costs at the book's $5 RT + 1t slip)."""
    c = pd.DataFrame([t for t in trades if t["pts"] is not None])
    if c.empty:
        print("no closed trades - no metrics")
        return
    c = c.sort_values(["date", "fill_time"]).reset_index(drop=True)
    days = c["date"].nunique()
    span_yrs = max((pd.to_datetime(c["date"]).max() - pd.to_datetime(c["date"]).min()).days, 1) / 365.25
    for label, cost in (("GROSS (no costs)", 0.0), ("NET  ($5 RT + 1t slip = $17.50/tr)", 17.5)):
        v = c["pts"].values * 50.0 - cost
        w = v[v > 0]; l = v[v <= 0]
        pf = w.sum() / -l.sum() if l.sum() < 0 else float("inf")
        eq = pd.Series(v).cumsum()
        mdd = float((eq - eq.cummax()).min())
        daily = pd.DataFrame({"d": c["date"], "v": v}).groupby("d")["v"].sum()
        sharpe = daily.mean() / daily.std() * (252 ** 0.5) if daily.std() > 0 else float("nan")
        print(f"\n===== {label}  (n={len(v)}, {days} trading days, {span_yrs:.2f}yr) =====")
        print(f"  net            ${v.sum():+,.0f}   ({v.sum() / span_yrs:+,.0f}/yr, 1 ES)")
        print(f"  PF             {pf:.2f}")
        print(f"  win rate       {100 * (v > 0).mean():.1f}%   ({len(w)}W / {len(l)}L)")
        print(f"  avg win        ${w.mean():+,.0f}    avg loss ${l.mean():+,.0f}    payoff {abs(w.mean() / l.mean()):.2f}")
        print(f"  expectancy     ${v.mean():+,.0f}/trade")
        print(f"  max drawdown   ${mdd:+,.0f}  (trade-equity)")
        print(f"  best / worst   ${v.max():+,.0f} / ${v.min():+,.0f}")
        print(f"  daily Sharpe   {sharpe:.2f}   trades/day {len(v) / days:.1f}")
        for d_ in ("L", "S"):
            x = v[(c["dir"] == d_).values]
            if len(x):
                pfx = x[x > 0].sum() / -x[x <= 0].sum() if (x <= 0).any() and x[x <= 0].sum() < 0 else float("inf")
                print(f"  {'2EL' if d_ == 'L' else '2ES'}:  n={len(x)}  PF {pfx:.2f}  net ${x.sum():+,.0f}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    csv_path = Path(args[0]) if args else DEFAULT_CSV
    if not csv_path.exists():
        sys.exit(f"CSV not found: {csv_path}")
    df = load(csv_path)
    trades, skips = build_trades(df)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTDIR.mkdir(parents=True, exist_ok=True)
    html = OUTDIR / f"setup_report_{stamp}.html"
    html.write_text(html_report(trades, skips, csv_path, stamp), encoding="utf-8")
    if trades:
        pd.DataFrame(trades).to_csv(OUTDIR / f"setup_trades_{stamp}.csv", index=False)
    print(f"events {len(df)} -> trades {len(trades)} (skips {len(skips)})")
    print_metrics(trades)
    print(f"\nreport: {html}")


if __name__ == "__main__":
    main()
