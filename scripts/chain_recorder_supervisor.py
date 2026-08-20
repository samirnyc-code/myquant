"""chain_recorder_supervisor.py — guarantee the 0DTE chain recorder is ALIVE from the
open to the close, every session. This is the fix for the real killer of our dataset:
the recorder crashed/exited silently (Aug 7-16 = 8 sessions lost, Aug 17-18 late) while
the FEED was fine. The delayed feed only ever cost ONE day (Aug 19). Process death cost
everything else — so we supervise the process.

What it does, 08:25→stop CT:
  * launches ONE recorder child and re-launches it within seconds if it exits
  * reads the recorder's heartbeat to tell two very different failures apart:
      - heartbeat STALE (no beat > STALL_S)     -> process hung/dead  -> kill + relaunch + page
      - heartbeat FRESH but state=feed_delayed   -> IB feed is delayed -> page (throttled), do NOT relaunch
      - heartbeat FRESH but state=waiting_spot    -> feed cold at open   -> wait, it will start on its own
  * on a clean stop, runs the recorder's EOD completeness gate (child already does) and
    pages if the day came out INCOMPLETE.

Run (what the scheduled task should call, from ~08:25 CT):
  .venv/Scripts/python.exe scripts/chain_recorder_supervisor.py --stop 15:05 --secs 30
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
CT = ZoneInfo("America/Chicago")
HEARTBEAT = SIM / "chain_heartbeat.json"
PYW = ROOT / ".venv" / "Scripts" / "pythonw.exe"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
RECORDER = ROOT / "scripts" / "options_chain_recorder.py"
LOGF = SIM / "chain_supervisor.log"

STALL_S = 90          # no heartbeat for this long during session = hung/dead -> relaunch
POLL_S = 15           # how often the supervisor checks
RELAUNCH_BACKOFF = 5  # pause before a relaunch so a hard-failing child can't spin


def now_ct():
    return dt.datetime.now(CT)


def log(msg):
    line = f"{now_ct():%Y-%m-%d %H:%M:%S} CT  {msg}"
    print(line, flush=True)
    try:
        with LOGF.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def page(msg, key, cooldown=1800):
    """Telegram page, deduped. Never let a telegram failure break the supervisor."""
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import notify_telegram as tg
        tg.send(msg, level="alert", dedup_key=key, cooldown_s=cooldown)
    except Exception as e:
        log(f"(telegram failed: {e})")


def read_heartbeat():
    try:
        d = json.loads(HEARTBEAT.read_text(encoding="utf-8"))
        d["age"] = time.time() - float(d.get("ts_epoch", 0))
        return d
    except Exception:
        return None


def launch(secs, pct, stop):
    """Start one recorder child detached-ish (own stdout to a log). Returns Popen."""
    exe = str(PYW) if PYW.exists() else str(PY)
    cmd = [exe, "-u", str(RECORDER), "--secs", str(secs), "--pct", str(pct), "--stop", stop]
    log(f"launching recorder: {' '.join(cmd[2:])}")
    return subprocess.Popen(cmd, cwd=str(ROOT),
                            creationflags=0x08000008,  # DETACHED_PROCESS | CREATE_NO_WINDOW
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stop", default="15:05", help="stop time CT HH:MM")
    ap.add_argument("--secs", type=int, default=30)
    ap.add_argument("--pct", type=float, default=1.25)
    a = ap.parse_args()

    import singleton
    singleton.ensure("chain_recorder_supervisor")   # one supervisor only

    sh, sm = map(int, a.stop.split(":"))
    stop_t = dt.time(sh, sm)
    log(f"supervisor up — keeping recorder alive until {a.stop} CT, cadence {a.secs}s")

    child = launch(a.secs, a.pct, a.stop)
    last_beat_seen = time.time()
    delayed_since = None

    while now_ct().time() < stop_t:
        time.sleep(POLL_S)
        # 1) did the child process exit?
        if child.poll() is not None:
            if now_ct().time() >= stop_t:
                break
            log(f"recorder process EXITED (code {child.returncode}) mid-session — relaunching")
            page("🔧 0DTE recorder died — auto-relaunching (supervised)", "chain_relaunch")
            time.sleep(RELAUNCH_BACKOFF)
            child = launch(a.secs, a.pct, a.stop)
            last_beat_seen = time.time()
            continue
        # 2) child alive — is it actually beating?
        hb = read_heartbeat()
        if hb is None:
            # no heartbeat file yet; give it one STALL window from launch before acting
            if time.time() - last_beat_seen > STALL_S:
                log("no heartbeat since launch — killing & relaunching")
                page("🔧 0DTE recorder not beating — restarting (supervised)", "chain_relaunch")
                _kill(child); time.sleep(RELAUNCH_BACKOFF)
                child = launch(a.secs, a.pct, a.stop); last_beat_seen = time.time()
            continue
        if hb["age"] <= STALL_S:
            last_beat_seen = time.time()
        # 3) alive & beating — classify the state
        state = hb.get("state")
        if hb["age"] > STALL_S:
            # beating stopped though process lives = hung (stuck in a call) -> relaunch
            log(f"heartbeat STALE ({hb['age']:.0f}s, state={state}) — process hung, restarting")
            page("🔧 0DTE recorder hung (no beat) — restarting (supervised)", "chain_relaunch")
            _kill(child); time.sleep(RELAUNCH_BACKOFF)
            child = launch(a.secs, a.pct, a.stop); last_beat_seen = time.time()
            delayed_since = None
        elif state == "feed_delayed":
            # FEED problem, not a process problem — relaunching won't help. Page, don't churn.
            if delayed_since is None:
                delayed_since = time.time()
            mins = (time.time() - delayed_since) / 60
            if mins >= 3:
                page(f"🔴 0DTE feed DELAYED {mins:.0f}m — realtime quotes unavailable, "
                     f"tape has a hole (not a recorder crash)", "chain_feed_delayed")
        else:
            if delayed_since is not None and state == "ok":
                page("✅ 0DTE feed realtime again — recording resumed", "chain_feed_delayed_ok",
                     cooldown=1)
            delayed_since = None

    # session over — reap the child and grade the day
    log("stop time reached — stopping recorder")
    _kill(child)
    _grade_day(a.secs, a.stop)
    log("supervisor done.")


def _kill(child):
    try:
        child.terminate()
        try:
            child.wait(timeout=15)
        except Exception:
            child.kill()
    except Exception:
        pass


def _grade_day(secs, stop):
    """Read the child's completeness report and page if the day is incomplete."""
    date = now_ct().strftime("%Y%m%d")
    f = SIM / f"chain_completeness_{date}.json"
    try:
        rep = json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        # child may not have written it (killed) — compute directly
        try:
            sys.path.insert(0, str(ROOT / "scripts"))
            import options_chain_recorder as rec
            rep = rec.validate_day(date, secs, stop)
        except Exception as e:
            log(f"could not grade day: {e}")
            return
    if rep.get("complete"):
        log(f"day COMPLETE: {rep['actual_snaps']}/{rep['expected_snaps']} snaps "
            f"({rep['coverage_pct']}%), max gap {rep['max_gap_s']}s")
    else:
        log(f"day INCOMPLETE: {rep['coverage_pct']}% coverage, max gap {rep.get('max_gap_s')}s")
        page(f"⚠️ 0DTE tape INCOMPLETE {date}: {rep['coverage_pct']}% "
             f"({rep['actual_snaps']}/{rep['expected_snaps']} snaps), "
             f"max gap {rep.get('max_gap_s')}s — does NOT count toward the 90", "chain_incomplete")


if __name__ == "__main__":
    sys.exit(main())
