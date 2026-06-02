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

`/history del` (체크박스):

1. dry-run 실행:
   ```sh
   cd "$PROJECT_DIR" && CLAUDE_SESSION_ID="$CLAUDE_CODE_SESSION_ID" python "$SKILL_DIR/scripts/main.py" del
   ```
2. 출력 첫 줄이 `CHECKED_NONE` → "체크 항목 없음. SESSION.md에서 삭제할 세션에 `x` 표시 후 재실행하세요." 종료.
3. 출력 첫 줄이 `INCLUDES_CURRENT row={n} sid={8자리} name={세션명}` →
   **반드시 아래 형식 그대로** 출력 후 종료:
   > "{n}번째 항목 '{세션명}' ({8자리})은 현재 세션이므로 삭제할 수 없습니다. 체크를 해제 후 다시 실행하세요."
4. 출력 첫 줄이 `CHECKED_LIST` → 이후 줄의 UUID 목록으로 사용자에게 확인 요청:
   > "다음 N개 세션을 삭제하시겠습니까?\n- {sid[:8]} ...\n(y/N)"
5. `y` 확인 시 삭제 실행:
   ```sh
   cd "$PROJECT_DIR" && CLAUDE_SESSION_ID="$CLAUDE_CODE_SESSION_ID" python "$SKILL_DIR/scripts/main.py" del --confirm {sid1} {sid2} ...
   ```
6. 결과 출력 후 종료.

`/history del {세션ID}` (단일):

1. dry-run 실행:
   ```sh
   cd "$PROJECT_DIR" && CLAUDE_SESSION_ID="$CLAUDE_CODE_SESSION_ID" python "$SKILL_DIR/scripts/main.py" del {세션ID}
   ```
2. 출력이 `NOT_FOUND` → "세션 `{세션ID}`를 찾을 수 없습니다." 종료.
3. 출력이 `IS_CURRENT_SESSION {full_uuid}` → "현재 세션은 삭제할 수 없습니다." 종료.
4. 출력이 `FOUND {full_uuid}` → "세션 `{세션ID}`를 삭제하시겠습니까? (y/N)"
5. `y` 확인 시 삭제 실행:
   ```sh
   cd "$PROJECT_DIR" && CLAUDE_SESSION_ID="$CLAUDE_CODE_SESSION_ID" python "$SKILL_DIR/scripts/main.py" del --confirm {full_uuid}
   ```
6. 결과 출력 후 종료.
