---
name: reference-github-repo
description: "GitHub 저장소 modory77/success 와 푸시 방법(gh 인증, 전역 설정 변경 없이 푸시)"
metadata:
  node_type: memory
  type: reference
  originSessionId: 8379606c-bf92-471f-a33a-3ccc4669d3c1
  modified: 2026-11-15T10:52:06.483Z
---

저장소: https://github.com/modory77/success (공개, 브랜치 main). 로컬 작업 폴더가 이 저장소의 원본이다.

푸시 방법: `gh` 는 WinGet 패키지 폴더에 설치돼 있어 PATH 에 없을 수 있다. git 전역 설정은 건드리지 않고 푸시할 때만 `git -c credential.helper= -c "credential.helper=!'<gh.exe 경로>' auth git-credential" push` 를 쓴다. 커밋 작성자는 공개 저장소라 개인 이메일 대신 GitHub noreply 주소를 쓴다.

**Why:** 저장소가 공개라 이메일과 키가 노출되면 안 된다.
**How to apply:** 커밋 전에 `.env` 와 키 패턴이 스테이징에 없는지 검사하고, 푸시 후 원격 파일 목록을 다시 조회해 확인한다.
