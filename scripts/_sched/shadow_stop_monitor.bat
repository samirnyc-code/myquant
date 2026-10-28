@echo off
"C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\run_at_ct.py" --at 08:35 -- "C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\shadow_stop_monitor.py" --loop --secs 120 --stop 15:10 >> "C:\Users\Admin\myquant\data\options_sim\shadow_stop_sched.log" 2>&1
