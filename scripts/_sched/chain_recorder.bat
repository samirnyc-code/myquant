@echo off
"C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\run_at_ct.py" --at 08:25 -- "C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\chain_recorder_supervisor.py" --stop 15:05 --secs 10 >> "C:\Users\Admin\myquant\data\options_sim\chain_recorder_sched.log" 2>&1
