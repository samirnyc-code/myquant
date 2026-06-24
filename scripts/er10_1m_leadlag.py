"""er10_1m_leadlag.py — does 1M-ER decay LEAD the price failure, or just confirm it?

The 5M readout arrives too late: at the 5M entry-bar close (~min 5) ~97% of flagged
trades are already underwater. This drills to 1-min resolution. For each flagged
trade we compute a causal 1M Kaufman ER (10-bar = 10-min window, known at each 1M
close) and find:
  • t_ER  = first minute (1..10) the 1M-ER is known < gate  (decay confirmed early)
  • where price is at that moment: excursion in R  (salvageable if ~>= 0)
Decisive question: at t_ER, is price still near/above entry (=> an earlier exit
captures value) or already deep red (=> too late even at 1M)?

Actionable test: exit flagged trades FLAT at the t_ER 1M close (market), respecting
the original stop/target up to then. Compare net vs baseline and vs the +4pt scalp.
Control: same rule on UNFLAGGED trades (must not help).

Causality: 1M-ER of the bar labeled T is known at its close T+1min (we never read a
bar's ER before it closes — no look-ahead). In-sample MC.
Out: docs/living/er10_1m_leadlag_<date>.md
"""
from __future__ import annotations

import sys, gc
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import massive                                                        # noqa: E402
import indicators as ind                                             # noqa: E402
from simulation_engine import simulate_trades                         # noqa: E402
from data_loader import bar_num_from_dt                               # noqa: E402
from er_lookahead_tab import _er10_both_modes                         # noqa: E402
from er10_block_exit_sweep import _net, GATE, SIM_KW, N_CHUNKS        # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS5   = _ROOT / "data" / "bars" / "_continuous.parquet"
_BARS1   = _ROOT / "data" / "bars" / "_continuous_1m.parquet"
_OUT     = _ROOT / "docs" / "living"

K_MIN   = 10          # scan up to 10 minutes after entry
MIN     = pd.Timedelta(minutes=1)


def log(m): print(f"[1m] {datetime.now():%H:%M:%S} {m}", flush=True)


def _flat_exit_gross(row, ticks, decision_dt):
    """Gross pts exiting FLAT (market) at the first tick >= decision_dt, respecting the
    baseline stop/target up to then. If the trade already exited at/before decision_dt
    (baseline), keep baseline; if no ticks after, keep baseline (EOD)."""
    if pd.Timestamp(row.ExitTime) <= decision_dt:
        return row.GrossPnLPts, np.nan
    seg = ticks.loc[ticks["DateTime"] >= decision_dt, "Price"].to_numpy()
    if seg.size == 0:
        return row.GrossPnLPts, np.nan
    px = float(seg[0])
    is_long = row.Direction == "Long"
    gross = (px - row.EntryPrice) if is_long else (row.EntryPrice - px)
    return gross, gross / row.RiskPts          # also return excursion in R at decision


