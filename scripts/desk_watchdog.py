"""Desk watchdog (S75M) — the recurring guard the desk lacked on 7/17.

That day a midday IB drop killed spot_feed (crashed out at 12:59 ET), hung the
sim daemon's sampler, and NOTHING noticed for 36 minutes because the only
healthcheck runs once at 08:40 CT. This script runs every 5 minutes via Task
Scheduler ("MyQuant Desk Watchdog") and:

  - checks each desk component's OUTPUT freshness (not just process presence —
    a hung process looks alive; its stale output doesn't)
  - restarts the component's own scheduled task when it's stale/dead
  - kills a hung daemon pair first (venv launcher + worker = ONE daemon)
  - toasts + logs every action via notify (same channel as the healthcheck)

Anti-flap: per-component cooldown (10 min) and daily restart cap (5), persisted
in data/_catalog/watchdog_state.json. Outside market hours it exits instantly.

Two modes (S75M-b):
  one-shot (default)  — Task Scheduler "MyQuant Desk Watchdog", every 5 min. Slow
                        thresholds. ALSO acts as meta-watchdog: restarts the
                        resident daemon if its heartbeat is stale.
  --daemon            — resident loop, 10s cadence, FAST thresholds (feed stale
                        at 45s not 180s). Task "MyQuant Desk Watchdog Live"
                        starts it daily; it exits itself outside market hours.
                        Writes data/_catalog/watchdog_heartbeat.txt each loop.
Detection latency = threshold + restart time, NOT poll rate — the daemon mode
matters because it carries the tight thresholds, the 10s loop is just free.

Run manually to test:  .venv/Scripts/python.exe scripts/desk_watchdog.py [--dry-run]
"""
import argparse
import datetime as dt
import json
import socket
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notify import notify

CT = ZoneInfo("America/Chicago")
ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "data" / "options_sim"
STATE = ROOT / "data" / "_catalog" / "watchdog_state.json"
LOG = ROOT / "data" / "_catalog" / "logs" / "desk_watchdog.log"

COOLDOWN_S = 600          # min seconds between restarts of one component
DAILY_CAP = 5             # max restarts per component per day
HEARTBEAT = ROOT / "data" / "_catalog" / "watchdog_heartbeat.txt"

# 2026-10-19 (S146-recurring): data/bid_ask/bid_ask_vol_buckets.csv is a manual
# snapshot, not a live stream -- BidAskVolumeRatio/Delta/Split and CumulativeDelta
# (NT8, all OnMarketData-dependent) fall back to it for any bar whose live
# accumulator was lost (e.g. a chart reload). Without a periodic re-run it falls
# behind and reopens the exact gap it was built to close -- happened 3+ times in
# one session before this was wired in. 30 min caps the worst-case gap.
BID_ASK_BACKFILL_INTERVAL_S = 1800

# staleness thresholds (seconds): slow = 5-min one-shot mode, fast = 10s daemon
THRESH = {
    "feed":  {"slow": 180, "fast": 45},    # live.json writes every ~5s
    "tape":  {"slow": 600, "fast": 300},   # underlying tape writes every ~60s
    "marks": {"slow": 420, "fast": 300},   # marks watch writes every ~120s
    "trig_hb": {"slow": 360, "fast": 300}, # daemon stamps every loop, BUT manage_open blocks ~2-3min
    #   quoting all legs at the 14:45 EOD close burst — fast=180 false-fired "HUNG" there (2026-09-17,
    #   191s). Both allow the manage burst; a real hang (connect stall) freezes for the whole session.
}
MODE = "slow"             # flipped to "fast" by --daemon

# component: (scheduled task to restart, window CT, staleness check)
# windows are (start, end) HH:MM strings; checks return (ok, detail)


def now():
    return dt.datetime.now(CT)


def log(msg):
    print(msg)  # first, so a log-file problem never hides the message entirely
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{now():%Y-%m-%d %H:%M:%S} {msg}\n")
    except OSError as e:
        print(f"log() could not write {LOG}: {e}")


def file_age_s(p):
    p = Path(p)
    if not p.exists():
        return 1e9
    return (dt.datetime.now() - dt.datetime.fromtimestamp(p.stat().st_mtime)).total_seconds()


def in_window(start, end):
    t = now().strftime("%H:%M")
    return start <= t < end


def procs_matching(pattern):
    """PIDs whose command line contains pattern (Windows, via PowerShell CIM)."""
    ps = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
          f"Where-Object {{ $_.CommandLine -match '{pattern}' }} | "
          "Select-Object -ExpandProperty ProcessId")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, timeout=60,
                       creationflags=0x08000000)   # NO console flash (this loops every 10s)
    return [int(x) for x in r.stdout.split() if x.strip().isdigit()]


