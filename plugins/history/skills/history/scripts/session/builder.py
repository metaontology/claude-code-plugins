"""SESSION.md 마크다운 문서 생성."""
import common.paths as paths
from pathlib import Path
from common.jsonl import all_jsonls_in_slug, parse_jsonl, get_session_meta
from common.time_util import parse_iso


def build_session_md(slug: str, current_session_id: str, history_dir: Path, all_sessions: bool = False) -> str:
    """프로젝트의 모든 세션을 읽어 SESSION.md 내용을 생성한다.

    링크 포함 조건 (세 가지 중 하나):
    - current_session_id 와 일치하는 세션 (현재 세션)
    - all_sessions=True (전체 갱신 모드)
    - history_dir/{sid}/user-prompts.md 가 이미 존재 (이전에 export된 세션)
    """
    rows = []
    for jpath in all_jsonls_in_slug(slug):
        sid = jpath.stem
        records = parse_jsonl(jpath)
        meta = get_session_meta(records)
        ts_str = meta["ts"]
        ai_title = meta["ai_title"] or "(제목 없음)"

        if ts_str:
            try:
                dt = parse_iso(ts_str)
                created_at = dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                created_at = "-"
        else:
            created_at = "-"

        short_id = sid[:8]
        # 이미 export된 세션은 /history 모드에서도 링크 유지
        has_prompts = (history_dir / "user-prompts" / sid / "user-prompts.md").exists()
        if sid == current_session_id or all_sessions or has_prompts:
            link = f"[{short_id}](./user-prompts/{sid}/user-prompts.md)"
        else:
            link = short_id

        words = ai_title.split()
        session_name = " ".join(words[:3]) if words else "(제목 없음)"

        rows.append((created_at, sid, link, session_name, ai_title))

    # 최신 세션이 위에 오도록 내림차순 정렬
    rows.sort(reverse=True)

    lines = [
        "# SESSION.md\n",
        f"원본 경로: `{paths.PROJECTS_DIR / slug}`\n",
        "> `/history` — 현재 세션만 갱신 · `/history all` — 모든 세션 갱신\n",
        "> 삭제할 세션은 🗑️ 열에 `x` 표시 후 `/history del` 실행\n",
        "---\n",
        "| 🗑️ | 생성일시 | 세션 ID | 세션명 | 설명 |",
        "|---|----------|---------|--------|------|",
    ]
    for created_at, sid, link, session_name, description in rows:
        lines.append(f"|  | {created_at} | {link} | {session_name} | {description} |")

    return "\n".join(lines) + "\n"
