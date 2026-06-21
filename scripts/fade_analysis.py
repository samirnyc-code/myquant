"""Fade hypothesis analysis — can we profit from reversing losing trades?

For each losing trade in the current system (ER>=0.30, pinned 1.0R singleleg),
compute what would have happened if we entered the OPPOSITE direction at the
same entry price with symmetric target/stop.

Buckets trades by regime context (VA location, ER bucket, TOD phase, bar number)
and identifies buckets where the fade has positive expectancy.

Pure diagnostic — reads existing signals + ticks, does NOT modify anything.
"""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime
import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

import massive                                  # noqa: E402
import indicators                               # noqa: E402
import regime_filter as rf                      # noqa: E402
from simulation_engine import simulate_trades, compute_summary, RTH_END_MIN  # noqa: E402

_SIGNALS = _ROOT / "saved_signals" / "ba_signals_mc.parquet"
_BARS    = _ROOT / "data" / "bars" / "_continuous.parquet"
_OUT     = _ROOT / "docs" / "living"

BASE = dict(entry_slip=1, exit_slip=0, stop_offset=1, tick_value=12.5,
            contracts=1, contracts_t1=1, contracts_t2=1, commission=4.36,
            ratchet_r=0.0, pb_round="nearest", target_r=1.0,
            multileg=False, threeleg=False, overrides=None)
CHOP_MIN = 0.30


def log(m):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[fade] [{ts}] {m}", flush=True)


def bucket_stats(pnl):
    if len(pnl) == 0:
        return {"n": 0}
    wins = (pnl > 0).sum()
    gw = float(pnl[pnl > 0].sum())
    gl = float(abs(pnl[pnl < 0].sum()))
    return {
        "n": len(pnl),
        "net": float(pnl.sum()),
        "exp": float(pnl.mean()),
        "win_pct": float(wins / len(pnl) * 100),
        "pf": gw / gl if gl > 0 else float("nan"),
    }


