"""TR-FADE setup — the complement to the 2E continuation edge. On BALANCE (range/chop) days,
fade the Initial-Balance extreme back toward the middle. Targets exactly the low-efficiency days
where 2E goes flat, so it should be uncorrelated with the long-2E book by construction.

DEFINITION (all causal):
  - Initial Balance (IB) = high/low of the first 60 min (08:30-09:30 CT, 12x 5M bars).
  - Balance-day filter (causal, prior-day): trade only when prior-day ER10 is BELOW its causal
    expanding median (choppy regime) -- the days 2E can't use.
  - Entry: after IB, first touch of IB-high -> SHORT (fade) at IB-high; first touch of IB-low ->
    LONG at IB-low. Limit at the level. One trade/side/day.
  - Stop: IB extreme +/- STOP (0.15xADR10, floor 8t). Target: IB midpoint. EOD flat.
  - Skip if |RTH gap|>0.9% (don't fade a gap-and-go).

Sim on 5M bars (touch = fill; intrabar stop-before-target assumed adverse-first = conservative).
Reports 16yr net R by 4-yr block + correlation vs the 2E long book.

  python scripts/trfade_test.py
Output: data/regime/trfade_20260725.csv + tables.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0; SLIP = 12.5; FLOOR = 8 * TICK
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
M5 = DATA / "bars" / "_db_es_5m_rth.parquet"
BLOCKS = [(2010, 2013), (2014, 2017), (2018, 2021), (2022, 2026)]
STOPMULT = 0.15


def pf(s):
    s = np.asarray(s, float); gp = s[s > 0].sum(); gl = -s[s < 0].sum()
    return round(gp / gl, 2) if gl > 0 else 0.0


def main():
    b = pd.read_parquet(M5); b["DateTime"] = pd.to_datetime(b["DateTime"]); b["Date"] = b["DateTime"].dt.date.astype(str)
    b["hm"] = b["DateTime"].dt.strftime("%H:%M")
    # daily aggregates
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index().sort_values("Date")
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    c = dly["dC"]; chg = c.diff().abs()
    dly["er10"] = ((c - c.shift(10)).abs() / chg.rolling(10).sum()).shift(1)
    dly["ermed"] = dly["er10"].expanding(min_periods=60).median()
    dly["chop"] = (dly["er10"] < dly["ermed"]).astype(float)          # balance-day flag (causal)
    gm = dly.set_index("Date")

    rows = []
    for dstr, g in b.groupby("Date"):
        if dstr not in gm.index:
            continue
        adr, gap = gm.loc[dstr, "adr10"], gm.loc[dstr, "gap"]
        if not np.isfinite(adr) or gap > 0.9:
            continue
        g = g.sort_values("DateTime").reset_index(drop=True)
        ib = g[(g.hm >= "08:30") & (g.hm < "09:30")]
        if len(ib) < 10:
            continue
        ibh, ibl = ib.High.max(), ib.Low.min()
        mid = (ibh + ibl) / 2.0
        # BALANCE filter (causal, known at 09:30): narrow IB relative to ADR
        if (ibh - ibl) > 0.6 * adr:
            continue
        post = g[g.hm >= "09:30"].reset_index(drop=True)
        buf = 2 * TICK
        for side in ("S", "L"):
            lvl = ibh if side == "S" else ibl
            # REJECTION entry: first bar that pokes THROUGH the level but CLOSES back inside
            rej = None
            for j, bar in post.iterrows():
                poked = (bar.High > lvl) if side == "S" else (bar.Low < lvl)
                closed_in = (bar.Close < lvl) if side == "S" else (bar.Close > lvl)
                if poked and closed_in:
                    rej = (j, bar); break
                if (bar.Close > lvl + buf) if side == "S" else (bar.Close < lvl - buf):
                    break  # clean breakout the OTHER way (range broke) -> no fade
            if rej is None:
                continue
            j, bar = rej
            entry = float(bar.Close)                                  # enter on the rejection close
            stop = (bar.High + buf) if side == "S" else (bar.Low - buf)  # beyond the rejection extreme
            stop_d = abs(stop - entry)
            if stop_d < FLOOR:
                stop = entry + FLOOR if side == "S" else entry - FLOOR; stop_d = FLOOR
            tgt = mid
            seq = post.iloc[j + 1:]
            net = None
            for _, bb in seq.iterrows():
                hitstop = bb.High >= stop if side == "S" else bb.Low <= stop
                hittgt = bb.Low <= tgt if side == "S" else bb.High >= tgt
                if hitstop:
                    ex = stop; net = ((entry - ex) if side == "S" else (ex - entry)) * PT - COMM - SLIP; break
                if hittgt:
                    ex = tgt; net = ((entry - ex) if side == "S" else (ex - entry)) * PT - COMM - SLIP; break
            if net is None:
                ex = seq.iloc[-1].Close if len(seq) else entry
                net = ((entry - ex) if side == "S" else (ex - entry)) * PT - COMM - SLIP
            rows.append({"Date": dstr, "yr": int(dstr[:4]), "side": side,
                         "net": round(net, 1), "R": net / (stop_d * PT)})
    df = pd.DataFrame(rows); df.to_csv(WT / "data" / "regime" / "trfade_20260725.csv", index=False)

    print(f"===== TR-FADE (IB fade on balance days), 16yr, 1 ES =====")
    print(f"trades {len(df)} ({len(df)/16.5:.0f}/yr)  net ${df.net.sum():+,.0f} (${df.net.sum()/16.5:+,.0f}/yr)  "
          f"PF {pf(df.net)}  meanR {df.R.mean():+.3f}  win {100*(df.net>0).mean():.0f}%")
    print("\nby 4-yr block:")
    for y0, y1 in BLOCKS:
        x = df[(df.yr >= y0) & (df.yr <= y1)]
        print(f"  {y0}-{y1}: n={len(x):4d} meanR {x.R.mean():+.3f} PF {pf(x.net):.2f} net ${x.net.sum():+,.0f}")
    print("\nby side:")
    for s in ("L", "S"):
        x = df[df.side == s]; print(f"  {s}: n={len(x):4d} PF {pf(x.net):.2f} meanR {x.R.mean():+.3f}")

    # correlation vs 2E long book (daily PnL)
    try:
        lg = pd.read_csv(WT / "data" / "regime" / "oos_pertrade_full_20260725.csv")
        lg = lg[lg.with_trend & (lg.dir == "L")]
        lp = lg.groupby("Date").net.sum(); fp = df.groupby("Date").net.sum()
        j = pd.concat([lp.rename("L2E"), fp.rename("TRfade")], axis=1).fillna(0)
        print(f"\ndaily-PnL corr (2E-long vs TR-fade) = {j.L2E.corr(j.TRfade):+.3f}  (low = good diversifier)")
        print(f"days both active: {((j.L2E!=0)&(j.TRfade!=0)).sum()}  | TR-fade-only days: {((j.L2E==0)&(j.TRfade!=0)).sum()}")
    except Exception as e:
        print("corr skipped:", e)


if __name__ == "__main__":
    main()
