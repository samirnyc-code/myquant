@echo off
"C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\run_at_ct.py" --at 07:05 -- "C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\options_gameplan.py" --force >> "C:\Users\Admin\myquant\data\options_sim\gameplan_early.log" 2>&1
