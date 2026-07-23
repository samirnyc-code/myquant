"""ACCOUNT-LEVEL sim of the S83 headline stack — one equity path, tradeable policies.

The research book booked every qualifying 2E independently (up to 5 concurrent).
This sim processes signals CHRONOLOGICALLY with an explicit position policy:

  P1 one-shot : ignore every signal while a position is open
  P2 pyramid3 : same-direction adds up to 3 units; opposite signals ignored
  P3 flip     : opposite qualifying fill closes all units at that tick, reverses;
                same-direction adds up to 3

Mechanics held at the audited headline: causal S61 2E, WT gate at trigger,
retest limit 4t THROUGH-fill, 4pt stop per unit, EOD flat, fills h09-13,
$5 RT per unit, 1 ES per unit. Reports train/test, yearly, closed-trade DD.

Output: data/regime/account_sim_20260723.csv
  python scripts/regime_2e_account_sim.py [--limit N]
"""
import sys, gc, time
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25; PT = 50.0; COMM = 5.0
WT_ROOT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT_ROOT / "scripts"))
from regime_second_entry_study import phase_transitions, load_day   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402

OUT = WT_ROOT / "data" / "regime" / "account_sim_20260723.csv"
GOOD_HOURS = {"09", "10", "11", "12", "13"}
TRAIN_END = "2023-12-31"


def day_signals(dstr, g, tP, tbar):
    """Qualifying headline signals with fill/stop tick indices, trigger-time order."""
    O, H, L, C = (g[c].values for c in ["Open", "High", "Low", "Close"])
    n = len(g)
    transitions = phase_transitions(H, L, n, tP, tbar)
    entries = detect_entries_causal(g, tP, tbar)
    tr_ix = [t for (t, _) in transitions]; tr_md = [m for (_, m) in transitions]
    g_dt = g["DateTime"].values
    sigs = []
    for (fb, sb, dr, cnt, trig) in entries:
        if cnt != 2:
            continue
        short = dr == "S"
        a = np.searchsorted(tbar, fb, "left"); z = np.searchsorted(tbar, fb, "right")
        s = tP[a:z]
        hit = np.nonzero(s <= trig)[0] if short else np.nonzero(s >= trig)[0]
        if not len(hit):
            continue
        jf = a + int(hit[0])
        want = "BEAR" if short else "BULL"
        if tr_md[bisect_right(tr_ix, jf) - 1] != want:
            continue
        lim = trig + 4 * TICK if short else trig - 4 * TICK
        seg0 = tP[jf:]
        jl_ = np.nonzero(seg0 > lim)[0] if short else np.nonzero(seg0 < lim)[0]
        if not len(jl_):
            continue
        jfl = jf + int(jl_[0])
        fill_bar = int(tbar[jfl])
        hh_ = pd.Timestamp(g_dt[min(fill_bar, n - 1)]).strftime("%H")
        if hh_ not in GOOD_HOURS:
            continue
        stop = lim + 16 * TICK if short else lim - 16 * TICK
        seg = tP[jfl:]
        js_ = np.nonzero(seg >= stop)[0] if short else np.nonzero(seg <= stop)[0]
        jstop = jfl + int(js_[0]) if len(js_) else np.inf
        sigs.append(dict(dir=dr, jf=jf, jfl=jfl, fill=lim, stop=stop, jstop=jstop))
    sigs.sort(key=lambda x: x["jf"])
    return sigs


def run_policy(sigs, tP, policy):
    """Sequential account. Returns list of unit trades (net$)."""
    open_units = []      # dicts: dir, fill, stop, jstop
    closed = []

    def close_unit(u, px):
        pnl = (u["fill"] - px) if u["dir"] == "S" else (px - u["fill"])
        closed.append(pnl * PT - COMM)

    for sg in sigs:
        # settle any stops that hit before this signal's FILL time
        still = []
        for u in open_units:
            if u["jstop"] <= sg["jfl"]:
                close_unit(u, u["stop"])
            else:
                still.append(u)
        open_units = still
        same = [u for u in open_units if u["dir"] == sg["dir"]]
        opp = [u for u in open_units if u["dir"] != sg["dir"]]
        take = False
        if policy == "P1":
            take = not open_units
        elif policy == "P2":
            take = not opp and len(same) < 3
        elif policy == "P3":
            if opp:
                for u in opp:
                    close_unit(u, sg["fill"])
                open_units = same
            take = len(same) < 3
        if take:
            open_units.append(dict(sg))
    for u in open_units:
        if np.isfinite(u["jstop"]):
            close_unit(u, u["stop"])
        else:
            close_unit(u, tP[-1])
    return closed


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    b = pd.read_parquet(DATA / "bars" / "_continuous.parquet")
    b["Date"] = b["DateTime"].dt.date.astype(str)
    days = sorted(b["Date"].unique())
    if limit:
        days = days[:limit]
    rows = []; t0 = time.time()
    for di, dstr in enumerate(days):
        g, tP, tbar = load_day(b, dstr)
        if g is None:
            continue
        try:
            sigs = day_signals(dstr, g, tP, tbar)
        except Exception as e:
            print(dstr, "ERR", repr(e), flush=True)
            continue
        if sigs:
            for pol in ("P1", "P2", "P3"):
                for netv in run_policy(sigs, tP, pol):
                    rows.append((dstr, pol, round(netv, 1)))
        del tP, tbar; gc.collect()
        if (di + 1) % 200 == 0:
            print(f"[{di+1}/{len(days)}] rows={len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    df = pd.DataFrame(rows, columns=["Date", "policy", "net"])
    df.to_csv(OUT, index=False)
    df["is_tr"] = df.Date <= TRAIN_END

    def pf(s):
        gp = s[s > 0].sum(); gl = -s[s < 0].sum()
        return gp / gl if gl > 0 else float("inf")

    print(f"\nDONE {time.time()-t0:.0f}s -> {OUT}")
    print("\npolicy  n     net$      PF    | train net/PF | test net/PF | maxDD(closed)")
    for pol in ("P1", "P2", "P3"):
        x = df[df.policy == pol]
        eq = x.net.cumsum(); dd = float((eq - eq.cummax()).min())
        trn = x[x.is_tr]; tst = x[~x.is_tr]
        print(f"{pol}  {len(x):5d}  {x.net.sum():+9,.0f}  {pf(x.net):5.2f} | "
              f"{trn.net.sum():+9,.0f} {pf(trn.net):5.2f} | "
              f"{tst.net.sum():+9,.0f} {pf(tst.net):5.2f} | {dd:+10,.0f}")
        y = x.copy(); y["yr"] = y.Date.str[:4]
        print("   yearly:", {k: int(v) for k, v in y.groupby('yr').net.sum().items()})


if __name__ == "__main__":
    main()
