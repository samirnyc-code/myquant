"""nt8_maintenance.py — restart NT8 in the daily halt and prove it is armed again.

Runs in the CME maintenance break (16:00-17:00 CT). NT8 leaks memory over multi-day
sessions, so a two-week unattended recording run needs a scheduled restart — and the halt
is the only hour where restarting costs no data.

THE TRAP THIS EXISTS FOR: restarting NT8 (or recompiling) DISABLES enabled strategies.
That happened twice on 2026-07-19 — the depth recorder sat disabled and the Control Center
looked perfectly healthy. So this does not just restart; it verifies afterwards that book
rows are actually arriving, and shouts if they are not.

    python scripts/nt8_maintenance.py                # restart + verify
    python scripts/nt8_maintenance.py --verify-only  # no restart, just check
    python scripts/nt8_maintenance.py --no-restart --wait 300

EXIT 0 = NT8 up and depth rows arriving (or market legitimately shut)
     1 = needs a human: NT8 down, or up but recording nothing
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
NOWIN = 0x08000000
NT8 = Path(os.environ["USERPROFILE"]) / "Documents" / "NinjaTrader 8"


def say(m):
    print(f"{dt.datetime.now():%H:%M:%S}  {m}", flush=True)


def _ping(text, level="info"):
    try:
        import notify_telegram as tg
        tg.send(text, level=level)
    except Exception:
        pass


def depth_size() -> int:
    """Total live depth bytes across the candidate days. Files carry the FULL contract
    (ES_09-26_depth_) and the TRADE DATE (session template: after 17:00 CT the live file
    is dated tomorrow), so glob by contract and scan -1/0/+1 — the old fixed 'ES_depth_'
    pattern matched nothing and made this silently return 0 (2026-07-20 fix)."""
    import pipeline_health as ph
    now = ph.chicago_now()
    tot = 0
    depth = ROOT / "data" / "depth"
    for d in (-1, 0, 1):
        day = (now.date() + dt.timedelta(days=d)).isoformat()
        for p in depth.glob(f"ES*_depth_{day}.csv"):
            tot += p.stat().st_size
    return tot


def nt8_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq NinjaTrader.exe"],
                             capture_output=True, text=True, timeout=20,
                             creationflags=NOWIN).stdout
        return "NinjaTrader.exe" in out
    except Exception:
        return False


def _save_workspace_hint() -> None:
    """Ask NT8 to persist the workspace BEFORE we close it, so a restart never eats the
    user's chart drawings and extra tabs (2026-07-20: a forced kill lost all of them).

    NT8 saves the workspace on a CLEAN exit; the danger is ONLY the force-kill path. We
    cannot press its menu from here, so the real guarantees are (a) the settings the user
    enabled once — Tools>Options>General 'Save workspaces on exit' + restore last workspace
    — and (b) NEVER force-killing except as an explicit, logged last resort below."""
    say("relying on NT8 clean-exit workspace save (force-kill is avoided below)")


NT_WORKSPACES = Path.home() / "Documents" / "NinjaTrader 8" / "workspaces"


def _newest_workspace_mtime() -> float:
    """Newest mtime across all workspace XMLs. NT8 rewrites the ACTIVE workspace (with its
    chart drawings) on a CLEAN exit, so this value ADVANCING after close = drawings saved.
    ReopenWorkspaces=false only stops the reload-all on startup; it does NOT stop the save."""
    try:
        return max((p.stat().st_mtime for p in NT_WORKSPACES.glob("*.xml")), default=0.0)
    except Exception:
        return 0.0


def restart(force_ok: bool = False) -> bool:
    """Restart NT8 while PRESERVING the workspace (drawings, extra tabs) and re-arming the
    recorder afterwards.

    A plain `taskkill` sends WM_CLOSE, which NT8 answers with a 'strategies are running'
    confirmation dialog and then SITS THERE. The old code waited 60s, force-killed, and so
    lost every unsaved drawing and left the strategy disabled. Now:
      1. hint a workspace save,
      2. graceful close, generous 120s grace for NT to flush its workspace,
      3. force-kill ONLY if explicitly allowed AND still hung — and shout that drawings
         since the last auto-save may be lost,
      4. relaunch via the scripted login,
      5. (caller) verify the recorder re-armed and PAGE if not.
    """
    if nt8_running():
        _save_workspace_hint()
        ws_before = _newest_workspace_mtime()   # to VERIFY the clean exit actually saved drawings
        say("closing NT8 (graceful — waiting for clean workspace save)")
        subprocess.run(["taskkill", "/IM", "NinjaTrader.exe"], capture_output=True,
                       timeout=60, creationflags=NOWIN)
        for _ in range(40):                 # 120s: give NT time to save + answer its dialog
            time.sleep(3)
            if not nt8_running():
                time.sleep(2)               # let NT finish flushing the workspace XML to disk
                if _newest_workspace_mtime() > ws_before:
                    say("NT8 closed cleanly — workspace SAVED (verified: workspace XML updated)")
                else:
                    say("⚠ NT8 closed but NO workspace XML updated — drawings may NOT be saved")
                    _ping("⚠️ NT8 closed on restart but its workspace file did not update — chart "
                          "drawings may not have saved. Verify on next launch before drawing more.", "warn")
                break
        if nt8_running():
            if not force_ok:
                say("NT8 did NOT close cleanly and force-kill is DISABLED (would lose "
                    "unsaved drawings). Leaving NT8 up — a human should close it.")
                _ping("🔴 NT8 restart aborted: it would not close cleanly and I refuse to "
                      "force-kill (that loses your chart drawings). NT8 left running.", "alert")
                return False
            say("NT8 still hung - FORCE killing (drawings since last auto-save may be lost)")
            _ping("⚠️ NT8 had to be force-killed on restart — drawings since the last "
                  "workspace auto-save may be lost.", "warn")
            subprocess.run(["taskkill", "/IM", "NinjaTrader.exe", "/F"], capture_output=True,
                           timeout=60, creationflags=NOWIN)
            time.sleep(5)
    say("starting NT8 (scripted login)")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                        "-ExecutionPolicy", "Bypass", "-File",
                        str(ROOT / "scripts" / "nt8_login.ps1")],
                       capture_output=True, text=True, timeout=600, creationflags=NOWIN)
    for line in (r.stdout or "").strip().splitlines()[-4:]:
        say("  " + line.strip())
    return r.returncode == 0


def _armed_state():
    """(armed, detail) — is the depth recorder ready for the open? Checkable while shut.

    Reads the NT8 log for the most recent Enabling/Disabling of MarketDepthRecorder and the
    latest connection state. 'Enabled and connected' == armed.
    """
    import pipeline_health as ph
    if not nt8_running():
        return False, "NT8 not running"
    logs = sorted((NT8 / "log").glob("log.*.txt"), key=lambda p: p.stat().st_mtime)
    if not logs:
        return False, "NT8 up, no log"
    txt = logs[-1].read_text(encoding="utf-8", errors="ignore")
    lines = txt.splitlines()
    enabled = None
    connected = None
    for ln in lines:
        if "MarketDepthRecorder" in ln and "Enabling" in ln:
            enabled = True
        elif "MarketDepthRecorder" in ln and "Disabling" in ln:
            enabled = False
        if "Price feed=Connected" in ln:
            connected = True
        elif "Price feed=Connection lost" in ln or "Price feed=Disconnected" in ln:
            connected = False
    if enabled is None:
        return False, "recorder never enabled this session"
    if enabled is False:
        return False, "recorder is DISABLED"
    if connected is False:
        return False, "recorder enabled but feed DISCONNECTED"
    return True, "NT8 up · recorder enabled · feed connected"


def verify(wait_s: int) -> bool:
    """Depth rows must actually be ARRIVING. 'NT8 is running' proves nothing — that is
    exactly what a disabled strategy looks like."""
    import pipeline_health as ph
    mkt = ph.market_state()
    if mkt != "open":
        # Before the open there is no data to watch grow — but "recorder armed?" IS
        # checkable, and it is the whole point of a PRE-open check. Verify NT8 is up, the
        # strategy is enabled, and the feed is connected, from the NT8 log. A trivial
        # silent pass here is what let the disabled-strategy failure through twice.
        armed, detail = _armed_state()
        if armed:
            say(f"pre-open ({mkt}): {detail}")
            _ping(f"✅ Pre-open check — recorder ARMED for the open. {detail}", "ok")
            return True
        say(f"pre-open ({mkt}): NOT ARMED — {detail}")
        _ping(f"🔴 Pre-open check — recorder NOT armed: {detail}. "
              "Enable MarketDepthRecorder in Control Center before the open.", "alert")
        return False
    say(f"watching the depth file for {wait_s}s …")
    a = depth_size()
    time.sleep(wait_s)
    b = depth_size()
    grew = b - a
    if grew > 0:
        say(f"OK - depth grew {grew/1024:,.0f} KB in {wait_s}s")
        _ping(f"✅ Pre-open check PASSED — depth growing (+{grew/1024:,.0f} KB in {wait_s}s), "
              "recorder armed for the open.", "ok")
        return True
    say("FAILED - market is OPEN but the depth file is NOT growing.")
    say("         Control Center -> Strategies -> MarketDepthRecorder must be ENABLED")
    say("         (a restart or recompile disables it).")
    _ping("🔴 Pre-open check FAILED — market open but depth NOT growing. Recorder likely "
          "disabled (a restart/recompile disables it). Enable it in Control Center.", "alert")
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--no-restart", action="store_true")
    ap.add_argument("--allow-force-kill", action="store_true",
                    help="permit a last-resort force-kill if NT8 will not close (RISKS "
                         "losing chart drawings since the last workspace save)")
    ap.add_argument("--wait", type=int, default=90, help="seconds to watch for growth")
    a = ap.parse_args()

    ok = True
    if not (a.verify_only or a.no_restart):
        ok = restart(force_ok=a.allow_force_kill)
        if not ok:
            say("restart FAILED - not proceeding to verify")
            return 1
    if not nt8_running():
        say("NT8 is not running")
        return 1
    return 0 if verify(a.wait) else 1


if __name__ == "__main__":
    sys.exit(main())
