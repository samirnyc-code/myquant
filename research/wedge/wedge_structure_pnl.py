"""wedge_structure_pnl.py — forward tick-sim P&L of the WedgeScalper structure.

Replays each MyWedge signal on the REAL ES tick trove (data/ticks_continuous,
RTH, CT) and simulates the exact 2-lot structure:

  entry  : stop 1t beyond the signal bar, valid the next ~2000 ticks (1 bar)
  stop   : 1t beyond the other side of the SB (shared by both lots)
  scalp  : lot 1 exits at +ScalpTgt ticks (limit)
  runner : lot 2 -> at +BETrig ticks stop to breakeven, then trails 1t beyond
           each completed 2000-tick bar (favourable-only ratchet)
  one position at a time; flat at session end.

Alignment: signal times and trove ticks are both CT, same price frame (verified
on 2026-08-25). A per-day median offset is still computed and applied to absorb
any residual continuous-contract adjustment; it prints per day so it can be
audited (should be ~0 near the front month).

Fill rules (conservative, post-S73):
  * entry fills only if price actually reaches the stop level (real trigger)
  * stop fills on touch; scalp target fills on reach (limit)
  * no slippage modelled -> treat results as an optimistic upper bound vs NT8

Scope caveats: RTH-only (trove), LookBack=20 signals (placeholder export, NOT
the user's real value), 2000t bars reconstructed in trove tick-space (not NT8's
exact bars). NT8 Strategy Analyzer on the same chart is the ground truth.

    python research/wedge/wedge_structure_pnl.py
        [--scalp 4] [--betrig 5] [--trail 1] [--off 1] [--fee 4]
"""
from __future__ import annotations
import argparse
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TROVE = ROOT / "data" / "ticks_continuous"
TICK = 0.25
TICK_USD = 12.5
BAR = 2000
INF = 1 << 60