def kill_pids(pids):
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                       creationflags=0x08000000)


def run_task(name):
    try:
        subprocess.run(["schtasks", "/run", "/tn", name], capture_output=True, text=True,
                       creationflags=0x08000000, timeout=30)
    except subprocess.TimeoutExpired:
        log(f"run_task({name}): schtasks /run did not return within 30s — skipping this cycle")


def task_enabled(name):
    """True unless the component's scheduled task is Disabled/Missing. A Disabled
    task means the component is intentionally OFF — the watchdog must not keep trying
    to restart it (2026-09-17: it burned its daily restart cap relaunching the
    Disabled 'MyQuant Sim Daemon' every cycle). General guard, not a sim_daemon hack."""
    ps = ("$t=Get-ScheduledTask -TaskName '%s' -ErrorAction SilentlyContinue; "
          "if ($t) { $t.State.ToString() } else { 'Missing' }") % name
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, text=True, timeout=30,
                       creationflags=0x08000000)
    return r.stdout.strip() not in ("Disabled", "Missing", "")


def port_open(port, host="127.0.0.1"):
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


# ---------- checks: each returns (ok, detail) ----------

def check_gateway():
    return port_open(4002), "API 4002"


def check_spot_feed():
    f = SIM / "live.json"
    age = file_age_s(f)
    if age > THRESH["feed"][MODE]:
        return False, f"live.json {age:.0f}s stale"
    try:
        state = json.loads(f.read_text()).get("state")
    except Exception:
        return False, "live.json unreadable"
    if state not in ("live", "no-quotes", "reconnecting"):
        return False, f"state={state} during RTH"
    return True, f"live.json {age:.0f}s, {state}"


def check_sim_daemon():
    pids = procs_matching("options_sim_daemon")
    tape = SIM / f"underlying_{now():%Y%m%d}.csv"
    age = file_age_s(tape)
    if not pids:
        return False, "process gone"
    # NB spot_feed also writes this tape ~1/min, so a fresh tape can mask a hung
    # daemon for a while — the daemon's own reconnect guard (S75M) covers that;
    # this outer check catches full deaths and >10-min total silence.
    if age > THRESH["tape"][MODE]:
        return False, f"pair alive but tape {age:.0f}s stale (hung)"
    return True, f"pair {pids}, tape {age:.0f}s"


def check_marks():
    age = file_age_s(SIM / "marks.csv")
    return age < THRESH["marks"][MODE], f"marks.csv {age:.0f}s"


def check_trigger_daemon():
    pids = procs_matching("options_trigger_daemon")
    if not pids:
        return False, "process gone"
    # HANG detection (2026-08-19 outage): the process can be alive yet stop iterating
    # (a blocking IB call, a wedged loop) — leaving open positions unmanaged. The daemon
    # stamps trigger_daemon_heartbeat.txt every loop; a stale stamp = hung -> restart.
    age = file_age_s(SIM / "trigger_daemon_heartbeat.txt")
    if age > THRESH["trig_hb"][MODE]:
        return False, f"alive but heartbeat {age:.0f}s stale (HUNG — open positions unmanaged)"
    return True, f"pids {pids}, hb {age:.0f}s"


COMPONENTS = [
    # (key, task name, window CT, check fn, kill pattern before restart or None)
    ("gateway",     "MyQuant Gateway Ensure", ("08:15", "15:20"), check_gateway, None),
    ("spot_feed",   "MyQuant Spot Feed",      ("08:30", "15:15"), check_spot_feed, "spot_feed"),
    ("sim_daemon",  "MyQuant Sim Daemon",     ("08:40", "14:50"), check_sim_daemon, "options_sim_daemon"),
    ("marks",       "MyQuant Marks Watch",    ("08:35", "15:10"), check_marks, "options_mark"),
    ("triggers",    "MyQuant Trigger Daemon", ("08:40", "14:55"), check_trigger_daemon,
     "options_trigger_daemon"),
]


