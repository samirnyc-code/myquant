"""Touch-band sensitivity sweep (S75K, pre-registered).

Runs orderflow_at_levels.run() at ±2 / ±4 / ±8 ticks AND the pre-registered
volatility-normalized band (0.35 * ABR20, causal, clipped [0.5, 3.0] pts;
K fixed BEFORE any outcome table — see handoff S75K). An effect that only
exists at one band width is not real.

Outputs:
  * comparison tables inline (episode counts, held rates, H2/H5 by config,
    DAY-CLUSTERED H2 — per-day held-rate diff, not pooled-n fake precision)
  * per-day audit charts for the two NEW widths (abr0.35, t8) ->
    scratchpad/touch_audit_<tag>.png  (mandatory before trusting any table)

  .venv/Scripts/python.exe scripts/touch_band_sweep.py
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import orderflow_at_levels as ol

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "scratchpad"

CONFIGS = [("t2", dict(band_ticks=2)), ("t4", dict(band_ticks=4)),
           ("t8", dict(band_ticks=8)), ("abr0.35", dict(band_abr=0.35))]
AUDIT_TAGS = ("t8", "abr0.35")  # new widths -> chart-audit before trusting


def day_clustered_h2(t):
    """Per-day held-rate difference (hvn_at_level True - False)."""
    rows = []
    for day, g in t.groupby("day"):
        a, b = g[g.hvn_at_level], g[~g.hvn_at_level]
        rows.append(dict(day=day, n_hvn=len(a), n_not=len(b),
                         held_hvn=a.held.mean() if len(a) else float("nan"),
                         held_not=b.held.mean() if len(b) else float("nan")))
    d = pd.DataFrame(rows)
    d["diff"] = d.held_hvn - d.held_not
    return d


def audit_chart(t, tag, band_kw):
    """4-panel per-day chart: price, MQ levels ± band ribbon, episode marks."""
    bars = ol.load_bars()
    bars, _ = ol.assign_band(bars, **{"band_ticks": None, **band_kw})
    days = sorted(t.day.unique())
    fig, axes = plt.subplots(len(days), 1, figsize=(16, 4 * len(days)), sharex=False)
    for ax, day in zip(axes, days):
        bd = bars[bars.day == day]
        x = range(len(bd))
        ax.plot(x, bd.Close.values, lw=0.7, color="#444", zorder=1)
        ax.fill_between(x, bd.Low.values, bd.High.values, color="#999", alpha=.25, lw=0)
        td = t[t.day == day]
        for lvl in td.level.unique():
            ax.axhline(lvl, color="#2a78d6", lw=0.6, alpha=.6)
            band = bd.band.values
            ax.fill_between(x, lvl - band, lvl + band, color="#2a78d6", alpha=.10, lw=0)
        idx_of = {bi: i for i, bi in enumerate(bd.BarIdx.values)}
        for _, r in td.iterrows():
            bi = bd[bd.BarTime == r.bar_time]
            if bi.empty:
                continue
            i = idx_of[bi.BarIdx.iloc[0]]
            ax.scatter([i], [r.level], marker="^" if r.held else "v", s=48, zorder=3,
                       color="#1f8a4c" if r.held else "#cf3f3f", edgecolors="k", lw=.4)
        n = len(td)
        ax.set_title(f"{day} — {tag}: {n} episodes, {td.held.sum()} held "
                     f"(▲ held / ▼ failed; ribbon = touch band)", fontsize=10)
        step = max(1, len(bd) // 10)
        ax.set_xticks(list(x)[::step])
        ax.set_xticklabels(bd.BarTime.str[11:16].values[::step], fontsize=8)
    fig.tight_layout()
    out = SCRATCH / f"touch_audit_{tag}.png"
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out


def main():
    results = {}
    for tag, kw in CONFIGS:
        results[tag] = ol.run(quiet=True, **kw)
        print(f"ran {tag}: {len(results[tag])} episodes")

    print("\n===== BAND SENSITIVITY — overall =====")
    rows = []
    for tag, t in results.items():
        rows.append(dict(band=tag, episodes=len(t), held=int(t.held.sum()),
                         held_rate=round(t.held.mean(), 3),
                         ret15_mean=round(t.ret_15m.mean(), 2)))
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n===== H2 (HVN at level) by band =====")
    rows = []
    for tag, t in results.items():
        a, b = t[t.hvn_at_level], t[~t.hvn_at_level]
        dc = day_clustered_h2(t)
        rows.append(dict(
            band=tag, n_hvn=len(a), held_hvn=round(a.held.mean(), 3) if len(a) else None,
            n_not=len(b), held_not=round(b.held.mean(), 3),
            pooled_diff=round(a.held.mean() - b.held.mean(), 3) if len(a) else None,
            day_diffs="  ".join(f"{d:+.2f}" if pd.notna(d) else "n/a" for d in dc["diff"]),
            days_pos=int((dc["diff"] > 0).sum()),
            days_with_both=int(dc["diff"].notna().sum())))
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n===== H5 (absorbing approach) by band =====")
    rows = []
    for tag, t in results.items():
        a, b = t[t.absorbing], t[~t.absorbing]
        rows.append(dict(band=tag, n_abs=len(a),
                         held_abs=round(a.held.mean(), 3) if len(a) else None,
                         n_not=len(b), held_not=round(b.held.mean(), 3)))
    print(pd.DataFrame(rows).to_string(index=False))

    print("\n===== audit charts (REQUIRED look before trusting the above) =====")
    for tag, kw in CONFIGS:
        if tag in AUDIT_TAGS:
            out = audit_chart(results[tag], tag, kw)
            print(f"  {out}")


if __name__ == "__main__":
    main()
