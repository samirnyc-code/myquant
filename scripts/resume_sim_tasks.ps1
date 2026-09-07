# One-shot resume: re-enable the sim tasks paused for the 2026-09-07 US market
# holiday (Labor Day), then unregister the one-time task that ran this.
# Registered to fire 2026-09-08 06:00 machine-time, well before Gameplan Early.
$ErrorActionPreference = 'Continue'
$log = Join-Path $PSScriptRoot '..\data\options_sim\resume_sim_tasks.log'
$tasks = 'MyQuant Trigger Daemon', 'MyQuant Chain Recorder', 'MyQuant Spot Feed'
foreach ($t in $tasks) {
    try {
        Enable-ScheduledTask -TaskName $t -ErrorAction Stop | Out-Null
        $s = (Get-ScheduledTask -TaskName $t).State
        Add-Content $log ("{0}  ENABLED {1} -> {2}" -f (Get-Date -Format s), $t, $s)
    } catch {
        Add-Content $log ("{0}  FAILED  {1} -> {2}" -f (Get-Date -Format s), $t, $_.Exception.Message)
    }
}
# remove this one-time resume task so it does not linger
try { Unregister-ScheduledTask -TaskName 'MyQuant Resume 20260908' -Confirm:$false -ErrorAction Stop }
catch { Add-Content $log ("{0}  unregister-self failed: {1}" -f (Get-Date -Format s), $_.Exception.Message) }
