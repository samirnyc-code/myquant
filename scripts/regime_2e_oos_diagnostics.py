"""OOS DIAGNOSTICS — is the pre-2021 null REAL, or a pipeline artifact?
Year-by-year integrity + signal decomposition on the Databento 1-min frames, plus a
bar-level Databento-vs-NT cross-check on the 2021-26 overlap.

Checks that would expose a FAKE null:
  * trading days/yr (~252), median 5M bars/day (~81), median 1M bars/day (~405)
  * time-of-day coverage (first/last RTH bar) per year  -> tz / session drift
  * % of 1-min bars that are single-print (H==L) per year -> pseudo-tick degradation in thin years
  * front-month roll audit sanity (quarterly, gap sizes)
  * price range per year (ES ~1050 in 2010 -> ~5600 in 2026) -> scale/roll errors
  * regime label mix (BULL/BEAR/NEUTRAL % of RTH bars) per year -> is the phase machine even
    labelling trends pre-2021, or calling everything NEUTRAL?
  * 2E entries detected / passing gate / filled per year -> are we generating signals at all?
  * Databento 5M vs NT _continuous.parquet 5M on 2021-26: max|OHLC diff| (bar-level)

  python scripts/regime_2e_oos_diagnostics.py
Output: data/regime/oos_diagnostics_20260725.csv + tables.
"""
import sys
from pathlib import Path
from bisect import bisect_right
import numpy as np
import pandas as pd

TICK = 0.25
WT = Path(__file__).resolve().parent.parent
DATA = Path(r"C:/Users/Admin/myquant/data")
sys.path.insert(0, str(WT / "scripts"))
from regime_second_entry_study import phase_transitions as pt_old   # noqa: E402
from regime_2e_causal_check import detect_entries_causal            # noqa: E402
from regime_2e_tickproxy_fidelity import proxy_ticks, bar_labels    # noqa: E402

M5 = DATA / "bars" / "_db_es_5m_rth.parquet"
M1 = DATA / "bars" / "_db_es_1m_rth.parquet"
GOOD = {"09", "10", "11", "12", "13"}


