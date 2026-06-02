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
    """레코드 목록에서 첫 timestamp와 ai-title을 추출해 반환.

    ai-title 레코드가 없으면 첫 번째 사용자 텍스트 메시지 앞 60자를 fallback으로 사용한다.
    """
    ts, ai_title, first_user_text = "", "", ""
    for d in records:
        if not ts and d.get("timestamp"):
            ts = d["timestamp"]
        if d.get("type") == "ai-title" and not ai_title:
            ai_title = d.get("aiTitle", "")
        # ai-title fallback: 첫 번째 일반 사용자 텍스트 메시지 수집
        if not first_user_text and d.get("type") == "user":
            msg = d.get("message", {})
            if msg.get("role") == "user":
                content = msg.get("content", "")
                text = ""
                if isinstance(content, str):
                    text = content.strip()
                elif isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            text = c.get("text", "").strip()
                            break
                # 태그·노이즈 제외: command 태그, skill 주입, stdout 포함 메시지는 건너뜀
                if (text
                        and "<command-name>" not in text
                        and "Base directory for this skill:" not in text
                        and "<local-command-stdout>" not in text
                        and "<local-command-caveat>" not in text):
                    first_user_text = text

    if not ai_title and first_user_text:
        # 줄바꿈 제거 후 60자 제한
        ai_title = first_user_text.replace("\n", " ")[:60]

    return {"ts": ts, "ai_title": ai_title}
