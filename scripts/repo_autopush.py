"""repo_autopush.py — PC-side auto-push (S120).

Pushes any commits you've ALREADY MADE on the current branch to origin, so the laptop's
auto-pull stays current. It NEVER creates commits (we commit deliberately) — it only pushes
committed work. Safe to run on a timer; a no-op when there's nothing to push or no network.

STAY-ON-MAIN GUARD (2026-09-22): this script pushes `origin HEAD` — whatever branch is
checked out. That is exactly how the two-PC split happened: this PC sat on `leglab` while the
other pushed `main`, so each machine quietly pushed a different branch and they diverged for
two months. The guard below REFUSES to push when HEAD is not `main` and raises a loud
log + Telegram alert instead of silently propagating a stray branch. `main` is the single
trunk; every machine must stay on it. To deliberately work off-main, push by hand.

Windows Task Scheduler (once approved):
    schtasks /create /tn "MyQuant Repo AutoPush" /tr "python C:\\Users\\Admin\\myquant\\scripts\\repo_autopush.py" /sc minute /mo 10 /f

Logs -> data\\_catalog\\logs\\repo_autopush.log
"""
import datetime as dt
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "_catalog" / "logs" / "repo_autopush.log"
TRUNK = "main"

# scripts/ on path so `notify_telegram` imports whether run from repo root or elsewhere
sys.path.insert(0, str(ROOT / "scripts"))


def _alert(text):
    """Best-effort Telegram alert; never fatal if notify is unavailable."""
    try:
        from notify_telegram import send
        send(text, level="warn", dedup_key="autopush_off_main")
    except Exception as e:  # noqa: BLE001 — alerting must never break the push job
        log(f"(telegram alert failed: {e})")


def run(*args):
    return subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True)


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def main():
    br = run("git", "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if not br or br == "HEAD":
        log("skip: detached HEAD / not a repo")
        return
    if br != TRUNK:
        msg = (f"OFF-MAIN — refusing to auto-push branch '{br}'. Trunk is '{TRUNK}'. "
               f"Two-PC sync only works when every machine stays on '{TRUNK}'. "
               f"Run `git checkout {TRUNK}` here (and push '{br}' by hand if you meant to).")
        log(f"BLOCKED: {msg}")
        _alert(f"⚠️ repo_autopush BLOCKED on {ROOT.name}: {msg}")
        return
    p = run("git", "push", "origin", "HEAD")
    out = ((p.stderr or "") + (p.stdout or "")).strip()
    if p.returncode != 0:
        log(f"push FAILED ({br}): {out[:200]}")
    elif not out or "up-to-date" in out.lower() or "up to date" in out.lower():
        log(f"up to date ({br})")
    else:
        last = out.splitlines()[-1].strip() if out.splitlines() else out
        log(f"pushed ({br}): {last[:140]}")


if __name__ == "__main__":
    main()
