<#
nt8_login.ps1 — launch NT8 and type the stored credentials into the login window.

Run scripts\nt8_cred_set.ps1 ONCE first to store the login (DPAPI-encrypted).

    powershell -ExecutionPolicy Bypass -File scripts\nt8_login.ps1

EXIT 0 = Control Center reached (really logged in)
     1 = failed / timed out
     2 = NinjaTrader.exe or stored credential missing

The password is decrypted in memory only, typed into the login window, and never
logged or written anywhere. UI automation is inherently fragile: if NT8 changes its
login layout this breaks, which is why success is verified by the Control Center
appearing, not by "we sent the keystrokes".
#>
[CmdletBinding()]
param(
    [int]$TimeoutSec = 300,
    [string]$ExePath = 'C:\Program Files\NinjaTrader 8\bin\NinjaTrader.exe',
    [string]$CredPath = "$env:LOCALAPPDATA\myquant\nt8_cred.xml",
    [string]$ReadyWindowPattern = 'Control Center'
)

function Say($m) { "{0:HH:mm:ss}  {1}" -f (Get-Date), $m }

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

function Get-NT8Windows {
    $p = Get-Process NinjaTrader -ErrorAction SilentlyContinue
    if (-not $p) { return @() }
    $p | ForEach-Object { $_.Refresh(); $_ } | Where-Object { $_.MainWindowTitle } |
        ForEach-Object { [PSCustomObject]@{ Id = $_.Id; Title = $_.MainWindowTitle; Handle = $_.MainWindowHandle } }
}

function Test-Ready { @(Get-NT8Windows | Where-Object { $_.Title -match $ReadyWindowPattern }).Count -gt 0 }

# --- already logged in? ------------------------------------------------------
if (Test-Ready) { Say "already at Control Center - nothing to do"; exit 0 }

if (-not (Test-Path $ExePath))  { Say "NinjaTrader.exe not found: $ExePath"; exit 2 }
if (-not (Test-Path $CredPath)) { Say "no stored credential - run scripts\nt8_cred_set.ps1 first"; exit 2 }

$cred = Import-Clixml $CredPath
$user = $cred.UserName

# --- start if needed ---------------------------------------------------------
if (-not (Get-Process NinjaTrader -ErrorAction SilentlyContinue)) {
    Say "starting NT8"
    Start-Process -FilePath $ExePath -WorkingDirectory (Split-Path $ExePath) | Out-Null
}

# --- wait for the login window ----------------------------------------------
$deadline = (Get-Date).AddSeconds($TimeoutSec)
$login = $null
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    if (Test-Ready) { Say "Control Center already up (saved session) - no login needed"; exit 0 }
    $w = Get-NT8Windows | Where-Object { $_.Title -notmatch $ReadyWindowPattern } | Select-Object -First 1
    if ($w) { $login = $w; break }
}
if (-not $login) { Say "no login window appeared within ${TimeoutSec}s"; exit 1 }
Say "login window: '$($login.Title)'"

# --- fill it via UI Automation ----------------------------------------------
Start-Sleep -Seconds 2
$root = [System.Windows.Automation.AutomationElement]::FromHandle($login.Handle)
if (-not $root) { Say "cannot attach to login window"; exit 1 }

$edits = $root.FindAll(
    [System.Windows.Automation.TreeScope]::Descendants,
    (New-Object System.Windows.Automation.PropertyCondition(
        [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
        [System.Windows.Automation.ControlType]::Edit)))

Say "found $($edits.Count) input field(s)"
if ($edits.Count -lt 2) {
    Say "expected >=2 fields (user, password) - layout not as expected, aborting"
    Say "nothing was typed. Log in manually this once and re-run to recalibrate."
    exit 1
}

function Set-Field($el, [string]$text) {
    try {
        $vp = $el.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
        $vp.SetValue($text); return $true
    } catch {
        # password boxes often refuse ValuePattern -> focus and type
        try { $el.SetFocus(); Start-Sleep -Milliseconds 200
              [System.Windows.Forms.SendKeys]::SendWait($text); return $true } catch { return $false }
    }
}

$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
         [Runtime.InteropServices.Marshal]::SecureStringToBSTR($cred.Password))
try {
    $okU = Set-Field $edits.Item(0) $user
    $okP = Set-Field $edits.Item(1) $plain
    Say "filled user=$okU pass=$okP"
} finally {
    $plain = $null; [GC]::Collect()          # do not leave the password in memory
}

# submit
$edits.Item(1).SetFocus()
Start-Sleep -Milliseconds 300
[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
Say "submitted - waiting for Control Center"

# --- verify by RESULT, not by "we sent keys" ---------------------------------
$deadline = (Get-Date).AddSeconds($TimeoutSec)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 3
    if (Test-Ready) { Say "OK - Control Center up"; exit 0 }
}
Say "FAILED: no '$ReadyWindowPattern' after login attempt. Titles now: $((Get-NT8Windows | ForEach-Object Title) -join ' | ')"
exit 1
