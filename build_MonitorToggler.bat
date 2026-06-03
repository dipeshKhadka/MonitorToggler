@echo off
echo Installing dependencies...
pip install -r requirements.txt

echo.
echo Building MonitorToggler.exe...
pyinstaller ^
  --onefile ^
  --noconsole ^
  --name MonitorToggler ^
  MonitorToggler.py

echo.
if exist dist\MonitorToggler.exe (
    echo Build complete: dist\MonitorToggler.exe
) else (
    echo Build FAILED. Check the output above for errors.
)
pause
