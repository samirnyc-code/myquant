"""watch_open.py — sit on the depth file across the ETH open and log what happens.

The first live L2 capture is the one that cannot be re-run: if book events do not
arrive at 17:00 CT, every minute spent not noticing is a minute of data that does not
exist. This polls the recorder's own output and writes a timestamped log, so the
question "did it work?" has an evidence trail rather than a memory.

    python scripts/watch_open.py                 # until 30 min past the next open
    python scripts/watch_open.py --minutes 90

Writes data/_catalog/logs/watch_open.log
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
LOG = ROOT / "data" / "_catalog" / "logs" / "watch_open.log"


def say(msg: str) -> None:
    import pipeline_health as ph
    line = f"{ph.chicago_now():%Y-%m-%d %H:%M:%S} CT  {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def snapshot():
    """(total_bytes, book_rows_in_tail, tape_rows_in_tail, newest_filename)"""
    import pipeline_health as ph
    now = ph.chicago_now()
    files = []
    for d in (-1, 0):
        day = (now.date() + dt.timedelta(days=d)).isoformat()
        files += sorted(ph.DEPTH_DIR.glob(f"ES*_depth_{day}.csv"))
    if not files:
        return 0, 0, 0, None
    size = sum(f.stat().st_size for f in files)
    book, tape = ph._tail_mix(files[-1])
    return size, book, tape, files[-1].name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=30, help="minutes to watch past the open")
    ap.add_argument("--poll", type=int, default=120, help="seconds between polls")
    a = ap.parse_args()

    import pipeline_health as ph
    sess = ph.session_info()
    open_epoch = sess["next_eth_epoch"]
    now_epoch = sess["chicago_epoch"]
    mins_to_open = (open_epoch - now_epoch) / 60

    say(f"watcher started — market {ph.market_state()}, "
        f"open in {mins_to_open:.0f} min, will watch {a.minutes} min past it")

    deadline = time.time() + (mins_to_open + a.minutes) * 60
    first_book_seen = False
    last_size = -1

    while time.time() < deadline:
        size, book, tape, name = snapshot()
        state = ph.market_state()
        grew = size - last_size if last_size >= 0 else 0

        if state == "open" and book > 0 and not first_book_seen:
            first_book_seen = True
            say(f"*** BOOK EVENTS ARRIVING — {book} book / {tape} tape in tail — {name}")
        elif state == "open" and book == 0 and tape > 0:
            say(f"!!! TAPE ONLY — {tape} tape rows, ZERO book. Depth subscription down? — {name}")
        elif size != last_size:
            say(f"{state:<7} {size/1e6:8.2f} MB (+{grew/1024:,.0f} KB)  "
                f"tail book={book} tape={tape}  {name or '-'}")

        last_size = size
        time.sleep(a.poll)

    size, book, tape, name = snapshot()
    say(f"watcher done — {size/1e6:.1f} MB, tail book={book} tape={tape}, file={name}")
    return 0 if first_book_seen or ph.market_state() != "open" else 1


if __name__ == "__main__":
    sys.exit(main())
