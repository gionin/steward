@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo   Steward  -  setup (run this once)
echo ============================================
echo.

where py >nul 2>nul && (set "PY=py -3") || (set "PY=python")
echo Using Python launcher: %PY%
echo.

%PY% -m venv .venv
if errorlevel 1 (
  echo.
  echo Could not create the environment. Is Python installed?
  echo Get it from https://www.python.org/downloads/ and tick "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install pywebview
if errorlevel 1 (
  echo.
  echo Installing pywebview failed. See the messages above.
  echo.
  pause
  exit /b 1
)

echo.
echo ============================================
echo   Setup complete. Double-click run.bat to start.
echo ============================================
pause
