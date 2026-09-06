@echo off
REM Phantom Tweeks launcher - double-click to start the GUI,
REM or run "PhantomTweeks.bat scan" for a CLI command.
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
    py -3 run.py %*
) else (
    python run.py %*
)

if %errorlevel% neq 0 (
    echo.
    echo Phantom Tweeks exited with an error.
    pause
)
endlocal