def main() -> int:
    log("load + tag; build causal 1M-ER series ...")
    sig = pd.read_parquet(_SIGNALS)
    bars5 = pd.read_parquet(_BARS5).drop(columns=["Contract"], errors="ignore")
    bars1 = pd.read_parquet(_BARS1).drop(columns=["Contract"], errors="ignore")
    bbd = {d: g.reset_index(drop=True) for d, g in bars5.groupby(bars5["DateTime"].dt.date)}
    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)

    # causal 1M ER over a 10-min (10-bar) window; known at the bar's CLOSE = label+1min.
    er1 = ind.bar_kaufman_er(bars1.sort_values("DateTime"), spans=(10,))
    er1 = er1[["DateTime", "ER_intra_10"]].dropna()
    er_dict = dict(zip(er1["DateTime"].to_numpy(), er1["ER_intra_10"].to_numpy()))

    tagged = _er10_both_modes(sig, bars5)
    causal_pass = tagged["ER10_causal"] >= GATE
    cur_pass    = tagged["ER10_current"] >= GATE
    flag = causal_pass & ~cur_pass
    g = tagged.loc[causal_pass].copy()
    g["FilterStatus"] = "ok"
    g["flagged"] = flag.loc[g.index].to_numpy()
    g["_date"] = pd.to_datetime(g["DateTime"]).dt.date

    rows = []
    dates = sorted(g["_date"].unique())
    for ci, chunk in enumerate(np.array_split(np.array(dates, object), N_CHUNKS)):
        cset = set(chunk.tolist())
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        sub = g[g["_date"].isin(cset)].drop(columns="_date").reset_index(drop=True)
        res = simulate_trades(sub, ticks_by_date=tbd, bars_by_date=bbd, **SIM_KW)
        filled = res[res["Filled"] == True].copy()
        for r in filled.itertuples(index=False):
            t = tbd.get(r.Date)
            entry_floor = pd.Timestamp(r.EntryTime).floor("1min")
            # first minute the causal 1M-ER is known < gate
            t_er = np.nan
            for m in range(1, K_MIN + 1):
                label = entry_floor + (m - 1) * MIN     # bar whose close = entry_floor+m
                ev = er_dict.get(np.datetime64(label))
                if ev is not None and ev < GATE:
                    t_er = m
                    break
            rec = {"flag": bool(r.flagged), "year": pd.Timestamp(r.EntryTime).year,
                   "net_base": _net(r.GrossPnLPts), "t_er": t_er,
                   "net_1mexit": _net(r.GrossPnLPts), "exc_R": np.nan}
            if not np.isnan(t_er) and t is not None and not t.empty:
                decision_dt = entry_floor + t_er * MIN
                gross, excR = _flat_exit_gross(r, t, decision_dt)
                rec["net_1mexit"] = _net(gross)
                rec["exc_R"] = excR
            rows.append(rec)
        del tbd; gc.collect()
        log(f"  chunk {ci+1}/{N_CHUNKS} done")

    df = pd.DataFrame(rows)
    df.to_parquet(_OUT / "er10_1m_leadlag_pertrade.parquet")   # per-trade t_er, excR, net
    F, U = df[df["flag"]], df[~df["flag"]]

    def block(d):
        trig = d["t_er"].notna()
        acted = trig & d["exc_R"].notna()
        return dict(
            n=len(d), n_trig=int(trig.sum()), pct_trig=trig.mean() * 100,
            pct_early=(d.loc[trig, "t_er"] < 5).mean() * 100 if trig.any() else np.nan,
            med_t=d.loc[trig, "t_er"].median(),
            med_excR=d.loc[acted, "exc_R"].median(),
            pct_excR_pos=(d.loc[acted, "exc_R"] >= 0).mean() * 100 if acted.any() else np.nan,
            base_net=d["net_base"].sum(), base_exp=d["net_base"].mean(),
            exit_net=d["net_1mexit"].sum(), exit_exp=d["net_1mexit"].mean(),
            dpt=d["net_1mexit"].mean() - d["net_base"].mean(),
        )

    bF, bU = block(F), block(U)

    md = [f"# ER10 1-minute lead/lag — does 1M-ER decay precede the price failure? ({datetime.now():%Y-%m-%d})\n",
          "Per flagged trade: first minute the causal 1M-ER (10-min window, known at each "
          "1M close) is < gate (`t_ER`), where price sits then (excursion in R), and the net "
          "from exiting FLAT at that minute vs baseline. Control = same rule on unflagged. "
          "In-sample MC.\n",
          f"**Set:** `ba_signals_mc.parquet`  **Gate:** {GATE:.2f}  **scan:** 1..{K_MIN} min.\n",
          "## Lead/lag + actionable 1M-ER flat exit\n",
          "| group | n | % with 1M-ER<gate | % triggering BEFORE min-5 | median t_ER (min) "
          "| median excursion@t_ER (R) | % excursion ≥0 @t_ER | baseline exp $ | 1M-exit exp $ | Δ/trade $ |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for name, b in (("FLAGGED", bF), ("UNFLAGGED (control)", bU)):
        md.append(
            f"| {name} | {b['n']:,} | {b['pct_trig']:.1f}% | {b['pct_early']:.1f}% | "
            f"{b['med_t']:.0f} | {b['med_excR']:+.3f} | {b['pct_excR_pos']:.1f}% | "
            f"${b['base_exp']:,.2f} | ${b['exit_exp']:,.2f} | ${b['dpt']:,.2f} |")

    md += ["", "## Read\n",
           f"- **Lead/lag:** of flagged trades, {bF['pct_trig']:.0f}% see 1M-ER drop below "
           f"{GATE:.2f} within {K_MIN} min (median minute **{bF['med_t']:.0f}**), and "
           f"{bF['pct_early']:.0f}% of those trigger BEFORE the 5M entry-bar close (min 5).",
           f"- **Salvageable?** at the moment 1M-ER first crosses, median excursion is "
           f"**{bF['med_excR']:+.3f}R** and only **{bF['pct_excR_pos']:.0f}%** of trades are "
           "still at/above entry. If this is deeply negative, price has ALREADY failed by the "
           "time 1M-ER confirms it → the finer resolution does not buy an earlier exit.",
           f"- **Actionable:** exiting flat at t_ER changes flagged exp by **${bF['dpt']:,.2f}/trade** "
           f"vs baseline (control unflagged: ${bU['dpt']:,.2f}/trade). Compare to the +4pt scalp "
           "(+$13.93/trade). If the 1M exit doesn't beat the scalp AND excursion@t_ER is already "
           "negative, the thread is exhausted.\n"]
    out = _OUT / f"er10_1m_leadlag_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    log(f"FLAGGED: trig {bF['pct_trig']:.0f}% medT {bF['med_t']:.0f} medExcR {bF['med_excR']:+.3f} "
        f"%pos {bF['pct_excR_pos']:.0f} | 1M-exit Δ ${bF['dpt']:.2f}/trade (ctrl ${bU['dpt']:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
