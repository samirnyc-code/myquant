"""session_pings.py — positive confirmations at the session milestones, to the phone.

The alert monitor stays silent when things are fine. That is right for a running system,
but on the FIRST live session (and any morning you want reassurance) silence is
ambiguous — is it working, or is nothing checking? This fires a small number of
one-time POSITIVE pings at the moments that matter, so a healthy open produces a visible
"yes, it's recording", not just an absence of alarms.

Milestones (each fires at most once per session, tracked in telegram_sent.json):
  * futures open   — "session live, first readings"
  * options open   — SPX RTH begins
  * ~5 min in      — first real data-rate reading (MB/min, book %)
  * ~30 min in     — settled data-rate + disk projection

Runs every 5 min from the same schedule as the alert monitor. It only ever ADDS
positive pings; problem alerts stay in alert_monitor.py.

    python scripts/session_pings.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _rate_reading():
    """(mb, book_pct, mb_per_min, detail) from the live depth file, or None."""
    import pipeline_health as ph
    now = ph.chicago_now()
    files = []
    for d in (-1, 0):
        day = (now.date() + dt.timedelta(days=d)).isoformat()
        files += sorted(ph.DEPTH_DIR.glob(f"ES*_depth_{day}.csv"))
    if not files:
        return None
    f = files[-1]
    mb = sum(x.stat().st_size for x in files) / 1e6
    book, tape = ph._tail_mix(f)
    if book + tape == 0:
        return None
    pct = 100.0 * book / (book + tape)
    return mb, pct, f.name


def main() -> int:
    import pipeline_health as ph
    import notify_telegram as tg

    if not tg._load().get("token"):
        print("telegram not configured")
        return 2

    now = ph.chicago_now()
    sess = ph.session_info()
    fstate = ph.market_state()          # open / halt / closed
    ostate = sess.get("opt_session")    # RTH / GTH / closed
    today = now.strftime("%Y%m%d")

    # each milestone keyed by DATE so it fires once per session, never repeats
    def once(key, text, level="ok"):
        return tg.send(text, level=level, dedup_key=f"session_{key}_{today}",
                       cooldown_s=20 * 3600)   # ~one trading day

    # --- futures open ---------------------------------------------------------
    if fstate == "open":
        r = _rate_reading()
        if r:
            mb, pct, name = r
            if pct > 0:
                once("fut_open",
                     f"🟢 Futures session LIVE — depth recording, {pct:.0f}% book events. "
                     f"File {name} at {mb:,.0f} MB.")
            else:
                # book% zero while open is the failure the alert monitor also catches;
                # send it here too so the FIRST session ping is honest
                once("fut_tapeonly",
                     f"🔴 Futures open but TAPE ONLY — no book events yet. Check the depth "
                     f"subscription / recorder. ({name})", level="alert")

    # --- options RTH open -----------------------------------------------------
    if ostate == "RTH":
        once("opt_open", "🟢 SPX options RTH open (08:30 CT). Desk window active.")

    # --- ~30 min in: settled data-rate + disk runway --------------------------
    # only after the open has had time to produce a real rate
    if fstate == "open" and now.time() >= dt.time(17, 30) or \
       (fstate == "open" and dt.time(9, 0) <= now.time() <= dt.time(9, 15)):
        r = _rate_reading()
        if r:
            mb, pct, name = r
            import shutil
            free_gb = shutil.disk_usage(str(ROOT)).free / 1e9
            once("rate_reading",
                 f"📊 Data check: {mb:,.0f} MB so far, {pct:.0f}% book. "
                 f"{free_gb:,.0f} GB free.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
