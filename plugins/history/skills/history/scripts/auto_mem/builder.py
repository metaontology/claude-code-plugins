"""AUTO-MEMORY.md 마크다운 문서 생성."""
import re
from pathlib import Path
import common.paths as paths


def build_auto_mem_md(slug: str) -> str:
    """~/.claude/projects/{slug}/memory/ 의 메모리 파일을 읽어 AUTO-MEMORY.md 내용을 생성한다.

    메모리 파일이 없으면 '현재 저장된 메모리 없음.' 메시지 반환.
    각 파일의 YAML frontmatter(name, description, type)를 파싱해 섹션으로 구성.
    """
    memory_dir = paths.PROJECTS_DIR / slug / "memory"
    header = [
        "# AUTO-MEMORY.md\n",
        f"원본 경로: `{memory_dir}`\n",
        "---\n",
    ]

    if not memory_dir.exists():
        return "\n".join(header) + "\n현재 저장된 메모리 없음.\n"

    mem_files = sorted(memory_dir.glob("*.md"))
    if not mem_files:
        return "\n".join(header) + "\n현재 저장된 메모리 없음.\n"

    sections = []
    for mf in mem_files:
        raw = mf.read_text(encoding="utf-8", errors="replace")
        # frontmatter(--- ... ---) 파싱
        fm_match = re.match(r"^---\n(.*?)\n---\n?(.*)", raw, re.DOTALL)
        if fm_match:
            fm_text, body = fm_match.group(1), fm_match.group(2).strip()
            name = re.search(r"^name:\s*(.+)$", fm_text, re.M)
            desc = re.search(r"^description:\s*(.+)$", fm_text, re.M)
            typ = re.search(r"type:\s*(.+)$", fm_text, re.M)
            name = name.group(1).strip() if name else mf.stem
            desc = desc.group(1).strip() if desc else ""
            typ = typ.group(1).strip() if typ else ""
        else:
            # frontmatter 없는 파일은 전체를 본문으로 처리
            name, desc, typ, body = mf.stem, "", "", raw.strip()

        sections.append(f"## {name}\n타입: {typ}\n설명: {desc}\n\n{body}\n\n---")

    return "\n".join(header) + "\n" + "\n\n".join(sections) + "\n"
