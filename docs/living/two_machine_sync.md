# Two-machine sync (PC ⇄ laptop) — setup

Goal: everything you **commit** on the PC shows up on the laptop automatically, hands-off.
Git only moves **committed** work — so keep committing deliberately; uncommitted edits don't
travel. Big data (tick DB, NT8 files, logs) is NOT synced (git-ignored, PC-only, by design).

## PC (Windows) — auto-push committed work
`scripts/repo_autopush.py` pushes any commits on the current branch to origin. It never makes
commits; it only pushes what you've committed. Enable as a scheduled task (every 10 min):

```
schtasks /create /tn "MyQuant Repo AutoPush" /tr "python C:\Users\Admin\myquant\scripts\repo_autopush.py" /sc minute /mo 10 /f
```
Disable:  `schtasks /delete /tn "MyQuant Repo AutoPush" /f`
Log:      `data\_catalog\logs\repo_autopush.log`

(Extend to other PC repos by duplicating the task with a copy of the script placed in each repo.)

## Laptop (macOS) — auto-pull every repo
`scripts/repo_autopull.sh` fast-forward-pulls every repo under `~/github` every 10 min +
at login, via launchd. `--ff-only` = never a merge commit; conflicts are logged, not forced.

One-time setup on the laptop (after cloning into `~/github/`):
```
cp ~/github/myquant/scripts/com.myquant.autopull.plist ~/Library/LaunchAgents/
# edit the path in the plist if your username is not "nuy"
launchctl load ~/Library/LaunchAgents/com.myquant.autopull.plist
```
Stop:  `launchctl unload ~/Library/LaunchAgents/com.myquant.autopull.plist`
Log:   `~/.myquant_sync_pull.log`

## The habit that makes it work
Commit on the PC when you finish a unit of work → the PC task pushes within ~10 min → the
laptop pulls within ~10 min. So the laptop is always current with committed work, no clicks.

## What is NOT synced (on purpose)
- The recording DB / tick data / NT8 database / logs — too large; PC-only where NT runs.
- This Claude Code chat history — machine-local (the work it produced syncs via git).
- Uncommitted edits — commit them to sync.
