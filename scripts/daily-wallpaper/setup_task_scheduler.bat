@echo off
:: ============================================================
:: setup_task_scheduler.bat
:: Registers TWO Windows Task Scheduler tasks:
::
::   1. WallendarDailyUpdate  — fires every day at 12:00 AM (midnight)
::   2. WallendarOnLogon      — fires once at every user logon
::
:: Prompts for wallpaper resolution before registering.
:: The chosen resolution is baked into both task commands so automated
:: runs never need user input.
::
:: Run this script as Administrator to install/update both tasks.
:: Re-running it will silently overwrite any existing tasks.
:: ============================================================

setlocal EnableDelayedExpansion

:: Resolve the directory this .bat file lives in (works regardless of CWD)
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%" == "\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

set "PY_SCRIPT=%SCRIPT_DIR%\wallendar_scheduler.py"
set "TASK_DAILY=WallendarDailyUpdate"
set "TASK_LOGON=WallendarOnLogon"

:: ── Locate Python ────────────────────────────────────────────
for /f "tokens=*" %%P in ('where python 2^>nul') do (
    set "PYTHON_EXE=%%P"
    goto :found_python
)
echo ERROR: Python was not found on PATH.
echo        Install Python 3.8+ and tick "Add to PATH" during setup.
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
:: RESOLUTION SELECTION
:: The chosen key is passed as --resolution <key> to Python
:: in both registered tasks, so automated runs are non-interactive.
:: ════════════════════════════════════════════════════════════

echo Select wallpaper resolution:
echo   1^)  Desktop HD   -  1280 x  720
echo   2^)  Desktop FHD  -  1920 x 1080  
echo   3^)  Desktop 4K   -  3840 x 2160
echo   4^)  Mobile HD    -   720 x 1280
echo   5^)  Mobile FHD   -  1080 x 1920
echo   6^)  Mobile 4K    -  1440 x 2560
echo.

choice /c 123456 /n /m "Enter choice [1-6] (default=2): "
set "CHOICE_NUM=%ERRORLEVEL%"

if "%CHOICE_NUM%"=="1" set "RESOLUTION=desktop-hd"   & set "RES_LABEL=Desktop HD   (1280x720)"
if "%CHOICE_NUM%"=="2" set "RESOLUTION=desktop-fhd"  & set "RES_LABEL=Desktop FHD  (1920x1080)"
if "%CHOICE_NUM%"=="3" set "RESOLUTION=desktop-4k"   & set "RES_LABEL=Desktop 4K   (3840x2160)"
if "%CHOICE_NUM%"=="4" set "RESOLUTION=mobile-hd"    & set "RES_LABEL=Mobile HD    (720x1280)"
if "%CHOICE_NUM%"=="5" set "RESOLUTION=mobile-fhd"   & set "RES_LABEL=Mobile FHD   (1080x1920)"
if "%CHOICE_NUM%"=="6" set "RESOLUTION=mobile-4k"    & set "RES_LABEL=Mobile 4K    (1440x2560)"

echo.
echo Selected: !RES_LABEL!
echo.

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
    /TR "\"!PYTHON_EXE!\" \"!PY_SCRIPT!\" --resolution !RESOLUTION!" ^
    /SC DAILY ^
    /ST 00:00 ^
    /RL HIGHEST ^
    /RU SYSTEM

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
::   /SC ONLOGON  — fires once each time any user logs on
::   /DELAY 0001:00 — 1-minute delay so desktop + network are ready
:: ════════════════════════════════════════════════════════════

echo Registering at-logon task...

schtasks /Create ^
    /F ^
    /TN "%TASK_LOGON%" ^
    /TR "\"!PYTHON_EXE!\" \"!PY_SCRIPT!\" --resolution !RESOLUTION!" ^
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
echo   Resolution : !RES_LABEL!
echo.
echo   Task 1: %TASK_DAILY%
echo           Trigger  : Every day at 12:00 AM
echo           Run as   : SYSTEM
echo.
echo   Task 2: %TASK_LOGON%
echo           Trigger  : At every user logon (+ 1 min delay)
echo           Run as   : Current user
echo.
echo To change resolution later, re-run this script as Administrator.
echo.
echo Open Task Scheduler to verify, or run immediately with:
echo   schtasks /Run /TN "%TASK_DAILY%"
echo   schtasks /Run /TN "%TASK_LOGON%"
echo ============================================================
echo.

endlocal
pause
