@echo off
"C:\Users\Admin\myquant\.venv\Scripts\python.exe" -u "C:\Users\Admin\myquant\scripts\run_at_ct.py" --at 08:26 -- "C:\Users\Admin\myquant\.venv\Scripts\python.exe" "C:\Users\Admin\myquant\scripts\spot_feed.py" >> "C:\Users\Admin\myquant\data\options_sim\spot_feed_sched.log" 2>&1
