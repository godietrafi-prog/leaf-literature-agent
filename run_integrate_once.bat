@echo off
setlocal
cd /d "%~dp0"
REM v2 full knowledge-integration pipeline for every PDF in inbox\pdfs
REM (deterministic mock extraction; add --real to use Claude on Bedrock via py_work).
python agent\integrate_paper.py --inbox --mock
pause
