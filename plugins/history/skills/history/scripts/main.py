"""history 스킬 진입점. CLAUDE_SESSION_ID 환경변수와 argv로 동작을 분기한다.

사용법:
    python main.py              # 현재 세션 export
    python main.py all          # 전체 세션 export
    python main.py del          # SESSION.md 체크 항목 dry-run 출력
    python main.py del {id}     # 단일 세션 존재 확인 dry-run
    python main.py del --confirm {id} [{id} ...]  # 실제 삭제 실행

[유지보수 주의]
user_prompt/builder.py의 스킬 주입 메시지 필터는 "Base directory for this skill:" 마커에
의존한다. Claude Code가 스킬 주입 포맷을 변경하면 SKILL.md 내용이 user-prompts.md에
그대로 기록될 수 있다 — 포맷 변경 시 extract_entries() 필터 재검토 필요.
"""
import os
import sys
from pathlib import Path

from common.jsonl import find_project_slug, all_jsonls_in_slug, find_jsonl
from session.builder import build_session_md
from session.delete import list_checked, list_checked_with_meta, find_full_id_by_prefix, delete_sessions, contains_current_session
from auto_mem.builder import build_auto_mem_md
from user_prompt.builder import write_user_prompts

# 현재 작업 디렉토리 기준 .history/ 폴더 (PROJECT_DIR에서 실행해야 정확한 위치)
HISTORY_DIR = Path(".history")


def run_export(session_id: str, all_sessions: bool):
    """user-prompts.md, SESSION.md, AUTO-MEMORY.md를 생성·갱신한다."""
    slug = find_project_slug(session_id)
    HISTORY_DIR.mkdir(exist_ok=True)

    if all_sessions and slug:
        # 전체 세션의 user-prompts.md 재생성
        for jpath in all_jsonls_in_slug(slug):
            sid = jpath.stem
            count = write_user_prompts(sid, HISTORY_DIR)
            print(f"저장: .history/user-prompts/{sid}/user-prompts.md ({count}개 항목)")
    else:
        # 현재 세션만 갱신
        count = write_user_prompts(session_id, HISTORY_DIR)
        print(f"저장: .history/user-prompts/{session_id}/user-prompts.md ({count}개 항목)")

    if slug:
        session_md_content = build_session_md(slug, session_id, HISTORY_DIR, all_sessions=all_sessions)
        session_file = HISTORY_DIR / "SESSION.md"
        session_file.write_text(session_md_content, encoding="utf-8")
        print(f"저장: {session_file}")

        auto_mem_content = build_auto_mem_md(slug)
        auto_mem_file = HISTORY_DIR / "AUTO-MEMORY.md"
        auto_mem_file.write_text(auto_mem_content, encoding="utf-8")
        print(f"저장: {auto_mem_file}")
    else:
        print("WARN: project slug 탐색 실패 — SESSION.md, AUTO-MEMORY.md 생략")


def run_delete_list_checked(session_id: str):
    """SESSION.md에서 [x] 체크된 세션 목록을 출력한다 (dry-run).

    skill.md가 이 출력을 읽고 사용자에게 확인을 요청한 뒤 --confirm으로 재호출한다.
    출력:
        CHECKED_NONE              — 체크 항목 없음
        CHECKED_LIST              — 체크 항목 있음 (이후 줄에 UUID 목록)
    """
    session_md = HISTORY_DIR / "SESSION.md"
    entries = list_checked_with_meta(session_md)
    if not entries:
        print("CHECKED_NONE")
        return
    current_entry = next((e for e in entries if e["sid"] == session_id), None)
    if current_entry:
        print(f"INCLUDES_CURRENT row={current_entry['row']} sid={session_id[:8]} name={current_entry['name']}")
        return
    print("CHECKED_LIST")
    for e in entries:
        print(e["sid"])


def run_delete_confirmed(session_id: str, target_ids: list[str]):
    """target_ids 세션을 실제 삭제하고 SESSION.md를 갱신한다."""
    if not target_ids:
        print("ERROR: --confirm 뒤에 세션 ID가 없습니다. 'del --confirm {uuid} ...' 형식으로 실행하세요.", file=sys.stderr)
        sys.exit(1)
    if contains_current_session(target_ids, session_id):
        print(f"ERROR: 현재 세션({session_id[:8]})이 삭제 목록에 포함되어 있어 실행이 중단되었습니다.", file=sys.stderr)
        sys.exit(1)
    slug = find_project_slug(session_id)
    if not slug:
        print("ERROR: project slug 탐색 실패", file=sys.stderr)
        sys.exit(1)
    deleted = delete_sessions(target_ids, slug, HISTORY_DIR)
    session_md_content = build_session_md(slug, session_id, HISTORY_DIR, all_sessions=False)
    (HISTORY_DIR / "SESSION.md").write_text(session_md_content, encoding="utf-8")
    for sid in deleted:
        print(f"삭제됨: {sid[:8]}")
    print("SESSION.md 갱신 완료")


def run_delete_check_single(session_id: str, target: str):
    """단일 세션 ID의 존재 여부를 확인한다 (dry-run).

    출력:
        FOUND {full_uuid}   — 세션 존재
        NOT_FOUND           — 세션 없음
    """
    slug = find_project_slug(session_id)
    if not slug:
        print("NOT_FOUND")
        return
    # 8자리 이하 prefix면 full UUID 탐색, 그 이상이면 full UUID로 간주
    full_id = find_full_id_by_prefix(target, slug) if len(target) <= 8 else target
    if not full_id or find_jsonl(full_id) is None:
        print("NOT_FOUND")
        return
    if full_id == session_id:
        print(f"IS_CURRENT_SESSION {full_id}")
        return
    print(f"FOUND {full_id}")


def main():
    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    if not session_id:
        print("ERROR: CLAUDE_SESSION_ID not set", file=sys.stderr)
        sys.exit(1)

    args = sys.argv[1:]

    if not args:
        run_export(session_id, all_sessions=False)
    elif args[0] == "all":
        run_export(session_id, all_sessions=True)
    elif args[0] == "del":
        if "--confirm" in args:
            idx = args.index("--confirm")
            run_delete_confirmed(session_id, args[idx + 1:])
        elif len(args) > 1 and not args[1].startswith("--"):
            run_delete_check_single(session_id, args[1])
        else:
            run_delete_list_checked(session_id)
    else:
        print(f"ERROR: unknown command '{args[0]}'", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
