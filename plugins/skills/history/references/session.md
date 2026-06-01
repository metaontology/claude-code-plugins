# SESSION.md 포맷 및 del 흐름

## 파일 헤더

```
# SESSION.md

원본 경로: `C:\Users\jun\.claude\projects\{프로젝트-슬러그}`

---
```

## 테이블

```
| 🗑️ | 생성일시 | 세션 ID | 세션명 | 설명 |
|---|----------|---------|--------|------|
| [ ] | YYYY-MM-DD HH:MM:SS | [8자리ID](./user-prompts/full-uuid/user-prompts.md) | 짧은 키워드 | 한 줄 설명 |
```

- **🗑️ 컬럼**: 삭제 대상 체크. `[ ]` = 미선택, `[x]` = 삭제 예정
- **세션 ID**: UUID 앞 8자리를 표시명으로, 링크 경로에 full UUID 포함
- **세션명**: ai-title 앞 2~3단어
- **설명**: ai-title 전체 또는 첫 사용자 메시지 요약
- 행 순서: 최신 위 (내림차순)

## /history del 흐름 (체크박스)

`/history del` (인수 없음) 실행 시:

1. `python "$SKILL_DIR/scripts/main.py" del` 실행
2. 출력이 `CHECKED_NONE`이면:
   > "체크 항목 없음. SESSION.md에서 삭제할 세션에 `[x]` 체크 후 `/history del`을 재실행하세요."
   종료.
3. 출력이 `CHECKED_LIST`이면 이후 줄의 UUID 목록을 읽어 사용자에게 표시:
   > "다음 N개 세션을 삭제하시겠습니까?
   > - {sid[:8]} ...
   > (y/N)"
4. `y` 확인 시:
   ```sh
   CLAUDE_SESSION_ID="$CLAUDE_CODE_SESSION_ID" python "$SKILL_DIR/scripts/main.py" del --confirm {sid1} {sid2} ...
   ```
5. 결과 출력 후 종료.

## /history del {세션ID} 흐름 (단일)

`/history del {세션ID}` 실행 시:

1. `python "$SKILL_DIR/scripts/main.py" del {세션ID}` 실행 (`CLAUDE_SESSION_ID` 환경변수 포함)
2. 출력이 `NOT_FOUND`이면:
   > "세션 `{세션ID}`를 찾을 수 없습니다."
   종료.
3. 출력이 `FOUND {full_uuid}`이면:
   > "세션 `{세션ID}`를 삭제하시겠습니까? (y/N)"
4. `y` 확인 시:
   ```sh
   CLAUDE_SESSION_ID="$CLAUDE_CODE_SESSION_ID" python "$SKILL_DIR/scripts/main.py" del --confirm {full_uuid}
   ```
5. 결과 출력 후 종료.
