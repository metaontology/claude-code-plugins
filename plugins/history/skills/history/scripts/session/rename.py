"""세션 이름 수정 — jsonl에 `custom-title` 레코드 한 줄을 덧붙인다.

Claude Code의 `/rename`이 남기는 것과 같은 형식이라, 여기서 바꾼 이름이 `/resume`
목록에도 같은 값으로 보인다. 한 파일에 여러 개가 있으면 **마지막 것이 현재 이름**이고,
읽는 쪽은 `common/jsonl.py`의 `get_session_meta`가 이미 갖고 있다.

**파일을 다시 쓰지 않는다.** 앞선 레코드를 지워서 얻는 것이 없고(마지막 값이 이긴다),
재작성은 Claude Code가 같은 순간에 append하고 있을 수 있는 파일을 통째로 갈아엎는
연산이다. 그 창에서 잃는 것은 세션 하나의 대화 전체다.
"""
import json
import os
import re
from pathlib import Path

import common.paths as paths
from session.delete import blocked_reason

# 이름 길이 상한
TITLE_LIMIT = 200
# jsonl에 쓰는 레코드 종류. Claude Code의 `/rename`이 쓰는 값과 같다
RECORD_TYPE = "custom-title"

_SPACES_RE = re.compile(r"\s+")


def normalize_title(raw) -> str:
    """이름을 한 줄짜리 값으로 정규화한다.

    이어진 공백을 하나로 줄이는 것은 줄바꿈·탭 때문이다. jsonl은 한 줄이 한 레코드이고,
    이 값은 목록에 한 줄로 서므로 줄바꿈이 든 이름은 어느 화면에서도 온전히 보이지 않는다.

    Args:
        raw: 화면이 보낸 값. 문자열이 아닐 수 있다

    Returns:
        str: 앞뒤 공백이 없고 줄바꿈이 없는 이름

    Raises:
        ValueError: 문자열이 아니거나, 비었거나, `TITLE_LIMIT`을 넘는다
    """
    if not isinstance(raw, str):
        raise ValueError("title이 문자열이 아닙니다")
    title = _SPACES_RE.sub(" ", raw).strip()
    if not title:
        raise ValueError("이름을 입력해야 합니다")
    if len(title) > TITLE_LIMIT:
        raise ValueError(f"이름은 {TITLE_LIMIT}자를 넘을 수 없습니다")
    return title


def rename_session(session_id: str, slug: str, current_id: str,
                   live_ids: set[str], title: str) -> dict:
    """세션 이름을 바꾸고 결과를 돌려준다.

    거부 판정은 삭제와 같은 근거를 쓴다 — `session/delete.py`의 `blocked_reason`을
    `verb="수정"`으로 부른다. 근거가 두 파일에 따로 있으면 한쪽만 고쳐지는 날이 온다.

    **실행 중인 세션을 막는 이유는 삭제와 다르다.** 파일이 깨져서가 아니라, 그 창의
    Claude Code가 자기 메모리에 든 옛 이름을 다음 저장에서 다시 덧붙이기 때문이다.
    우리 줄이 뒤로 밀리면 이름이 조용히 되돌아가고, 그것은 실패보다 나쁘다 — 실패는
    화면에 사유가 남지만 이것은 아무 흔적도 남기지 않는다.

    Args:
        session_id (str): 이름을 바꿀 세션 UUID
        slug (str): 프로젝트 슬러그
        current_id (str): `/history`를 실행한 세션 UUID. 이 값은 거부된다
        live_ids (set[str]): 지금 살아 있는 세션 UUID의 집합. 이 값들도 거부된다
        title (str): `normalize_title`을 통과한 이름

    Returns:
        dict: `{"ok", "reason", "title"}`. 실패하면 `title`은 빈 문자열
    """
    reason = blocked_reason(session_id, current_id, live_ids, verb="수정")
    if reason:
        return _result(False, reason)

    jsonl = paths.PROJECTS_DIR / slug / f"{session_id}.jsonl"
    if not jsonl.exists():
        # 조용히 성공으로 처리하지 않는다. 화면의 식별자가 디스크와 맞지 않는 것은
        # 산출물이 낡았다는 뜻이고, 사용자가 알아야 하는 사실이다
        return _result(False, "해당 세션 파일이 없습니다")

    try:
        _append_record(jsonl, session_id, title)
    except OSError as exc:
        return _result(False, f"수정 실패: {exc.strerror or exc}")
    return _result(True, "", title)


def _append_record(jsonl: Path, session_id: str, title: str) -> None:
    """`custom-title` 레코드 한 줄을 파일 끝에 덧붙인다.

    키 순서를 Claude Code가 쓰는 것과 같게 둔다. JSON 객체에 순서는 의미가 없지만,
    사람이 파일 끝을 눈으로 볼 때 같은 모양이라야 두 줄을 나란히 읽는다.

    `newline="\\n"`을 준다. 비워 두면 Windows에서 `\\r\\n`이 되어 한 파일 안에 줄 끝이
    두 종류가 된다.
    """
    record = json.dumps(
        {"type": RECORD_TYPE, "customTitle": title, "sessionId": session_id},
        ensure_ascii=False,
    )
    # 앞줄이 개행으로 끝나지 않으면 개행을 먼저 쓴다. 확인 없이 붙이면 그 세션의
    # 마지막 줄과 이 줄이 한 줄로 이어져 **둘 다 파싱되지 않는다**
    prefix = "" if _ends_with_newline(jsonl) else "\n"
    with open(jsonl, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"{prefix}{record}\n")


def _ends_with_newline(jsonl: Path) -> bool:
    """파일이 개행으로 끝나는가.

    빈 파일도 참으로 본다 — 이어붙을 앞줄이 없으므로 개행을 넣으면 첫 줄이 빈 줄이 된다.
    """
    with open(jsonl, "rb") as handle:
        try:
            handle.seek(-1, os.SEEK_END)
        except OSError:
            return True
        return handle.read(1) == b"\n"


def _result(ok: bool, reason: str, title: str = "") -> dict:
    """결과 하나를 만든다."""
    return {"ok": ok, "reason": reason, "title": title}
