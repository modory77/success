@echo off
rem 영상 1개 직접 처리: run.bat 영상.mp4  (영상을 이 파일에 드래그&드롭해도 됨)
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
".venv\Scripts\python.exe" -m autoedit %*
pause
