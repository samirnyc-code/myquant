@echo off
"C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\run_at_ct.py" --at 08:32 -- "C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\deadman_0832.py" >> "C:\Users\Admin\myquant\data\options_sim\deadman.log" 2>&1
