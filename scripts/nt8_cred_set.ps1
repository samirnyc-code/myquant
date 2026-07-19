<#
nt8_cred_set.ps1 — store the NT8 login once, encrypted. Run this ONCE, interactively.

The password is encrypted with Windows DPAPI (CurrentUser scope): only YOUR Windows
account on THIS machine can decrypt it. It is never written in plaintext, never printed,
and the file it writes is gitignored.

    powershell -ExecutionPolicy Bypass -File scripts\nt8_cred_set.ps1
#>
$dir = "$env:LOCALAPPDATA\myquant"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$out = Join-Path $dir 'nt8_cred.xml'

Write-Host "NT8 login (NinjaTrader Account Dashboard credentials)"
$cred = Get-Credential -Message 'NinjaTrader account login'
if (-not $cred) { Write-Host 'cancelled'; exit 1 }

$cred | Export-Clixml -Path $out          # DPAPI-encrypted, CurrentUser scope
Write-Host "saved: $out"
Write-Host "user : $($cred.UserName)"
Write-Host "(password encrypted - only this Windows account on this PC can read it)"
