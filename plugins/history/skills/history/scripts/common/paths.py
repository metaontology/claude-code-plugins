"""Claude Code 프로젝트 데이터 경로 상수."""
from pathlib import Path

# 세션 최초 시작 시각을 기록하는 레지스트리 파일
REGISTRY_FILE = Path.home() / ".claude" / "hooks" / "session_registry.json"

# Claude Code가 프로젝트별 jsonl·memory 파일을 저장하는 루트 디렉토리
PROJECTS_DIR = Path.home() / ".claude" / "projects"

# 실행 중인 Claude Code 인스턴스가 자기 정보를 두는 디렉토리. 파일 하나가 인스턴스
# 하나이고 파일명은 pid다. 위의 REGISTRY_FILE과 다른 것이므로 이름을 갈라 둔다
LIVE_SESSIONS_DIR = Path.home() / ".claude" / "sessions"

# 이 스킬의 사용자 설정. 프로젝트의 `.history/`(산출물)와 다른 것이므로 점을 붙이지 않아
# 이름이 갈린다. 산출물은 지워도 다시 생기지만 이 파일은 사용자가 정한 값이다
USER_CONFIG_DIR = Path.home() / ".claude" / "history"
USER_CONFIG_FILE = USER_CONFIG_DIR / "config.json"
