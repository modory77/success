# 클라우드 세션 설정 (cloud-setup)

클라우드(원격) Claude Code 세션에서 이 저장소를 열어 작업할 때의 준비 사항.

## 먼저 읽기
1. `CLAUDE.md` — 구조와 규칙
2. `agent.md` — 다른 AI 도구용 요약
3. `docs/ai-context/` — 로컬 Claude 메모리 복사본(프로젝트 배경, 환경 제약, 규칙)

## 환경 만들기
```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt   # nvidia-cublas/cudnn 은 GPU 가 없으면 설치 실패해도 무방
cp .env.example .env                        # 키는 세션의 시크릿/환경변수로 넣는다 (커밋 금지)
```

## 비밀키
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` 는 클라우드 환경 변수(시크릿)로만 설정한다. 저장소에는 절대 올리지 않는다.
- 키가 없으면 기획·이미지 단계는 건너뛰고 나머지는 동작한다.

## 알려진 차이 (Windows 로컬 기준으로 만든 코드)
- 한글 폰트 경로가 Windows 용이다(`autoedit/common.py` 의 `KOREAN_FONT`, `autoedit/render.py` 의 `fontsdir=C\\:/Windows/Fonts`). 리눅스에서는 Noto Sans CJK 등으로 바꿔야 자막/SVG 글자가 나온다.
- `ctypes.windll`(DLL 오류 팝업 억제)은 Windows 전용이며 예외 처리로 건너뛴다.
- GPU(NVENC/CUDA)가 없는 환경에서는 전사/인코딩이 CPU 로 자동 전환되어 느리다. 시험은 1분 이내 클립으로.
- 영상/산출물(`work/ output/ uploads/ samples/ inbox/`)은 저장소에 없으므로 클라우드에서 직접 준비해야 한다.

## 웹 UI 미리보기
`.claude/launch.json` 의 `autoedit-ui` 설정으로 `http://127.0.0.1:8766` 을 띄운다. 서버는 로컬 바인딩 + 헤더 검사만 있고 로그인이 없으므로 외부에 노출하지 않는다.
