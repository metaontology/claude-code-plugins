"""디스크에 쓰는 엔드포인트 — 파괴적 연산 둘, 세션 이름 수정, 사용자 설정 저장.

조회는 API를 통하지 않는다. 데이터가 생성 시점에 embed되므로 화면이 서버에 물어볼 것이 없고,
조회 엔드포인트를 두면 같은 데이터를 만드는 경로가 둘이 되어 추출 범위가 어긋난다.
설정도 같다 — 읽기는 산출물에 심겨 오고 여기서는 쓰기만 받는다.
"""
import json

from auto_memory.discard import discard_items
from auto_memory.model import memory_dir
from common.jsonl import find_project_slug
from server.live import project_session_ids
from session.delete import delete_sessions
from session.rename import normalize_title, rename_session
from store.config import reset_config, save_config, with_defaults
from store.layout import index_path


def parse_targets(body: bytes) -> list[str]:
    """요청 본문에서 대상 목록을 꺼낸다.

    Raises:
        ValueError: JSON이 아니거나 `targets`가 문자열 목록이 아니다
    """
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("요청 본문이 JSON이 아닙니다") from exc
    if not isinstance(payload, dict):
        raise ValueError("요청 본문이 객체가 아닙니다")
    targets = payload.get("targets")
    if not isinstance(targets, list) or not all(isinstance(t, str) for t in targets):
        raise ValueError("targets가 문자열 목록이 아닙니다")
    return targets


def handle_sessions_delete(server, body: bytes) -> tuple[int, dict]:
    """세션 jsonl을 삭제한다."""
    try:
        targets = parse_targets(body)
    except ValueError as exc:
        return 400, {"error": str(exc)}

    current_id = server.current_session_id()
    slug = find_project_slug(current_id) if current_id else None
    if slug is None:
        # 슬러그를 모르면 어떤 경로도 지목할 수 없다. 추측해 지우지 않는다
        return 409, {"error": "현재 프로젝트의 세션 디렉토리를 찾을 수 없습니다"}

    # 살아 있는 목록을 요청 시점에 다시 읽는다. 화면이 보내온 값을 쓰면 가드의 근거를
    # 요청자가 제공하게 되어 우회 방어가 사라진다 — 현재 세션을 요청마다 다시 읽는
    # 것과 같은 이유다.
    # `set`으로 접는 자리가 여기다. 목록은 창 하나에 원소 하나여서 중복이 있는데,
    # 가드가 묻는 것은 "살아 있는가" 하나여서 개수가 답을 바꾸지 않는다
    live_ids = set(project_session_ids(server.project_root))
    results = delete_sessions(targets, slug, current_id, live_ids)
    _rebuild_if_any(server, results)
    return 200, {"results": results}


def parse_rename(body: bytes) -> tuple[str, str]:
    """요청 본문에서 `(대상, 정규화된 이름)`을 꺼낸다.

    `parse_targets`를 쓰지 않는다 — 그쪽은 **문자열 목록**을 꺼내는데 이 요청은 대상 하나와
    이름 하나를 함께 싣는다. 목록으로 받아 길이 1을 강제하는 쪽은 쓰지 않는다. 화면이 보낼
    수 없는 형태를 API가 받아들이는 모양이 되고, 「대상은 하나」라는 계약이 파서가 아니라
    검사 코드에 숨는다.

    Raises:
        ValueError: JSON이 아니거나, `target`이 문자열이 아니거나, 이름이 규칙에 어긋난다
    """
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("요청 본문이 JSON이 아닙니다") from exc
    if not isinstance(payload, dict):
        raise ValueError("요청 본문이 객체가 아닙니다")
    target = payload.get("target")
    if not isinstance(target, str) or not target:
        raise ValueError("target이 문자열이 아닙니다")
    return target, normalize_title(payload.get("title"))


def handle_session_rename(server, body: bytes) -> tuple[int, dict]:
    """세션 이름을 바꾼다. **대상은 하나다.**

    응답을 `{"results": […]}`로 만들지 않는다. 그 형태는 부분 성공이 있는 다중 대상 연산의
    것이고, 대상이 하나면 성공과 실패가 갈릴 자리가 없다. 화면도 배열의 첫 항목을 꺼내는
    코드를 갖게 된다.

    상태코드는 사유의 성질로 가른다 — **400은 요청을 고치면 통과하는 것**이고 **409는
    요청은 옳은데 지금 상태가 거부하는 것**이다.

    성공하면 산출물을 판정 없이 다시 만든다. jsonl의 mtime이 올라가므로 `GET /`의 판정도
    잡기는 하지만, 여기서 만들어 두면 화면이 새 이름을 보려고 한 번 더 왕복하지 않는다.
    """
    try:
        target, title = parse_rename(body)
    except ValueError as exc:
        return 400, {"error": str(exc)}

    current_id = server.current_session_id()
    slug = find_project_slug(current_id) if current_id else None
    if slug is None:
        return 409, {"error": "현재 프로젝트의 세션 디렉토리를 찾을 수 없습니다"}

    # 살아 있는 목록을 요청 시점에 다시 읽는다. 화면이 보내온 값을 쓰면 가드의 근거를
    # 요청자가 제공하게 되어 우회 방어가 사라진다 — 삭제와 같은 이유다
    live_ids = set(project_session_ids(server.project_root))
    result = rename_session(target, slug, current_id, live_ids, title)
    if not result["ok"]:
        return 409, {"error": result["reason"]}
    _rebuild(server)
    return 200, {"ok": True, "title": result["title"]}


