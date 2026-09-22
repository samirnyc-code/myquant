#!/usr/bin/env bash
# repo_autopull.sh — laptop-side (macOS) auto-pull (S120).
#
# Fast-forward-pulls every git repo under ~/github so the laptop stays current with what the
# PC pushes. Uses --ff-only so it NEVER makes merge commits; if a repo has diverged it logs
# the conflict and leaves it for you to resolve by hand (laptop is read-mostly).
#
# Manual run:   bash ~/github/myquant/scripts/repo_autopull.sh
# Automatic:    load com.myquant.autopull.plist via launchd (see two_machine_sync.md).
#
# Override the folder scanned with:  GHDIR=/some/path bash repo_autopull.sh
set -u
GHDIR="${GHDIR:-$HOME/github}"
LOG="$HOME/.myquant_sync_pull.log"
ts() { date "+%Y-%m-%d %H:%M:%S"; }

[ -d "$GHDIR" ] || { echo "[$(ts)] no dir $GHDIR" >> "$LOG"; exit 0; }

for d in "$GHDIR"/*/; do
  [ -d "${d}.git" ] || continue
  name=$(basename "$d")
  git -C "$d" fetch --quiet 2>/dev/null
  out=$(git -C "$d" pull --ff-only 2>&1)
  echo "[$(ts)] ${name}: $(echo "$out" | tail -1)" >> "$LOG"
done
