@echo off
"C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\run_at_ct.py" --at 08:30 -- "C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\skew_condor_shadow.py" --live >> "C:\Users\Admin\myquant\data\options_sim\skew_condor_sched.log" 2>&1
