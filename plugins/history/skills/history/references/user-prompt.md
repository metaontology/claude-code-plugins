# user-prompts.md 포맷

## 파일 위치

`.history/user-prompts/{full-session-uuid}/user-prompts.md`

## 항목 형식

```
[YYYY-MM-DD HH:MM:SS]
{텍스트}

[YYYY-MM-DD HH:MM:SS]
[local_command] /history
```

- 타임스탬프: jsonl의 timestamp 필드를 로컬 시간으로 변환 (UTC+9 등)
- 일반 user 메시지: 타임스탬프 + 텍스트
- 로컬 커맨드: `[local_command]` 접두사 + 명령어
- 항목 구분: 빈 줄 1개

## 필터링 규칙

다음은 기록에서 제외합니다:
- `<command-name>` 태그만 있고 나머지 텍스트 없는 메시지
- `# Context Usage` 헤더로 시작하는 메시지
- skill 로딩 메시지 (`Base directory for this skill:` 포함 + `다음 명령을 실행` 포함)
- `<local-command-stdout>` 포함된 로컬 커맨드
