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
    """'open' | 'halt' | 'closed' - CME Globex equity index futures."""
    now = now or chicago_now()
    wd, t = now.weekday(), now.time()
    if wd == 5:
        return "closed"
    if wd == 6:
        return "open" if t >= dt.time(17, 0) else "closed"
    if wd == 4 and t >= dt.time(16, 0):
        return "closed"
    if dt.time(16, 0) <= t < dt.time(17, 0):
        return "halt"
    return "open"


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
    files = [p for p in (DEPTH_DIR / f"ES_depth_{(now.date()+dt.timedelta(days=d)).isoformat()}.csv"
                         for d in (-1, 0)) if p.exists()]
    if not files:
        return _chk("L2 depth", BAD if mkt == "open" else IDLE,
                    "no file for today" if mkt == "open" else f"market {mkt}")
    mb = sum(f.stat().st_size for f in files) / 1e6
    age = min(_age(f) for f in files)
    if mkt in ("closed", "halt"):
        return _chk("L2 depth", IDLE, f"{mb:,.0f}MB - market {mkt}", mb=round(mb, 1))
    if age > 180:
        return _chk("L2 depth", BAD, f"STALLED {_fmt_age(age)} - data being lost", mb=round(mb, 1))
    return _chk("L2 depth", OK, f"{mb:,.0f}MB, {_fmt_age(age)} ago", mb=round(mb, 1))


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
    fp = sorted(FOOTPRINT_DIR.glob("*_footprint_*.csv"))
    if not fp:
        legacy = FOOTPRINT_DIR / "ES_footprint.csv"
        if legacy.exists():
            return _chk("Footprint", WARN if market_state() == "open" else IDLE,
                        f"legacy file only, {_fmt_age(_age(legacy))} ago")
        return _chk("Footprint", IDLE, "no stamped file yet")
    newest = fp[-1]
    age = _age(newest)
    mkt = market_state()
    if mkt == "open" and age > 900:
        return _chk("Footprint", WARN, f"{newest.name} stale {_fmt_age(age)}")
    return _chk("Footprint", OK if mkt == "open" else IDLE, f"{newest.name} ({_fmt_age(age)})")


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


def check_ib_gateway() -> dict:
    """Login != API port. Port 4002 answering is the only proof (S75 incident)."""
    s = socket.socket()
    s.settimeout(1.5)
    try:
        s.connect(("127.0.0.1", 4002))
        return _chk("IB gateway", OK, "port 4002 answering")
    except Exception:
        return _chk("IB gateway", WARN, "port 4002 not answering")
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
    if mkt != "open":
        return _chk("Options sim", IDLE, f"market {mkt} - feed idle ({_fmt_age(age)})")
    if age > 3600:
        return _chk("Options sim", WARN, f"live.json stale {_fmt_age(age)}")
    return _chk("Options sim", OK, f"{n} position(s), {_fmt_age(age)} ago")


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
    return _chk("Scheduled tasks", WARN,
                f"{len(bad)} failing{note}: " + ", ".join(b[8:] for b in bad[:4]), failing=bad)


CHECKS = [check_depth, check_contract, check_footprint, check_nt8, check_tick_db,
          check_ib_gateway, check_options_sim, check_disk, check_tasks]


def health() -> dict:
    now = chicago_now()
    results = []
    for fn in CHECKS:
        try:
            results.append(fn())
        except Exception as e:
            results.append(_chk(fn.__name__, WARN, f"check error: {type(e).__name__}: {e}"))
    worst = max(results, key=lambda r: RANK[r["state"]])["state"] if results else IDLE
    return {"overall": worst, "market": market_state(now),
            "chicago": now.strftime("%Y-%m-%d %H:%M:%S"), "checks": results}


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
    return {r["n"]: {"result": r.get("r"), "last": r.get("l", ""),
                     "next": r.get("x", ""), "day": r.get("d", -1)} for r in rows}


if __name__ == "__main__":
    h = health()
    icon = {OK: "OK  ", WARN: "WARN", BAD: "BAD ", IDLE: "idle"}
    print(f"\noverall={h['overall'].upper()}   market={h['market']}   {h['chicago']} CT\n")
    for c in h["checks"]:
        print(f"  [{icon[c['state']]}] {c['name']:16s} {c['detail']}")
    print()
