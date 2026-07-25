"""Combined portfolio: S83 2E three-book + RevFT regime Book B (hours-filtered). 2026-07-25 (S85).

2E final three-book = WT-L (2EL long BULL) + WT-S (2ES short BEAR) + FADE-S (f2EL fade short BEAR).
  FADE-L (f2ES-long) is DEAD per the 2E spec and EXCLUDED.
RevFT Book B = neg-gamma & drop-counter-trend / wide-0.30xADR + hold-EOD, HOURS 09-13 (same window
  as the 2E book, per Samir).

Question: run both at once — total, correlation, combined PF/maxDD (diversification?), block-boot DD.
    python scripts/revft_2e_combined.py
Outputs a table + docs/living/revft_2e_combined_equity_20260725.png.
"""
from pathlib import Path
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
WT = Path(r"C:/Users/Admin/myquant-regime")
CB = WT / "data" / "regime" / "combined_books_20260724.csv"
RB = ROOT / "data" / "regime" / "revft_regime_full_20260725.parquet"
OUTPNG = ROOT / "docs" / "living" / "revft_2e_combined_equity_20260725.png"
RNG = np.random.default_rng(20260725)


def pf(v):
    v = np.asarray(v, float); gp = v[v > 0].sum(); gl = -v[v < 0].sum()
    return gp / gl if gl > 0 else float("inf")


def maxdd(v):
    eq = np.cumsum(np.asarray(v, float)); return float((eq - np.maximum.accumulate(eq)).min())


def block_dd(v, blocks=5, paths=5000):
    v = np.asarray(v, float); nb = max(1, len(v) // blocks)
    out = np.empty(paths)
    for i in range(paths):
        s = RNG.integers(0, max(1, len(v) - blocks), nb)
        out[i] = maxdd(np.concatenate([v[j:j+blocks] for j in s]))
    return np.percentile(out, 5), np.percentile(out, 1)


def summarize(name, v):
    v = np.asarray(v, float)
    b5, b1 = block_dd(v)
    print(f"  {name:26s} n={len(v):5d}  tot=${v.sum():>9,.0f}  $/tr={v.mean():6.1f}  PF={pf(v):4.2f}  "
          f"maxDD=${maxdd(v):>8,.0f}  boot-DD 5%/1%=${b5:>8,.0f}/${b1:>8,.0f}")


def main():
    # ---- 2E final three-book ----
    cb = pd.read_csv(CB); cb["Date"] = cb.Date.astype(str)
    cb = cb[cb.book != "FADE-L"].copy()                 # drop the dead sleeve
    print(f"2E three-book (excl FADE-L): {len(cb)} trades, ${cb.net.sum():,.0f}, PF {pf(cb.net.values):.2f}, "
          f"books {cb.book.value_counts().to_dict()}")

    # ---- RevFT Book B + hours ----
    t = pd.read_parquet(RB); t["Date"] = t.Date.astype(str)
    L, S = t.dir == "L", t.dir == "S"
    bull, bear, neu = t.reg == "BULL", t.reg == "BEAR", t.reg == "NEUTRAL"
    notCT = (L & bull) | (S & bear) | neu
    Bmask = (t.mq == "negative_gamma") & notCT & t.hour.isin(["09", "10", "11", "12", "13"])
    rb = t[Bmask][["Date", "dir", "w30eod"]].rename(columns={"w30eod": "net"})
    print(f"RevFT Book B+hours:          {len(rb)} trades, ${rb.net.sum():,.0f}, PF {pf(rb.net.values):.2f}")

    print("\n=== STANDALONE (per-trade series, chronological) ===")
    cb_s = cb.sort_values("Date"); rb_s = rb.sort_values("Date")
    summarize("2E three-book", cb_s.net.values)
    summarize("RevFT B (hours)", rb_s.net.values)

    # ---- daily aggregation for correlation + combined ----
    d2e = cb.groupby("Date").net.sum().rename("e2e")
    drb = rb.groupby("Date").net.sum().rename("erb")
    daily = pd.concat([d2e, drb], axis=1)
    both = daily.dropna()
    all_days = daily.fillna(0.0)
    print("\n=== OVERLAP / CORRELATION (daily P&L) ===")
    print(f"  2E days={d2e.shape[0]}  RevFT-B days={drb.shape[0]}  both-trade days={both.shape[0]}")
    print(f"  Pearson corr on both-trade days:     {both.e2e.corr(both.erb):+.3f}")
    print(f"  Pearson corr over union (0-filled):  {all_days.e2e.corr(all_days.erb):+.3f}")
    print(f"  mean 2E on shared days ${both.e2e.mean():,.0f} | mean RevFT ${both.erb.mean():,.0f}")

    # ---- combined chronological (merge all trades by date) ----
    comb = pd.concat([cb_s[["Date", "net"]].assign(sys="2E"),
                      rb_s[["Date", "net"]].assign(sys="RevFT")]).sort_values("Date").reset_index(drop=True)
    print("\n=== COMBINED (both systems, all trades) ===")
    summarize("2E + RevFT-B", comb.net.values)
    print(f"  sum-of-standalone maxDD = ${maxdd(cb_s.net.values)+maxdd(rb_s.net.values):,.0f}  "
          f"vs combined maxDD ${maxdd(comb.net.values):,.0f}  "
          f"(diversification saves ${(maxdd(cb_s.net.values)+maxdd(rb_s.net.values))-maxdd(comb.net.values):,.0f})")

    # per-year combined
    comb["year"] = comb.Date.str[:4].astype(int)
    print("  year: " + "  ".join(f"{y}:${comb[comb.year==y].net.sum():>7,.0f}" for y in sorted(comb.year.unique())))

    # ---- chart ----
    fig, ax = plt.subplots(figsize=(12, 6.2))
    for name, d, c in (("2E three-book", cb_s, "#8b5cf6"), ("RevFT B (hours)", rb_s, "#1f7a3d")):
        x = pd.to_datetime(d.Date).values; ax.plot(x, d.net.cumsum().values, label=f"{name}  (${d.net.sum():+,.0f})", color=c, lw=1.6)
    x = pd.to_datetime(comb.Date).values
    ax.plot(x, comb.net.cumsum().values, label=f"COMBINED  (${comb.net.sum():+,.0f}, DD ${maxdd(comb.net.values):,.0f})", color="#111", lw=2.2)
    ax.axhline(0, color="#999", lw=.8); ax.set_title("2E three-book + RevFT Book B (hours 09-13) — cumulative net $, 1 ES", fontsize=11)
    ax.set_ylabel("cumulative net $"); ax.legend(loc="upper left", fontsize=9); ax.grid(alpha=.25)
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    fig.tight_layout(); fig.savefig(OUTPNG, facecolor="white", dpi=110); print(f"\nsaved {OUTPNG}")


if __name__ == "__main__":
    main()
