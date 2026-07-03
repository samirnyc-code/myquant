"""
refresh_stale_flatfiles.py — integrity sweep for cached daily flatfiles.

Some cached .csv.gz came down partial during the bulk build (e.g. 2022-06-21
cached=14.6MB/NQ=6k vs remote=17.8MB/NQ=64k). A partial file still decompresses
and yields *some* bars, so it hides as reduced volume rather than a missing day.

This HEADs every cached flatfile against S3 and compares ContentLength to the
local size. If remote > local (we're missing data), it re-downloads the full
file. Pass --apply to actually re-download; default is measure-only (dry run).

Covers all four exchange caches (CME shared by ES/NQ/6E/6J, plus CBOT/COMEX/NYMEX).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import massive as m  # noqa: E402

DIRS = {
    "flatfiles_cache":        "us_futures_cme/trades_v1",
    "flatfiles_cache_cbot":   "us_futures_cbot/trades_v1",
    "flatfiles_cache_comex":  "us_futures_comex/trades_v1",
    "flatfiles_cache_nymex":  "us_futures_nymex/trades_v1",
}

APPLY = "--apply" in sys.argv


def main() -> None:
    s3 = m._make_s3()
    t0 = time.time()
    grand_stale = 0
    grand_bytes = 0

    for subdir, prefix in DIRS.items():
        d = ROOT / "data" / subdir
        files = sorted(d.glob("*.csv.gz"))
        if not files:
            print(f"[{subdir}] no cached files", flush=True)
            continue
        stale = []
        for f in files:
            ds = f.name[:-len(".csv.gz")]     # "2022-06-21" (.stem leaves ".csv")
            y, mo, _ = ds.split("-")
            key = f"{prefix}/{y}/{mo}/{ds}.csv.gz"
            try:
                remote = s3.head_object(Bucket=m._S3_BUCKET, Key=key)["ContentLength"]
            except Exception:
                continue                     # missing remote (rare) — leave as is
            local = f.stat().st_size
            if remote > local:
                stale.append((ds, local, remote))

        print(f"[{subdir}] {len(files)} cached, {len(stale)} STALE (remote>local), "
              f"{(time.time()-t0):.0f}s elapsed", flush=True)
        for ds, lo, re_ in stale[:8]:
            print(f"    {ds}: local={lo/1e6:.1f}MB remote={re_/1e6:.1f}MB", flush=True)
        grand_stale += len(stale)
        grand_bytes += sum(r - l for _, l, r in stale)

        if APPLY and stale:
            for i, (ds, _lo, _re) in enumerate(stale, 1):
                y, mo, _dd = ds.split("-")
                key = f"{prefix}/{y}/{mo}/{ds}.csv.gz"
                s3.download_file(m._S3_BUCKET, key, str(d / f"{ds}.csv.gz"))
                if i % 20 == 0:
                    print(f"    re-downloaded {i}/{len(stale)}…", flush=True)
            print(f"[{subdir}] re-downloaded {len(stale)} files.", flush=True)

    print(f"\nTOTAL stale: {grand_stale} files, ~{grand_bytes/1e6:.0f}MB missing. "
          f"{'RE-DOWNLOADED' if APPLY else 'DRY RUN (pass --apply to fix)'}. "
          f"{(time.time()-t0)/60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
