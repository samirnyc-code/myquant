# nt8_compile_check.ps1 — pre-flight compile check for our NT8 NinjaScript files
# WITHOUT touching the running NinjaTrader install (output goes to %TEMP%).
#
# Usage:  powershell -File scripts\nt8_compile_check.ps1 [path\to\File.cs ...]
#         (no args = check every .cs under nt8\indicators and nt8\strategies)
#
# Compiles against the real NT8 assemblies with the .NET Framework 4.8 csc
# (C# 5 — fine for our files; NT's own F5 uses Roslyn). Types that already
# exist inside NinjaTrader.Custom.dll surface as CS0436 warnings, not errors,
# which is why warnings are suppressed: only genuine compile ERRORS matter.
# NOTE: NT's F5 additionally generates wrapper code (Indicators/Strategies
# constructors in sibling namespaces); errors that only occur inside those
# generated wrappers (e.g. custom enums not visible from the wrapper
# namespace) are NOT caught here — keep custom enums in namespace
# NinjaTrader.NinjaScript to stay safe.

param([string[]]$Files)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (-not $Files -or $Files.Count -eq 0) {
    $Files = Get-ChildItem -Path (Join-Path $repo 'nt8\indicators'), (Join-Path $repo 'nt8\strategies') -Filter *.cs -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName }
}

$csc = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$out = Join-Path $env:TEMP ('ntcheck_' + [Guid]::NewGuid().ToString('N').Substring(0,8) + '.dll')

$refs = @(
    'C:\Program Files\NinjaTrader 8\bin\NinjaTrader.Core.dll',
    'C:\Program Files\NinjaTrader 8\bin\NinjaTrader.Gui.dll',
    'C:\Users\Admin\Documents\NinjaTrader 8\bin\Custom\NinjaTrader.Custom.dll',
    'C:\Program Files\NinjaTrader 8\bin\SharpDX.dll',
    'C:\Program Files\NinjaTrader 8\bin\SharpDX.Direct2D1.dll',
    'System.dll', 'System.Core.dll', 'System.Xml.dll',
    'System.ComponentModel.DataAnnotations.dll', 'System.Drawing.dll',
    'System.Windows.Forms.dll', 'WindowsBase.dll', 'PresentationCore.dll',
    'PresentationFramework.dll', 'System.Xaml.dll'
)

$args = @('/nologo', '/t:library', '/warn:0', "/out:$out",
          '/lib:C:\Windows\Microsoft.NET\Framework64\v4.0.30319\WPF')
foreach ($r in $refs) { $args += "/r:$r" }
$args += $Files

& $csc $args
$code = $LASTEXITCODE
if (Test-Path $out) { Remove-Item $out -Force }
if ($code -eq 0) {
    Write-Output ("COMPILE_OK: " + (($Files | ForEach-Object { Split-Path $_ -Leaf }) -join ', '))
} else {
    Write-Output "COMPILE_FAILED (exit $code)"
}
exit $code