def handle_auto_memory_discard(server, body: bytes) -> tuple[int, dict]:
    """auto-memory 항목 파일과 인덱스 줄을 함께 제거한다."""
    try:
        targets = parse_targets(body)
    except ValueError as exc:
        return 400, {"error": str(exc)}

    current_id = server.current_session_id()
    slug = find_project_slug(current_id) if current_id else None
    if slug is None:
        return 409, {"error": "현재 프로젝트의 메모리 디렉토리를 찾을 수 없습니다"}

    results = discard_items(memory_dir(slug), targets)
    _rebuild_if_any(server, results)
    return 200, {"results": results}


def handle_config_save(server, body: bytes) -> tuple[int, dict]:
    """사용자 설정을 병합 저장하고 병합 결과를 돌려준다.

    산출물을 다시 만들지 않는다. 파괴적 연산이 재생성을 부르는 것은 원본이 사라져 화면이
    낡기 때문인데, 설정은 화면이 이미 반영한 값을 뒤따라 저장하는 것이라 다시 만들 이유가
    없다. 다음 `/history` 실행이 새 값을 심는다.

    `server`를 쓰지 않지만 라우트가 넘기는 인자이므로 자리를 지킨다.

    **저장하지 못한 것을 상태코드로 알리지 않는다.** 설정 파일은 프로젝트마다 갈리지 않으므로
    다른 프로젝트의 서버가 그 순간 교체 중일 수 있고, 그러면 병합 근거가 없어 쓰지 않는다
    ([사용자 설정](../../../docs/dev-plans/20-viewer/050-user-config.md)). 화면은 그때 잠시 뒤
    같은 값을 다시 보내므로 **재시도가 이 경로의 정상 동작**인데, 4xx로 답하면 브라우저가
    그것을 콘솔에 ERROR로 남긴다(실측) — 정상 동작이 매번 빨간 줄을 만든다.

    그래서 `ok`를 본문에 담아 200으로 답한다. 세션 이름 수정이 성공을 `{"ok": True}`로 싣는
    것과 같은 형태다. 그쪽이 실패에 409를 쓰는 것은 **사유가 사용자에게 보이는 값**이기
    때문이고, 이 응답은 아무에게도 보이지 않고 화면이 자동으로 처리한다.

    실패에 `config`를 담지 않는다. 쓰지 않았으므로 디스크가 지금 무엇인지 이 함수는 모른다.
    """
    try:
        payload = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 400, {"error": "요청 본문이 JSON이 아닙니다"}
    if not isinstance(payload, dict):
        return 400, {"error": "요청 본문이 객체가 아닙니다"}
    merged = save_config(payload)
    if merged is None:
        return 200, {"ok": False}
    return 200, {"ok": True, "config": merged}


def handle_config_reset(server, body: bytes) -> tuple[int, dict]:
    """사용자 설정을 지우고 그 뒤의 기본값을 돌려준다.

    본문을 읽지 않는다 — 지우는 대상이 파일 하나뿐이라 요청이 지목할 것이 없다.
    그래도 `body`를 받는 것은 라우트가 넘기는 인자이기 때문이다.

    **산출물을 판정 없이 다시 만든다.** `handle_config_save`와 갈리는 자리다 — 저장은 파일의
    mtime을 올리므로 다음 `GET /`의 갱신 판정이 알아서 잡지만, **초기화는 파일이 사라지는
    연산이라 어떤 mtime도 올리지 않는다.** 판정에 맡기면 지워진 설정이 심긴 화면이 그대로
    다시 열린다 — 파괴적 연산이 `_rebuild_if_any`를 부르는 것과 같은 이유다.
    """
    reset_config()
    _rebuild(server)
    return 200, {"config": with_defaults({})}


def _rebuild_if_any(server, results: list[dict]) -> None:
    """하나라도 처리됐으면 산출물을 다시 만든다.

    전부 실패했으면 부르지 않는다 — 화면이 낡을 이유가 없다.
    """
    if not any(result["ok"] for result in results):
        return
    _rebuild(server)


def _rebuild(server) -> None:
    """산출물을 다시 만든다. **갱신 판정을 거치지 않는다.**

    원본이 사라지는 것은 어떤 파일의 mtime도 올리지 않으므로, 판정에 맡기면 지워진 세션이
    남아 있는 화면이 다시 열린다. 설정 초기화도 같은 성질이다.

    재생성이 실패하면 산출물을 지운다. 남겨두면 판정이 "갱신 불필요"라 답하지만, 지우면
    같은 판정이 "산출물이 없다 → 전량 생성"으로 답하므로 저절로 복구된다.
    """
    rebuild = getattr(server, "rebuild", None)
    if rebuild is None:
        return
    try:
        rebuild()
    except Exception:
        index_path(server.project_root).unlink(missing_ok=True)
