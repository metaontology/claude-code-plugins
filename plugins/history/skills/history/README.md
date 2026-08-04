# history 스킬

Claude Code 세션의 대화 기록을 프로젝트 `.history/` 폴더에 모아 **브라우저에서 열람·정리**한다.

---

## 명령어

| 명령 | 설명 |
|------|------|
| `/history` | 기록을 최신 상태로 갱신하고, 현재 프로젝트의 모든 세션을 담은 뷰어를 브라우저에 연다 |
| `/history rebuild` | 갱신 판정을 무시하고 전 세션을 다시 만든 뒤, 위와 같다 |

`rebuild`는 열람 범위를 바꾸는 옵션이 아니다. 두 명령이 보여주는 것은 항상 같다.
`refresh`, `전체 갱신`, `다시 빌드` 등으로 요청해도 `rebuild`와 같이 동작한다.

세션 삭제·정리 명령은 없다. **뷰어 안에서** 한다.

---

## 산출물

프로젝트 루트의 `.history/` 폴더 아래에 뷰어와 그 데이터가 생성된다.
`.history/`는 재생성 가능한 산출물이며, 원본은 Claude Code가 저장하는 jsonl이다.

## 사용자 설정

뷰어에서 고른 테마와 패널 폭은 프로젝트 밖에 남는다.

```
~/.claude/history/config.json
```

프로젝트마다 갈리지 않으므로 어느 프로젝트에서 열어도 같은 화면이다. 사람이 열어 고칠 수
있고, 지우면 기본값(시스템 테마 · 340px)으로 돌아간다. `.history/`를 통째로 지워도 남는다.

## 원본 데이터 경로

```
~/.claude/projects/{프로젝트-슬러그}/
├── {세션UUID}.jsonl            ← Claude Code가 저장하는 세션 원본
└── memory/
    └── *.md                    ← 자동 메모리 파일
```

프로젝트 슬러그는 프로젝트 절대 경로의 구분자를 `-`로 치환한 디렉토리명이다.
예: `C:\Users\jun\hook-test` → `C--Users-jun-hook-test`

세션을 지우면 이 jsonl 원본도 함께 지워진다. **복구되지 않는다.**

---

## 구성

| 경로 | 역할 |
|---|---|
| `SKILL.md` | 스킬 진입점. 사용자 표현을 CLI 인자로 정규화한다 |
| `scripts/main.py` | 명령 해석 진입점 |
| `scripts/common/` | 경로 상수, jsonl 탐색·파싱 |
| `scripts/session/` · `scripts/auto_memory/` | 뷰어가 표시할 값을 뽑는 모델 계층 |
| `scripts/store/` | 산출물 경로와 갱신 판정, 사용자 설정 파일 |
| `scripts/server/` | 뷰어에 파괴적 연산을 제공하는 로컬 HTTP 서버 |
| `scripts/viewer/` | 뷰어 HTML 생성과 정적 자산 |
| `scripts/tests/` | pytest 테스트 |