def refresh_bid_ask_backfill(state, today, dry_run=False):
    """Periodic timer action, not a check-then-restart component: re-runs
    backfill_bid_ask_log.py --day <today> --force on a fixed interval so the NT8
    bid/ask bucket log never falls more than ~BID_ASK_BACKFILL_INTERVAL_S behind
    live. Returns a problem string on failure, else None (success is silent/logged,
    not notified -- this is routine, not an outage)."""
    st = state.get("bid_ask_backfill", {})
    since_last = ((dt.datetime.now() - dt.datetime.fromisoformat(st["last"])).total_seconds()
                  if st.get("last") else 1e9)
    if since_last < BID_ASK_BACKFILL_INTERVAL_S:
        return None
    if dry_run:
        log(f"bid_ask_backfill: due for refresh (dry-run, not executing) — {since_last:.0f}s since last")
        return None
    script = ROOT / "scripts" / "backfill_bid_ask_log.py"
    try:
        r = subprocess.run([sys.executable, str(script), "--day", today, "--force"],
                           capture_output=True, text=True, timeout=180,
                           creationflags=0x08000000, cwd=str(ROOT))
        ok = r.returncode == 0
        tail = (r.stdout.strip().splitlines() or [""])[-1]
        detail = tail[:200] if ok else (r.stderr.strip().splitlines() or [""])[-1][:200]
    except Exception as e:
        ok, detail = False, str(e)[:200]
    state["bid_ask_backfill"] = {"last": dt.datetime.now().isoformat(timespec="seconds"), "ok": ok}
    log(f"bid_ask_backfill: {'ok' if ok else 'FAILED'} — {detail}")
    return None if ok else f"bid_ask_backfill: refresh failed — {detail}"


def load_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def save_state(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=1))


# process-list checks spawn PowerShell (~2s) — in daemon mode run them at most
# every PROC_CHECK_S; file/port checks are free and run every loop.
PROC_CHECK_S = 60
_check_cache = {}   # key -> (ts, (ok, detail))
_disabled_logged = set()   # components skipped because their task is Disabled (log once/run)


def cycle(dry_run):
    """One pass over all components. Returns list of problem strings."""
    state = load_state()
    today = now().date().isoformat()
    problems = []
    heavy = {"sim_daemon", "triggers"}

    for key, task, window, check, kill_pat in COMPONENTS:
        if not in_window(*window):
            continue
        if MODE == "fast" and key in heavy:
            ts, cached = _check_cache.get(key, (0, None))
            if cached is not None and dt.datetime.now().timestamp() - ts < PROC_CHECK_S:
                ok, detail = cached
            else:
                ok, detail = check()
                _check_cache[key] = (dt.datetime.now().timestamp(), (ok, detail))
        else:
            ok, detail = check()
        if ok:
            continue
        if not task_enabled(task):
            if key not in _disabled_logged:
                log(f"{key}: {detail} — task '{task}' Disabled; intentionally off, not restarting")
                _disabled_logged.add(key)
            continue
        st = state.get(key, {})
        restarts_today = st.get("count", 0) if st.get("day") == today else 0
        since_last = (dt.datetime.now()
                      - dt.datetime.fromisoformat(st["last"])).total_seconds() if st.get("last") else 1e9
        if restarts_today >= DAILY_CAP:
            problems.append(f"{key}: {detail} — RESTART CAP HIT ({DAILY_CAP}/day), manual fix needed")
            continue
        if since_last < COOLDOWN_S:
            log(f"{key}: {detail} — in cooldown ({since_last:.0f}s), waiting")
            continue
        problems.append(f"{key}: {detail} — restarting via '{task}'")
        if not dry_run:
            if kill_pat:
                pids = procs_matching(kill_pat)
                if pids:
                    log(f"{key}: killing hung pair {pids}")
                    kill_pids(pids)
            run_task(task)
            _check_cache.pop(key, None)
            state[key] = {"day": today, "count": restarts_today + 1,
                          "last": dt.datetime.now().isoformat(timespec="seconds")}

    # ClaudeTracker (2026-10-16): runs INSIDE NT8, not a Python process/task — there is no
    # scheduled task to restart, so this is notify-only, not part of COMPONENTS above. Reuses
    # pipeline_health's own check (same evidence: health-file freshness + stuck-open scan) so
    # there's one source of truth for what counts as a problem, not a second definition to
    # drift out of sync with the status light / Mission Control. Same COOLDOWN_S as everything
    # else here, so a stuck-open trade doesn't re-notify every cycle while it stays stuck.
    try:
        import pipeline_health as ph
        ct = ph.check_claude_tracker_trades()
        if ct["state"] == ph.BAD:
            st = state.get("claude_tracker", {})
            since_last = (dt.datetime.now() - dt.datetime.fromisoformat(st["last"])).total_seconds() if st.get("last") else 1e9
            if since_last >= COOLDOWN_S:
                problems.append(f"claude_tracker: {ct['detail']} — NO AUTO-FIX (runs inside NT8; check the Output window)")
                state["claude_tracker"] = {"last": dt.datetime.now().isoformat(timespec="seconds")}
    except Exception as e:
        log(f"claude_tracker check failed: {e}")

    try:
        prob = refresh_bid_ask_backfill(state, today, dry_run)
        if prob:
            problems.append(prob)
    except Exception as e:
        log(f"bid_ask_backfill refresh failed: {e}")

    # Always persist state, not just on problems: refresh_bid_ask_backfill updates
    # state[...]["last"] on a SUCCESSFUL run (no problem appended) -- if save only
    # happened inside the `if problems` branch below, that timestamp would never
    # reach disk, load_state() would see it as "never run" every cycle, and the
    # 30-min gate above would never actually hold (re-run every cycle instead).
    save_state(state)
    if problems:
        body = " | ".join(problems)
        log("ACTION " + body)
        try:
            notify("Desk watchdog", body[:250])
        except Exception as e:
            log(f"notify failed: {e}")
    return problems


