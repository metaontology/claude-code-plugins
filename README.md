# claude-code-plugins

Claude Code 플러그인 모음.

## 설치

```bash
/plugin marketplace add metaontology/claude-code-plugins
```

---

## dash-statusline

Claude Code 응답 완료 시 컨텍스트·토큰·비용·모델·경로·도구 활동을 4~5줄로 출력하는 statusline 렌더러.

### 추가 설정 필요

플러그인 설치 후 다음 두 단계 실행하세요.

#### 1. 심볼릭 링크 생성

기존 `~/.claude/dash-statusline`이 있으면 삭제하고, 플러그인 캐시 경로로 symlink를 생성.

```bash
# 기존 파일/디렉토리 제거
rm -rf ~/.claude/dash-statusline

# 심볼릭 링크 생성 (버전 번호는 실제 설치된 버전으로 교체)
ln -sfn ~/.claude/plugins/cache/metaontology-claude-code-plugins/dash-statusline/{버전} \
    ~/.claude/dash-statusline

# 실행 권한 부여 (plugin install 시 누락되는 경우 있음)
chmod +x ~/.claude/dash-statusline/main.py
```

> **버전 업데이트 시**: `ln -sfn` 명령의 버전 번호만 새 버전으로 바꿔 재실행하면 됩니다.

#### 2. settings.json 설정

`~/.claude/settings.json`에 다음 내용 추가하세요.

```json
{
  "statusLine": {
    "type": "command",
    "command": "python ~/.claude/dash-statusline/main.py"
  }
}
```

### 동작 확인

```bash
echo '{}' | python ~/.claude/dash-statusline/main.py
```

### 업데이트

```bash
/plugin
```

업데이트가 있으면 `✔ Updated dash-statusline` 메시지가 표시됩니다. 이후:

```bash
/reload-plugins
```

그리고 심볼릭 링크를 새 버전으로 재연결하세요.

```bash
# 새 버전으로 심링크 재연결 (버전 번호 교체)
ln -sfn ~/.claude/plugins/cache/metaontology-claude-code-plugins/dash-statusline/{새버전} \
    ~/.claude/dash-statusline

# 실행 권한 부여 (버전마다 누락되는 경우 있음)
chmod +x ~/.claude/dash-statusline/main.py

# 이전 버전 캐시 삭제 (선택)
rm -rf ~/.claude/plugins/cache/metaontology-claude-code-plugins/dash-statusline/{이전버전}
```

> `settings.json` 수정은 불필요합니다. 심링크 재연결 + 실행 권한 부여 후 새 버전이 즉시 적용됩니다.
