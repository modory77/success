---
name: feedback-secrets-and-public-repo
description: "API 키는 .env 에만 두고 절대 노출하지 않으며, 공개 저장소에는 개인정보·영상·키를 올리지 않는다"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 8379606c-bf92-471f-a33a-3ccc4669d3c1
  modified: 2026-11-15T10:52:12.798Z
---

API 키(Anthropic/OpenAI)는 `.env` 에만 저장한다. 키 값을 출력·로그·채팅·커밋에 노출하지 않고, 견본 `.env.example` 은 값을 비운다. 사용자가 예시 파일에 키를 넣어 둔 적이 있어, 그럴 때는 `.env` 로 옮기고 예시 파일은 비운다.

**Why:** 저장소가 공개이고 대화에도 키가 한 번 노출된 적이 있다.
**How to apply:** 푸시 전 스테이징 검사(`.env` 미포함, 키 패턴 없음), 영상/산출물/개인 메모는 `.gitignore`. 키가 노출됐다면 재발급을 권한다.
