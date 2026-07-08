@echo off
setlocal
cd /d "%~dp0"
python agent\auto_ingest.py --watch --interval 300
