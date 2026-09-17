"""repo_autopush.py — PC-side auto-push (S120).

Pushes any commits you've ALREADY MADE on the current branch to origin, so the laptop's
auto-pull stays current. It NEVER creates commits (we commit deliberately) — it only pushes
committed work. Safe to run on a timer; a no-op when there's nothing to push or no network.

Windows Task Scheduler (once approved):
    schtasks /create /tn "MyQuant Repo AutoPush" /tr "python C:\\Users\\Admin\\myquant\\scripts\\repo_autopush.py" /sc minute /mo 10 /f

Logs -> data\\_catalog\\logs\\repo_autopush.log
"""
import datetime as dt
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "data" / "_catalog" / "logs" / "repo_autopush.log"


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
