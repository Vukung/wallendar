@echo off
:: ============================================================
:: setup_task_scheduler.bat
:: Registers TWO Windows Task Scheduler tasks:
::
::   1. WallendarDailyUpdate  — fires every day at 12:00 AM (midnight)
::   2. WallendarOnLogon      — fires once at every user logon
::                              (covers the "first boot of the day" case)
::
:: Run this script as Administrator to install both tasks.
:: Re-running it will silently overwrite any existing tasks of the same names.
:: ============================================================

setlocal EnableDelayedExpansion

:: Resolve the directory this .bat file lives in (works regardless of CWD)
set "SCRIPT_DIR=%~dp0"
:: Remove trailing backslash for cleanliness
if "%SCRIPT_DIR:~-1%" == "\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

set "PY_SCRIPT=%SCRIPT_DIR%\wallendar_scheduler.py"
set "TASK_DAILY=WallendarDailyUpdate"
set "TASK_LOGON=WallendarOnLogon"

:: ── Locate the Python executable ────────────────────────────
for /f "tokens=*" %%P in ('where python 2^>nul') do (
    set "PYTHON_EXE=%%P"
    goto :found_python
)

echo ERROR: Python was not found on PATH.
echo        Install Python 3.8+ and ensure it is added to your PATH, then re-run this script.
exit /b 1

:found_python
echo Using Python: !PYTHON_EXE!
echo Script path:  !PY_SCRIPT!
echo.

:: ── Verify the Python script exists ─────────────────────────
if not exist "!PY_SCRIPT!" (
    echo ERROR: wallendar_scheduler.py not found at:
    echo        !PY_SCRIPT!
    echo        Make sure both files are in the same folder.
    exit /b 1
)

:: ════════════════════════════════════════════════════════════
:: TASK 1 — Daily at 12:00 AM (midnight)
::   /SC DAILY /ST 00:00  — every day at midnight
::   /RL HIGHEST          — elevated privileges
::   /RU SYSTEM           — runs even when no user is logged in
:: ════════════════════════════════════════════════════════════

echo Registering daily midnight task...

schtasks /Create ^
    /F ^
    /TN "%TASK_DAILY%" ^
    /TR "\"!PYTHON_EXE!\" \"!PY_SCRIPT!\"" ^
    /SC DAILY ^
    /ST 00:00 ^
    /RL HIGHEST

if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Failed to register "%TASK_DAILY%".
    echo        Try running this script as Administrator.
    exit /b 1
)

echo   OK — "%TASK_DAILY%" will run every day at 12:00 AM.
echo.

:: ════════════════════════════════════════════════════════════
:: TASK 2 — At every user logon
::   /SC ONLOGON — fires once each time any user logs on
::   /DELAY 0001:00 — 1-minute delay so the desktop is fully loaded
::                    before the wallpaper is applied
:: ════════════════════════════════════════════════════════════

echo Registering at-logon task...

schtasks /Create ^
    /F ^
    /TN "%TASK_LOGON%" ^
    /TR "\"!PYTHON_EXE!\" \"!PY_SCRIPT!\"" ^
    /SC ONLOGON ^
    /DELAY 0001:00 ^
    /RL HIGHEST


if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Failed to register "%TASK_LOGON%".
    echo        Try running this script as Administrator.
    exit /b 1
)

echo   OK — "%TASK_LOGON%" will run 1 minute after every logon.
echo.

:: ════════════════════════════════════════════════════════════
:: Summary
:: ════════════════════════════════════════════════════════════

echo ============================================================
echo Both tasks registered successfully.
echo.
echo   Task 1: %TASK_DAILY%
echo           Trigger  : Every day at 12:00 AM
echo           Run as   : SYSTEM
echo.
echo   Task 2: %TASK_LOGON%
echo           Trigger  : At every user logon (+ 1 min delay)
echo           Run as   : Current user
echo.
echo Open Task Scheduler to verify, or run immediately with:
echo   schtasks /Run /TN "%TASK_DAILY%"
echo   schtasks /Run /TN "%TASK_LOGON%"
echo ============================================================
echo.

endlocal
pause
