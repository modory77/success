@echo off
rem 사용법: edit.bat 영상.mp4 [추가 옵션]   (영상 파일을 이 bat 위로 드래그&드롭해도 됩니다)
chcp 65001 >nul
set PYTHONUTF8=1
"%~dp0.venv\Scripts\python.exe" -m autoedit %*
pause
