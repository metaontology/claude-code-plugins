# context-observer

입력창 위에 두 줄을 그리는 Claude Code mod.

```
● cache   100% [cached: r 271k, uncached: w 878 new 2] | timeout 56:59/1h | auto compact 50:49
● context  28% [279.4k/1m] | 𝟓hr 28% | 𝟕day 13%
```

- **cache 줄** — 직전 메인 루프 요청의 캐시 적중률 `r ÷ (r + w + new)`, 캐시 만료까지 남은 시간 / 수명, 자리 비움 압축까지 남은 시간
  - `r` 캐시에서 읽음 · `w` 캐시에 새로 씀 · `new` 캐시를 거치지 않음
  - 머리 아이콘: `●` warm(초록) · `▲` 곧 만료(노랑) · `✖` 만료·빗나감(빨강) · `○` 셀 것 없음
  - 자리 비움 압축 카운트다운이 없으면 끝에 안내 문장(`warm: keep going`, `expired: … /compact first` 등)
  - 90칸보다 좁으면 괄호 안이 `[245k tok]` 로 줄어든다
- **context 줄** — 컨텍스트 사용률 `[토큰/창]`, 5시간·7일 사용량. 색은 `~/.claude/dash-statusline` default 테마(70%↑ 노랑, 90%↑ 빨강)
- 두 줄 모두 라벨 8칸 + 퍼센트 4칸 오른쪽 정렬이라 `[` 가 같은 열에 선다
- `/cache` — 턴별 read·wrote·new 표와 남은 시간 막대 창. `/cache stop` 으로 닫는다
- 리로드 직후에는 요청 기록이 비어 cache 줄이 없다. 메시지를 하나 주고받으면 나온다

## 설치

```
/plugin install context-observer@metaontology-claude-code-plugins
```

Claude Code 2.1.287 이상. 설치 뒤 `/reload-plugins`, 그다음 메시지를 하나 주고받으면 두 줄이 나온다.

## 파일

| 파일 | 맡은 일 |
| --- | --- |
| `hooks/register.tsx` | 상태를 들고 이벤트를 잇는다 |
| `hooks/band.tsx` | 입력창 위 두 줄 그리기 |
| `hooks/pane.tsx` | `/cache` 창 그리기 |
| `hooks/cache.ts` | 캐시 계산(순수 함수, 원본 그대로) |
| `hooks/usage.ts` | context 줄 계산과 색(순수 함수) |
| `hooks/settings.ts` | 설정 파일 읽기(읽기만) |
| `tests/` | `claude plugin test <플러그인 폴더>` |

## 읽는 것

- 환경변수: 캐시·압축 관련(`ENABLE_PROMPT_CACHING_1H`, `FORCE_PROMPT_CACHING_5M`, `CLAUDE_CODE_PROMPT_CACHE_TTL`, `DISABLE_PROMPT_CACHING*`, `CLAUDE_CODE_IDLE_COMPACT_MIN_TOKENS`, `DISABLE_*COMPACT`, `HOME`, `CLAUDE_CONFIG_DIR`)
- 파일: `.claude/settings.local.json` · `.claude/settings.json` · `~/.claude/settings.json` 의 `promptCacheTtl`·`idleCompaction`·`autoCompactEnabled`, `~/.claude.json` 의 배포 플래그와 `autoCompactEnabled`
- 네트워크 요청·프로세스 실행·파일 쓰기는 없다

## 옵션

`~/.claude/settings.json` 의 `pluginConfigs["context-observer@<마켓플레이스>"].options`, 또는 `/plugin configure context-observer@<마켓플레이스>`.
`metaontology-claude-code-plugins` 에서 설치했으면 `context-observer@metaontology-claude-code-plugins`.

| 옵션 | 기본 | 뜻 |
| --- | --- | --- |
| `ttl` | `auto` | 캐시 수명. `5m`·`1h` 로 고정 |
| `warnSeconds` | 60 | 만료 경고 문턱(초) |
| `compactAtTokens` | 100000 | 만료된 캐시가 `/compact` 를 권하는 프롬프트 크기 |
| `band` | true | cache 줄. context 줄은 늘 그린다 |
| `status` | false | 입력창 아래 짧은 항목 `cache 98% · 3:41` |
| `toast` | true | 만료 직전 토스트(문턱, 10·3·2·1초) |
| `idleCompact` | true | 자리 비움 압축 카운트다운 |

## 출처와 원본과 다른 점

cache 쪽은 [davila7/claude-code-templates](https://github.com/davila7/claude-code-templates) 의
`cli-tool/components/mods/observability/prompt-cache-control`(커밋 `3c468dd`, MIT, `LICENSE` 참조)을 바탕으로 한다.

- cache 줄 모양: 막대 제거, `[cached: … , uncached: … ]`, `timeout mm:ss/ttl`, `auto compact mm:ss`, 한 Text 한 줄
- `session.compact` hook 제거 — 조직이 관리하는 Claude Code 에서는 사용자가 설치한 mod 의 이 hook 이 돌지 않는다.
  그래서 "자리 비움 중 압축됨" 토스트가 없고, 압축 직후 다음 메시지 전까지 cache 줄이 옛 카운트다운을 보인다
- context 줄(옛 usage-line mod)을 합쳤다
- 테스트의 가짜 파일 경로를 Windows 에서도 맞게 고쳤다
