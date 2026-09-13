"""tick_pipeline.py — headless NT .ncd -> continuous trove pipeline (S104).

Asks TickExportAddOn (running inside NT8) to export the missing days' ticks from NT's
OWN .ncd via BarsRequest, then folds them into data/ticks_continuous/ with the verified
ingest (contract/offset/roll/tz + seam checks). NT decodes its own binary; we never
parse .ncd by hand.

  python scripts/tick_pipeline.py                     # nightly: last-trove-day+1 .. yesterday
  python scripts/tick_pipeline.py --from 2026-08-04 --to 2026-08-17    # explicit backfill
  python scripts/tick_pipeline.py --from 2026-07-31 --to 2026-07-31 --dry-run  # validate vs a trove day

Requires NT8 running with TickExportAddOn loaded (F5 once). Times out with a clear
message if the AddOn never answers.
"""
from __future__ import annotations
import argparse
import datetime as dt
import glob
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NT_TICKS = ROOT / "data" / "nt_ticks"
TROVE = ROOT / "data" / "ticks_continuous"
REQ = NT_TICKS / "_request.json"
DONE = NT_TICKS / "_request.done.json"
CONTRACT = "ES 09-26"   # current front-month anchor; the ingest roll-guard aborts wrong-contract days


ETH_TROVE = ROOT / "data" / "ticks_continuous_eth"
ETH_HOURS = "CME US Index Futures ETH"


def last_trove_day():
    days = sorted(p.stem for p in TROVE.glob("*.parquet"))
    return dt.date.fromisoformat(days[-1]) if days else None


def last_eth_day():
    days = sorted(p.stem for p in ETH_TROVE.glob("*.parquet") if not p.stem.startswith("_"))
    return dt.date.fromisoformat(days[-1]) if days else None


def eth_pass(contract, frm, to, timeout):
    """Nightly ETH step: export [frm,to] with the ETH session template and fold into
    the ETH trove (parallel to RTH). Small incrementally (1-2 days). Refreshes the
    integrity manifest and syncs the off-dir backup after a successful write."""
    print(f"\n[ETH 1/3] requesting {contract} ETH-session ticks {frm}..{to}")
    DONE.unlink(missing_ok=True)
    before = set(glob.glob(str(NT_TICKS / "*_ticks_*.csv")))
    REQ.write_text(json.dumps({"contract": contract, "from": frm.isoformat(),
                               "to": to.isoformat(), "hours": ETH_HOURS}))
    t0 = time.time()
    while time.time() - t0 < timeout:
        if DONE.exists():
            print("      AddOn:", DONE.read_text().strip()); break
        time.sleep(10)
    else:
        REQ.unlink(missing_ok=True)
        print("! ETH: AddOn never answered"); return 2
    new = sorted(set(glob.glob(str(NT_TICKS / "*_ticks_*.csv"))) - before)
    if not new:
        print("! ETH: no CSVs produced"); return 2
    print(f"[ETH 2/3] exported {len(new)} CSV file(s); ingesting to ETH trove")
    # ingest ONLY this pass's own new CSVs (--files), never a broad glob — the RTH pass
    # leaves same-named RTH-only CSVs in this dir, and a glob would mix them in.
    rc = subprocess.run([sys.executable, str(ROOT / "scripts" / "ingest_nt_ticks_eth.py"),
                         "--files", *new, "--force", "--validate-rth"], check=False).returncode
    for f in new:                       # free disk (ETH CSVs are large)
        try: Path(f).unlink()
        except OSError: pass
    if rc == 0:
        print("[ETH 3/3] refreshing integrity manifest + backup")
        subprocess.run([sys.executable, str(ROOT / "scripts" / "eth_store_manifest.py")], check=False)
        try:
            import shutil
            bk = Path(r"C:\eth_trove_backup")
            if bk.exists():
                for p in ETH_TROVE.glob("*.parquet"):
                    if not p.stem.startswith("_"):
                        dst = bk / p.name
                        if not dst.exists() or dst.stat().st_size != p.stat().st_size:
                            shutil.copy2(p, dst)
        except Exception as e:
            print(f"  (backup sync skipped: {e})")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm", help="YYYY-MM-DD (default: last trove day + 1)")
    ap.add_argument("--to", dest="to", help="YYYY-MM-DD (default: yesterday)")
    ap.add_argument("--contract", default=CONTRACT)
    ap.add_argument("--timeout", type=int, default=2400, help="secs to wait for the AddOn (default 40min)")
    ap.add_argument("--dry-run", action="store_true", help="export + validate, do NOT write the trove")
    a = ap.parse_args()

    NT_TICKS.mkdir(parents=True, exist_ok=True)
    # CT-anchored dates (this PC runs Berlin; NT/market run CT). Default 'to' = today only
    # once the CT session is complete (>=15:30), else yesterday — so a run at any hour never
    # ingests a half-finished day into the trove.
    import pipeline_health as ph
    now = ph.chicago_now()
    today, yday = now.date(), now.date() - dt.timedelta(days=1)
    default_to = today if now.time() >= dt.time(15, 30) else yday
    frm = dt.date.fromisoformat(a.frm) if a.frm else ((last_trove_day() or yday) + dt.timedelta(days=1))
    to = dt.date.fromisoformat(a.to) if a.to else default_to
    if to < frm:
        print(f"nothing to do — trove is current through {frm - dt.timedelta(days=1)}")
        return 0

    print(f"[1/3] requesting {a.contract} ticks {frm}..{to} from NT8 (TickExportAddOn)")
    DONE.unlink(missing_ok=True)
    before = set(glob.glob(str(NT_TICKS / "*_ticks_*.csv")))
    REQ.write_text(json.dumps({"contract": a.contract, "from": frm.isoformat(), "to": to.isoformat()}))

    t0 = time.time()
    while time.time() - t0 < a.timeout:
        if DONE.exists():
            print("      AddOn:", DONE.read_text().strip())
            break
        time.sleep(10)
    else:
        REQ.unlink(missing_ok=True)
        print("! AddOn never answered — is NT8 running with TickExportAddOn loaded (F5)?")
        return 2

    new = sorted(set(glob.glob(str(NT_TICKS / "*_ticks_*.csv"))) - before)
    if not new:
        print("! AddOn produced no CSVs — no .ncd for that range, or the days were empty.")
        return 2
    print(f"[2/3] exported {len(new)} CSV file(s)")

    cmd = [sys.executable, str(ROOT / "scripts" / "ingest_nt_ticks.py"),
           "--files", *new, "--src-tz", "America/Chicago"]
    print("\n[3/3] ingest DRY-RUN (validates contract/offset/roll + seam; writes nothing):")
    subprocess.run(cmd + ["--dry-run"], check=False)
    if a.dry_run:
        print("\ndry-run only — trove NOT written. Review the seam/RTH numbers above.")
        return 0
    print("\n--- ingest WRITE ---")
    rc = subprocess.run(cmd, check=False).returncode
    if rc == 0:
        for f in new:                       # clean RTH CSVs so they don't accumulate
            try: Path(f).unlink()
            except OSError: pass
        print(f"\nRTH trove now current. (If the 5M cache is used downstream, rebuild it: "
              f"python research/scalp_swing/build_5m.py)")

    # ETH trove — keep it current alongside RTH (its own last-day range)
    if not a.dry_run:
        eth_last = last_eth_day()
        eth_frm = (eth_last + dt.timedelta(days=1)) if eth_last else frm
        if to >= eth_frm:
            eth_pass(a.contract, eth_frm, to, a.timeout)
        else:
            print(f"\nETH trove already current through {eth_last}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