def sim_trade(u, entryU, stopU, tgt_t, be_t, trail_t):
    """u = side*price from the fill tick to session end. Returns
    (scalp_ticks, run_ticks, life_len, mae_t, mfe_t). All in the signed 'u'
    frame so long/short share one code path."""
    t = TICK
    m = len(u)
    target = entryU + tgt_t * t
    # ---- scalp: first stop-touch vs first target-reach --------------------
    s_hits = np.nonzero(u <= stopU)[0]
    t_hits = np.nonzero(u >= target)[0]
    s_i = s_hits[0] if s_hits.size else INF
    t_i = t_hits[0] if t_hits.size else INF
    if s_i == INF and t_i == INF:
        scalp_ticks = (u[-1] - entryU) / t; scalp_i = m - 1
    elif s_i <= t_i:
        scalp_ticks = (stopU - entryU) / t; scalp_i = s_i
    else:
        scalp_ticks = tgt_t; scalp_i = t_i

    # ---- runner: stop0 until BE, then BE + 1t/bar trail -------------------
    be_hits = np.nonzero(u >= entryU + be_t * t)[0]
    be_i = be_hits[0] if be_hits.size else INF
    pre_stop = s_i  # same stop0 touches as scalp
    if pre_stop < be_i:
        run_ticks = (stopU - entryU) / t; run_i = pre_stop
    elif be_i == INF:
        run_ticks = (u[-1] - entryU) / t; run_i = m - 1
    else:
        run_stop = max(stopU, entryU)          # breakeven
        i = be_i; run_i = None
        while i < m:
            bar_end = ((i // BAR) + 1) * BAR
            hi = min(bar_end, m)
            blk = u[i:hi]
            hit = np.nonzero(blk <= run_stop)[0]
            if hit.size:
                run_i = i + hit[0]; break
            if bar_end <= m:                    # bar completed -> trail
                bstart = bar_end - BAR
                if bstart < 0:
                    bstart = 0
                run_stop = max(run_stop, u[bstart:bar_end].min() - trail_t * t)
            i = bar_end
        if run_i is None:
            run_ticks = (u[-1] - entryU) / t; run_i = m - 1
        else:
            run_ticks = (run_stop - entryU) / t
    life = max(scalp_i, run_i)
    exc = (u[:life + 1] - entryU) / t
    return scalp_ticks, run_ticks, life, -float(exc.min()), float(exc.max())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=str(ROOT / "data" / "wedge" / "wedge_signals_ES_2000t_6mo.csv"))
    ap.add_argument("--scalp", type=int, default=4)
    ap.add_argument("--betrig", type=int, default=5)
    ap.add_argument("--trail", type=int, default=1)
    ap.add_argument("--off", type=int, default=1, help="StopBeyondSBTicks")
    ap.add_argument("--fee", type=float, default=4.0, help="$ RT per contract")
    a = ap.parse_args()

    sig = pd.read_csv(a.csv)
    sig["SignalTime"] = pd.to_datetime(sig["SignalTime"])
    off = a.off * TICK

    rows = []
    days_used = 0
    no_trove = 0
    for date, g in sig.groupby("Date"):
        f = TROVE / f"{date}.parquet"
        if not f.exists():
            no_trove += g.shape[0]; continue
        tv = pd.read_parquet(f, columns=["DateTime", "Price"])
        ttimes = pd.to_datetime(tv["DateTime"]).values.astype("datetime64[ns]")
        price = tv["Price"].to_numpy(dtype=float)
        n = len(price)
        if n < BAR:
            continue
        days_used += 1
        # per-day offset: NT8 signal Close vs trove price at the signal instant
        gg = g.sort_values("SignalTime")
        st = gg["SignalTime"].values.astype("datetime64[ns]")
        i0s = np.searchsorted(ttimes, st, side="left")
        inwin = (i0s < n) & (i0s >= 0)
        if inwin.sum() == 0:
            continue
        med_off = float(np.median(gg["Close"].to_numpy()[inwin] - price[np.clip(i0s[inwin], 0, n - 1)]))

        busy = -1
        for k, (_, r) in enumerate(gg.iterrows()):
            i0 = int(i0s[k])
            if i0 >= n or i0 <= busy:
                continue
            side = 1 if r["Signal"] == "BL" else -1
            if side == 1:
                entry = (r["High"] + off) - med_off
                stop0 = (r["Low"] - off) - med_off
            else:
                entry = (r["Low"] - off) - med_off
                stop0 = (r["High"] + off) - med_off
            # entry valid for next BAR ticks: does price reach the stop level?
            w = price[i0:min(i0 + BAR, n)]
            reach = np.nonzero((side * w) >= (side * entry))[0]
            if reach.size == 0:
                continue                        # no fill -> signal lapses
            fill = i0 + int(reach[0])
            u = side * price[fill:n]
            entryU = side * entry
            stopU = side * stop0
            sc, rn, life, mae, mfe = sim_trade(u, entryU, stopU, a.scalp, a.betrig, a.trail)
            busy = fill + life
            rows.append((date, r["Signal"], sc, rn, mae, mfe))

    if not rows:
        print("no trades simulated"); return
    df = pd.DataFrame(rows, columns=["date", "side", "scalp_t", "run_t", "mae_t", "mfe_t"])
    df["gross_t"] = df["scalp_t"] + df["run_t"]
    df["net_usd"] = df["gross_t"] * TICK_USD - 2 * a.fee   # 2 lots RT

    n = len(df)
    out = []
    def P(s=""): out.append(s); print(s)

    P(f"WedgeScalper structure P&L — forward tick-sim on RTH trove")
    P(f"params: entry 1t beyond SB, scalp +{a.scalp}t, BE @+{a.betrig}t, trail {a.trail}t/bar, "
      f"fee ${a.fee}/ct RT")
    P(f"signals in file {len(sig)} | trove days used {days_used} | "
      f"signals with no trove day {no_trove}")
    P(f"TRADES simulated (filled, RTH, 1-at-a-time): {n}\n")

    sc, rn, net = df["scalp_t"].to_numpy(), df["run_t"].to_numpy(), df["net_usd"].to_numpy()
    def leg(name, x):
        win = (x > 0).mean() * 100
        P(f"  {name:6}: net {x.sum():+.0f}t  avg {x.mean():+.2f}t  "
          f"win {win:.1f}%  (>0 counts BE as loss after fee-free ticks)")
    P("PER-LEG (ticks, pre-fee):")
    leg("scalp", sc); leg("runner", rn)

    gw = net[net > 0].sum(); gl = -net[net < 0].sum()
    P(f"\nCOMBINED per trade (2 lots, after ${a.fee}/ct RT):")
    P(f"  total net  : ${net.sum():+,.0f}")
    P(f"  per trade  : ${net.mean():+.2f}   median ${np.median(net):+.2f}")
    P(f"  win rate   : {(net > 0).mean()*100:.1f}%")
    P(f"  profit factor: {gw/gl:.3f}" if gl else "  profit factor: inf")
    P(f"  gross ticks/trade: {df['gross_t'].mean():+.2f}t")
    P(f"\nMAE/MFE (ticks): MAE avg {df['mae_t'].mean():.1f} med {df['mae_t'].median():.0f} | "
      f"MFE avg {df['mfe_t'].mean():.1f} med {df['mfe_t'].median():.0f}")
    P(f"\nby side:")
    for s, gs in df.groupby("side"):
        P(f"  {s}: n={len(gs):4d}  net ${gs['net_usd'].sum():+,.0f}  "
          f"per-trade ${gs['net_usd'].mean():+.2f}")

    P("\naudit — first 8 trades:")
    P(df.head(8).to_string(index=False))

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (ROOT / "research" / "wedge" / f"wedge_structure_pnl_{stamp}.txt").write_text("\n".join(out), encoding="utf-8")
    df.to_csv(ROOT / "research" / "wedge" / f"wedge_structure_pnl_{stamp}.csv", index=False)
    print(f"\nsaved: research/wedge/wedge_structure_pnl_{stamp}.txt + .csv")


if __name__ == "__main__":
    main()
