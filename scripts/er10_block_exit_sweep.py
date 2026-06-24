"""er10_block_exit_sweep.py — salvage the trades the ER10 look-ahead "phantom-blocked".

Idea (S38, user): the pre-fix bug gated on the ENTRY bar's ER10 — look-ahead at
DECISION time. But the entry-bar ER10 is legitimately KNOWN at the entry bar's
CLOSE (~5 min after entry; bars are 5-min). So using it as an EXIT signal at EB
close is fully causal. The bug's only "skill" was phantom-BLOCKING ~2,148 trades
whose ER10 had decayed below the gate by EB close. Those are the trades the causal
(now-live) strategy still TAKES. Can we cut their drag by exiting once the decayed
ER10 is known (at EB close)?

This script:
  1. Tags ER10 both modes (reusing er_lookahead_tab._er10_both_modes — no code change).
  2. Flags the phantom-BLOCK set: causal ER10 >= GATE (we trade it) AND entry-bar
     ER10 < GATE (the bug would have skipped it).
  3. Runs the production engine on the FULL causal-gated population (baseline).
  4. For each flagged trade that is still OPEN at EB close, replays ticks from EB
     close with an overlay exit at price = entry + k (favorable k), keeping the
     original stop & 1R target as outer guards. Sweeps k (points), plus a
     "flat @ EB close" market-exit reference.
  5. Reports the flagged subset's P&L per exit rule AND the whole-strategy net
     (unflagged trades unchanged + flagged trades under the overlay).

Trades that hit their stop/target DURING the entry bar (before EB close) are
unaffected — the overlay can't act in time; they keep their baseline outcome.

Exec = original ER10 study pin: 1.0R single-leg, 1c, entry_slip=1t, exit_slip=0,
stop_offset=1t, comm $4.36 RT. Signal set = ba_signals_mc.parquet. GATE = 0.70.
Out: docs/living/er10_block_exit_sweep_<date>.md
"""
from __future__ import annotations

import sys, gc
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                                                        # noqa: E402
from simulation_engine import simulate_trades, TICK_SIZE             # noqa: E402
from data_loader import bar_num_from_dt                              # noqa: E402
from er_lookahead_tab import _er10_both_modes                        # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"

GATE       = 0.70
COMMISSION = 4.36
TV         = 12.5          # tick_value * 1 contract
TS         = TICK_SIZE     # 0.25
N_CHUNKS   = 4
EB         = pd.Timedelta(minutes=5)   # 5-min bar → EB close = entry bar open + 5m
SIM_KW = dict(target_r=1.0, entry_slip=1, exit_slip=0, stop_offset=1,
              tick_value=TV, contracts=1, commission=COMMISSION, overrides=None)
# overlay exit offsets in POINTS (favorable sign): <0 tighter stop, 0 = breakeven,
# >0 = tight take-profit. "flat" handled separately.
K_GRID = [-8, -6, -4, -3, -2, -1, 0, 1, 2, 3, 4, 6]


def log(m): print(f"[blk] {datetime.now():%H:%M:%S} {m}", flush=True)


def _overlay_gross_pts(row, ticks: pd.DataFrame, k) -> float:
    """Gross POINTS for one flagged trade under exit rule `k`.

    k is a number (favorable points offset) or the string "flat" (market exit at
    the first tick >= EB close). Survivors only; callers pass baseline for trades
    that exited within the entry bar. Stops/targets fill AT their level (engine
    convention)."""
    is_long = row.Direction == "Long"
    entry, stop0, tgt = row.EntryPrice, row.ActualStop, row.Target
    ebc = pd.Timestamp(row.EntryTime).floor("5min") + EB
    if pd.Timestamp(row.ExitTime) < ebc:   # already exited INSIDE entry bar → can't act
        return row.GrossPnLPts
    seg = ticks.loc[ticks["DateTime"] >= ebc, "Price"].to_numpy()
    if seg.size == 0:                      # no path after EB close → baseline EOD
        return row.GrossPnLPts

    if k == "flat":                        # market exit at first post-EB-close tick
        exit_px = float(seg[0])
        return (exit_px - entry) if is_long else (entry - exit_px)

    L = (entry + k) if is_long else (entry - k)   # favorable offset
    if is_long:
        up = tgt if k <= 0 else min(tgt, L)        # nearest profit-side exit
        dn = stop0 if k > 0 else max(stop0, L)     # tightest loss-side exit
        up_hit, dn_hit = seg > up, seg <= dn
    else:
        dn = tgt if k <= 0 else max(tgt, L)        # profit side (price down)
        up = stop0 if k > 0 else min(stop0, L)     # loss side (price up)
        dn_hit, up_hit = seg < dn, seg >= up

    hit = up_hit | dn_hit
    if not hit.any():
        exit_px = float(seg[-1])                   # EOD
    else:
        i = int(np.argmax(hit))
        if i == 0:
            # Level already breached at the FIRST post-EB-close tick → in reality
            # you'd send a market order on the flag and fill at that tick, NOT at the
            # (already-passed) level. Filling at the level here would fabricate a
            # breakeven/clean-stop exit on a trade that is already underwater.
            exit_px = float(seg[0])
        elif is_long:
            exit_px = up if up_hit[i] else dn      # crossed mid-path → fill at level
        else:
            exit_px = dn if dn_hit[i] else up
    return (exit_px - entry) if is_long else (entry - exit_px)


