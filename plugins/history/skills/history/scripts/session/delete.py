"""SESSION.md 체크박스 파싱 및 세션 삭제."""
import re
import shutil
import common.paths as paths
from pathlib import Path
from common.jsonl import all_jsonls_in_slug


def parse_session_id_from_cell(cell: str) -> str | None:
    """마크다운 링크 셀에서 full UUID 추출.

    예: '[abcd1234](./user-prompts/abcd1234-0000-.../user-prompts.md)' → 'abcd1234-0000-...'
    링크 형식이 아니면 None 반환.
    """
    m = re.search(r'\[[^\]]+\]\(\./user-prompts/([0-9a-f]{8}-[0-9a-f-]{27,35})/user-prompts\.md\)', cell)
    if m:
        return m.group(1)
    return None


def list_checked(session_md_path: Path) -> list[str]:
    """SESSION.md에서 삭제 컬럼이 비어있지 않은 행의 full UUID 목록 반환.

    파일이 없거나 체크 항목이 없으면 빈 리스트 반환.
    셀에 어떤 문자든 입력되어 있으면 삭제 대상으로 인식 (x, [x], v, ✓ 등).
    """
    return [entry["sid"] for entry in list_checked_with_meta(session_md_path)]


def list_checked_with_meta(session_md_path: Path) -> list[dict]:
    """SESSION.md에서 체크된 행의 메타 정보 목록 반환.

    반환 항목: {"row": int(1-based 데이터 행 번호), "sid": str, "name": str}
    파일이 없거나 체크 항목이 없으면 빈 리스트 반환.
    """
    if not session_md_path.exists():
        return []
    result = []
    data_row = 0
    for line in session_md_path.read_text(encoding="utf-8").splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 5:
            continue
        checkbox_col = parts[1]
        sid = parse_session_id_from_cell(parts[3])
        if sid:
            data_row += 1
            if checkbox_col:
                name = parts[4] if len(parts) > 4 else ""
                result.append({"row": data_row, "sid": sid, "name": name})
    return result


def find_full_id_by_prefix(prefix: str, slug: str) -> str | None:
    """8자리 prefix로 시작하는 jsonl 파일의 full UUID 반환. 없으면 None."""
    for jpath in all_jsonls_in_slug(slug):
        if jpath.stem.startswith(prefix):
            return jpath.stem
    return None


def contains_current_session(session_ids: list[str], current_id: str) -> bool:
    """session_ids에 current_id가 포함되어 있으면 True를 반환한다."""
    return current_id in session_ids


def delete_sessions(session_ids: list[str], slug: str, history_dir: Path) -> list[str]:
    """지정된 세션의 jsonl 파일과 .history/user-prompts/{sid}/ 디렉토리를 삭제한다.

    파일·디렉토리가 없으면 무시하고 계속 진행.
    삭제 처리된 세션 ID 목록을 반환.
    """
    deleted = []
    for sid in session_ids:
        # ~/.claude/projects/{slug}/{sid}.jsonl 삭제
        jsonl = paths.PROJECTS_DIR / slug / f"{sid}.jsonl"
        if jsonl.exists():
            jsonl.unlink()
        # .history/user-prompts/{sid}/ 디렉토리 삭제
        hist = history_dir / "user-prompts" / sid
        if hist.exists():
            shutil.rmtree(hist)
        deleted.append(sid)
    return deleted
