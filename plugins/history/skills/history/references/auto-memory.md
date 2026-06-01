# AUTO-MEMORY.md 포맷 및 메모리 이전 패턴

## 파일 헤더

```
# AUTO-MEMORY.md

원본 경로: `C:\Users\jun\.claude\projects\{프로젝트-슬러그}\memory`

---
```

## 메모리가 없는 경우

```
현재 저장된 메모리 없음.
```

## 메모리가 있는 경우

memory/ 폴더의 각 `.md` 파일을 읽어 아래 형식으로 인라인 기재:

```
## {name 필드}
타입: {metadata.type}
설명: {description 필드}

{본문}

---
```

## 메모리 파일 구조 (frontmatter)

```yaml
---
name: short-kebab-case-slug
description: 한 줄 요약
metadata:
  type: user | feedback | project | reference
---
```

## 메모리 이전 요청 패턴

"AUTO-MEMORY를 프로젝트 내부로 옮겨줘", "메모리를 docs/에 저장해줘" 류 요청 시:

1. 이동 대상 경로 확인 (`.claude/rules` / `docs/guides` / `docs/` 등 — 사용자 지정 또는 문맥 판단)
2. 메모리 파일 내용을 대상 경로에 적합한 형식으로 변환 후 저장
3. 원본(`~/.claude/projects/{slug}/memory/`) 파일 삭제 전 반드시 확인:
   > "원본 메모리 파일 N개를 `~/.claude/projects/{slug}/memory/`에서 삭제하시겠습니까? (y/N)"
4. 삭제 후 AUTO-MEMORY.md 갱신
