---
name: dash-statusline
description: Use when installing, configuring, or updating the dash-statusline status line for Claude Code — registering it in ~/.claude/settings.json, fixing a missing execution permission, or repointing it after a plugin version update.
---

# dash-statusline

Claude Code 응답 완료 시 컨텍스트·토큰·비용·모델·경로·도구 활동을 5~6줄로 출력하는 statusline 렌더러. 이 skill은 설치·설정·갱신을 자동화한다 (수동 설치 절차 대행).

## 서브커맨드

| 호출 | 용도 |
|------|------|
| `/dash-statusline setup` | 최초 설정: settings.json 등록 + 실행권한 + 동작확인 |
| `/dash-statusline update` | 플러그인 새 버전으로 경로 갱신 |

`/dash-statusline start`는 `setup`과 동일하게 처리한다.

## setup

플러그인 설치 후 statusline을 활성화한다.

1. **설치 경로·버전 확인** — `~/.claude/plugins/cache/metaontology-claude-code-plugins/dash-statusline/` 아래의 버전 디렉토리를 찾는다. 실행 진입점은 `{버전}/skills/dash-statusline/scripts/main.py`.

2. **안정 경로(심볼릭 링크) 생성** — 버전이 바뀌어도 settings.json을 고정하기 위해 `~/.claude/dash-statusline`를 cache의 `{버전}/skills/dash-statusline` 폴더로 연결한다. 기존 링크/디렉토리가 있으면 제거 후 재생성.
   - macOS/Linux: `ln -sfn ~/.claude/plugins/cache/metaontology-claude-code-plugins/dash-statusline/{버전}/skills/dash-statusline ~/.claude/dash-statusline`
   - Windows(개발자 모드/관리자): `New-Item -ItemType SymbolicLink -Path "$HOME\.claude\dash-statusline" -Target "$HOME\.claude\plugins\cache\metaontology-claude-code-plugins\dash-statusline\{버전}\skills\dash-statusline"`

3. **실행 권한 부여** (Unix 계열, plugin install 시 누락되는 경우) — `chmod +x ~/.claude/dash-statusline/scripts/main.py`

4. **settings.json 등록** — `~/.claude/settings.json`의 `statusLine`을 설정. 기존 statusLine이 있으면 사용자에게 확인 후 교체.
   ```json
   {
     "statusLine": {
       "type": "command",
       "command": "python ~/.claude/dash-statusline/scripts/main.py"
     }
   }
   ```

5. **동작 확인** — 아래가 5~6줄을 출력하면 성공.
   ```bash
   echo '{}' | python ~/.claude/dash-statusline/scripts/main.py
   ```

## update

`/plugin`으로 플러그인을 갱신한 뒤 실행한다.

1. cache에서 새 버전 디렉토리를 확인한다.
2. 안정 경로 심볼릭 링크를 새 버전으로 재연결한다 (setup 2번, 버전만 교체).
3. 실행 권한을 재부여한다 (Unix, 버전마다 누락 가능): `chmod +x ~/.claude/dash-statusline/scripts/main.py`
4. (선택) 이전 버전 cache 디렉토리를 삭제한다.
5. 동작을 확인한다 (setup 5번).

> settings.json은 안정 경로(`~/.claude/dash-statusline`)를 가리키므로 update 시 수정이 불필요하다.

## Common Mistakes

- **`main.py`를 루트에서 찾음** — 코드는 `scripts/` 아래에 있다. 경로는 `~/.claude/dash-statusline/scripts/main.py`.
- **실행 권한 누락** — plugin install/update 시 `+x`가 빠져 statusline이 안 뜨는 경우가 잦다. setup·update마다 `chmod +x`를 확인한다 (Unix).
- **settings.json을 cache 버전 경로로 직접 지정** — 버전이 바뀌면 깨진다. 반드시 안정 심볼릭 링크 경로를 가리키게 한다.
- **`python3` 사용** — `python`으로 실행한다.
