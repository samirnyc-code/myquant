"""
Layer A — Sim-engine invariant validator (offline, CLI).

Runs simulate_trades() on real signals + the continuous tick cache, then checks
properties that MUST hold regardless of how the engine is implemented. This is a
correctness net, not a regression test against the engine's own past output.

Focus areas (Session-14 risk): entry = first tick after the signal, and the new
PB scale-in path in the tick engine.

Usage:
    .venv\\Scripts\\python scripts\\validate_engine.py
    .venv\\Scripts\\python scripts\\validate_engine.py --mode multileg --start 2021-06-18 --end 2022-06-18
    .venv\\Scripts\\python scripts\\validate_engine.py --mode single
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from simulation_engine import simulate_trades, TICK_SIZE  # noqa: E402

TS = TICK_SIZE
SIGNALS_PARQUET = ROOT / "saved_signals" / "ba_signals_mc.parquet"
TICKS_DIR = ROOT / "data" / "ticks_continuous"

# Default execution params (mirror the Bar Analysis ES multileg defaults).
DEFAULTS = dict(
    tick_value=12.50, commission=3.0,
    entry_slip=1.0, exit_slip=1.0, stop_offset=0,
    contracts_t1=1, contracts_t2=1,
    t1_r=1.5, target_r=1.0, ml_pb_r=-0.50,
)


# ── helpers ───────────────────────────────────────────────────────────────────
def _load_ticks(d) -> pd.DataFrame:
    p = TICKS_DIR / f"{pd.Timestamp(d).date().isoformat()}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    return pd.DataFrame(columns=["DateTime", "Price", "Volume"])


def _round_tick(x: float) -> float:
    return round(round(x / TS) * TS, 10)


class Check:
    """One invariant: accumulate pass/fail and a few example failures."""
    def __init__(self, name: str, max_examples: int = 5):
        self.name = name
        self.npass = 0
        self.nfail = 0
        self.nskip = 0
        self.examples: list[str] = []
        self.max_examples = max_examples

    def ok(self):
        self.npass += 1

    def skip(self):
        self.nskip += 1

    def fail(self, signal_num, detail: str):
        self.nfail += 1
        if len(self.examples) < self.max_examples:
            self.examples.append(f"    #{signal_num}: {detail}")

    def assert_close(self, signal_num, actual, expected, label, tol=1e-6):
        if actual is None or (isinstance(actual, float) and np.isnan(actual)):
            self.skip(); return
        if abs(float(actual) - float(expected)) <= tol:
            self.ok()
        else:
            self.fail(signal_num, f"{label}: got {actual:.6f} expected {expected:.6f} (d{float(actual)-float(expected):+.6f})")

    def assert_true(self, signal_num, cond, detail):
        if cond:
            self.ok()
        else:
            self.fail(signal_num, detail)


# ── main validation ─────────────────────────────────────────────────────────--
def validate(results: pd.DataFrame, ticks_by_date: dict, cfg: dict, max_examples: int, is_ml: bool) -> dict:
    ts = TS
    es, xs = cfg["entry_slip"], cfg["exit_slip"]
    so = cfg["stop_offset"]
    tv1 = cfg["tick_value"] * cfg["contracts_t1"]
    tv2 = cfg["tick_value"] * cfg["contracts_t2"]
    comm = cfg["commission"]
    tv_single = cfg["tick_value"] * cfg["contracts_t1"]

    checks = {k: Check(k, max_examples) for k in [
        "entry_is_first_tick_time",
        "entry_fillprice_is_first_tick",
        "entry_price_slip",
        "stop_value",
        "risk_pts",
        "risk_dollar",
        "exit_price_vs_reason",
        "exit_eod_is_last_tick",
        "pb_e2_at_pb_level",
        "pb_blended_entry",
        "pb_e2_time_order",
        "time_ordering",
        "bar_ordering",
        "leg1_pnl_recon",
        "leg2_pnl_recon",
        "gross_pnl_recon",
        "net_pnl_recon",
        "stop_reachable_in_ticks",
        "target_reachable_in_ticks",
    ]}

    filled = results[results["Filled"] == True] if "Filled" in results.columns else results.iloc[0:0]

    for _, r in filled.iterrows():
        sn = r.get("SignalNum", "?")
        is_long = r["Direction"] == "Long"
        sgn = 1.0 if is_long else -1.0
        day_ticks = ticks_by_date.get(r["Date"])
        if day_ticks is None or day_ticks.empty:
            continue

        sig_dt = pd.Timestamp(r["DateTime"])
        after = day_ticks[day_ticks["DateTime"] > sig_dt]
        if after.empty:
            continue
        first_tick = after.iloc[0]
        first_px = float(first_tick["Price"])
        last_px = float(after.iloc[-1]["Price"])
        prices_after = after["Price"].values
        ticks_post_entry = prices_after[1:]  # after the entry tick itself

        # ── ENTRY (Session-14 entry-logic change) ──────────────────────────────
        checks["entry_is_first_tick_time"].assert_true(
            sn, pd.Timestamp(r["EntryTime"]) == pd.Timestamp(first_tick["DateTime"]),
            f"EntryTime {r['EntryTime']} != first tick after sig {first_tick['DateTime']}")
        checks["entry_fillprice_is_first_tick"].assert_close(sn, r.get("FillPrice"), first_px, "FillPrice")
        checks["entry_price_slip"].assert_close(sn, r["EntryPrice"], first_px + sgn * es * ts, "EntryPrice")

        # ── STOP / RISK ────────────────────────────────────────────────────────
        exp_stop = float(r["StopPrice"]) - sgn * so * ts
        checks["stop_value"].assert_close(sn, r["ActualStop"], exp_stop, "ActualStop")
        checks["risk_pts"].assert_close(sn, r["RiskPts"], abs(r["EntryPrice"] - r["ActualStop"]), "RiskPts")
        checks["risk_dollar"].assert_close(sn, r["RiskDollar"], r["RiskPts"] / ts * tv1, "RiskDollar")

        # ── EXIT PRICE vs REASON (internal-consistency arithmetic) ─────────────
        reason = str(r["ExitReason"])
        exit_px = float(r["ExitPrice"])
        level_map = {
            "Stop": r["ActualStop"],
            "Target": r.get("Target"),          # single-leg
            "T1_only": r.get("Target1"),        # multileg
            "E1E2+Target": r.get("Target"),     # multileg
        }
        level_map = {k: v for k, v in level_map.items() if v is not None and not (isinstance(v, float) and np.isnan(v))}
        if reason in level_map:
            checks["exit_price_vs_reason"].assert_close(
                sn, exit_px, float(level_map[reason]) - sgn * xs * ts, f"Exit({reason})")
        elif reason in ("EOD", "E1E2+EOD"):
            checks["exit_eod_is_last_tick"].assert_close(
                sn, exit_px, last_px - sgn * xs * ts, f"Exit({reason})=last tick")
        else:
            checks["exit_price_vs_reason"].skip()

        # ── PB SCALE-IN (Session-14 addition) ──────────────────────────────────
        e2_px = r.get("E2FillPrice")
        e2_filled = e2_px is not None and not (isinstance(e2_px, float) and np.isnan(e2_px))
        if e2_filled:
            pb_lvl = float(r["PBLevel"])
            exp_e2 = _round_tick(pb_lvl + sgn * es * ts)
            checks["pb_e2_at_pb_level"].assert_close(sn, float(e2_px), exp_e2, "E2FillPrice", tol=ts / 2 + 1e-6)
            blended = (r["EntryPrice"] * tv1 + float(e2_px) * tv2) / (tv1 + tv2)
            # BlendedEntry output column is round(_, 2) for display -> max 0.005 deviation.
            checks["pb_blended_entry"].assert_close(sn, r.get("BlendedEntry"), blended, "BlendedEntry", tol=0.005 + 1e-6)
            e2t = r.get("E2FillTime")
            checks["pb_e2_time_order"].assert_true(
                sn, e2t is not None and pd.notna(e2t) and pd.Timestamp(e2t) >= pd.Timestamp(r["EntryTime"]),
                f"E2FillTime {e2t} < EntryTime {r['EntryTime']}")
        else:
            checks["pb_e2_at_pb_level"].skip()
            checks["pb_blended_entry"].skip()
            checks["pb_e2_time_order"].skip()

        # ── ORDERING / SANITY ──────────────────────────────────────────────────
        checks["time_ordering"].assert_true(
            sn,
            sig_dt < pd.Timestamp(r["EntryTime"]) <= pd.Timestamp(r["ExitTime"]),
            f"order sig<{r['EntryTime']}<= {r['ExitTime']} violated")
        checks["bar_ordering"].assert_true(
            sn, r["ExitBarNum"] >= r["EntryBarNum"],
            f"ExitBar {r['ExitBarNum']} < EntryBar {r['EntryBarNum']}")

        # ── PnL RECONSTRUCTION (internal) ──────────────────────────────────────
        if is_ml:
            checks["leg1_pnl_recon"].assert_close(sn, r["Leg1GrossPnL"], r["Leg1GrossPts"] / ts * tv1, "Leg1GrossPnL")
            l2_traded = str(r.get("Leg2ExitReason", "NoFill")) != "NoFill" and pd.notna(r.get("Leg2ExitReason"))
            if l2_traded:
                checks["leg2_pnl_recon"].assert_close(sn, r["Leg2GrossPnL"], r["Leg2GrossPts"] / ts * tv2, "Leg2GrossPnL")
            else:
                checks["leg2_pnl_recon"].skip()
            checks["gross_pnl_recon"].assert_close(
                sn, r["GrossPnL"], r["Leg1GrossPnL"] + (r["Leg2GrossPnL"] if l2_traded else 0.0), "GrossPnL")
            active_c = (cfg["contracts_t1"] + cfg["contracts_t2"]) if l2_traded else cfg["contracts_t1"]
        else:
            checks["leg1_pnl_recon"].skip()
            checks["leg2_pnl_recon"].skip()
            checks["gross_pnl_recon"].assert_close(sn, r["GrossPnL"], r["GrossPnLPts"] / ts * tv_single, "GrossPnL")
            active_c = cfg["contracts_t1"]
        checks["net_pnl_recon"].assert_close(sn, r["NetPnL"], r["GrossPnL"] - comm * active_c, "NetPnL")

        # ── MARKET-TRUTH REACHABILITY (phantom-exit guard) ─────────────────────
        if reason == "Stop":
            reach = np.any(ticks_post_entry <= r["ActualStop"]) if is_long else np.any(ticks_post_entry >= r["ActualStop"])
            checks["stop_reachable_in_ticks"].assert_true(sn, reach, "Stop exit but no tick reaches stop")
        else:
            checks["stop_reachable_in_ticks"].skip()
        if reason in ("T1_only", "E1E2+Target", "Target"):
            lvl = float(r["Target1"]) if reason == "T1_only" else float(r["Target"])
            reach = np.any(ticks_post_entry > lvl) if is_long else np.any(ticks_post_entry < lvl)
            checks["target_reachable_in_ticks"].assert_true(sn, reach, f"{reason} but no tick reaches target")
        else:
            checks["target_reachable_in_ticks"].skip()

    return checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["multileg", "single"], default="multileg")
    ap.add_argument("--start", default=None, help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--limit", type=int, default=0, help="cap number of signals (0 = all)")
    ap.add_argument("--max-examples", type=int, default=5)
    args = ap.parse_args()

    if not SIGNALS_PARQUET.exists():
        sys.exit(f"No signals parquet at {SIGNALS_PARQUET}")

    sigs = pd.read_parquet(SIGNALS_PARQUET)
    sigs["DateTime"] = pd.to_datetime(sigs["DateTime"])
    if "Date" not in sigs.columns:
        sigs["Date"] = sigs["DateTime"].dt.date

    if args.start:
        sigs = sigs[sigs["DateTime"] >= pd.Timestamp(args.start)]
    if args.end:
        sigs = sigs[sigs["DateTime"] <= pd.Timestamp(args.end) + pd.Timedelta(days=1)]

    # Keep only signals whose date actually has a tick file (others -> no_tick_data).
    sig_dates = sorted(sigs["Date"].unique())
    ticks_by_date = {}
    for d in sig_dates:
        t = _load_ticks(d)
        if not t.empty:
            ticks_by_date[d] = t
    sigs = sigs[sigs["Date"].isin(ticks_by_date.keys())].copy()
    if args.limit:
        sigs = sigs.head(args.limit).copy()

    cfg = dict(DEFAULTS)
    print(f"Mode: {args.mode}  |  signals with ticks: {len(sigs)}  |  tick-days: {len(ticks_by_date)}")
    print(f"Params: {cfg}\n")

    common = dict(
        entry_slip=cfg["entry_slip"], exit_slip=cfg["exit_slip"], stop_offset=cfg["stop_offset"],
        tick_value=cfg["tick_value"], commission=cfg["commission"],
    )
    if args.mode == "multileg":
        results = simulate_trades(
            sigs, ticks_by_date, cfg["target_r"], **common,
            contracts=cfg["contracts_t1"] + cfg["contracts_t2"],
            multileg=True, t1_r=cfg["t1_r"], t1_action="exit",
            contracts_t1=cfg["contracts_t1"], contracts_t2=cfg["contracts_t2"],
            ml_pb_r=cfg["ml_pb_r"],
        )
    else:
        results = simulate_trades(
            sigs, ticks_by_date, cfg["target_r"], **common, contracts=cfg["contracts_t1"],
        )

    n_filled = int((results["Filled"] == True).sum()) if "Filled" in results.columns else 0
    print(f"Trades: {len(results)} rows  |  filled: {n_filled}")
    if "ExitReason" in results.columns:
        vc = results[results["Filled"] == True]["ExitReason"].value_counts()
        print("Exit reasons:", dict(vc))
    print()

    checks = validate(results, ticks_by_date, cfg, args.max_examples, is_ml=(args.mode == "multileg"))

    print("=" * 72)
    print(f"{'CHECK':<32}{'PASS':>7}{'FAIL':>7}{'SKIP':>7}")
    print("-" * 72)
    total_fail = 0
    for c in checks.values():
        total_fail += c.nfail
        flag = "  <-- FAIL" if c.nfail else ""
        print(f"{c.name:<32}{c.npass:>7}{c.nfail:>7}{c.nskip:>7}{flag}")
    print("=" * 72)

    if total_fail:
        print(f"\n{total_fail} violations. Examples:\n")
        for c in checks.values():
            if c.nfail:
                print(f"[{c.name}]  ({c.nfail} total)")
                for ex in c.examples:
                    print(ex)
                print()
        sys.exit(1)
    else:
        print("\nAll invariants passed.")


if __name__ == "__main__":
    main()
