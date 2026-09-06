@echo off
setlocal
python build_exe.py
if errorlevel 1 pause
