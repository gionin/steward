@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo The environment is missing. Please double-click setup.bat first.
  echo.
  pause
  exit /b 1
)

echo Starting Steward...  (close the app window to come back here)
echo.
.venv\Scripts\python app.py

echo.
echo ------------------------------------------------------------
echo Steward has exited.
echo If it crashed, the reason is shown above and saved in:
echo    "%USERPROFILE%\.steward\steward.log"
echo ------------------------------------------------------------
pause
