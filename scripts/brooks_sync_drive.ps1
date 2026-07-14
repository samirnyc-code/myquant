# Sync the Brooks Codex from the repo to the Google Drive folder.
# Run after any rebuild; other machines get it via normal Drive sync.
#   powershell -File scripts\brooks_sync_drive.ps1
$src = "c:\Users\Admin\myquant\docs\living\brooks_codex"
$dst = "G:\My Drive\Brooks Codex"
if (-not (Test-Path $dst)) { Write-Error "Drive folder not found: $dst"; exit 1 }
python "c:\Users\Admin\myquant\scripts\brooks_font_ctl.py"
robocopy $src $dst /E /XO /R:2 /W:3 /NP /NDL /NFL
if ($LASTEXITCODE -le 7) { Write-Host "Sync OK ($LASTEXITCODE)"; exit 0 } else { exit $LASTEXITCODE }
