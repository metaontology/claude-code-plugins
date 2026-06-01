"""Claude Code 프로젝트 데이터 경로 상수."""
from pathlib import Path

# 세션 최초 시작 시각을 기록하는 레지스트리 파일
REGISTRY_FILE = Path.home() / ".claude" / "hooks" / "session_registry.json"

# Claude Code가 프로젝트별 jsonl·memory 파일을 저장하는 루트 디렉토리
PROJECTS_DIR = Path.home() / ".claude" / "projects"
