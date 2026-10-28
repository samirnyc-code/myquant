' Runs a .bat file with its console window fully hidden, waiting for it to finish.
' Used by Task Scheduler actions that used to call cmd.exe directly (which always
' flashes a visible console window on the desktop even when launched by the scheduler).
' This keeps the task in the normal interactive session (so GUI-dependent payloads like
' IBC Gateway login still work) -- it only hides the console chrome of this one process.
'
' Usage: wscript.exe run_hidden.vbs "<path to .bat file>"
Set objShell = CreateObject("WScript.Shell")
objShell.Run """" & WScript.Arguments(0) & """", 0, True
