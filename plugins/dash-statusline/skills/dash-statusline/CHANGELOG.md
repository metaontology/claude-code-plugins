# Changelog

## [1.3.0] - 2026-06-26

### Added
- skill 승격: `SKILL.md` 추가, `/dash-statusline setup`·`update` 커맨드로 설치·갱신 자동화 (수동 symlink·settings.json 절차 대행)

### Changed
- marketplace 표준 구조로 재배치: `plugins/dash-statusline/skills/dash-statusline/` (Python 소스를 `scripts/` 하위로 이동)

## [1.2.0] - 2026-06-16

### Changed
- `statuses/effort`: effort level 우측에 정량 점수 표시 (`low x0` / `medium x25` / `high x50` / `xhigh x75` / `max 🔥100`)

## [1.1.0] - 2026-06-16

### Added
- `statuses/rate_limits`: 구독(Anthropic login) 사용자에게 5시간/7일 rate limit 소비율 표시 (line 1 suffix `| 𝟓hr X% | 𝟕day Y%`)
- `statuses/effort`: 현재 추론 노력(effort level) 표시 (line 2, `effort high` 형식)
- `statuses/thinking`: 확장 사고 활성화 여부 표시 (line 2, `thinking on` 형식)
- 테마에 `effort`(#9de494), `thinking`(#d9f585), `blue`(#5fafd7), `purple_red` 색상 추가

## [1.0.0] - 2026-06-01

### Added
- 최초 릴리스
- line 1: 컨텍스트 사용률 바·토큰(in/out/cache/total)·비용·소요시간
- line 2: 모델명·언어(IME)
- line 3: 작업 경로·git 브랜치
- line 4: 도구 요약 (tool / agent / mcp / skill / task)
- line 5: 도구 상세 + permission mode + 모델 short name
