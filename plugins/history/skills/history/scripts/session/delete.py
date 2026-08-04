"""세션 jsonl 원본 삭제.

대상은 `~/.claude/projects/{슬러그}/{세션ID}.jsonl` 원본이다. **복구할 수 없다.**

마크다운 표를 역파싱해 선택된 세션을 얻는 함수들은 없다. 산출물이 마크다운이 아니고,
화면이 식별자를 직접 갖고 보내므로 역파싱할 표현이 없다.
"""
import common.paths as paths


def blocked_reason(session_id: str, current_id: str, live_ids: set[str],
                   verb: str = "삭제") -> str:
    """그 세션에 손대는 것을 거부할 사유. 거부하지 않으면 빈 문자열.

    근거를 "살아 있는가" 하나로 줄이지 않고 현재 세션과의 합집합으로 둔다. 레지스트리를
    읽지 못하면 `live_ids`가 비는데, 그때 현재 세션 가드까지 사라지면 보호가 후퇴한다.
    합집합이면 최악이 레지스트리가 없던 시절과 같다.

    두 사유가 겹치면 현재 세션이 이긴다 — 현재 세션은 거의 항상 살아 있고, 사용자에게
    더 구체적인 사실이 "그건 지금 이 창이다"이다.

    판정이 삭제 전용이 아니므로 문구의 동사만 인자로 받는다. 이름 수정
    (`session/rename.py`)이 같은 근거를 쓰며, 판정을 그쪽에 복사해 두면 한쪽만 고쳐지는
    날이 온다. 함수가 이 파일에 남는 것은 여기서 태어났기 때문이다.

    Args:
        session_id (str): 판정할 세션 UUID
        current_id (str): `/history`를 실행한 세션 UUID
        live_ids (set[str]): 지금 살아 있는 세션 UUID의 집합
        verb (str): 사유 문구에 들어갈 동사

    Returns:
        str: 거부 사유. 손대도 되면 빈 문자열
    """
    if session_id == current_id:
        return f"현재 세션은 {verb}할 수 없습니다"
    if session_id in live_ids:
        return f"실행 중인 세션은 {verb}할 수 없습니다"
    return ""


def delete_sessions(session_ids: list[str], slug: str, current_id: str,
                    live_ids: set[str]) -> list[dict]:
    """세션 jsonl을 지우고 대상마다 결과를 돌려준다.

    일부가 실패해도 나머지는 처리한다. 파일 삭제는 되돌릴 수 없으므로 요청을 통째로
    취소하는 방식이 성립하지 않는다 — 부분 성공을 사실대로 보고한다.

    Args:
        session_ids (list[str]): 삭제할 세션 UUID 목록
        slug (str): 프로젝트 슬러그
        current_id (str): 현재 세션 UUID. 이 값은 거부된다
        live_ids (set[str]): 지금 살아 있는 세션 UUID의 집합. 이 값들도 거부된다

    Returns:
        list[dict]: `{"target", "ok", "reason"}` 목록. 순서는 입력과 같다
    """
    results = []
    for session_id in session_ids:
        # 화면에 체크박스가 없는 것은 실수를 막고, 이 가드는 우회를 막는다.
        # 살아 있는 세션의 jsonl은 Claude Code가 계속 쓰고 있는 파일이다
        reason = blocked_reason(session_id, current_id, live_ids)
        if reason:
            results.append(_result(session_id, False, reason))
            continue

        jsonl = paths.PROJECTS_DIR / slug / f"{session_id}.jsonl"
        if not jsonl.exists():
            # 조용히 성공으로 처리하지 않는다. 화면의 식별자가 디스크와 맞지 않는 것은
            # 산출물이 낡았다는 뜻이고, 사용자가 알아야 하는 사실이다
            results.append(_result(session_id, False, "해당 세션 파일이 없습니다"))
            continue

        try:
            jsonl.unlink()
        except OSError as exc:
            results.append(_result(session_id, False, f"삭제 실패: {exc.strerror or exc}"))
            continue
        results.append(_result(session_id, True, ""))
    return results


def _result(target: str, ok: bool, reason: str) -> dict:
    """항목별 결과 하나를 만든다."""
    return {"target": target, "ok": ok, "reason": reason}