def _net(gross_pts) -> float:
    return gross_pts / TS * TV - COMMISSION


def main() -> int:
    log("load + tag both modes ...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bbd = {d: g.reset_index(drop=True) for d, g in bars.groupby(bars["DateTime"].dt.date)}
    if "BarNum" not in sig.columns:
        sig["BarNum"] = sig["DateTime"].apply(bar_num_from_dt)

    tagged = _er10_both_modes(sig, bars)
    causal_pass = tagged["ER10_causal"] >= GATE                 # we trade it (live)
    cur_pass    = tagged["ER10_current"] >= GATE                # bug would trade it
    flag = causal_pass & ~cur_pass                              # phantom-BLOCK set
    g = tagged.loc[causal_pass].copy()                          # the live (causal) book
    g["FilterStatus"] = "ok"
    g["_flag"] = flag.loc[g.index].to_numpy()
    g["_date"] = pd.to_datetime(g["DateTime"]).dt.date
    log(f"causal book: {len(g):,} signals;  phantom-blocked (flagged): {int(g['_flag'].sum()):,}")

    base_rows, ov_rows = [], []
    dates = sorted(g["_date"].unique())
    for ci, chunk in enumerate(np.array_split(np.array(dates, object), N_CHUNKS)):
        cset = set(chunk.tolist())
        tbd = {d: massive.load_continuous_ticks(d) for d in chunk}
        tbd = {d: t for d, t in tbd.items() if not t.empty}
        sub = g[g["_date"].isin(cset)].drop(columns="_date").reset_index(drop=True)
        res = simulate_trades(sub, ticks_by_date=tbd, bars_by_date=bbd, **SIM_KW)
        filled = res[res["Filled"] == True].copy()
        base_rows.append(filled[["SignalNum", "DateTime", "Date", "_flag", "Direction",
                                 "EntryPrice", "EntryTime", "ActualStop", "Target",
                                 "RiskPts", "ExitTime", "GrossPnLPts"]])
        # overlay only on flagged filled trades
        fl = filled[filled["_flag"]].copy()
        for r in fl.itertuples(index=False):
            t = tbd.get(r.Date)
            rec = {"SignalNum": r.SignalNum, "GrossPnLPts_base": r.GrossPnLPts,
                   "RiskPts": r.RiskPts}
            if t is None or t.empty:
                for k in K_GRID + ["flat"]:
                    rec[f"k_{k}"] = r.GrossPnLPts
            else:
                for k in K_GRID + ["flat"]:
                    rec[f"k_{k}"] = _overlay_gross_pts(r, t, k)
            ov_rows.append(rec)
        del tbd; gc.collect()
        log(f"  chunk {ci+1}/{N_CHUNKS} done")

    base = pd.concat(base_rows, ignore_index=True)
    base["net_base"] = _net(base["GrossPnLPts"])
    ov = pd.DataFrame(ov_rows)
    base.to_parquet(_OUT / "er10_block_base.parquet")        # per-trade baseline + flag
    ov.to_parquet(_OUT / "er10_block_overlay.parquet")       # per-trade overlay grid (gross pts)

    flagged_base = base[base["_flag"]]
    unflag_net   = float(base.loc[~base["_flag"], "net_base"].sum())
    n_flag       = len(flagged_base)
    n_unflag     = int((~base["_flag"]).sum())
    base_total   = float(base["net_base"].sum())

    # survivors = flagged trades still open at EB close (overlay can actually act)
    surv = (pd.to_datetime(flagged_base["ExitTime"]).values >
            (pd.to_datetime(flagged_base["EntryTime"]).dt.floor("5min") + EB).values)
    n_surv = int(surv.sum())

    def summarize(net_series: np.ndarray) -> dict:
        n = len(net_series)
        wins = (net_series > 0).sum()
        return dict(net=float(net_series.sum()), exp=float(net_series.mean()) if n else 0.0,
                    win=float(wins / n * 100) if n else 0.0)

    fb = summarize(flagged_base["net_base"].to_numpy())
    rows = [("BASELINE (no overlay)", fb["net"], fb["exp"], fb["win"], unflag_net + fb["net"])]
    for k in ["flat"] + K_GRID:
        net_k = _net(ov[f"k_{k}"].to_numpy())
        s = summarize(net_k)
        label = "flat @ EB close" if k == "flat" else f"exit @ entry{k:+d}pt"
        rows.append((label, s["net"], s["exp"], s["win"], unflag_net + s["net"]))

    # ── report ───────────────────────────────────────────────────────────────
    best = max(rows[1:], key=lambda x: x[4])
    md = [f"# ER10 phantom-block exit sweep ({datetime.now():%Y-%m-%d})\n",
          "**Premise (causally valid):** the entry-bar ER10 the bug used as a *gate* "
          "(look-ahead) is legitimately *known at the entry bar's close* (~5 min after "
          "entry). Use it as an **exit** signal there instead. These are the "
          f"**{n_flag:,} trades** the causal book takes but whose ER10 had decayed below "
          f"{GATE:.2f} by EB close (the bug skipped them).\n",
          f"**Signal set:** `ba_signals_mc.parquet`  **Gate:** ER10 ≥ {GATE:.2f}  "
          "**Exec:** 1.0R single-leg, 1c, entry_slip=1t, exit_slip=0, comm $4.36 RT.\n",
          f"- Causal book: **{len(g):,}** signals → **{n_unflag:,}** unflagged + "
          f"**{n_flag:,}** flagged (filled).",
          f"- Of the flagged, **{n_surv:,}** are still OPEN at EB close (overlay can act); "
          f"the other **{n_flag - n_surv:,}** already hit stop/target inside the entry bar "
          "(unaffected — kept at baseline).",
          f"- Unflagged trades' net (held fixed): **${unflag_net:,.0f}**.  "
          f"Whole-book causal baseline: **${base_total:,.0f}**.\n",
          "## Flagged-subset exit rules\n",
          "| exit rule | flagged net $ | flagged exp $/trade | flagged win % | WHOLE-BOOK net $ |",
          "|---|---|---|---|---|"]
    for label, net, exp, win, tot in rows:
        star = "  ⭐" if (label, net, exp, win, tot) == best else ""
        md.append(f"| {label}{star} | ${net:,.0f} | ${exp:,.2f} | {win:.1f}% | ${tot:,.0f} |")
    md += ["",
           f"**Best whole-book result:** `{best[0]}` → flagged net ${best[1]:,.0f} "
           f"(exp ${best[2]:,.2f}/trade), whole-book **${best[4]:,.0f}** vs baseline "
           f"**${unflag_net + fb['net']:,.0f}** "
           f"(Δ **${best[4] - (unflag_net + fb['net']):,.0f}**).\n",
           "_Overlay stops/targets fill at their level when price crosses them mid-path; "
           "a level already breached at the first post-EB-close tick fills at market there "
           "(no fabricated breakeven on already-underwater trades). 'flat @ EB close' exits "
           "at the first tick at/after EB close (market)._\n"]
    out = _OUT / f"er10_block_exit_sweep_{datetime.now():%Y%m%d}.md"
    out.write_text("\n".join(md), encoding="utf-8")
    log(f"wrote {out}")
    log(f"flagged baseline net=${fb['net']:,.0f} exp=${fb['exp']:.2f} win={fb['win']:.1f}% (n={n_flag})")
    log(f"BEST: {best[0]} → flagged ${best[1]:,.0f}, whole-book ${best[4]:,.0f} "
        f"(Δ ${best[4]-(unflag_net+fb['net']):,.0f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
