"""ib_edge_equity.py — stitched equity + drawdown PATH for the IB-edge gate at 2.0R.

The sweep said exit=2.0R lifts the gate to ~+0.16R / net-DD ~8.9. But max-DD alone
doesn't tell you if a 48%-win book is survivable — the PATH does (streaks, time
underwater, recovery). This builds the 1-contract stitched curve and the DD metrics
that decide prop tradeability, both-directions and short-only.

Memory-frugal chunked tick load. Out: docs/living/ib_edge_equity_<date>.md (+ PNG).
Run: .venv/Scripts/python.exe scripts/ib_edge_equity.py
"""
from __future__ import annotations

import sys, gc
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                                                       # noqa: E402
from simulation_engine import simulate_trades                        # noqa: E402
from indicators import tag_signals                                   # noqa: E402
from data_loader import bar_num_from_dt                              # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"

BASE = dict(entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5, contracts=1,
            contracts_t1=1, contracts_t2=1, commission=4.36, ratchet_r=0.0,
            pb_round="nearest", target_r=2.0, multileg=False, threeleg=False, overrides=None)
EDGE_MAX = 0.10


def log(m): print(f"[eq] {datetime.now():%H:%M:%S} {m}", flush=True)


def dd_metrics(dt, pnl):
    """Drawdown path metrics on the chronologically-ordered trade pnl."""
    order = np.argsort(dt)
    dt, pnl = dt[order], pnl[order]
    eq = np.cumsum(pnl)
    peak = np.maximum.accumulate(eq)
    dd = peak - eq
    maxdd = float(dd.max())
    underwater = float((dd > 1e-9).mean()) * 100
    # longest losing streak (consecutive losing trades)
    streak = mx = 0
    for p in pnl:
        streak = streak + 1 if p < 0 else 0
        mx = max(mx, streak)
    # longest drawdown duration in CALENDAR days (peak → recovery)
    i_trough = int(np.argmax(dd))
    # find last peak before trough, and first recovery after
    i_peak = int(np.where(eq[:i_trough + 1] == peak[i_trough])[0][0]) if i_trough > 0 else 0
    rec = np.where(eq[i_trough:] >= peak[i_trough])[0]
    i_rec = i_trough + int(rec[0]) if len(rec) else len(eq) - 1
    days_peak_trough = (pd.Timestamp(dt[i_trough]) - pd.Timestamp(dt[i_peak])).days
    days_to_recover = (pd.Timestamp(dt[i_rec]) - pd.Timestamp(dt[i_trough])).days if len(rec) else None
    return dict(net=float(eq[-1]), maxdd=maxdd, mar=float(eq[-1] / maxdd) if maxdd else np.inf,
                underwater=underwater, max_loss_streak=mx,
                dd_decline_days=days_peak_trough, dd_recover_days=days_to_recover,
                worst_trade=float(pnl.min()), best_trade=float(pnl.max()),
                eq=eq, dd=dd, dt=dt)


