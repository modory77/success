@echo off
rem 웹 UI 실행 -> 브라우저에서 http://127.0.0.1:8766
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
".venv\Scripts\python.exe" -m autoedit.webui
pause
