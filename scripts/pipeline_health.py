"""pipeline_health.py — one place that answers "is everything actually working?"

Every check is EVIDENCE-BASED. A process being alive proves nothing: on 2026-07-19 the
platform sat at a login prompt, a strategy was silently disabled by a recompile, and the
depth subscription was missing for weeks - all three would have shown green under a
"is the process running?" check. So each check here looks at the artefact the process is
supposed to produce, and how fresh it is.

Consumed by:
    scripts/status_light.py   the always-on-top traffic light
    scripts/launcher.py       Mission Control /health page
    python scripts/pipeline_health.py         # console

Every timestamp is Chicago-anchored: NT8 and all market data run CT, this PC runs Berlin.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEPTH_DIR = ROOT / "data" / "depth"
FOOTPRINT_DIR = ROOT / "data" / "footprint"
CATALOG = ROOT / "data" / "_catalog"
NT8 = Path(os.environ["USERPROFILE"]) / "Documents" / "NinjaTrader 8"

OK, WARN, BAD, IDLE = "ok", "warn", "bad", "idle"
RANK = {OK: 0, IDLE: 1, WARN: 2, BAD: 3}

# Windows: without CREATE_NO_WINDOW every subprocess flashes a console window on screen.
# These checks run every 10-15s from the status light AND Mission Control, so an unflagged
# call is a strobe of popping black windows (2026-07-19).
_NOWIN = 0x08000000 if os.name == "nt" else 0

_CACHE: dict = {}


def _cached(key: str, ttl: float, fn):
    """Slow, rarely-changing probes (Task Scheduler ~1s) must not run on every poll."""
    now = dt.datetime.now().timestamp()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    _CACHE[key] = (now, val)
    return val


# ------------------------------------------------------------------ time / session
def chicago_now() -> dt.datetime:
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo("America/Chicago"))
    except Exception:
        return dt.datetime.utcnow() - dt.timedelta(hours=5)


def market_state(now: dt.datetime | None = None) -> str:
    """'open' | 'halt' | 'closed' for ES on Globex.

    Delegates to market_calendar, which knows US market HOLIDAYS and half days. Without
    that, every check treats Thanksgiving or Good Friday as a normal session: the board
    lights amber because nothing is recording, and the desk's 15:00 flat-by and 15:15
    postmortem run after an early close as though the day were whole.
    """
    now = now or chicago_now()
    try:
        import market_calendar as mc
        return mc.futures_state(now)[0]
    except Exception:
        wd, t = now.weekday(), now.time()      # fall back to the weekday-only rule
        if wd == 5:
            return "closed"
        if wd == 6:
            return "open" if t >= dt.time(17, 0) else "closed"
        if wd == 4 and t >= dt.time(16, 0):
            return "closed"
        if dt.time(16, 0) <= t < dt.time(17, 0):
            return "halt"
        return "open"


def market_reason(now: dt.datetime | None = None) -> str:
    """Why the market is in that state - 'Thanksgiving', 'daily maintenance halt', ..."""
    try:
        import market_calendar as mc
        return mc.futures_state(now or chicago_now())[1]
    except Exception:
        return ""


def _age(path: Path) -> float:
    """Seconds since last write, using WALL time (mtime is PC-clock based)."""
    try:
        return dt.datetime.now().timestamp() - path.stat().st_mtime
    except Exception:
        return float("inf")


def _fmt_age(sec: float) -> str:
    if sec == float("inf"):
        return "never"
    if sec < 90:
        return f"{sec:.0f}s"
    if sec < 5400:
        return f"{sec/60:.0f}m"
    return f"{sec/3600:.1f}h"


def _chk(name, state, detail, **extra):
    return dict(name=name, state=state, detail=detail, **extra)


# ------------------------------------------------------------------ checks
def check_depth() -> dict:
    """The one dataset that can never be re-collected."""
    now = chicago_now()
    mkt = market_state(now)
    # ES_09-26_depth_YYYY-MM-DD.csv (and legacy ES_depth_...) - match any contract.
    # +1: files carry the TRADE DATE (session template), so after 17:00 CT the LIVE
    # file is dated tomorrow. Without +1 every evening looks like "no file" (S75V).
    files = []
    for d in (-1, 0, 1):
        day = (now.date() + dt.timedelta(days=d)).isoformat()
        files += sorted(DEPTH_DIR.glob(f"ES*_depth_{day}.csv"))
    if not files:
        return _chk("L2 depth", BAD if mkt == "open" else IDLE,
                    "no file for today" if mkt == "open" else f"market {mkt}")
    mb = sum(f.stat().st_size for f in files) / 1e6
    age = min(_age(f) for f in files)
    if mkt in ("closed", "halt"):
        return _chk("L2 depth", IDLE, f"{mb:,.0f}MB - market {mkt}", mb=round(mb, 1))
    if age > 180:
        return _chk("L2 depth", BAD, f"STALLED {_fmt_age(age)} - data being lost", mb=round(mb, 1))

    # A GROWING FILE IS NOT PROOF OF DEPTH. On 7/17 the recorder ran a full 7h session and
    # wrote 922,703 rows that were 100% TRADES and zero book events - the subscription was
    # missing and every size/freshness check looked perfectly healthy. So read the tail and
    # confirm actual A/U/R book rows are arriving, not just tape.
    book, tape = _tail_mix(files[-1])
    if book + tape == 0:
        return _chk("L2 depth", WARN, f"{mb:,.0f}MB, tail unreadable", mb=round(mb, 1))
    if book == 0:
        return _chk("L2 depth", BAD,
                    f"TAPE ONLY - no book events in the last {tape:,} rows "
                    f"(depth subscription down?)", mb=round(mb, 1), book=0, tape=tape)
    pct = 100.0 * book / (book + tape)
    return _chk("L2 depth", OK,
                f"{mb:,.0f}MB, {_fmt_age(age)} ago, {pct:.0f}% book",
                mb=round(mb, 1), book=book, tape=tape)


def _tail_mix(path, nbytes: int = 60_000):
    """(book_rows, tape_rows) in the last chunk of a depth CSV.

    Reads only the tail so it stays cheap on a multi-GB file and reflects what is
    happening NOW rather than what happened at the open.
    """
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - nbytes))
            chunk = f.read().decode("ascii", "ignore")
        book = tape = 0
        for line in chunk.splitlines()[1:-1]:      # drop partial first/last lines
            parts = line.split(",", 2)
            if len(parts) < 2:
                continue
            ev = parts[1]
            if ev == "T":
                tape += 1
            elif ev in ("A", "U", "R"):
                book += 1
        return book, tape
    except Exception:
        return 0, 0


def front_month(now: dt.datetime | None = None) -> str:
    """Which ES contract SHOULD be front month right now.
    ES is quarterly (Mar/Jun/Sep/Dec) and rolls ~2nd Thursday of the expiry month, so from
    mid-month the next quarter leads. Recording a dead contract looks perfectly healthy -
    a file grows, rows arrive - which is exactly why this is checked explicitly."""
    now = now or chicago_now()
    y, m = now.year, now.month
    for em in (3, 6, 9, 12):
        if m < em or (m == em and now.day < 10):
            return f"{em:02d}-{y % 100:02d}"
    return f"03-{(y + 1) % 100:02d}"


def check_contract() -> dict:
    """Is NT8 recording the contract we expect? (roll traps: 'ES 12-20' was still in a
    workspace on 2026-07-19 - a chart on a dead contract records nothing, silently.)"""
    want = front_month()
    base = NT8 / "db" / "tick"
    seen, active = [], None
    if base.exists():
        dirs = sorted((p for p in base.glob("ES *") if p.is_dir()), key=lambda p: p.stat().st_mtime)
        seen = [p.name for p in dirs[-3:]]
        if dirs:
            active = dirs[-1].name.replace("ES ", "").strip()
    if not active:
        return _chk("Contract", WARN, f"expected ES {want}, no tick data found", want=want)
    if active != want:
        return _chk("Contract", BAD,
                    f"recording ES {active} but front month is ES {want}",
                    want=want, active=active, seen=seen)
    return _chk("Contract", OK, f"ES {active} (front month)", want=want, active=active)


def check_footprint() -> dict:
    fp = sorted(FOOTPRINT_DIR.glob("*_footprint_*.csv"), key=lambda x: x.stat().st_mtime)
    if not fp:
        legacy = FOOTPRINT_DIR / "ES_footprint.csv"
        if legacy.exists():
            return _chk("Footprint", WARN if market_state() == "open" else IDLE,
                        f"legacy file only, {_fmt_age(_age(legacy))} ago")
        return _chk("Footprint", IDLE, "no stamped file yet")
    newest = fp[-1]
    age = _age(newest)
    mkt = market_state()
    if mkt != "open":
        return _chk("Footprint", IDLE, f"{newest.name} ({_fmt_age(age)})")
    # Footprint updates on BAR CLOSE, and these are VOLUME bars (6500V): a bar closes only
    # when 6,500 contracts trade. In thin overnight ETH that is routinely 15-40 min apart,
    # so a flat "stale > 15m" flag false-alarms all night. Only treat footprint as stale if
    # DEPTH is also not flowing (then nothing is being captured at all) or during RTH, where
    # volume is high enough that a long gap is genuinely abnormal.
    depth = check_depth()
    depth_live = depth.get("book", 0) and depth["state"] == OK
    rth = _desk_hours()
    limit = 1800 if rth else 999999      # RTH: 30 min is a real gap; ETH: bar-close driven
    if depth_live and age <= limit:
        return _chk("Footprint", OK, f"{newest.name} ({_fmt_age(age)}, bar-close driven)")
    if not depth_live:
        return _chk("Footprint", WARN, f"{newest.name} stale {_fmt_age(age)} and depth not flowing")
    return _chk("Footprint", WARN, f"{newest.name} stale {_fmt_age(age)} during RTH")


def check_nt8() -> dict:
    """Running AND past the login prompt AND writing logs."""
    return _cached("nt8", 30, _check_nt8_uncached)


def _check_nt8_uncached() -> dict:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq NinjaTrader.exe"],
                             capture_output=True, text=True, timeout=15,
                             creationflags=_NOWIN).stdout
        running = "NinjaTrader.exe" in out
    except Exception:
        running = False
    if not running:
        return _chk("NinjaTrader", BAD if market_state() == "open" else IDLE, "not running")
    logs = sorted((NT8 / "log").glob("log.*.txt"), key=lambda p: p.stat().st_mtime) if (NT8 / "log").exists() else []
    if not logs:
        return _chk("NinjaTrader", WARN, "running, no log found")
    return _chk("NinjaTrader", OK, f"running, log {_fmt_age(_age(logs[-1]))} ago")


def check_tick_db() -> dict:
    """'Record live data as historical' actually persisting."""
    base = NT8 / "db" / "tick"
    if not base.exists():
        return _chk("NT8 tick DB", WARN, "db/tick missing")
    # sort by RECENCY, not name: "ES 12-25" sorts after "ES 09-26" alphabetically but is
    # a year older, which made this report a dead contract as the live one.
    es = sorted((p for p in base.glob("ES *") if p.is_dir()), key=lambda p: p.stat().st_mtime)
    if not es:
        return _chk("NT8 tick DB", WARN, "no ES contract folder")
    newest_dir = es[-1]
    files = sorted(newest_dir.glob("*.ncd"), key=lambda p: p.stat().st_mtime)
    if not files:
        return _chk("NT8 tick DB", WARN, f"{newest_dir.name}: empty")
    age = _age(files[-1])
    mkt = market_state()
    if mkt == "open" and age > 1800:
        return _chk("NT8 tick DB", WARN, f"{newest_dir.name} stale {_fmt_age(age)}")
    return _chk("NT8 tick DB", OK if mkt == "open" else IDLE,
                f"{newest_dir.name}, {len(files)} files, {_fmt_age(age)} ago")


def _desk_hours() -> bool:
    """The options desk runs ~08:00-15:00 CT on trading days. Outside that (overnight ETH,
    weekends, holidays) the gateway/feed/sim are SUPPOSED to be down - flagging them then
    is a false alarm, the same trap as the weekend one."""
    now = chicago_now()
    try:
        import market_calendar as mc
        if mc.day_type(now.date())[0] in ("weekend", "holiday"):
            return False
    except Exception:
        if now.weekday() >= 5:
            return False
    return dt.time(8, 0) <= now.time() <= dt.time(15, 15)


def check_ib_gateway() -> dict:
    """Login != API port. Port 4002 answering is the only proof (S75 incident).
    Only meaningful during desk hours - overnight the gateway is intentionally down."""
    s = socket.socket()
    s.settimeout(1.5)
    try:
        s.connect(("127.0.0.1", 4002))
        return _chk("IB gateway", OK, "port 4002 answering")
    except Exception:
        return _chk("IB gateway", WARN if _desk_hours() else IDLE,
                    "port 4002 not answering" + ("" if _desk_hours() else " (desk closed)"))
    finally:
        s.close()


def check_options_sim() -> dict:
    """The desk's live feed. Only meaningful while the market is open: the spot feed
    stops at the close by design, so a stale live.json on a Sunday is correct behaviour,
    not a fault. Reporting it as WARN made half the timeline amber for no reason."""
    live = ROOT / "data" / "options_sim" / "live.json"
    mkt = market_state()
    if not live.exists():
        return _chk("Options sim", WARN if mkt == "open" else IDLE, "live.json missing")
    age = _age(live)
    try:
        d = json.loads(live.read_text())
        n = len(d.get("positions", d)) if isinstance(d, (dict, list)) else 0
    except Exception:
        n = 0
    if mkt != "open" or not _desk_hours():
        return _chk("Options sim", IDLE, f"desk closed - feed idle ({_fmt_age(age)})")
    # PRE-OPEN ARMING WINDOW (08:00-08:35 CT): the spot feed + sim daemon do not start
    # until ~08:26-08:28 CT, so a stale/missing live.json BEFORE the desk is armed is
    # idle-BY-DESIGN, not a dead daemon. This is a NEUTRAL state, never red -- flagging
    # it BAD (and self-healing) is the false alarm that scrambled the morning on 07-21/22.
    # Red must mean damage: only after 08:35 CT is a stale feed / missing gameplan a fault.
    now = chicago_now()
    armed_by = now.replace(hour=8, minute=35, second=0, microsecond=0)
    if now < armed_by:
        return _chk("Options sim", IDLE,
                    f"pre-open - desk arms by 08:35 CT (feed idle {_fmt_age(age)})")
    # 08:35 CT onward, market open: a dead daemon is a PAGE, not a shrug. On 2026-07-20 the
    # daemon failed at the 08:28 launch and nothing alerted - only a screenshot caught it.
    gp = ROOT / "data" / "options_sim" / f"gameplan_{now:%Y%m%d}.json"
    if not gp.exists():
        return _chk("Options sim", BAD,
                    f"NO GAMEPLAN for {now:%Y-%m-%d} - desk NOT armed")
    if age > 600:
        return _chk("Options sim", BAD,
                    f"sim daemon feed DEAD - live.json stale {_fmt_age(age)}")
    return _chk("Options sim", OK, f"{n} position(s), {_fmt_age(age)} ago")


def check_dashboard() -> dict:
    """The options desk web dashboard (:8600). On 2026-07-20 it crashed on a malformed
    trade record and stayed dead all session with nothing flagging it. Now it is a
    first-class health tile: if the port stops answering during desk hours, it is WARN
    (self-healed by alert_monitor). Off-hours a down dashboard is fine."""
    s = socket.socket()
    s.settimeout(1.5)
    try:
        s.connect(("127.0.0.1", 8600))
        return _chk("Options dashboard", OK, "serving :8600")
    except Exception:
        return _chk("Options dashboard", WARN if _desk_hours() else IDLE,
                    ":8600 not answering" + ("" if _desk_hours() else " (desk closed)"))
    finally:
        s.close()


def check_disk() -> dict:
    free = shutil.disk_usage(str(ROOT)).free / 1e9
    if free < 20:
        return _chk("Disk", BAD, f"{free:,.0f}GB free - recording will fail")
    if free < 60:
        return _chk("Disk", WARN, f"{free:,.0f}GB free")
    return _chk("Disk", OK, f"{free:,.0f}GB free")


def check_tasks() -> dict:
    """Scheduled jobs whose LAST run exited non-zero. Cached: the query costs ~1s and the
    answer changes at most a few times a day."""
    return _cached("tasks", 300, _check_tasks_uncached)


def _check_tasks_uncached() -> dict:
    # LastRunTime comes back too so a stale WEEKEND result is not reported as a failure:
    # the tasks are weekday-only now, but the last recorded result lingers until Monday.
    ps = ("Get-ScheduledTask | Where-Object {$_.TaskName -like 'MyQuant*'} | "
          "ForEach-Object { $i=$_|Get-ScheduledTaskInfo; "
          "[PSCustomObject]@{n=$_.TaskName;r=$i.LastTaskResult;"
          "d=(&{if($i.LastRunTime){[int]$i.LastRunTime.DayOfWeek}else{-1}})} } | ConvertTo-Json -Compress")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                              "-WindowStyle", "Hidden", "-Command", ps],
                             capture_output=True, text=True, timeout=45,
                             creationflags=_NOWIN).stdout.strip()
        rows = json.loads(out) if out else []
        if isinstance(rows, dict):
            rows = [rows]
    except Exception as e:
        return _chk("Scheduled tasks", WARN, f"query failed: {type(e).__name__}")
    # 267009 = currently running, 267011 = never run, 267014 = terminated (normal for the
    # long-running dashboard server), 0 = success. Day 0/6 = Sunday/Saturday -> ignore.
    ok_codes = (0, 267009, 267011, 267014)
    bad, weekend = [], 0
    for r in rows:
        if r.get("r") in ok_codes:
            continue
        if r.get("d") in (0, 6):
            weekend += 1
            continue
        bad.append(r["n"])
    note = f" ({weekend} stale weekend)" if weekend else ""
    if not bad:
        return _chk("Scheduled tasks", OK, f"{len(rows)} tasks, all clean{note}")
    # While the market is shut, a stale weekday failure is history, not a live problem, and
    # nothing is due to run - so report it without lighting the board amber all weekend.
    state = WARN if _desk_hours() else OK
    suffix = "" if state == WARN else " (desk closed - recheck at the open)"
    return _chk("Scheduled tasks", state,
                f"{len(bad)} failing{note}: " + ", ".join(b[8:] for b in bad[:4]) + suffix,
                failing=bad)


def check_archive() -> dict:
    """Is the irreplaceable depth data actually backed up OFF-MACHINE?

    A local parquet is not a backup - losing the drive loses it, and no vendor sells this
    history back. This verifies the private data repo exists, has a remote, and has no
    unpushed commits (off-machine copy up to date). Cached 5 min - it spawns git.
    """
    return _cached("archive", 300, _check_archive_uncached)


def _check_archive_uncached() -> dict:
    arch = Path.home() / "myquant-data"
    if not (arch / ".git").exists():
        return _chk("Data archive", WARN, "no archive repo - irreplaceable data not backed up")
    n = len(list((arch / "depth").glob("*.parquet"))) if (arch / "depth").exists() else 0

    def g(*a):
        return subprocess.run(["git", "-C", str(arch), *a], capture_output=True,
                              text=True, timeout=30, creationflags=_NOWIN)
    try:
        if not g("remote").stdout.strip():
            return _chk("Data archive", WARN,
                        f"{n} days LOCAL ONLY - no remote, not off-machine", n=n)
        # commits made locally but not yet pushed = off-machine copy is behind
        unpushed = g("rev-list", "--count", "@{u}..HEAD").stdout.strip()
        if unpushed and unpushed.isdigit() and int(unpushed) > 0:
            return _chk("Data archive", WARN,
                        f"{n} days archived, {unpushed} commit(s) UNPUSHED - backup behind", n=n)
        return _chk("Data archive", OK, f"{n} days backed up off-machine", n=n)
    except Exception as e:
        return _chk("Data archive", WARN, f"git check failed: {type(e).__name__}", n=n)


CHECKS = [check_depth, check_contract, check_footprint, check_nt8, check_tick_db, check_archive,
          check_ib_gateway, check_options_sim, check_dashboard, check_disk, check_tasks]


def health() -> dict:
    now = chicago_now()
    results = []
    for fn in CHECKS:
        try:
            results.append(fn())
        except Exception as e:
            results.append(_chk(fn.__name__, WARN, f"check error: {type(e).__name__}: {e}"))
    # Headline priority: a real problem wins, else if ANYTHING is actively working show OK
    # (green), and only fall to IDLE when everything is dormant. Without this the idle
    # desk items dragged the headline to grey while depth was recording green.
    states = {r["state"] for r in results}
    overall = (BAD if BAD in states else WARN if WARN in states
               else OK if OK in states else IDLE)
    return {"overall": overall, "market": market_state(now),
            "chicago": now.strftime("%Y-%m-%d %H:%M:%S"), "checks": results}


# ---------------------------------------------------------------- session clock
RTH_OPEN, RTH_CLOSE = dt.time(8, 30), dt.time(15, 15)   # ES regular hours, Chicago
# SPX/SPXW on Cboe. RTH ends 15:00 - FIFTEEN MINUTES BEFORE ES - which is also the prop
# flat-by rule and where options_trigger_daemon stops. GTH is the overnight session.
OPT_OPEN, OPT_CLOSE = dt.time(8, 30), dt.time(15, 0)
GTH_OPEN, GTH_CLOSE = dt.time(19, 0), dt.time(8, 15)


def session_info(now: dt.datetime | None = None) -> dict:
    """Which session we are in, and when the next RTH / ETH session starts.

    Returned as UTC epoch seconds so the browser can tick a countdown without
    re-deriving Chicago time (this PC runs Berlin - every clock question here has to be
    anchored to the exchange or it is 7h wrong).
    """
    now = now or chicago_now()
    mkt = market_state(now)
    if mkt == "open":
        session = "RTH" if (RTH_OPEN <= now.time() < RTH_CLOSE and now.weekday() < 5) else "ETH"
    else:
        session = mkt                      # 'closed' | 'halt'

    def _next_rth(frm: dt.datetime) -> dt.datetime:
        d = frm
        for _ in range(8):
            cand = d.replace(hour=RTH_OPEN.hour, minute=RTH_OPEN.minute,
                             second=0, microsecond=0)
            if d.weekday() < 5 and cand > frm:
                return cand
            d = (d + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return frm

    def _next_eth(frm: dt.datetime) -> dt.datetime:
        """Next time the market re-opens: 17:00 CT on a session-starting day."""
        d = frm
        for _ in range(8):
            cand = d.replace(hour=17, minute=0, second=0, microsecond=0)
            # Sun-Thu 17:00 starts a session; Friday 17:00 does not (weekend)
            if cand > frm and d.weekday() in (6, 0, 1, 2, 3):
                return cand
            d = (d + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return frm

    # ---- options (SPX/SPXW) session, tracked separately from futures ----
    wd, t = now.weekday(), now.time()
    if wd < 5 and OPT_OPEN <= t < OPT_CLOSE:
        opt = "RTH"
    elif (wd < 5 and t >= GTH_OPEN) or (wd == 6 and t >= GTH_OPEN) or          (wd < 5 and t < GTH_CLOSE):
        opt = "GTH"
    else:
        opt = "closed"

    def _next_at(frm: dt.datetime, hhmm: dt.time, weekdays=(0, 1, 2, 3, 4)) -> dt.datetime:
        d = frm
        for _ in range(9):
            cand = d.replace(hour=hhmm.hour, minute=hhmm.minute, second=0, microsecond=0)
            if cand > frm and d.weekday() in weekdays:
                return cand
            d = (d + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return frm

    return {
        "session": session,
        "opt_session": opt,
        "chicago_epoch": int(now.timestamp()),
        "next_rth_epoch": int(_next_rth(now).timestamp()),
        "next_eth_epoch": int(_next_eth(now).timestamp()),
        "rth_close_epoch": int(now.replace(hour=RTH_CLOSE.hour, minute=RTH_CLOSE.minute,
                                           second=0, microsecond=0).timestamp()),
        "next_opt_epoch": int(_next_at(now, OPT_OPEN).timestamp()),
        "opt_close_epoch": int(now.replace(hour=OPT_CLOSE.hour, minute=OPT_CLOSE.minute,
                                           second=0, microsecond=0).timestamp()),
        "next_gth_epoch": int(_next_at(now, GTH_OPEN, (6, 0, 1, 2, 3)).timestamp()),
    }


def next_process_epoch(ct_hhmm: str, now: dt.datetime | None = None) -> int:
    """Epoch seconds of the next weekday occurrence of a HH:MM Chicago time."""
    now = now or chicago_now()
    hh, mm = (int(x) for x in ct_hhmm.split(":"))
    d = now
    for _ in range(8):
        cand = d.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand > now and d.weekday() < 5:
            return int(cand.timestamp())
        d = (d + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(now.timestamp())


def task_status() -> dict:
    """taskname -> {result, last, next, day} for every MyQuant scheduled task.

    Cached for 60s: the Mission Control timeline asks for this on every poll and the
    Get-ScheduledTask query costs ~1s and spawns a console if unflagged."""
    return _cached("taskstatus", 60, _task_status_uncached)


def _task_status_uncached() -> dict:
    ps = ("Get-ScheduledTask | Where-Object {$_.TaskName -like 'MyQuant*'} | "
          "ForEach-Object { $i=$_|Get-ScheduledTaskInfo; [PSCustomObject]@{"
          "n=$_.TaskName; r=$i.LastTaskResult; "
          "l=(&{if($i.LastRunTime){$i.LastRunTime.ToString('yyyy-MM-dd HH:mm')}else{''}}); "
          "x=(&{if($i.NextRunTime){$i.NextRunTime.ToString('MM-dd HH:mm')}else{''}}); "
          "s=$_.State.ToString(); "
          "d=(&{if($i.LastRunTime){[int]$i.LastRunTime.DayOfWeek}else{-1}}) } } | ConvertTo-Json -Compress")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                              "-WindowStyle", "Hidden", "-Command", ps],
                             capture_output=True, text=True, timeout=45,
                             creationflags=_NOWIN).stdout.strip()
        rows = json.loads(out) if out else []
        if isinstance(rows, dict):
            rows = [rows]
    except Exception:
        return {}
    return {r["n"]: {"result": r.get("r"), "last": r.get("l", ""), "next": r.get("x", ""),
                     "day": r.get("d", -1), "tstate": r.get("s", "")} for r in rows}


if __name__ == "__main__":
    h = health()
    icon = {OK: "OK  ", WARN: "WARN", BAD: "BAD ", IDLE: "idle"}
    print(f"\noverall={h['overall'].upper()}   market={h['market']}   {h['chicago']} CT\n")
    for c in h["checks"]:
        print(f"  [{icon[c['state']]}] {c['name']:16s} {c['detail']}")
    print()
