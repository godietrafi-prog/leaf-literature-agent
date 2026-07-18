@echo off
setlocal
cd /d "%~dp0"
REM Watch inbox\pdfs and run the full v2 pipeline on each dropped paper.
python agent\integrate_paper.py --inbox --mock --watch --interval 300
