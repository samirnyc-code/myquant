"""Risk/reward harness for marked setups (S75K).

For every mark in data/annotations/marks.csv, simulate a bracket trade under
multiple STOP MODES x MANAGEMENT MODES and report R-multiples, so setups can be
screened for the user's 2:1+ requirement.

Real-fill discipline (backtest_fill_realism rules):
  * Entry = stop order 1 tick beyond the signal bar (SB) in trade direction,
    filled only when a LATER bar trades through it (no fill within FILL_BARS
    bars -> no trade). Entry price = order price (stop order, conservative).
  * A bar that touches both stop and target counts as a STOP (pessimistic —
    intrabar path unknown on volume bars).
  * Time exit: flat by 15:00 CT (prop terms) or end of data, at bar close.

Stop modes (all 1-tick offset):
  sb      — beyond the signal bar's opposite extreme.
  struct  — beyond the last CONFIRMED pivot (strength 2) before the SB:
            pivot high above entry for shorts / pivot low below for longs.
            Pivot must complete (2 bars after it) at or before the SB.
            Falls back to sb if no qualifying pivot in the last 40 bars.
  swing   — beyond the 25-bar swing extreme before the SB.

Management modes:
  2R / 3R          — fixed target at 2R / 3R of initial risk.
  2R+BE(+2pt)      — 2R target; stop to breakeven once +2 pts favorable.
  trail(+2pt/2pt)  — once +2 pts favorable, trail stop 2 pts behind MFE.

Output: inline per-mark and per-mode tables + data/annotations/marks_rr.csv
        + styled HTML report data/annotations/marks_rr.html (auto-opened
        with --open; regenerated every run).
NOTE: results on hindsight-lagged marks (lag > 15 bars) are workflow tests,
not evidence — the table flags them.

  .venv/Scripts/python.exe scripts/mark_rr.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
TICK = 0.25
FILL_BARS = 5
PIVOT_K = 2
SWING_N = 25
STRUCT_LOOKBACK = 40
BE_TRIG = 2.0     # pts favorable before BE / trail arms
TRAIL_PTS = 2.0
FLAT_HHMM = "15:00"
MES_PT_USD = 5.0   # MES $/point per contract
MES_RT_COST = 5.0  # user's REAL prop round-turn cost on MES
RISK_BUDGET_USD = 100.0  # fixed-$-risk normalization unit for cross-mode compare
LAG_OK = 15       # marks placed more than this many bars after the fact are flagged


def load_bars():
    b = pd.read_csv(ROOT / "data" / "footprint" / "ES_bars.csv")
    b["ts"] = pd.to_datetime(b.BarTime)
    b["day"] = b.BarTime.str[:10]
    return b.sort_values("BarIdx").reset_index(drop=True)


def pivots(day_bars, upto, kind):
    """Confirmed pivot highs/lows (strength PIVOT_K) completed by bar index `upto`."""
    hs, ls = day_bars.High.values, day_bars.Low.values
    out = []
    for i in range(PIVOT_K, min(upto, len(day_bars) - 1) - PIVOT_K + 1):
        seg = slice(i - PIVOT_K, i + PIVOT_K + 1)
        if kind == "high" and hs[i] == hs[seg].max():
            out.append((i, hs[i]))
        if kind == "low" and ls[i] == ls[seg].min():
            out.append((i, ls[i]))
    return out


def stop_price(mode, day_bars, sb_pos, entry, short):
    sb = day_bars.iloc[sb_pos]
    sb_stop = sb.High + TICK if short else sb.Low - TICK
    if mode == "sb":
        return sb_stop
    if mode == "swing":
        w = day_bars.iloc[max(0, sb_pos - SWING_N):sb_pos + 1]
        return w.High.max() + TICK if short else w.Low.min() - TICK
    # struct: last confirmed pivot beyond entry, within lookback
    kind = "high" if short else "low"
    pv = [(i, p) for i, p in pivots(day_bars, sb_pos, kind)
          if i >= sb_pos - STRUCT_LOOKBACK
          and (p > entry if short else p < entry)]
    if not pv:
        return sb_stop
    return pv[-1][1] + TICK if short else pv[-1][1] - TICK


def simulate(day_bars, sb_pos, short, stop, entry, mgmt):
    """Bar-by-bar bracket sim from the bar AFTER the signal bar. Returns dict."""
    sgn = -1.0 if short else 1.0
    risk = sgn * (stop - entry) * -1.0
    if risk <= 0:
        return dict(result="bad_stop", r=np.nan, risk=np.nan)
    target = None
    if mgmt in ("2R", "2R+BE"):
        target = entry + sgn * 2 * risk
    elif mgmt == "3R":
        target = entry + sgn * 3 * risk
    filled = False
    fill_i = None
    cur_stop = stop
    mfe = 0.0
    flat_t = day_bars.iloc[0].BarTime[:11] + FLAT_HHMM
    for pos in range(sb_pos + 1, len(day_bars)):
        b = day_bars.iloc[pos]
        if not filled:
            if pos > sb_pos + FILL_BARS:
                return dict(result="no_fill", r=np.nan, risk=risk)
            if (short and b.Low <= entry) or (not short and b.High >= entry):
                filled = True
                fill_i = pos
            else:
                continue
        # stop first (pessimistic), then target, then management updates
        if (short and b.High >= cur_stop) or (not short and b.Low <= cur_stop):
            r = sgn * (cur_stop - entry) / risk
            return dict(result="stop" if cur_stop == stop else
                        ("be" if abs(cur_stop - entry) < 1e-9 else "trail"),
                        r=round(r, 2), risk=risk, bars=pos - fill_i)
        if target is not None and (
                (short and b.Low <= target) or (not short and b.High >= target)):
            return dict(result="target", r=round(sgn * (target - entry) / risk, 2),
                        risk=risk, bars=pos - fill_i)
        fav = sgn * ((b.Low if short else b.High) - entry)
        mfe = max(mfe, fav)
        if mgmt in ("2R+BE", "trail") and mfe >= BE_TRIG:
            be = entry
            new_stop = be if mgmt == "2R+BE" else entry + sgn * (mfe - TRAIL_PTS)
            cur_stop = min(cur_stop, new_stop) if short else max(cur_stop, new_stop)
        if b.BarTime >= flat_t:
            return dict(result="flat_time", r=round(sgn * (b.Close - entry) / risk, 2),
                        risk=risk, bars=pos - fill_i)
    b = day_bars.iloc[-1]
    if not filled:
        return dict(result="no_fill", r=np.nan, risk=risk)
    return dict(result="eod", r=round(sgn * (b.Close - entry) / risk, 2),
                risk=risk, bars=len(day_bars) - 1 - fill_i)


STOP_MODES = ["sb", "struct", "swing"]
MGMT_MODES = ["2R", "3R", "2R+BE", "trail"]


def main():
    marks = pd.read_csv(ROOT / "data" / "annotations" / "marks.csv")
    bars = load_bars()
    rows = []
    for _, m in marks.iterrows():
        db = bars[bars.day == m.day].reset_index(drop=True)
        sb_pos = db.index[db.BarIdx == m.bar_idx]
        if sb_pos.empty:
            continue
        sb_pos = int(sb_pos[0])
        sb = db.iloc[sb_pos]
        short = m.direction == "short"
        entry = (sb.Low - TICK) if short else (sb.High + TICK)
        lag = int(m.reveal_idx) - int(m.bar_idx)
        for sm in STOP_MODES:
            stop = stop_price(sm, db, sb_pos, entry, short)
            for mg in MGMT_MODES:
                res = simulate(db, sb_pos, short, stop, entry, mg)
                rows.append(dict(day=m.day, time=m.bar_time[11:], setup=m.setup,
                                 dir=m.direction, lag=lag,
                                 lag_ok=lag <= LAG_OK, entry=entry,
                                 stop_mode=sm, stop=stop,
                                 risk_pts=round(res.get("risk", np.nan), 2),
                                 mgmt=mg, result=res["result"], r=res["r"]))
    t = pd.DataFrame(rows)
    out = ROOT / "data" / "annotations" / "marks_rr.csv"
    t.to_csv(out, index=False)

    print(f"=== {len(marks)} marks x {len(STOP_MODES)} stops x {len(MGMT_MODES)} mgmt -> {out} ===")
    print("\n-- initial risk (pts) per mark & stop mode --")
    piv = t[t.mgmt == "2R"].pivot_table(index=["time", "setup", "dir"],
                                        columns="stop_mode", values="risk_pts")
    print(piv.round(2).to_string())
    print("\n-- R result per mark (rows) x stop/mgmt (cols) --")
    t["cell"] = t.stop_mode + "/" + t.mgmt
    piv = t.pivot_table(index=["time", "setup"], columns="cell", values="r")
    print(piv.round(2).to_string())
    print("\n-- outcomes --")
    piv = t.pivot_table(index=["time", "setup"], columns="cell", values="result",
                        aggfunc="first")
    print(piv.to_string())
    print("\n-- aggregate (filled trades; $ = MES 1-lot, $5/pt, net of $5 RT) --")
    f = t[t.r.notna()].copy()
    f["pts"] = f.r * f.risk_pts
    f["pnl_usd"] = f.pts * MES_PT_USD - MES_RT_COST
    def pf(s):
        wins, losses = s[s > 0].sum(), -s[s < 0].sum()
        return wins / losses if losses > 0 else float("inf")

    def maxdd(usd):
        eq = usd.cumsum()
        return float((eq.cummax() - eq).max())

    def streak(rs):
        """(worst consecutive-loss count, $ of that streak) in trade order."""
        worst_n = worst_usd = cur_n = cur_usd = 0
        for r_, u in rs:
            if r_ < 0:
                cur_n, cur_usd = cur_n + 1, cur_usd + u
                if cur_n > worst_n or (cur_n == worst_n and cur_usd < worst_usd):
                    worst_n, worst_usd = cur_n, cur_usd
            else:
                cur_n = cur_usd = 0
        return worst_n, worst_usd

    # fixed-$-risk normalization: every trade risks RISK_BUDGET_USD (fractional
    # contracts allowed — it's a comparison unit, not an order ticket)
    f["contracts_norm"] = RISK_BUDGET_USD / (f.risk_pts * MES_PT_USD)
    f["pnl_norm"] = f.r * RISK_BUDGET_USD - MES_RT_COST * f.contracts_norm

    hdr = (f"{'':2}{'stop':<8}{'mgmt':<8}{'n':>3}{'win%':>7}{'ExpR':>7}"
           f"{'Exp$':>8}{'PF':>7}{'Tot$':>9}{'MaxDD$':>9}{'streak':>8}"
           f"{'strk$':>8}{'Exp$/100r':>11}")
    for setup, fs in [("ALL SETUPS", f)] + list(f.groupby("setup")):
        print(f"\n\n  ================ {setup}  (n marks = {fs.time.nunique()}) "
              f"================\n\n{hdr}\n  " + "-" * 93)
        for sm in STOP_MODES:
            for mg in MGMT_MODES:
                g = fs[(fs.stop_mode == sm) & (fs.mgmt == mg)].sort_values(["day", "time"])
                if g.empty:
                    continue
                sn, susd = streak(list(zip(g.r, g.pnl_usd)))
                pfv = pf(g.pnl_usd)
                print(f"{'':2}{sm:<8}{mg:<8}{len(g):>3}"
                      f"{(g.r > 0).mean() * 100:>6.0f}%{g.r.mean():>7.2f}"
                      f"{g.pnl_usd.mean():>8.2f}"
                      f"{'inf' if pfv == float('inf') else f'{pfv:.2f}':>7}"
                      f"{g.pnl_usd.sum():>9.2f}{maxdd(g.pnl_usd):>9.2f}"
                      f"{sn:>8}{susd:>8.2f}{g.pnl_norm.mean():>11.2f}")
            print()
    print(f"  Exp$/100r = expectancy with every trade sized to risk ${RISK_BUDGET_USD:.0f}"
          " (fractional MES lots), net of costs — comparable ACROSS stop modes.\n"
          "  MaxDD$/streak are 1-lot, in mark order.")

    print("\nNOTE: n is tiny and marks with lag>15 are hindsight-contaminated —"
          " this is a HARNESS demo, not evidence.")
    html_report(f, marks)
    if "--open" in sys.argv:
        import webbrowser
        webbrowser.open((ROOT / "data" / "annotations" / "marks_rr.html").as_uri())


def html_report(f, marks):
    """Roomy styled report: per-setup aggregate tables + per-mark grid."""
    def pf(s):
        wins, losses = s[s > 0].sum(), -s[s < 0].sum()
        return wins / losses if losses > 0 else float("inf")

    def maxdd(usd):
        eq = usd.cumsum()
        return float((eq.cummax() - eq).max())

    def streak_usd(g):
        worst_n = worst_usd = cur_n = cur_usd = 0
        for r_, u in zip(g.r, g.pnl_usd):
            if r_ < 0:
                cur_n, cur_usd = cur_n + 1, cur_usd + u
                if cur_n > worst_n or (cur_n == worst_n and cur_usd < worst_usd):
                    worst_n, worst_usd = cur_n, cur_usd
            else:
                cur_n = cur_usd = 0
        return worst_n, worst_usd

    def cls(v):
        return "pos" if v > 0 else ("neg" if v < 0 else "")

    sections = []
    for setup, fs in [("All setups", f)] + list(f.groupby("setup")):
        rows = []
        for sm in STOP_MODES:
            block = []
            for mg in MGMT_MODES:
                g = fs[(fs.stop_mode == sm) & (fs.mgmt == mg)].sort_values(["day", "time"])
                if g.empty:
                    continue
                sn, susd = streak_usd(g)
                pfv = pf(g.pnl_usd)
                block.append(
                    f"<tr><td>{sm}</td><td>{mg}</td><td>{len(g)}</td>"
                    f"<td>{(g.r > 0).mean() * 100:.0f}%</td>"
                    f"<td class='{cls(g.r.mean())}'>{g.r.mean():+.2f}</td>"
                    f"<td class='{cls(g.pnl_usd.mean())}'>{g.pnl_usd.mean():,.2f}</td>"
                    f"<td>{'∞' if pfv == float('inf') else f'{pfv:.2f}'}</td>"
                    f"<td class='{cls(g.pnl_usd.sum())}'>{g.pnl_usd.sum():,.2f}</td>"
                    f"<td>{maxdd(g.pnl_usd):,.2f}</td><td>{sn}</td>"
                    f"<td class='{cls(susd)}'>{susd:,.2f}</td>"
                    f"<td class='{cls(g.pnl_norm.mean())}'>{g.pnl_norm.mean():,.2f}</td></tr>")
            rows.append("\n".join(block))
        body = "<tbody class='blk'>" + "</tbody><tbody class='blk'>".join(rows) + "</tbody>"
        n_mk = fs.groupby(["day", "time"]).ngroups
        sections.append(
            f"<section><h2>{setup} <span class='n'>{n_mk} marks</span></h2>"
            "<table><thead><tr><th>stop</th><th>mgmt</th><th>n</th><th>win %</th>"
            "<th>Exp R</th><th>Exp $</th><th>PF</th><th>Total $</th><th>MaxDD $</th>"
            f"<th>streak</th><th>streak $</th><th>Exp $ @ ${RISK_BUDGET_USD:.0f} risk</th>"
            f"</tr></thead>{body}</table></section>")

    mk_rows = "".join(
        f"<tr><td>{m.day}</td><td>{m.bar_time[11:]}</td><td>{m.setup}</td>"
        f"<td>{m.direction}</td><td>{m.grade if isinstance(m.grade, str) else '—'}</td>"
        f"<td>{int(m.reveal_idx) - int(m.bar_idx)}</td></tr>"
        for _, m in marks.iterrows())
    doc = HTML_RR.replace("__SECTIONS__", "\n".join(sections)) \
                 .replace("__MARKS__", mk_rows) \
                 .replace("__STAMP__", pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))
    out = ROOT / "data" / "annotations" / "marks_rr.html"
    out.write_text(doc, encoding="utf-8")
    print(f"\nHTML report -> {out}")


HTML_RR = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Marked Setups — R/R report</title>
<style>
:root{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
  --border:rgba(11,11,11,.10);--card:#fff;--pos:#1f8a4c;--neg:#cf3f3f;--accent:#2a78d6}
@media (prefers-color-scheme:dark){:root{--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;
  --ink2:#c3c2b7;--muted:#898781;--border:rgba(255,255,255,.12);--card:#1f1f1e;
  --pos:#37b06a;--neg:#e66767;--accent:#3987e5}}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);font-size:14.5px;
  font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
header{padding:16px 28px;background:var(--surface);border-bottom:1px solid var(--border)}
h1{font-size:18px;margin:0}
.sub{color:var(--muted);font-size:12.5px;margin-top:4px}
main{max-width:1150px;margin:0 auto;padding:10px 28px 80px}
section{margin-top:44px}
h2{font-size:15px;font-weight:650;margin:0 0 14px}
h2 .n{color:var(--muted);font-weight:400;font-size:12.5px;margin-left:8px}
table{border-collapse:separate;border-spacing:0;width:100%;background:var(--card);
  border:1px solid var(--border);border-radius:12px;overflow:hidden}
th,td{padding:10px 14px;text-align:right;font-variant-numeric:tabular-nums}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}
thead th{font-size:11.5px;text-transform:uppercase;letter-spacing:.04em;
  color:var(--ink2);border-bottom:1px solid var(--border);background:var(--surface)}
tbody.blk{border-top:6px solid transparent}
tbody.blk tr:first-child td{border-top:10px solid var(--plane)}
td{border-top:1px solid var(--border)}
.pos{color:var(--pos)}.neg{color:var(--neg)}
.note{color:var(--muted);font-size:12.5px;margin-top:14px;line-height:1.6}
.warn{background:var(--card);border:1px solid var(--neg);border-radius:10px;
  padding:12px 16px;margin-top:26px;font-size:13px;line-height:1.55}
</style></head><body>
<header><h1>Marked Setups — R/R report</h1>
<div class="sub">entry = stop order 1 tick beyond signal bar · both-touch bars count as
stop-outs · flat 15:00 CT · MES $5/pt net of $5 RT · generated __STAMP__</div></header>
<main>
<div class="warn"><b>Read with care:</b> n is tiny and marks placed &gt;15 bars after
the fact are hindsight-contaminated. This report screens management styles; it is not
evidence of edge until marks accumulate (≥25 per setup over ≥10 sessions) and the
extracted rule survives unmarked history.</div>
__SECTIONS__
<section><h2>Marks in this run</h2>
<table><thead><tr><th>day</th><th>time</th><th>setup</th><th>dir</th><th>grade</th>
<th>lag (bars)</th></tr></thead><tbody>__MARKS__</tbody></table></section>
<div class="note">Exp $ @ fixed risk sizes every trade to the same $ risk (fractional
MES lots) — the only $ column comparable across stop modes. MaxDD $ and streak $ are
1-lot equity-curve values in mark order. PF on tiny n (or with near-zero losses) is
meaningless — treat PF &gt; 3 as suspect until proven.</div>
</main></body></html>
"""


if __name__ == "__main__":
    main()