def main():
    log("Loading data...")
    sig = pd.read_parquet(_SIGNALS)
    bars = pd.read_parquet(_BARS).drop(columns=["Contract"], errors="ignore")
    bars_by_date = {d: g.reset_index(drop=True)
                    for d, g in bars.groupby(bars["DateTime"].dt.date)}

    log("Tagging for ER filter + regime context...")
    tagged, _ = rf.tag_and_bucket(sig, bars)
    er = tagged["ER_intra_6"].astype(float)
    sig_filtered = sig[er.fillna(0) >= CHOP_MIN].copy()
    tagged_filtered = tagged[er.fillna(0) >= CHOP_MIN].copy()
    log(f"Signals after ER>=0.30: {len(sig_filtered)}")

    all_dates = sorted(sig_filtered["Date"].unique())
    log(f"Loading ticks for {len(all_dates)} days...")
    ticks_by_date = {}
    for d in all_dates:
        t = massive.load_continuous_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t
    log(f"Ticks loaded: {len(ticks_by_date)} days")

    # Run original direction simulation
    log("Simulating original trades (1.0R singleleg)...")
    results = simulate_trades(
        signals=sig_filtered,
        ticks_by_date=ticks_by_date,
        bars_by_date=bars_by_date,
        **BASE,
    )
    filled = results[results["Filled"] == True].copy()
    log(f"Filled trades: {len(filled)}")

    # Identify losers
    losers = filled[filled["NetPnL"] < 0].copy()
    log(f"Losing trades: {len(losers)} ({len(losers)/len(filled)*100:.1f}%)")
    log(f"Total loss from losers: ${losers['NetPnL'].sum():,.0f}")

    # Create FADED signals — flip direction
    loser_indices = losers.index
    sig_faded = sig_filtered.loc[loser_indices].copy()
    sig_faded["Direction"] = sig_faded["Direction"].map({"Long": "Short", "Short": "Long"})
    # Flip the stop: for a long->short fade, stop should be above entry
    # The simulation engine handles this via Direction, but we need to ensure
    # the stop price makes sense. The stop in the signal is the ORIGINAL stop.
    # For a fade, we use the original target as our stop and original stop as target.
    # Actually, let's keep it simple: same R, opposite direction, same entry price.
    # The engine computes stop from Direction + stop_offset, so flipping Direction
    # should give us the symmetric opposite trade.

    log("Simulating faded trades (reversed direction, same entry)...")
    results_faded = simulate_trades(
        signals=sig_faded,
        ticks_by_date=ticks_by_date,
        bars_by_date=bars_by_date,
        **BASE,
    )
    filled_faded = results_faded[results_faded["Filled"] == True].copy()
    log(f"Faded fills: {len(filled_faded)}")

    # Overall fade stats
    if len(filled_faded) > 0:
        fade_pnl = filled_faded["NetPnL"].to_numpy()
        orig_pnl = losers["NetPnL"].to_numpy()
        log(f"\nOVERALL FADE RESULTS:")
        log(f"  Original losers: {len(losers)} trades, ${orig_pnl.sum():,.0f}")
        log(f"  Faded trades:    {len(filled_faded)} fills, ${fade_pnl.sum():,.0f}")
        log(f"  Fade exp: ${fade_pnl.mean():.0f}  win%: {(fade_pnl>0).mean()*100:.1f}%")
        log(f"  Net improvement: ${fade_pnl.sum() - orig_pnl.sum():,.0f}")

    # Tag losers with regime context for bucketing
    sig_dt = pd.to_datetime(losers["DateTime"])
    losers = losers.copy()
    losers["sig_min_of_day"] = sig_dt.dt.hour * 60 + sig_dt.dt.minute

    # Session phase
    def phase_label(m):
        if m < 10*60: return "Open"
        elif m < 11*60+30: return "Mid"
        elif m < 13*60: return "Lunch"
        elif m < 14*60+15: return "Afternoon"
        else: return "Close"

    losers["phase"] = losers["sig_min_of_day"].apply(phase_label)

    # ER bucket on the loser
    loser_tagged = tagged_filtered.loc[loser_indices].copy()
    losers["er_bucket"] = pd.cut(loser_tagged["ER_intra_6"].astype(float),
                                  bins=[0, 0.35, 0.45, 0.55, 0.70, 1.0],
                                  labels=["0.30-0.35", "0.35-0.45", "0.45-0.55", "0.55-0.70", "0.70+"])

    # VA location if available
    if "session_loc" in loser_tagged.columns:
        losers["va_loc"] = loser_tagged["session_loc"].values
    else:
        losers["va_loc"] = "unknown"

    # Direction
    losers["orig_dir"] = losers["Direction"]

    # MFE analysis — how far did the trade go in the right direction before losing?
    if "MFE" in losers.columns:
        losers["mfe_bucket"] = pd.cut(losers["MFE"].fillna(0),
                                       bins=[-np.inf, 25, 50, 100, 200, np.inf],
                                       labels=["<$25", "$25-50", "$50-100", "$100-200", "$200+"])

    # Align faded results with losers for bucketed comparison
    filled_faded_aligned = filled_faded.reindex(losers.index)

    # Bucket analyses
    analyses = [
        ("By session phase", "phase"),
        ("By ER bucket", "er_bucket"),
        ("By VA location", "va_loc"),
        ("By original direction", "orig_dir"),
    ]
    if "mfe_bucket" in losers.columns:
        analyses.append(("By MFE bucket", "mfe_bucket"))

    all_tables = {}
    for title, col in analyses:
        rows = []
        for bucket_val in losers[col].dropna().unique():
            mask = losers[col] == bucket_val
            idx = losers[mask].index

            orig_pnl = losers.loc[idx, "NetPnL"].to_numpy()
            orig_stats = bucket_stats(orig_pnl)

            fade_in_bucket = filled_faded_aligned.loc[idx].dropna(subset=["NetPnL"])
            fade_pnl = fade_in_bucket["NetPnL"].to_numpy() if len(fade_in_bucket) else np.array([])
            fade_stats = bucket_stats(fade_pnl)

            rows.append({
                "bucket": str(bucket_val),
                "orig_n": orig_stats["n"],
                "orig_net": orig_stats.get("net", 0),
                "orig_exp": orig_stats.get("exp", 0),
                "fade_n": fade_stats["n"],
                "fade_net": fade_stats.get("net", 0),
                "fade_exp": fade_stats.get("exp", 0),
                "fade_win%": fade_stats.get("win_pct", 0),
                "fade_pf": fade_stats.get("pf", float("nan")),
                "net_improvement": fade_stats.get("net", 0) - abs(orig_stats.get("net", 0)),
            })
        df = pd.DataFrame(rows).sort_values("fade_exp", ascending=False)
        all_tables[title] = df

        print(f"\n{'='*70}")
        print(title)
        print("="*70)
        print(df.to_string(index=False, float_format=lambda x: f"{x:,.1f}"))

    # Find the best fade candidates
    print("\n" + "=" * 70)
    print("BEST FADE CANDIDATES (fade_exp > 0 AND n >= 30)")
    print("=" * 70)
    for title, df in all_tables.items():
        good = df[(df["fade_exp"] > 0) & (df["fade_n"] >= 30)]
        if len(good):
            print(f"\n{title}:")
            print(good.to_string(index=False, float_format=lambda x: f"{x:,.1f}"))

    # Save report
    out_file = _OUT / "fade_analysis.md"
    with open(out_file, "w") as f:
        f.write("# Fade Hypothesis Analysis\n\n")
        f.write(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**Baseline:** ER>=0.30, pinned 1.0R singleleg\n")
        f.write(f"**Method:** For each losing trade, simulate the opposite direction ")
        f.write(f"at the same entry with symmetric 1.0R target/stop.\n\n")

        if len(filled_faded) > 0:
            fade_pnl = filled_faded["NetPnL"].to_numpy()
            orig_pnl_all = losers["NetPnL"].to_numpy()
            f.write("## Overall\n\n")
            f.write(f"| Metric | Original losers | Faded |\n")
            f.write(f"|--------|----------------|-------|\n")
            f.write(f"| Trades | {len(losers)} | {len(filled_faded)} |\n")
            f.write(f"| Net PnL | ${orig_pnl_all.sum():,.0f} | ${fade_pnl.sum():,.0f} |\n")
            f.write(f"| Expectancy | ${orig_pnl_all.mean():.0f} | ${fade_pnl.mean():.0f} |\n")
            f.write(f"| Win% | {(orig_pnl_all>0).mean()*100:.1f}% | {(fade_pnl>0).mean()*100:.1f}% |\n")
            f.write(f"\n**Net improvement if all losers were faded: ${fade_pnl.sum() - orig_pnl_all.sum():,.0f}**\n\n")

        for title, df in all_tables.items():
            f.write(f"\n## {title}\n\n")
            f.write(df.to_markdown(index=False, floatfmt=".1f"))
            f.write("\n")

        f.write("\n## Interpretation\n\n")
        f.write("Buckets where `fade_exp > 0` AND `fade_n >= 30` are genuine fade candidates.\n")
        f.write("These represent market contexts where the breakout signal reliably fails ")
        f.write("and the opposite direction has a real edge.\n\n")
        f.write("**Action levels per bucket:**\n")
        f.write("- `fade_exp > 0, PF > 1.2, n >= 50`: Strong fade candidate\n")
        f.write("- `fade_exp > 0, PF > 1.0, n >= 30`: Weak candidate, needs more data\n")
        f.write("- `fade_exp < 0`: Not a fade — just random; skip/filter instead\n")

    log(f"Report saved: {out_file}")


if __name__ == "__main__":
    main()
