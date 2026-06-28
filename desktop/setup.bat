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
  call :find_python
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

:: Try winget first (built into Windows 10 1709+ and Windows 11)
where winget >nul 2>nul
if not errorlevel 1 (
  echo.
  echo Installing Python via winget...
  winget install --id Python.Python.3 --source winget --accept-package-agreements --accept-source-agreements
  if not errorlevel 1 (
    echo.
    echo Python installed. Refreshing PATH...
    for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%B"
    for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%B"
    set "PATH=%SYS_PATH%;%USR_PATH%"
    exit /b 0
  )
  echo winget install failed, trying manual download...
)

:: Fallback: download the official installer via PowerShell
echo.
echo Downloading Python installer from python.org...
set "INSTALLER=%TEMP%\python_setup.exe"
powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe' -OutFile '%INSTALLER%'"
if not exist "%INSTALLER%" (
  echo [!] Download failed. Please install Python manually from https://www.python.org/downloads/
  pause
  exit /b 0
)
echo Running installer (this may take a minute)...
"%INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1
del /q "%INSTALLER%" 2>nul
for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%B"
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USR_PATH=%%B"
set "PATH=%SYS_PATH%;%USR_PATH%"
exit /b 0
