@echo off
setlocal
cd /d "%~dp0"

echo Extracting target evidence from searched PDFs with Bedrock...
py_work agent\store_extractions.py --search-only --target-only --skip-llm-existing
if errorlevel 1 (
  echo.
  echo py_work failed or is unavailable. Trying WSL test_project_env...
  wsl ~/.virtualenvs/test_project_env/bin/python agent/store_extractions.py --search-only --target-only --skip-llm-existing
)
if errorlevel 1 (
  echo.
  echo WSL fallback failed. Trying the default Python interpreter...
  python agent\store_extractions.py --search-only --target-only --skip-llm-existing
)

echo.
pause
