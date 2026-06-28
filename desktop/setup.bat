@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo   Steward  -  setup (run this once)
echo ============================================
echo.

:: ── Detect a real Python (ignore the Windows Store stub) ─────────────────────
call :find_python
if not defined PY (
  call :install_python
  if not defined PY call :find_python
)

if not defined PY (
  echo.
  echo [!] Python still not found after install attempt.
  echo     Please restart this script, or install manually from:
  echo       https://www.python.org/downloads/
  echo     and tick "Add Python to PATH".
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
  pause
  exit /b 1
)

:: ── Upgrade pip ────────────────────────────────────────────────────────────────
echo Upgrading pip...
.venv\Scripts\python -m pip install --upgrade pip
if errorlevel 1 (
  echo [!] pip upgrade failed. See the messages above.
  pause
  exit /b 1
)

:: ── Install dependencies ───────────────────────────────────────────────────────
echo Installing dependencies...
.venv\Scripts\python -m pip install pywebview
if errorlevel 1 (
  echo [!] Installing pywebview failed. See the messages above.
  pause
  exit /b 1
)

echo.
echo ============================================
echo   Setup complete. Double-click run.bat to start.
echo ============================================
pause
exit /b 0


:: ─────────────────────────────────────────────────────────────────────────────
:find_python
set "PY="
for %%C in (py python python3) do (
  if not defined PY (
    where %%C >nul 2>nul && (
      %%C --version >nul 2>nul && set "PY=%%C"
    )
  )
)
exit /b 0


:: ─────────────────────────────────────────────────────────────────────────────
:install_python
echo [!] Python was not found on this computer.
echo.
set /p "AUTO=Install Python automatically now? [Y/n]: "
if /i "%AUTO%"=="n" (
  echo.
  echo Please install Python 3 from https://www.python.org/downloads/
  echo Tick "Add Python to PATH", then re-run this script.
  pause
  exit /b 0
)

:: Download the official installer via PowerShell
echo.
echo Downloading Python 3.12 installer from python.org (this may take a moment)...
set "INSTALLER=%TEMP%\python_setup.exe"
powershell -NoProfile -Command ^
  "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;" ^
  "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe' -OutFile '%INSTALLER%'"
if not exist "%INSTALLER%" (
  echo.
  echo [!] Download failed. Please install Python manually from:
  echo       https://www.python.org/downloads/
  echo     Tick "Add Python to PATH", then re-run this script.
  pause
  exit /b 0
)

echo Installing Python (this may take a minute)...
"%INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1
del /q "%INSTALLER%" 2>nul

:: Point PY directly at the known install location so we don't need a PATH refresh
set "PYDIR=%LOCALAPPDATA%\Programs\Python\Python312"
if exist "%PYDIR%\python.exe" (
  set "PY=%PYDIR%\python.exe"
  echo Python installation complete.
) else (
  echo Python installation complete. Re-run this script if setup fails.
)
exit /b 0
