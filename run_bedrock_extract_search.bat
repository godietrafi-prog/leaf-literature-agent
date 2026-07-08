@echo off
setlocal
cd /d "%~dp0"

echo Extracting target evidence from searched PDFs with Bedrock...
py_work agent\store_extractions.py --search-only --target-only
if errorlevel 1 (
  echo.
  echo py_work failed or is unavailable. Trying the default Python interpreter...
  python agent\store_extractions.py --search-only --target-only
)

echo.
pause
