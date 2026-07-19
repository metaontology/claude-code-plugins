# Changelog

## [1.4.0] - 2026-07-19

### Added
- `statuses/context`: 직전 턴 usage 스냅샷 전용 라인 신설 (line 2). `🗃️ 🇵🇷🇪🇻`(응답 직후 현재 컨텍스트 4합) + `📥 🇮🇳 read/creation/uncached` + `📤 🇴🇺🇹` output, 각 그룹에 턴 비용 참고치($) 표기. `cache_read == 0 && cache_creation > 0`일 때만 `🥶 cache-cold` 인디케이터 노출
- `statuses/context/pricing`: 모델별 단가표(prefix 매칭) × 배율(cache read 0.1× / creation 1.25×)로 턴 비용 계산. 모델 미등록 시 $ 생략
- 테마에 `orange_soft`(#38;5;179, tan) 색상 추가 — line 2 $ 전용(line 1 `orange`보다 얕은 톤)

### Changed
- `statuses/context`: line 1 재설계 — 토큰 나열(`in/out/cache/total`) 제거, 스냅샷 3합을 대괄호 `[393.4k/1m]`로 축약하고 누적 비용은 `$` 라벨로만 표기. `_fmt_tok`으로 k/m 단위 소수 1자리 표시
- 출력 줄 수 4~5줄 → 5~6줄 (line 2에 턴 라인 삽입)

### Fixed
- line 1 `total 1m/1m` 오표기 수정: 누적 계열(`total_input/output_tokens`)과 스냅샷 계열(`current_usage.*`)을 혼합 합산해 window와 비교하던 이중 계산 제거 — 토큰 표시를 `current_usage` 스냅샷 기준으로 통일

## [1.3.1] - 2026-07-10

### Added
- `statuses/telemetry`: OTEL 텔레메트리 활성화 시 line 2 `🌍 EN` 뒤에 `📡 telemetry on` 표시. `~/.claude/settings.json`의 `env`에서 상위 7개 KEY의 VALUE 일치 + 하위 2개(CLIENT_CERT/KEY) 경로의 파일 존재를 모두 만족할 때만 노출

### Changed
- `statuses/context`: line 1 소요시간(🕒)이 60분 이상이면 시간 단위를 포함해 표시 (`2h 3m 4s`), 60분 미만은 기존 `Xm Ys` 유지

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
