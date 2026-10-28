@echo off
"C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\run_at_ct.py" --at 05:30 -- cmd.exe /c C:\IBC\StartGateway.bat /INLINE >> "C:\Users\Admin\myquant\data\options_sim\gateway_login_sched.log" 2>&1
