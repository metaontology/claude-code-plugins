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

플러그인 설치만으로는 statusline이 동작하지 않는다. 아래 두 단계가 필요하다.

#### 1. 심볼릭 링크 생성

기존 `~/.claude/dash-statusline`이 있으면 삭제하고, 플러그인 캐시 경로로 symlink를 건다.

```bash
# 기존 파일/디렉토리 제거
rm -rf ~/.claude/dash-statusline

# 심볼릭 링크 생성 (버전 번호는 실제 설치된 버전으로 교체)
ln -sfn ~/.claude/plugins/cache/metaontology-claude-code-plugins/dash-statusline/1.0.0 \
    ~/.claude/dash-statusline

# 실행 권한 부여 (plugin install 시 누락되는 경우 있음)
chmod +x ~/.claude/dash-statusline/main.py
```

> **버전 업데이트 시**: `ln -sfn` 명령의 버전 번호만 새 버전으로 바꿔 재실행하면 된다. `settings.json`은 수정 불필요.

#### 2. settings.json 설정

`~/.claude/settings.json`에 아래 항목을 추가한다.

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

정상이면 4~5줄이 출력된다.
