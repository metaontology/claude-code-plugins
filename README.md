# claude-code-plugins

Claude Code 플러그인 모음.

## 설치

```bash
/plugin marketplace add metaontology/claude-code-plugins
```

---

## dash-statusline

Claude Code 응답 완료 시 컨텍스트·토큰·비용·모델·경로·도구 활동을 4~5줄로 출력하는 statusline 렌더러.

### 설치 및 설정

플러그인 설치 후 다음 한 줄이면 됩니다.

```bash
/dash-statusline setup
```

`setup`이 심볼릭 링크 생성, `settings.json` 등록, 실행 권한 부여, 동작 확인까지 자동으로 처리합니다. (`/dash-statusline start`도 동일하게 동작합니다.)

### 동작 확인

`setup` 마지막에 자동으로 확인하지만, 수동으로 확인하려면:

```bash
echo '{}' | python ~/.claude/dash-statusline/scripts/main.py
```

4~5줄이 출력되면 정상입니다.

### 업데이트

```bash
/plugin
```

업데이트가 있으면 `✔ Updated dash-statusline` 메시지가 표시됩니다. 이후:

```bash
/reload-plugins
/dash-statusline update
```

`update`가 새 버전으로 심볼릭 링크를 재연결하고 실행 권한을 재부여합니다. `settings.json` 수정은 불필요합니다.
