---
name: history
description: 현재 세션의 모든 user prompt, skill 호출, 로컬 커맨드를 jsonl에서 읽어 {프로젝트폴더}/.history/{세션UUID}/user-prompts.md 로 저장한다. `/history`로 호출한다.
---

현재 세션(또는 전체 세션)의 대화 기록을 `.history/` 폴더에 저장한다.

## 포맷 레퍼런스

- `references/session.md` — SESSION.md 포맷, 체크박스 규칙, del 확인 흐름
- `references/auto-memory.md` — AUTO-MEMORY.md 포맷, 메모리 이전 패턴
- `references/user-prompt.md` — user-prompts.md 포맷

## 지원 명령

| 명령 | 동작 |
|------|------|
| `/history` | 현재 세션 user-prompts.md 재생성, SESSION.md·AUTO-MEMORY.md 갱신 |
| `/history all` | 모든 세션 user-prompts.md 재생성, SESSION.md·AUTO-MEMORY.md 갱신 |
| `/history del` | SESSION.md에서 `[x]` 체크된 세션 삭제 |
| `/history del {세션ID}` | 특정 세션 삭제 |

## 실행

`/history` 및 `/history all`:

```sh
cd "$PROJECT_DIR" && CLAUDE_SESSION_ID="$CLAUDE_CODE_SESSION_ID" python "$SKILL_DIR/scripts/main.py" $ARGUMENTS
```

`/history del` 및 `/history del {세션ID}`:

`references/session.md`의 확인 흐름에 따라 처리한다. 두 단계로 진행:
1. Python dry-run으로 대상 확인
2. 사용자 확인 후 `--confirm`으로 실제 삭제 실행
