@echo off
rem inbox 폴더 감시 모드: inbox 에 영상을 넣으면 자동 편집 -> output 폴더
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
".venv\Scripts\python.exe" watch_inbox.py %*
pause
