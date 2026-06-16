---
name: git
description: Use when performing git operations — commit, branch, merge, or PR
allowed-tools: Bash
disable-model-invocation: true
---

`$ARGUMENTS`의 첫 토큰으로 서브커맨드를 결정한다.

| 호출 | 동작 |
|------|------|
| `/git commit` | 스테이지 확인 → 이모지 컨벤셔널 커밋 |
| `/git branch [name]` | 브랜치 생성/전환/목록 |
| `/git merge [branch]` | 안전 병합 |
| `/git pr` | PR 생성 |
| `/git` (인수 없음) | 사용법 출력 |

---

## commit

1. `git status` 로 스테이지된 파일 확인
   - 스테이지된 파일이 있으면 해당 파일만 커밋
   - 없으면 `git diff` 분석 후 스테이지할 파일 제안
2. `git diff --staged` 분석 — 관심사가 다른 변경사항이 섞이면 분할 커밋 제안
3. 커밋 메시지 포맷: `<이모지> <타입>: <설명>`
   - 명령형 어조, 72자 미만
   - **커밋에 Claude 서명 절대 추가하지 않음**

**타입 / 이모지:**
✨ feat | 🐛 fix | 📝 docs | 💄 style | ♻️ refactor | ⚡ perf | ✅ test | 🔧 chore | 🚀 ci | 🔒️ security | 🔥 remove | 🚑️ hotfix | 🎉 init | 🔖 release | 🚧 wip | 💥 breaking | 🩹 minor-fix | ⏪️ revert

---

## branch

`/git branch [name]`

- **name 없음**: `git branch -v` 로 로컬 브랜치 목록 출력
- **name 있음**: 새 브랜치 생성 후 전환

브랜치 생성 절차:
1. uncommitted 변경사항 있으면 stash 여부 확인
2. 브랜치명 검증 — 권장 프리픽스: `feature/`, `fix/`, `hotfix/`, `docs/`, `chore/`, `refactor/`, `test/`
3. `git checkout -b <name>` 실행

---

## merge

`/git merge [branch]`

- **branch 없음**: 병합할 브랜치명 입력 요청
- **branch 있음**: 아래 절차 실행

병합 절차:
1. uncommitted 변경사항 확인 — 있으면 중단
2. `git fetch` 후 대상 브랜치 최신화 확인
3. fast-forward 가능 여부 확인
   - 가능하면 `git merge <branch>`
   - 불가하면 전략 선택 제안 (ff / no-ff / squash)
4. 충돌 발생 시 충돌 파일 목록 표시 → 파일별 해결 안내 → `git add` + `git commit`
5. 병합 완료 후 소스 브랜치 삭제 여부 확인

---

## pr

1. `git status` 확인 — uncommitted 변경사항 있으면 중단
2. 현재 브랜치가 원격에 push 되어 있는지 확인
   - 없으면 `git push -u origin <branch>` 실행 후 계속
3. `git log origin/main..HEAD --oneline` 으로 커밋 목록 분석
4. 브랜치명과 커밋 메시지 기반으로 PR 제목/본문 초안 생성
5. `gh pr create` 실행 (gh CLI 없으면 안내 출력)

PR 본문 기본 구조:
```
## 변경사항 요약
[커밋 목록 기반 자동 생성]

## 체크리스트
- [ ] Self-review 완료
- [ ] 테스트 확인
- [ ] 문서 업데이트 (필요시)
```
