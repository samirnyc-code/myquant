@echo off
"C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\run_at_ct.py" --at 08:29 -- "C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\options_trigger_daemon.py" --until 15:00 >> "C:\Users\Admin\myquant\data\options_sim\trigger_daemon_sched.log" 2>&1
