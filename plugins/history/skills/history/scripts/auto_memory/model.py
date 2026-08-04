"""auto-memory를 뷰어가 표시할 수 있는 값으로 읽어내는 계층.

대상은 `~/.claude/projects/{슬러그}/memory/` 하나다. 프로젝트의 `CLAUDE.md`나 `docs/`,
사용자 전역 지침은 대상이 아니다.

이 계층은 문자열을 조립하지 않는다. 마크다운 문서를 만들지 않고 구조화된 값만 반환한다.
"""
import re
from pathlib import Path

import common.paths as paths

# 인덱스 파일. 항목이 아니라 항목을 가리키는 포인터 목록이다
INDEX_FILE = "MEMORY.md"

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)", re.DOTALL)
# 줄머리에 앵커를 건다. 앵커가 없으면 `type`이 `node_type`의 뒷부분에 매치한다
_NAME_RE = re.compile(r"^\s*name:\s*(.+)$", re.M)
_DESC_RE = re.compile(r"^\s*description:\s*(.+)$", re.M)
_TYPE_RE = re.compile(r"^\s*type:\s*(.+)$", re.M)
# `- [제목](파일명.md) — 요약` 에서 링크 대상만 꺼낸다
_POINTER_RE = re.compile(r"^\s*-\s*\[[^\]]*\]\(([^)]+)\)")


def memory_dir(slug: str) -> Path:
    """프로젝트 슬러그의 auto-memory 디렉토리 경로 반환."""
    return paths.PROJECTS_DIR / slug / "memory"


def index_path(directory: Path) -> Path:
    """auto-memory 인덱스(`MEMORY.md`) 경로 반환."""
    return directory / INDEX_FILE


def parse_item(path: Path) -> dict:
    """항목 파일 하나를 항목 값으로 읽는다.

    frontmatter가 없거나 형식이 어긋나도 항목에서 빠지지 않는다 — 그 경우 파일명을
    이름으로 쓰고 전체를 본문으로 담는다. 형식이 어긋난 파일이야말로 사람이 봐야 하는
    대상이므로 목록에서 사라지면 영구히 방치된다.

    본문은 절단하지 않는다. 승격 판정은 본문을 읽어야 답할 수 있다.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    matched = _FRONTMATTER_RE.match(raw)
    if matched:
        front, body = matched.group(1), matched.group(2).strip()
        name = _first(_NAME_RE, front) or path.stem
        description = _first(_DESC_RE, front)
        item_type = _first(_TYPE_RE, front)
    else:
        name, description, item_type, body = path.stem, "", "", raw.strip()

    return {
        "file": path.name,
        "path": str(path),
        "name": name,
        "description": description,
        "type": item_type,
        "body": body,
        "index_line": "",
    }


def _first(pattern: re.Pattern, text: str) -> str:
    """정규식의 첫 매치 그룹을 다듬어 반환. 없으면 빈 문자열."""
    matched = pattern.search(text)
    return matched.group(1).strip() if matched else ""


def parse_index(text: str) -> dict:
    """인덱스 전문에서 포인터 줄을 뽑아 `{파일명: 줄 전문}`으로 반환한다.

    포인터 형태가 아닌 줄은 무시한다 — 사람이 머리말이나 빈 줄을 넣을 수 있다.
    """
    pointers = {}
    for line in text.splitlines():
        matched = _POINTER_RE.match(line)
        if matched:
            pointers[matched.group(1).strip()] = line.strip()
    return pointers


def load_auto_memory(slug: str) -> dict:
    """슬러그의 auto-memory를 항목 목록·인덱스·불일치로 읽는다.

    `MEMORY.md`는 항목 목록에 들어가지 않는다. 인덱스가 항목인 척 섞이면 폐기 기능이
    붙었을 때 **인덱스가 삭제 후보로 제시된다.**

    디렉토리가 없거나 비어 있으면 빈 항목 목록을 돌려준다. 오류를 내지 않는다.

    반환값의 키 — `items` · `index_lines` · `broken` · `missing`
    """
    directory = memory_dir(slug)
    index_file = index_path(directory)
    index_text = (
        index_file.read_text(encoding="utf-8", errors="replace")
        if index_file.exists()
        else ""
    )
    pointers = parse_index(index_text)

    items = []
    if directory.exists():
        for path in sorted(directory.glob("*.md")):
            if path.name == INDEX_FILE:
                continue
            item = parse_item(path)
            item["index_line"] = pointers.get(item["file"], "")
            items.append(item)

    present = {item["file"] for item in items}
    return {
        "items": items,
        "index_lines": list(pointers.values()),
        # 인덱스에 줄이 있는데 가리키는 항목 파일이 없다
        "broken": [
            {"target": target, "line": line}
            for target, line in pointers.items()
            if target not in present
        ],
        # 항목 파일이 있는데 인덱스에 줄이 없다
        "missing": [item["file"] for item in items if not item["index_line"]],
    }