def main():
    global MODE
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only, restart nothing")
    ap.add_argument("--daemon", action="store_true",
                    help="resident 10s loop with fast thresholds (until 23:55 CT)")
    a = ap.parse_args()

    # HOLIDAY / EARLY-CLOSE AWARE (S75V).
    # The weekday+window test alone fired on Thanksgiving, Good Friday and after a half-day
    # close, popping "daemon down" alerts for components that are correctly not running.
    # An alert that cries wolf on known-closed days is worse than no alert - you learn to
    # dismiss it, and then you dismiss the real one too.
    try:
        import market_calendar as mc
        kind, label = mc.day_type(now().date())
        if kind in ("weekend", "holiday"):
            log(f"skip: {label} — market closed")
            return
        if kind == "early":
            log(f"{label} — early close (options-desk COMPONENTS below still self-gate to "
                "their own narrower RTH windows; this only affects how long the OUTER loop runs)")
    except Exception:
        if now().weekday() >= 5:
            return

    # 2026-10-20: widened from RTH-only (08:15-15:20 CT) to span essentially the whole ES ETH
    # session. The options-desk COMPONENTS list below is UNCHANGED -- each entry already self-
    # gates to its own narrower RTH window independently (checked per-component inside cycle()),
    # so widening this outer bound does not make gateway/spot_feed/sim_daemon/marks/triggers run
    # outside RTH. What WAS RTH-scoped and shouldn't have been: refresh_bid_ask_backfill() inside
    # cycle() -- meaning it never ran during ETH, which is exactly when the user needs
    # BidAskVolumeRatio/Delta/Split/CumulativeDelta to stay current (hit this directly after
    # switching NT8 bar types forced reliance on a backfill that hadn't refreshed since the prior
    # RTH session). Does NOT cover Sunday evening ETH open -- the weekday>=5 check above still
    # excludes Sat/Sun entirely; not addressed here, flagged as a known remaining gap.
    START = "00:05"
    close = "23:55"
    nowhm = now().strftime("%H:%M")
    if nowhm >= close:
        return  # the day's window is already over

    if a.daemon:
        MODE = "fast"
        # The task fires on a FIXED Berlin clock, but the window is Chicago time, so it can
        # land well before 08:15 CT — a few minutes normally, up to ~1h during the DST-mismatch
        # weeks (Berlin=CT+6 not +7 for ~3wk in Mar and ~1wk in Oct/Nov). WAIT for the window in
        # a loop rather than exit or single-sleep — 2026-09-16 an early start insta-exited and the
        # watchdog never ran all day; a capped one-shot sleep would fail the same way past the cap.
        import time
        if now().strftime("%H:%M") < START:
            log(f"daemon: before {START} CT window (now {now():%H:%M} CT) — waiting for open")
        while now().strftime("%H:%M") < START and now().strftime("%H:%M") < close:
            time.sleep(60)
        log("daemon mode: 10s cadence, fast thresholds")
        last_green = 0.0
        while in_window(START, close):
            HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
            HEARTBEAT.write_text(dt.datetime.now().isoformat(timespec="seconds"))
            try:
                if not cycle(a.dry_run):
                    if dt.datetime.now().timestamp() - last_green > 600:
                        log("all green (daemon)")
                        last_green = dt.datetime.now().timestamp()
            except Exception as e:
                log(f"daemon cycle error: {str(e)[:150]}")
            import time
            time.sleep(10)
        log("daemon: market window closed, exiting")
        return

    # one-shot (5-min task): slow thresholds + meta-guard for the daemon
    if not in_window(START, close):
        return  # a repetition tick outside the market window — nothing to do
    hb_age = file_age_s(HEARTBEAT)
    if hb_age > 120:
        log(f"resident watchdog heartbeat {hb_age:.0f}s stale — restarting Live task")
        if not a.dry_run:
            run_task("MyQuant Desk Watchdog Live")
    if not cycle(a.dry_run):
        log("all green")


if __name__ == "__main__":
    main()