def main():
    b = pd.read_parquet(M5); b["DateTime"] = pd.to_datetime(b["DateTime"]); b["Date"] = b["DateTime"].dt.date.astype(str)
    m1 = pd.read_parquet(M1); m1["DateTime"] = pd.to_datetime(m1["DateTime"]); m1["Date"] = m1["DateTime"].dt.date.astype(str)
    m1["flat"] = (m1.High == m1.Low)
    m1g = {d: x.sort_values("DateTime").reset_index(drop=True) for d, x in m1.groupby("Date")}
    dly = b.groupby("Date").agg(dO=("Open", "first"), dC=("Close", "last"), dH=("High", "max"), dL=("Low", "min")).reset_index()
    dly["adr10"] = (dly.dH - dly.dL).rolling(10).mean().shift(1)
    dly["gap"] = ((dly.dO - dly.dC.shift(1)) / dly.dC.shift(1) * 100).abs()
    gm = dly.set_index("Date")[["adr10", "gap"]]
    days = sorted(b["Date"].unique())

    per_day = []
    for dstr in days:
        if dstr not in gm.index or dstr not in m1g:
            continue
        adr, gapv = gm.loc[dstr, "adr10"], gm.loc[dstr, "gap"]
        g = b[b.Date == dstr].sort_values("DateTime").reset_index(drop=True)
        if len(g) < 30:
            continue
        m1day = m1g[dstr]; m1day = m1day[m1day.DateTime >= g["DateTime"].values[0]]
        if len(m1day) < 30:
            continue
        yr = int(dstr[:4])
        traded = np.isfinite(adr) and gapv <= 0.54
        H, L = g["High"].values, g["Low"].values; n = len(g)
        # regime mix + entries via pseudo-ticks (only for traded days, to mirror the book)
        n_ent = n_gate = n_fill = 0
        bull = bear = neut = 0
        if traded:
            tP2, tbar2 = proxy_ticks(g, m1day)
            trans = pt_old(H, L, n, tP2, tbar2)
            lab = bar_labels(trans, tbar2, n)
            bull = int((lab == "BULL").sum()); bear = int((lab == "BEAR").sum()); neut = int((lab == "NEUTRAL").sum())
            tr_ix = [t for (t, _) in trans]; tr_md = [m for (_, m) in trans]
            entries = detect_entries_causal(g, tP2, tbar2)
            gdt = g["DateTime"].values
            for (fb, sb, dr, cnt, trig) in entries:
                if cnt != 2:
                    continue
                n_ent += 1
                short = dr == "S"; want = "BEAR" if short else "BULL"
                a = np.searchsorted(tbar2, fb, "left"); z = np.searchsorted(tbar2, fb, "right")
                hit = np.nonzero(tP2[a:z] <= trig)[0] if short else np.nonzero(tP2[a:z] >= trig)[0]
                if not len(hit):
                    continue
                jf = a + int(hit[0]); reg = tr_md[bisect_right(tr_ix, jf) - 1]
                if reg == want:
                    n_gate += 1
                    lim = trig + 6 * TICK if short else trig - 6 * TICK; s0 = tP2[jf:]
                    jl = np.nonzero(s0 > lim)[0] if short else np.nonzero(s0 < lim)[0]
                    if len(jl):
                        jfl = jf + int(jl[0]); fb2 = int(tbar2[jfl])
                        if fb2 - fb <= 6 and pd.Timestamp(gdt[min(fb2, n - 1)]).strftime("%H") in GOOD:
                            n_fill += 1
        per_day.append({
            "Date": dstr, "yr": yr, "traded": traded,
            "n5m": len(g), "n1m": len(m1day), "flat1m": float(m1day.flat.mean()),
            "t_first": g["DateTime"].dt.strftime("%H:%M").iloc[0],
            "t_last": g["DateTime"].dt.strftime("%H:%M").iloc[-1],
            "close": g["Close"].iloc[-1], "adr": adr if np.isfinite(adr) else np.nan,
            "bull": bull, "bear": bear, "neut": neut,
            "n_ent": n_ent, "n_gate": n_gate, "n_fill": n_fill,
        })
    d = pd.DataFrame(per_day)
    d.to_csv(WT / "data" / "regime" / "oos_diagnostics_20260725.csv", index=False)

    print("\n===== PER-YEAR INTEGRITY + SIGNAL =====")
    print(f"{'yr':>4} {'days':>4} {'trd':>4} {'5m/d':>5} {'1m/d':>5} {'flat1m%':>7} "
          f"{'tfirst':>6} {'tlast':>6} {'close':>7} {'adr':>5} {'BULL%':>5} {'BEAR%':>5} {'NEU%':>5} "
          f"{'ent':>4} {'gate':>4} {'fill':>4}")
    for yr, x in d.groupby("yr"):
        t = x[x.traded]
        tot = t[["bull", "bear", "neut"]].sum().sum()
        bp = 100 * t.bull.sum() / tot if tot else 0
        rp = 100 * t.bear.sum() / tot if tot else 0
        npc = 100 * t.neut.sum() / tot if tot else 0
        print(f"{yr:>4} {len(x):>4} {int(x.traded.sum()):>4} {x.n5m.median():>5.0f} {x.n1m.median():>5.0f} "
              f"{100*x.flat1m.mean():>7.1f} {x.t_first.mode().iloc[0]:>6} {x.t_last.mode().iloc[0]:>6} "
              f"{x.close.median():>7.0f} {x.adr.median():>5.0f} {bp:>5.1f} {rp:>5.1f} {npc:>5.1f} "
              f"{int(t.n_ent.sum()):>4} {int(t.n_gate.sum()):>4} {int(t.n_fill.sum()):>4}")

    print("\n===== DATABENTO 5M vs NT _continuous.parquet 5M (2021-26 overlap, bar-level) =====")
    nt = pd.read_parquet(DATA / "bars" / "_continuous.parquet"); nt["DateTime"] = pd.to_datetime(nt["DateTime"])
    j = b.merge(nt, on="DateTime", suffixes=("_db", "_nt"))
    if len(j):
        # levels differ by a constant panama offset per contract era; compare RANGE and RETURNS not level
        j = j.sort_values("DateTime")
        rng_db = (j.High_db - j.Low_db); rng_nt = (j.High_nt - j.Low_nt)
        ret_db = j.Close_db.pct_change(); ret_nt = j.Close_nt.pct_change()
        print(f"overlap bars: {len(j):,}")
        print(f"bar-RANGE  corr={rng_db.corr(rng_nt):.5f}  max|diff|={ (rng_db-rng_nt).abs().max():.3f} pt")
        print(f"bar-RETURN corr={ret_db.corr(ret_nt):.5f}  max|diff|={ (ret_db-ret_nt).abs().dropna().max():.5f}")
        print(f"median |range diff| = {(rng_db-rng_nt).abs().median():.4f} pt  "
              f"(0 => identical bar geometry => identical signals)")
    else:
        print("no overlapping 5M timestamps (tz mismatch!) — this alone would explain a fake null")


if __name__ == "__main__":
    main()
