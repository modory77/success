# agent.md

AI 에이전트(Codex, Claude Code 등)용 안내. 자세한 구조와 규칙은 [CLAUDE.md](CLAUDE.md) 를 따른다.

## 한눈에
- 프로젝트: `autoedit` — 유튜브 영상 1차 자동 편집기(전사·컷·일러스트/로고·모자이크·자막·렌더), Windows 로컬 실행.
- 언어/환경: Python 3.12 (`.venv`), ffmpeg(imageio-ffmpeg), faster-whisper, OpenCV, RapidOCR.
- 진입점: 웹 UI `ui.bat`, CLI `run.bat 영상.mp4`, 폴더 감시 `watch.bat`.
- 코드: `autoedit/` (파이프라인 6단계는 `pipeline.py` 의 `STAGES`).

## 작업 규칙
1. `.env` 와 API 키를 읽어 출력하거나 커밋하지 않는다. 새 설정은 `.env.example` 에 이름만 추가한다.
2. 영상/산출물(`work/ output/ uploads/ samples/ inbox/ models/`)과 로고 이미지는 저장소에 올리지 않는다(.gitignore).
3. 한국어로 주석·로그·문서를 작성한다. 기존 스타일(짧은 docstring, 한국어 로그 `[n/6]`)을 따른다.
4. 변경 후 짧은 영상으로 해당 단계를 실제로 실행해 확인하고, 확인하지 못한 부분은 그대로 밝힌다.
5. 웹 UI 의 보안 장치(로컬 바인딩, Host/헤더 검사, 파일명 화이트리스트)를 약화시키지 않는다.
6. 보안 정책으로 막힌 DLL/GPU 문제는 우회 코드(폴백)로만 다루고 시스템 보안 설정을 바꾸지 않는다.
