@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
  if not errorlevel 1 (
    py -3 launch.py
    goto :finished
  )
)
where python >nul 2>&1
if not errorlevel 1 (
  python -c "import sys; raise SystemExit(sys.version_info < (3, 10))" >nul 2>&1
  if not errorlevel 1 (
    python launch.py
    goto :finished
  )
)
echo FastReads Taso requires Python 3.10 or newer on PATH.
pause
exit /b 1
:finished
if errorlevel 1 (
  echo FastReads Taso did not start. Read the message above.
  pause
  exit /b 1
)
endlocal
