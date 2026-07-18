@echo off
setlocal
cd /d "%~dp0"
REM Rebuild all derived knowledge layers from the immutable raw rows
REM (entities, harmonization, claim links, candidate matrix). No re-extraction.
python agent\integrate_paper.py --reindex
pause
