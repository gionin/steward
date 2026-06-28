@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo   Steward  -  setup (run this once)
echo ============================================
echo.

:: ── Check for Python ──────────────────────────────────────────────────────────
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)

if not defined PY (
  echo [!] Python was not found on this computer.
  echo.
  echo     Please install Python 3 from:
  echo       https://www.python.org/downloads/
  echo.
  echo     IMPORTANT: on the installer's first page, tick
  echo       "Add Python to PATH"  before clicking Install.
  echo.
  set /p "OPEN=Open the download page now in your browser? [Y/n]: "
  if /i not "%OPEN%"=="n" (
    start "" "https://www.python.org/downloads/"
  )
  echo.
  echo Re-run this script after Python is installed.
  pause
  exit /b 1
)

echo Using Python: %PY%
%PY% --version
echo.

:: ── Create virtual environment ─────────────────────────────────────────────────
%PY% -m venv .venv
if errorlevel 1 (
  echo.
  echo [!] Could not create the virtual environment.
  echo     Make sure Python 3.3 or later is installed correctly.
  pause
  exit /b 1
)

:: ── Upgrade pip ────────────────────────────────────────────────────────────────
echo Upgrading pip...
.venv\Scripts\python -m pip install --upgrade pip
if errorlevel 1 (
  echo.
  echo [!] pip upgrade failed. See the messages above.
  pause
  exit /b 1
)

:: ── Install dependencies ───────────────────────────────────────────────────────
echo Installing dependencies...
.venv\Scripts\python -m pip install pywebview
if errorlevel 1 (
  echo.
  echo [!] Installing pywebview failed. See the messages above.
  pause
  exit /b 1
)

echo.
echo ============================================
echo   Setup complete. Double-click run.bat to start.
echo ============================================
pause
