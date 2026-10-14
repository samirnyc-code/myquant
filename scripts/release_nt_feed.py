r"""release_nt_feed.py -- release the myquant NT AddOns' ES subscription so you can
"Reload All Historical Data" without the platform crashing on a file-sharing violation.

The L1 + Depth recorder AddOns subscribe ES 24/7 (which keeps NT recording and holding
today's live db file open), and TickExportAddOn opens db/tick on request. When NT reloads
historical data it DELETES and re-downloads those files; if an AddOn is holding one, NT's
delete throws an unhandled IOException and the whole platform crashes.

Touching data/nt_ticks/_release_feed makes all three AddOns drop/skip the ES subscription
within ~2s. Removing it resubscribes them.

Usage:
    python scripts/release_nt_feed.py              # hold the release, reload NT, press Enter to resubscribe
    python scripts/release_nt_feed.py --secs 25    # hold for 25s then auto-resubscribe (no prompt)
    python scripts/release_nt_feed.py --on         # just create the file (release and leave it)
    python scripts/release_nt_feed.py --off         # just remove the file (resubscribe)

NOTE: this only releases the myquant AddOns. Your CHARTS and any running STRATEGY also hold
the instrument; for a fully clean reload, do it on a chart whose other same-instrument tabs
are closed (or disable the strategy) as well.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

RELEASE = Path(r"C:\Users\Admin\myquant\data\nt_ticks\_release_feed")


def _on():
    RELEASE.parent.mkdir(parents=True, exist_ok=True)
    RELEASE.write_text("released " + time.strftime("%Y-%m-%d %H:%M:%S"), encoding="ascii")
    print(f"[release] ON  -> {RELEASE}  (AddOns drop ES within ~2s)")


def _off():
    try:
        RELEASE.unlink()
        print("[release] OFF -> AddOns resubscribe ES within ~2s")
    except FileNotFoundError:
        print("[release] OFF -> (file was not present)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secs", type=float, default=None, help="hold the release this many seconds, then resubscribe")
    ap.add_argument("--on", action="store_true", help="create the release file and exit (stay released)")
    ap.add_argument("--off", action="store_true", help="remove the release file and exit (resubscribe)")
    a = ap.parse_args()

    if a.off:
        _off(); return
    if a.on:
        _on(); return

    _on()
    try:
        if a.secs is not None:
            print(f"[release] holding {a.secs:.0f}s -- reload NT now ...")
            time.sleep(a.secs)
        else:
            input("[release] reload NT now, then press Enter to resubscribe ... ")
    finally:
        _off()


if __name__ == "__main__":
    sys.exit(main())
