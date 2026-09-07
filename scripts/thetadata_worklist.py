"""thetadata_worklist.py — build the exact ThetaData pull list to validate our
Aug–Sep-2026 options-sim fills against real OPRA NBBO.  READ-ONLY.

WHY: the fill-realism audit (scripts/fill_vs_nbbo_audit.py) showed sim fills sit at
the marketable cross (median pos 0.000, 79% <= mid) but had ~21% quote-snapshot
timing noise.  ThetaData (historical NBBO w/ bid_size/ask_size + trade prints) lets
us ground-truth every leg's fill against the real book at fill time.  This script
enumerates WHICH contracts to pull.

SCOPE: SPX only (root SPXW). XSP is a retired side-book — excluded (user, S112).

SOURCES (authoritative leg enumeration — every SPX trade, incl. cash-settled):
  * data/options_log/trades.parquet      — SPX book (root SPXW), `legs` JSON per trade
  * data/options_log/orders.csv          — per-LEG IB fills (ts_et=ET, avg_fill); SPXW only
                                           -> enriches SPX legs with ET-second fill anchors

VERIFIED FACTS (baked into the report, re-checked each run):
  * 100% 0DTE: every leg's `expiry` == its trade's entry date -> date==expiry for the pull.
  * TZ: trades.parquet entry_dt/exit_dt = CT (daemon now_ct, America/Chicago, MINUTE prec);
        orders.csv ts_et = ET (America/New_York, SECOND prec); xsp_fills.csv ts = CT.
        ThetaData ms_of_day is ET, so per-tick ALIGNMENT (a later comparison script) must
        convert CT->ET (+1h std).  The PULL here is by calendar DATE — identical in CT/ET
        for daytime fills — so the work-list is tz-safe.  orders.csv (ET, seconds) is the
        preferred alignment anchor.
  * Strike encoding: v3 wants DOLLARS (e.g. 6450.000); v2 wants 1/10-cent int (6450*1000).
        (Handoff example digit-count for v2 to be re-confirmed at smoke-test; v3 is primary.)
  * ROOT MAPPING IS UNCONFIRMED until the terminal smoke-test: our OPRA roots are SPXW / XSP.
        ThetaData may serve SPX weeklys under 'SPXW' or under 'SPX'.  The fetcher's --probe
        resolves this empirically.  We emit theta_root = OPRA root (SPXW/XSP) as the primary
        guess and carry the alternative.

OUTPUT (DATED, per S80):
  data/options_sim/thetadata_worklist_legs_<YYYYMMDD>.csv  — one row per (trade, leg, side)
  data/options_sim/thetadata_pull_list_<YYYYMMDD>.csv      — deduped contracts to fetch
        (this is the fetcher's input; scripts/thetadata_fetch.py reads the newest one)

Run:
  .venv/Scripts/python.exe scripts/thetadata_worklist.py
  .venv/Scripts/python.exe scripts/thetadata_worklist.py --start 2026-08-01 --end 2026-08-31
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OL = ROOT / "data" / "options_log"
OUT = ROOT / "data" / "options_sim"

# OPRA root (from trades `symbol`) -> primary ThetaData root guess + alternative.
# UNCONFIRMED: resolved empirically by `thetadata_fetch.py --probe`.
THETA_ROOT = {"SPXW": ("SPXW", "SPX")}


def _legs(val):
    """trades.parquet `legs` is a JSON string (or already a list). -> list[dict]."""
    if isinstance(val, list):
        return val
    if isinstance(val, str) and val.strip():
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return []
    return []


def _parse_local_symbol(sym: str):
    """'SPXW  260715C07605000' -> (root, expiry YYYYMMDD, right C/P, strike float)."""
    if not isinstance(sym, str):
        return None
    m = re.match(r"^([A-Z]+)\s+(\d{6})([CP])(\d{8})$", sym.strip())
    if not m:
        return None
    root, yymmdd, right, strike8 = m.groups()
    expiry = "20" + yymmdd                       # 260715 -> 20260715
    strike = int(strike8) / 1000.0               # OCC: dollars x 1000
    return root, expiry, right, strike


def load_legs(start: str | None, end: str | None) -> pd.DataFrame:
    """Explode the SPX book into one row per (trade, leg)."""
    frames = []
    p = OL / "trades.parquet"
    if not p.exists():
        print(f"  !! missing {p.relative_to(ROOT)}")
        return pd.DataFrame()
    df = pd.read_parquet(p)
    for _, r in df.iterrows():
        entry_date = str(r["entry_dt"])[:10]                # CT, YYYY-MM-DD
        if start and entry_date < start:
            continue
        if end and entry_date > end:
            continue
        for i, lg in enumerate(_legs(r["legs"])):
            frames.append({
                "book": "SPX",
                "trade_id": r["trade_id"],
                "strategy": r.get("strategy_id"),
                "source": r.get("source"),
                "structure": r.get("structure"),
                "occ_root": r["symbol"],                     # SPXW
                "leg_idx": i,
                "side": lg.get("side"),                      # buy / sell
                "right": (lg.get("right") or "").upper(),    # C / P
                "strike": float(lg.get("strike")),
                "expiry": str(lg.get("expiry")),             # YYYYMMDD (== trade date, 0DTE)
                "qty": lg.get("qty"),
                "entry_dt_ct": r["entry_dt"],                # CT minute
                "exit_dt_ct": r.get("exit_dt"),              # CT minute
                "fill_model": r.get("fill_model"),
                "close_reason": r.get("close_reason"),
                "credit": r.get("credit"),
                "exit_cost": r.get("exit_cost"),
            })
    return pd.DataFrame(frames)


def load_order_fills(start: str | None, end: str | None) -> pd.DataFrame:
    """orders.csv filled legs -> ET-second fill anchors keyed by contract."""
    p = OL / "orders.csv"
    if not p.exists():
        return pd.DataFrame()
    od = pd.read_csv(p)
    od = od[od["status"] == "Filled"].copy()
    rows = []
    for _, r in od.iterrows():
        parsed = _parse_local_symbol(r["localSymbol"])
        if not parsed:
            continue
        root, expiry, right, strike = parsed
        date = f"{expiry[:4]}-{expiry[4:6]}-{expiry[6:]}"
        if start and date < start:
            continue
        if end and date > end:
            continue
        rows.append({
            "occ_root": root, "expiry": expiry, "right": right, "strike": strike,
            "ts_et": r["ts_et"], "action": r["action"], "avg_fill": r["avg_fill"],
            "order_id": r.get("order_id"),
        })
    return pd.DataFrame(rows)


def build_pull_list(legs: pd.DataFrame, fills: pd.DataFrame) -> pd.DataFrame:
    """Dedupe legs to unique (occ_root, expiry, strike, right) contracts to fetch."""
    key = ["occ_root", "expiry", "strike", "right"]
    g = legs.groupby(key, dropna=False)
    out = []
    for (occ_root, expiry, strike, right), grp in g:
        # ET fill anchors for this contract (SPX only; XSP has none in orders.csv)
        if not fills.empty:
            fm = fills[(fills.occ_root == occ_root) & (fills.expiry == expiry)
                       & (fills.right == right) & (abs(fills.strike - strike) < 1e-6)]
        else:
            fm = fills
        theta_primary, theta_alt = THETA_ROOT.get(occ_root, (occ_root, occ_root))
        ts_list = sorted(fm.ts_et.tolist()) if not fm.empty else []
        out.append({
            "occ_root": occ_root,
            "theta_root": theta_primary,
            "theta_root_alt": theta_alt,
            "expiry": expiry,                                # YYYYMMDD
            "date": expiry,                                  # 0DTE: pull date == expiry
            "right": right,                                  # C / P
            "right_v3": "call" if right == "C" else "put",
            "strike": strike,
            "strike_v3": f"{strike:.3f}",                    # dollars, 3dp  (v3)
            "strike_v2": int(round(strike * 1000)),          # 1/10-cent int (v2) — confirm @smoke
            "n_trades": grp.trade_id.nunique(),
            "n_legs": len(grp),
            "n_order_fills": len(fm),
            "first_fill_ts_et": ts_list[0] if ts_list else "",
            "last_fill_ts_et": ts_list[-1] if ts_list else "",
        })
    d = pd.DataFrame(out).sort_values(["date", "occ_root", "strike", "right"])
    return d.reset_index(drop=True)


def verify_and_report(legs: pd.DataFrame, pull: pd.DataFrame, fills: pd.DataFrame):
    print("\n================= ThetaData work-list — VERIFICATION =================")
    # 0DTE check: expiry == entry date (CT) for every leg
    legs = legs.copy()
    legs["entry_date"] = legs["entry_dt_ct"].astype(str).str[:10].str.replace("-", "", regex=False)
    mism = (legs["expiry"] != legs["entry_date"]).sum()
    print(f"  0DTE check (expiry == entry date) .... {'PASS' if mism == 0 else f'FAIL ({mism} mismatches)'}")
    print(f"  legs total ........................... {len(legs)}")
    print(f"  trades ............................... {legs.trade_id.nunique()}")
    print(f"  book split ........................... " + ", ".join(
        f"{b}:{n}" for b, n in legs.book.value_counts().items()))
    print(f"  OPRA roots ........................... " + ", ".join(
        f"{r}:{n}" for r, n in legs.occ_root.value_counts().items()))
    dmin, dmax = legs.entry_date.min(), legs.entry_date.max()
    print(f"  date span (CT entry) ................. {dmin} -> {dmax}")
    print(f"  unique contracts to PULL (SPXW) ...... {len(pull)}")
    print(f"  unique pull DATES .................... {pull.date.nunique()}")
    print(f"  orders.csv filled-leg anchors (ET) ... {len(fills)} "
          f"(matched to {(pull.n_order_fills > 0).sum()} contracts)")
    print(f"  strategies ........................... " + ", ".join(sorted(legs.strategy.dropna().unique())))
    print("\n  encoding samples (first 3 contracts):")
    for _, r in pull.head(3).iterrows():
        print(f"    {r.occ_root} {r.expiry} {r.strike:>8.3f} {r.right}  ->  "
              f"v3 symbol={r.theta_root} strike={r.strike_v3} right={r.right_v3}  |  "
              f"v2 strike={r.strike_v2} right={r.right}")
    print("\n  ROOT MAPPING IS A GUESS (theta_root=SPXW, alt=SPX) — confirm with "
          "`thetadata_fetch.py --probe` once the terminal is up.")
    print("  TZ: trades=CT(min), orders=ET(sec), ThetaData=ET ms_of_day. Align via orders.csv (ET).")
    print("======================================================================\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the ThetaData fill-validation work-list")
    ap.add_argument("--start", help="min trade date YYYY-MM-DD (CT entry), inclusive")
    ap.add_argument("--end", help="max trade date YYYY-MM-DD (CT entry), inclusive")
    args = ap.parse_args()

    legs = load_legs(args.start, args.end)
    if legs.empty:
        print("No legs found for the given range — nothing to do.")
        return 1
    fills = load_order_fills(args.start, args.end)
    pull = build_pull_list(legs, fills)

    verify_and_report(legs, pull, fills)

    stamp = dt.datetime.now().strftime("%Y%m%d")
    legs_path = OUT / f"thetadata_worklist_legs_{stamp}.csv"
    pull_path = OUT / f"thetadata_pull_list_{stamp}.csv"
    legs.drop(columns=["entry_date"], errors="ignore").to_csv(legs_path, index=False)
    pull.to_csv(pull_path, index=False)
    print(f"saved -> {legs_path.relative_to(ROOT)}  ({len(legs)} legs)")
    print(f"saved -> {pull_path.relative_to(ROOT)}  ({len(pull)} contracts)")
    print("\nnext: .venv/Scripts/python.exe scripts/thetadata_fetch.py --dry-run   (verify URLs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
