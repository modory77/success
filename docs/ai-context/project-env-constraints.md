---
name: project-env-constraints
description: "이 PC 환경 제약 - Python 3.12 venv, Windows 앱 제어 정책의 DLL 차단, 4K 영상 느림, API 크레딧"
metadata:
  node_type: memory
  type: project
  originSessionId: 8379606c-bf92-471f-a33a-3ccc4669d3c1
  modified: 2026-11-15T10:52:09.675Z
---

- Python 3.15 는 휠이 없어 `.venv`(Python 3.12)를 쓴다. 항상 `.venv\Scripts\python.exe`.
- Windows 앱 제어 정책이 `av`, `shapely`, `cublas64_12.dll` 등을 간헐적으로 차단한다. `av` 는 더미 모듈로 대체, CUDA 는 `cuda_ok()` 로 감지해 CPU 폴백. 보안 설정은 바꾸지 않는다.
- 테스트 영상(4K 60fps)은 CPU 전사/렌더가 매우 느려 1분 이내 클립으로 시험한다.
- Anthropic/OpenAI API 크레딧이 없으면 기획·이미지 단계는 건너뛰고 나머지는 계속 진행한다.

**Why:** 같은 오류가 반복돼 폴백 구조를 만들었다.
**How to apply:** DLL 오류는 우회/폴백 코드로 해결하고 시스템 보안 설정은 사용자가 직접 판단하게 안내한다.
