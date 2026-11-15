@echo off
rem 웹 UI 실행 -> 브라우저에서 http://127.0.0.1:8766
rem 코드를 고치면 자동 반영: 처리 코드는 작업 시작 때마다 다시 불러오고, 서버 코드(webui.py)가 바뀌면 이 창이 알아서 재시작합니다.
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
:start
".venv\Scripts\python.exe" -m autoedit.webui
if %errorlevel%==75 (
  echo 서버를 다시 시작합니다...
  goto start
)
pause
