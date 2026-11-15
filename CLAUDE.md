# CLAUDE.md — autoedit (유튜브 1차 자동 편집기)

영상 1개를 넣으면 전사 → 무음/필러/말더듬 컷 → 설명 일러스트·로고 오버레이 → 개인정보 모자이크 → 자막 → 렌더까지 처리하는 Windows 로컬 도구. 사용자는 한국어 사용자이며 강의(웹 UI + 단계별 파이프라인)를 따라가며 만들고 있다. 설명/주석/로그는 한국어로 쓴다.

## 실행
- 환경: **Python 3.12 venv(`.venv`)**. 시스템 Python 3.15 는 휠이 없어 쓰지 않는다. 항상 `.venv\Scripts\python.exe` 사용.
- 웹 UI: `ui.bat` → http://127.0.0.1:8766 (`python -m autoedit.webui`)
- CLI: `run.bat 영상.mp4` (= `python -m autoedit 영상.mp4`, 옵션은 `--help`). 폴더 감시: `watch.bat` (inbox → output)
- 테스트 프레임워크는 없다. 변경 후에는 짧은 영상(`samples/`)으로 `python -m autoedit <영상> --stage <단계>` 를 돌려 확인한다.

## 구조 (`autoedit/`)
| 파일 | 역할 |
|---|---|
| `common.py` | .env 로딩, 로그 싱크, ffmpeg(imageio-ffmpeg) 실행, `probe`, `load_audio`, 인코더 선택(NVENC/x264), CUDA DLL 점검 |
| `config.py` | 옵션 기본값(.env 이름은 강의 자료와 동일) + `merge(overrides)` |
| `transcribe.py` | faster-whisper 전사(GPU 불가 시 CPU 폴백) |
| `cut.py` | 무음(MIN/KEEP_SILENCE, dB 자동 보정)·필러·말더듬 컷, 프레임 격자 스냅, 컷 렌더 |
| `illustrate.py` | Claude 기획(scenes+overlays), 이미지 생성(OpenAI gpt-image-1 → 실패 시 Claude SVG), 로고 카드 |
| `privacy.py` | OCR(RapidOCR) 패턴 탐지, 얼굴(YuNet, 선택), 말로 읽은 번호 음소거 구간 |
| `render.py` | 모자이크 프레임 → ffmpeg 파이프 → 오버레이/자막 합성 한 번에 인코딩 |
| `subtitles.py` | ASS 자막 생성(세로/가로 크기·위치 보정) |
| `pipeline.py` | 6단계(`STAGES`)와 단계별 캐시(`work/<영상>/*.json`). 앞 단계 없으면 자동 실행 |
| `webui.py`, `web/index.html` | 표준 라이브러리 HTTP 서버 + 단일 페이지 UI |

## 규칙
- **비밀키**: `.env` 는 절대 커밋하지 않는다(.gitignore). 키 값을 출력/로그/채팅에 노출하지 않는다. 견본은 `.env.example`(값 비움).
- **웹 UI 보안 유지**: 127.0.0.1 바인딩, Host 검사, POST 는 `X-Autoedit: 1` 헤더 필수, 파일 접근은 폴더+파일명만. 외부 노출이 필요하면 로그인부터 추가.
- 필터 그래프는 길어서 파일로 넘긴다. ffmpeg 9 는 `-/filter_complex`, 구버전은 `-filter_complex_script` (`run_ffmpeg`/`final_render` 가 처리).
- 컷 구간은 **영상 프레임 격자에 스냅**해야 A/V 싱크가 안 어긋난다. 영상은 `fps`+`select`, 오디오는 `atrim`+`concat`.
- 자막은 짧은 변 기준 크기, 세로 영상은 하단 UI 때문에 위로 올린다.
- 단계 결과는 캐시되므로 옵션을 바꾼 뒤엔 해당 단계를 `--force`(UI: 강제 재실행)로 다시 돌린다.

## Windows 환경 주의
- 앱 제어 정책이 DLL 을 막을 때가 있다(`av`, `shapely`, `cublas64_12.dll` 등). `av` 는 `common.py` 에서 더미 모듈로 대체(오디오는 ffmpeg 로 직접 디코딩). CUDA 불가 시 `cuda_ok()` 로 감지해 CPU 로 폴백. 보안 설정 자체는 건드리지 않는다.
- 4K 60fps 영상은 CPU 전사/렌더가 매우 느리다. 시험은 1분 이내 클립으로.
- API 크레딧이 없으면 기획/이미지 단계는 실패해도 파이프라인은 건너뛰고 계속 진행한다(실패 결과는 캐시하지 않음).

## 알려진 한계
- 기본 OCR 은 한글(이름·주소)이 약해 `BLUR_WORDS` 로 보완. Whisper 가 필러를 못 받아적으면 컷되지 않음. 말 없는 배경음/웃음은 무음 판정될 수 있음(dB·자동 보정으로 완화).
