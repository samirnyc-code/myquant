<#
nt8_cred_set.ps1 — store the NT8 login once, encrypted. Run this ONCE, interactively.

Prompts IN THE CONSOLE (Get-Credential opens a popup that hides behind other windows
and looks like a hang - 2026-07-19).

The password is encrypted with Windows DPAPI (CurrentUser scope): only YOUR Windows
account on THIS machine can decrypt it. Never written in plaintext, never printed,
and the file is gitignored.

    powershell -ExecutionPolicy Bypass -File scripts\nt8_cred_set.ps1
#>
$dir = "$env:LOCALAPPDATA\myquant"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$out = Join-Path $dir 'nt8_cred.xml'

Write-Host ''
Write-Host 'NT8 login - NinjaTrader Account Dashboard credentials' -ForegroundColor Cyan
Write-Host ''

$user = Read-Host 'Username'
if ([string]::IsNullOrWhiteSpace($user)) { Write-Host 'no username - aborted' -ForegroundColor Red; exit 1 }

$pass = Read-Host 'Password' -AsSecureString
if (-not $pass -or $pass.Length -eq 0) { Write-Host 'no password - aborted' -ForegroundColor Red; exit 1 }

$cred = New-Object System.Management.Automation.PSCredential($user, $pass)
$cred | Export-Clixml -Path $out          # DPAPI-encrypted, CurrentUser scope

Write-Host ''
Write-Host "saved: $out" -ForegroundColor Green
Write-Host "user : $user"
Write-Host '(password encrypted - only this Windows account on this PC can read it)'