def main() -> int:
    log("loading + tagging...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bbd = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)
    tg = tag_signals(sig, bars).sort_values("DateTime").reset_index(drop=True)

    adr = tg["prior_ATR"].replace(0, np.nan).to_numpy()
    isL = tg["Direction"].str.lower().str.startswith("l").values
    origin = tg["StopPrice"].to_numpy()
    d_edge = np.where(isL, origin - tg["OR60_Low"].to_numpy(),
                            tg["OR60_High"].to_numpy() - origin) / adr
    G = (d_edge >= 0) & (d_edge <= EDGE_MAX)
    gtg = tg.loc[G].reset_index(drop=True)
    gtg["_date"] = pd.to_datetime(gtg["DateTime"]).dt.date

    TGTS = [1.0, 1.25, 1.5, 2.0]
    log(f"gated {len(gtg)} — simulating targets {TGTS} in 4 chunks...")
    BASE_NT = {k: v for k, v in BASE.items() if k != "target_r"}
    parts = {t: [] for t in TGTS}
    for ci, chunk in enumerate(np.array_split(np.array(sorted(gtg["_date"].unique()), object), 4)):
        cset = set(chunk.tolist())
        sub = gtg[gtg["_date"].isin(cset)].reset_index(drop=True)
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        for t in TGTS:
            res = simulate_trades(signals=sub, ticks_by_date=tbd, bars_by_date=bbd,
                                  target_r=t, **BASE_NT).reset_index(drop=True)
            fl = res["Filled"] == True
            keep = res.loc[fl, ["DateTime", "Direction", "NetPnL"]].copy()
            parts[t].append(keep)
            del res
        del tbd; gc.collect()
        log(f"  chunk {ci+1}/4 done")

    # path-shape comparison across targets (both-dir)
    def depth_profile(bk):
        bk = bk.sort_values("DateTime")
        eq = np.cumsum(bk["NetPnL"].values)
        dd = np.maximum.accumulate(eq) - eq
        return dict(net=float(eq[-1]), maxdd=float(dd.max()),
                    mar=float(eq[-1] / dd.max()) if dd.max() else np.inf,
                    p5=float((dd > 5000).mean()) * 100,
                    p10=float((dd > 10000).mean()) * 100,
                    p2=float((dd > 2500).mean()) * 100)

    cmp_rows = []
    for t in TGTS:
        bk = pd.concat(parts[t], ignore_index=True)
        bk["DateTime"] = pd.to_datetime(bk["DateTime"])
        m = depth_profile(bk)
        cmp_rows.append(f"| {t}R | ${m['net']:,.0f} | ${m['maxdd']:,.0f} | {m['mar']:.2f} | "
                        f"{m['p2']:.0f}% | {m['p5']:.0f}% | {m['p10']:.0f}% |")

    book = pd.concat(parts[2.0], ignore_index=True)
    book["RiskDollar"] = np.nan
    book["DateTime"] = pd.to_datetime(book["DateTime"])
    book = book.sort_values("DateTime").reset_index(drop=True)
    dt = book["DateTime"].values
    pnl = book["NetPnL"].values
    isS = ~book["Direction"].str.lower().str.startswith("l").values

    both = dd_metrics(dt, pnl)
    short = dd_metrics(dt[isS], pnl[isS])

    # monthly
    mon = book.set_index("DateTime").groupby(pd.Grouper(freq="ME"))["NetPnL"].sum()
    pos = int((mon > 0).sum()); tot = int((mon != 0).sum())

    def block(name, m):
        rec = f"{m['dd_recover_days']}d" if m["dd_recover_days"] is not None else "not recovered"
        return (f"### {name}\n"
                f"- Net (1 contract, 5yr): **${m['net']:,.0f}** · MAR (net/maxDD): **{m['mar']:.2f}**\n"
                f"- **Max drawdown: ${m['maxdd']:,.0f}** · time underwater: {m['underwater']:.0f}%\n"
                f"- Longest DD: {m['dd_decline_days']}d peak→trough, {rec} to recover\n"
                f"- Longest losing streak: {m['max_loss_streak']} trades · "
                f"worst trade ${m['worst_trade']:,.0f} · best ${m['best_trade']:,.0f}\n")

    md = [f"# IB-edge Gate — Equity & Drawdown Path ({datetime.now():%Y-%m-%d})\n",
          "Stitched 1-contract gated book (origin ≤0.10 ADR inside IB edge). The DD PATH "
          "decides prop survivability — and the right TARGET is vehicle-dependent.\n",
          "\n## Target vs drawdown-PATH tradeoff (both-dir)\n",
          "Higher target = higher total/MAR but does it sit deeper, longer? "
          "(% time = fraction of trades that deep below peak.)\n",
          "| target | net $ | maxDD $ | MAR | %time >$2.5k | %time >$5k | %time >$10k |",
          "|---|---|---|---|---|---|---|", *cmp_rows, "",
          "\n## Detail @2.0R\n",
          f"- trades: {len(book)} · monthly positive: {pos}/{tot} ({100*pos/max(tot,1):.0f}%)\n",
          block("Both directions", both), block("Short only", short)]

    # drawdown DEPTH distribution — how much of "underwater" is shallow vs painful?
    dd = both["dd"]
    bands = [(0, 250), (250, 1000), (1000, 2500), (2500, 5000),
             (5000, 10000), (10000, 15000), (15000, np.inf)]
    blab = ["< $250 (≈at peak)", "$250–1k", "$1k–2.5k", "$2.5k–5k",
            "$5k–10k", "$10k–15k", "> $15k"]
    md.append("\n### Drawdown DEPTH distribution (both-dir) — how deep is the 'underwater'?\n")
    md.append("| drawdown band | % of trades (time) |\n|---|---|")
    for (lo, hi), lab in zip(bands, blab):
        pct = float(((dd >= lo) & (dd < hi)).mean()) * 100
        md.append(f"| {lab} | {pct:.0f}% |")
    md.append("")

    # worst 10 months
    md.append("\n### Worst 6 months (both-dir)\n| month | $ |\n|---|---|")
    for d, v in mon.sort_values().head(6).items():
        md.append(f"| {d:%Y-%m} | ${v:,.0f} |")
    md.append("")

    # chart
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 1, figsize=(11, 7), sharex=True, height_ratios=[2, 1])
        ax[0].plot(both["dt"], both["eq"], lw=1.2, label="both")
        ax[0].plot(short["dt"], short["eq"], lw=1.0, color="#d62728", label="short only")
        ax[0].set_title("IB-edge gate @2.0R — stitched equity (1 contract)")
        ax[0].legend(); ax[0].grid(alpha=0.3); ax[0].set_ylabel("cum $")
        ax[1].fill_between(both["dt"], -both["dd"], 0, color="#d62728", alpha=0.5)
        ax[1].set_ylabel("drawdown $"); ax[1].grid(alpha=0.3)
        fig.tight_layout()
        png = _OUT / f"ib_edge_equity_{datetime.now():%Y%m%d}.png"
        fig.savefig(png, dpi=110); plt.close(fig)
        md.append(f"\n![equity]({png.name})\n")
        log(f"chart -> {png}")
    except Exception as e:
        log(f"chart skipped: {e}")

    out = _OUT / f"ib_edge_equity_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
