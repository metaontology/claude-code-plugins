"""Claude Code 프로젝트의 jsonl 세션 파일 탐색 및 파싱."""
import json
from datetime import datetime
from pathlib import Path
import common.paths as paths
from common.paths import REGISTRY_FILE


def find_jsonl(session_id: str) -> Path | None:
    """session_id에 해당하는 jsonl 파일 경로 반환. 없으면 None."""
    for f in paths.PROJECTS_DIR.rglob(f"{session_id}.jsonl"):
        return f
    return None


def find_project_slug(session_id: str) -> str | None:
    """session_id가 속한 프로젝트 슬러그(디렉토리명) 반환. 없으면 None."""
    for f in paths.PROJECTS_DIR.rglob(f"{session_id}.jsonl"):
        return f.parent.name
    return None


def all_jsonls_in_slug(slug: str) -> list[Path]:
    """slug 디렉토리 내 모든 jsonl 파일을 이름순으로 반환."""
    d = paths.PROJECTS_DIR / slug
    return sorted(d.glob("*.jsonl")) if d.exists() else []


def get_session_start(session_id: str) -> str:
    """session_registry.json에서 세션 최초 시작 시각 반환. 레지스트리 없으면 현재 시각."""
    if REGISTRY_FILE.exists():
        try:
            registry = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
            if session_id in registry:
                return registry[session_id]
        except (json.JSONDecodeError, OSError):
            pass
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_jsonl(path: Path) -> list[dict]:
    """jsonl 파일을 파싱해 레코드 목록 반환. 빈 줄·파싱 오류 행은 건너뜀."""
    records = []
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def get_session_meta(records: list[dict]) -> dict:
    """레코드 목록에서 첫 timestamp와 ai-title을 추출해 반환."""
    ts, ai_title = "", ""
    for d in records:
        if not ts and d.get("timestamp"):
            ts = d["timestamp"]
        if d.get("type") == "ai-title" and not ai_title:
            ai_title = d.get("aiTitle", "")
    return {"ts": ts, "ai_title": ai_title}
