@echo off
:: ============================================================
:: setup_task_scheduler.bat
:: Registers TWO Windows Task Scheduler tasks:
::
::   1. WallendarDailyUpdate  - fires every day at 12:00 AM (midnight)
::   2. WallendarOnLogon      - fires once at every user logon
::
:: Prompts for resolution and background mode before registering.
:: After applying the wallpaper, offers to reconfigure if unsatisfied.
::
:: Run this script as Administrator to install/update both tasks.
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
:: :configure — Entry point for the configuration loop.
:: Jumped back to here whenever the user wants to reconfigure.
:: ════════════════════════════════════════════════════════════

:configure
echo.
echo ============================================================
echo  WALLENDAR CONFIGURATION
echo ============================================================
echo.

:: ── STEP 1: Resolution ──────────────────────────────────────

echo [Step 1/2]  Select wallpaper resolution:
echo.
echo   1^)  Desktop HD   -  1280 x  720
echo   2^)  Desktop FHD  -  1920 x 1080   [recommended]
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
echo   Selected: !RES_LABEL!

:: ── STEP 2: Background mode ─────────────────────────────────

echo.
echo [Step 2/2]  Background mode:
echo.
echo   1^)  Rotate - cycle through all backgrounds on each run  [default]
echo   2^)  Fixed  - always use the same background (only calendar changes)
echo.

choice /c 12 /n /m "Enter choice [1-2] (default=1): "
set "BG_CHOICE=%ERRORLEVEL%"

if "%BG_CHOICE%"=="1" (
    set "BG_LABEL=Rotate (cycles through all 7 backgrounds)"
    set "BGMODE_ARGS=--background-mode rotate"
)

if "%BG_CHOICE%"=="2" (
    echo.
    echo   Which background should be fixed?
    echo.
    echo     1^)  sample-bg1.jpg
    echo     2^)  sample-bg2.jpg
    echo     3^)  sample-bg3.jpg
    echo     4^)  sample-bg4.jpg
    echo     5^)  sample-bg5.jpg
    echo     6^)  sample-bg6.jpg
    echo     7^)  sample-bg7.jpg
    echo.
    choice /c 1234567 /n /m "Enter choice [1-7] (default=1): "
    set "FIX_IDX=%ERRORLEVEL%"
    set "BG_LABEL=Fixed (sample-bg!FIX_IDX!.jpg)"
    set "BGMODE_ARGS=--background-mode fixed --fixed-index !FIX_IDX!"
)

echo.
echo   Selected: !BG_LABEL!
echo.

:: ── Register Task Scheduler tasks ───────────────────────────

echo Registering scheduled tasks...

schtasks /Create /F /TN "%TASK_DAILY%" /TR "\"%PYTHON_EXE%\" \"%PY_SCRIPT%\" --resolution %RESOLUTION% %BGMODE_ARGS%" /SC DAILY /ST 00:00 /RL HIGHEST /RU SYSTEM >nul 2>&1

if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Failed to register "%TASK_DAILY%".
    echo        Try running this script as Administrator.
    goto :ask_retry
)

schtasks /Create /F /TN "%TASK_LOGON%" /TR "\"%PYTHON_EXE%\" \"%PY_SCRIPT%\" --resolution %RESOLUTION% %BGMODE_ARGS%" /SC ONLOGON /DELAY 0001:00 /RL HIGHEST >nul 2>&1

if %ERRORLEVEL% neq 0 (
    echo.
    echo ERROR: Failed to register "%TASK_LOGON%".
    echo        Try running this script as Administrator.
    goto :ask_retry
)

echo   Tasks registered.
echo.

:: ── Apply wallpaper immediately ──────────────────────────────

echo Applying wallpaper now with new settings...
echo.

"%PYTHON_EXE%" "%PY_SCRIPT%" --resolution %RESOLUTION% %BGMODE_ARGS%
set "PY_EXIT=%ERRORLEVEL%"

:: ── Force Explorer to refresh the desktop at normal integrity level ──
:: When this bat runs elevated, direct RUNDLL32 calls are blocked by
:: Windows UIPI from reaching Explorer (which runs at Medium IL).
:: Fix: create a one-shot temp task WITHOUT /RL HIGHEST so it runs at
:: Medium IL — the signal can then cross the integrity boundary to Explorer.
set "TEMP_TASK=WallendarRefreshTemp"
schtasks /Create /F /TN "%TEMP_TASK%" /TR "RUNDLL32.EXE user32.dll,UpdatePerUserSystemParameters ,1 ,True" /SC ONCE /ST 00:00 >nul 2>&1
schtasks /Run /TN "%TEMP_TASK%" >nul 2>&1
timeout /t 3 /nobreak >nul
schtasks /Delete /F /TN "%TEMP_TASK%" >nul 2>&1

if "%PY_EXIT%" neq "0" (
    echo.
    echo WARNING: Wallpaper update failed. See error above.
    echo          Scheduled tasks are still registered correctly.
    goto :ask_reconfigure
)

:: ── Post-update: ask if satisfied ───────────────────────────

echo.
echo ============================================================
echo  Wallpaper applied with:
echo    Resolution : %RES_LABEL%
echo    Background : %BG_LABEL%
echo ============================================================
echo.
echo Are you happy with the result?
echo.
echo   1^)  Yes - keep this configuration and exit
echo   2^)  No  - change the settings and regenerate
echo.

choice /c 12 /n /m "Enter choice [1-2]: "

if "%ERRORLEVEL%"=="1" goto :done
if "%ERRORLEVEL%"=="2" goto :configure

:: ── Ask to reconfigure after a task registration error ──────

:ask_retry
echo.
echo   1^)  Try again (re-enter configuration)
echo   2^)  Exit
echo.
choice /c 12 /n /m "Enter choice [1-2]: "
if "%ERRORLEVEL%"=="1" goto :configure
if "%ERRORLEVEL%"=="2" goto :exit_now

:: ── Ask to reconfigure after a wallpaper apply error ────────

:ask_reconfigure
echo.
echo   1^)  Change settings and try again
echo   2^)  Exit (tasks are registered, wallpaper will apply at midnight)
echo.
choice /c 12 /n /m "Enter choice [1-2]: "
if "%ERRORLEVEL%"=="1" goto :configure
if "%ERRORLEVEL%"=="2" goto :done

:: ════════════════════════════════════════════════════════════
:: :done — Clean exit with final summary
:: ════════════════════════════════════════════════════════════

:done
echo.
echo ============================================================
echo  All done. Final configuration:
echo.
echo    Resolution : %RES_LABEL%
echo    Background : %BG_LABEL%
echo.
echo    Task 1: %TASK_DAILY%  -  Daily at 12:00 AM (SYSTEM)
echo    Task 2: %TASK_LOGON%  -  At every logon (current user)
echo.
echo  To reconfigure anytime, re-run this script as Administrator.
echo ============================================================
echo.

:exit_now
endlocal
pause
