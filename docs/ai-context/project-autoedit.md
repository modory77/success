---
name: project-autoedit
description: autoedit 프로젝트 개요 - 유튜브 1차 자동 편집기(전사·컷·일러스트/로고·모자이크·자막·웹 UI)
metadata:
  node_type: memory
  type: project
  originSessionId: 8379606c-bf92-471f-a33a-3ccc4669d3c1
  modified: 2026-11-15T10:52:00.321Z
---

`C:\Users\USER\Desktop\success` 의 `autoedit` 은 영상 1개를 넣으면 전사 → 무음/필러/말더듬 컷 → 설명 일러스트·로고 오버레이 → 개인정보 모자이크 → 자막 → 렌더까지 처리하는 Windows 로컬 도구다. 진입점은 웹 UI(`ui.bat`, 127.0.0.1:8766), CLI(`run.bat`), 폴더 감시(`watch.bat`).

**Why:** 사용자가 유튜브 영상 편집 반복 작업을 자동화하려고 만든다. 강의(웹 UI + 6단계 파이프라인 + 캐시)를 따라가며 같은 구성으로 맞추는 중이다.
**How to apply:** 구조/규칙은 CLAUDE.md 를 따른다. 새 기능은 강의 자료의 설정 이름(.env 키)과 같은 이름을 쓴다. 관련: [[user-korean-lecture-follower]], [[reference-github-repo]], [[project-env-constraints]].
