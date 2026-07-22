# push.ps1 - push local myquant commits to origin/main.
# Run this yourself in a normal PowerShell window (not via the Claude Code
# sandbox) - Git Credential Manager needs your real desktop/login session to
# authenticate against github.com.

Set-Location $PSScriptRoot

git fetch origin

$ahead = git rev-list --count origin/main..HEAD
$behind = git rev-list --count HEAD..origin/main

if ($behind -gt 0) {
    Write-Host "origin/main is $behind commit(s) ahead of local HEAD - pull/rebase before pushing." -ForegroundColor Yellow
    exit 1
}

if ($ahead -eq 0) {
    Write-Host "Nothing to push - local main matches origin/main." -ForegroundColor Green
    exit 0
}

Write-Host "Pushing $ahead commit(s) to origin/main..." -ForegroundColor Cyan
git push origin main

Read-Host "Press Enter to close"
