@echo off
"C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\run_at_ct.py" --at 19:05 -- "C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\gexlog_evening.py" >> "C:\Users\Admin\myquant\data\options_sim\evening_sched.log" 2>&1
