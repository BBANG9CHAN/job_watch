@echo off
chcp 65001 > nul
set PYTHONIOENCODING=utf-8
cd /d %~dp0

REM ------------------------------------------------
REM  Job Watch - run in this console window (close = stop)
REM  To run in background without a window: start_hidden.vbs
REM ------------------------------------------------

if not exist .venv\Scripts\python.exe (
    echo [setup] creating venv and installing packages...
    python -m venv .venv
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)
if not exist .env copy .env.example .env > nul

.venv\Scripts\python.exe run.py
pause
