"""수명 규칙의 검증. 브라우저를 띄우지 않는다.

`http.client`로 `/api/live`에 연결을 열고 소켓을 닫는 것이 곧 "탭을 닫는 것"이다.
유예 시간을 짧게 주입하므로 수 초 안에 끝난다.

산문으로 적힌 수명 규칙은 아무도 읽지 않지만, 같은 이름의 테스트는 누가 유예를 지우면
그 자리에서 깨진다.
"""
import http.client
import json
import os
import socket
import threading
import time

import pytest

import common.paths as paths
from server.app import HOST, Server
from store.layout import server_file  # noqa: F401
from tests.test_app import TOKEN, get

# 실제 값(5초·30초·15초·2초)의 1/25~1/100 규모. 같은 동작을 검증하면서 수 초 안에 끝난다
SHUTDOWN = 0.2
STARTUP = 0.6
PING = 0.05
POLL = 0.02
# 유예가 만료되기를 기다리는 여유
SETTLE = 0.35

# 스트림이 미는 두 목록의 원본을 임시 디렉토리에 세울 때 쓰는 값
SLUG = "lifecycle-slug"
SESSION = "aaaaaaaa-0000-0000-0000-000000000000"


def add_recorded(tmp_path, session_id: str) -> None:
    """슬러그에 jsonl을 하나 만든다 — 기록이 남은 세션 하나다.

    내용은 보지 않는다. 이 스트림이 미는 것은 파일명뿐이다.
    """
    (tmp_path / "projects" / SLUG / f"{session_id}.jsonl").write_text(
        "", encoding="utf-8")


@pytest.fixture
def server(tmp_path, monkeypatch):
    """짧은 유예를 주입한 서버. 테스트가 끝나면 정리한다.

    스트림이 미는 두 목록의 원본을 **둘 다** `tmp_path` 아래로 갈아 끼운다. 실물을 보게
    두면 살아 있는 목록은 지금 돌고 있는 Claude Code 인스턴스 수에 따라, 기록된 목록은
    이 컴퓨터에 쌓인 세션 수에 따라 결과가 달라진다.
    """
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    monkeypatch.setattr(paths, "LIVE_SESSIONS_DIR", live_dir)
    (tmp_path / "projects" / SLUG).mkdir(parents=True)
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path / "projects")
    add_recorded(tmp_path, SESSION)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((HOST, 0))
    sock.listen(5)
    instance = Server(sock, tmp_path, TOKEN,
                      shutdown_grace=SHUTDOWN, startup_grace=STARTUP,
                      ping_interval=PING, poll_interval=POLL)
    server_file(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    # 기록된 목록은 현재 세션에서 슬러그를 찾으므로 그 값이 있어야 한다
    server_file(tmp_path).write_text(
        json.dumps({"session_id": SESSION}), encoding="utf-8")
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()


def open_live(port: int):
    """`/api/live`에 SSE 연결을 열고 첫 코멘트까지 받는다 — 탭 하나를 여는 것이다.

    돌려주는 것은 **응답 객체**다. `BaseHTTPRequestHandler`가 HTTP/1.0으로 답하므로
    `http.client`는 `getresponse()` 직후 자기 소켓 참조를 버리고, 소켓의 실제 수명은
    응답 객체가 갖는다. 따라서 "탭을 닫는 것"은 `response.close()`다.
    """
    connection = http.client.HTTPConnection(HOST, port, timeout=3)
    connection.request("GET", f"/api/live?t={TOKEN}")
    response = connection.getresponse()
    assert response.status == 200
    assert response.headers["Content-Type"] == "text/event-stream"
    assert response.readline() == b": ping\n"  # 첫 코멘트가 도착할 때까지 막힌다
    return response


def wait_connections(instance, expected: int, timeout: float = 2.0) -> None:
    """카운트가 기대값에 닿기를 기다린다."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if instance.lifecycle.connections == expected:
            return
        time.sleep(0.01)
    assert instance.lifecycle.connections == expected


def is_serving(instance) -> bool:
    """서버가 아직 응답하는가.

    **health를 쓰지 않는다.** health는 예약된 종료를 취소하므로, 그것으로 생존을 확인하면
    확인 행위가 결과를 바꾼다. 토큰 없는 요청의 403도 "서버가 응답한다"를 증명하고
    수명에 손대지 않는다.
    """
    try:
        return get(instance.server_address[1], "/api/probe")[0] == 403
    except OSError:
        return False


# ── SSE 연결 ───────────────────────────────────────────────────────────────

def read_event(response, name: str = "live", limit: int = 40):
    """다음 `event: {name}` 블록의 `data`를 파싱해 돌려준다.

    코멘트와 **다른 이름의 이벤트**는 건너뛴다. 한 연결에 두 종류가 흐르므로,
    찾는 것만 골라야 이벤트가 늘어도 호출부가 흔들리지 않는다.
    """
    wanted = f"event: {name}\n".encode("utf-8")
    for _ in range(limit):
        line = response.readline()
        if not line:
            raise AssertionError("스트림이 끊겼다")
        if line == wanted:
            data = response.readline()
            assert data.startswith(b"data: ")
            return json.loads(data[len(b"data: "):].decode("utf-8"))
    raise AssertionError(f"{limit}줄 안에 {name} 이벤트가 오지 않았다")


def add_live(tmp_path, name: str, session_id: str) -> None:
    """레지스트리에 살아 있는 항목 하나를 넣는다. cwd는 서버의 프로젝트 루트다."""
    (tmp_path / "live" / name).write_text(
        json.dumps({"pid": os.getpid(), "sessionId": session_id,
                    "cwd": str(tmp_path)}), encoding="utf-8")


def set_window(tmp_path, pid: int) -> None:
    """`.server`에 창의 pid를 적는다 — 현재 세션을 레지스트리에 되묻는 근거다."""
    server_file(tmp_path).write_text(
        json.dumps({"session_id": SESSION, "session_pid": pid}), encoding="utf-8")


def test_live_streams_comments(server):
    """열린 채 유지되고 일정 간격으로 코멘트 줄이 도착한다."""
    response = open_live(server.server_address[1])
    try:
        # 첫 줄은 open_live가 이미 읽었다. 코멘트가 이어서 또 온다
        assert response.readline() == b"\n"
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if response.readline() == b": ping\n":
                return
        raise AssertionError("코멘트가 이어지지 않았다")
    finally:
        response.close()


def test_live_connection_counted(server):
    response = open_live(server.server_address[1])
    try:
        wait_connections(server, 1)
    finally:
        response.close()
    wait_connections(server, 0)


# ── 살아 있는 세션 목록을 민다 ─────────────────────────────────────────────
# 산출물에 담지 않는다 — 뷰어가 열려 있는 동안 변하는 값이고, file:// 사본은 생존을
# 보증할 수 없다. 조회 엔드포인트도 두지 않는다. 남는 통로가 이미 열려 있는 이 연결이다

def test_live_sends_session_list_on_connect(server):
    """접속 직후 반드시 한 번 온다. 살아 있는 세션이 없으면 빈 배열이다."""
    response = open_live(server.server_address[1])
    try:
        assert read_event(response) == []
    finally:
        response.close()


def test_live_sends_new_event_when_registry_changes(server, tmp_path):
    """접속을 유지한 채 세션이 늘면 새 이벤트가 온다."""
    response = open_live(server.server_address[1])
    try:
        assert read_event(response) == []
        add_live(tmp_path, "1.json", "aaa")
        assert read_event(response, limit=200) == ["aaa"]
    finally:
        response.close()


def test_live_sends_event_when_window_joins_same_session(server, tmp_path):
    """**같은 세션에 창이 하나 더 붙어도 변화다.**

    목록을 집합으로 접으면 이 이벤트가 나가지 않고, 화면은 그 세션을 두 곳에서 쓰고
    있다는 것을 영원히 모른다.
    """
    add_live(tmp_path, "1.json", "aaa")
    response = open_live(server.server_address[1])
    try:
        assert read_event(response) == ["aaa"]
        add_live(tmp_path, "2.json", "aaa")
        assert read_event(response, limit=200) == ["aaa", "aaa"]
    finally:
        response.close()


def test_live_sends_event_when_session_disappears(server, tmp_path):
    """줄어드는 것도 변화다 — 그래야 화면이 체크박스를 되돌려 준다."""
    add_live(tmp_path, "1.json", "aaa")
    response = open_live(server.server_address[1])
    try:
        assert read_event(response) == ["aaa"]
        (tmp_path / "live" / "1.json").unlink()
        assert read_event(response, limit=200) == []
    finally:
        response.close()


def test_stream_stays_silent_while_nothing_changes(server):
    """셋이 모두 그대로면 보내지 않는다. 매 틱 보내면 화면이 계속 다시 그려진다."""
    response = open_live(server.server_address[1])
    try:
        assert read_event(response) == []
        assert read_event(response, "current") == SESSION
        assert read_event(response, "known") == [SESSION]
        # 폴링 틱이 여러 번 지나는 동안 코멘트만 와야 한다
        for _ in range(12):
            assert response.readline() in (b": ping\n", b"\n")
    finally:
        response.close()


def test_live_excludes_other_projects(server, tmp_path):
    """이 서버가 서빙하는 프로젝트에서 시작된 세션만 담긴다."""
    (tmp_path / "live" / "1.json").write_text(
        json.dumps({"pid": os.getpid(), "sessionId": "elsewhere",
                    "cwd": str(tmp_path / "다른프로젝트")}), encoding="utf-8")
    response = open_live(server.server_address[1])
    try:
        assert read_event(response) == []
    finally:
        response.close()


# ── 기록된 세션 목록을 민다 ────────────────────────────────────────────────
# 살아 있는 목록과 같은 연결·같은 규칙으로 흐르지만 답하는 물음이 다르다. 그쪽은
# "무엇이 돌고 있는가"이고 이쪽은 "다시 만들면 목록에 무엇이 설 수 있는가"다

def test_known_sends_recorded_sessions_on_connect(server):
    """접속 직후 반드시 한 번 온다. 화면은 이 값을 자기 embed 목록과 견준다."""
    response = open_live(server.server_address[1])
    try:
        assert read_event(response, "known") == [SESSION]
    finally:
        response.close()


def test_known_sends_new_event_when_session_recorded(server, tmp_path):
    """뷰어가 열려 있는 동안 세션이 기록되면 새 이벤트가 온다 — 이 스트림의 존재 이유다."""
    response = open_live(server.server_address[1])
    try:
        assert read_event(response, "known") == [SESSION]
        later = "bbbbbbbb-0000-0000-0000-000000000000"
        add_recorded(tmp_path, later)
        assert read_event(response, "known", limit=200) == sorted([SESSION, later])
    finally:
        response.close()


def test_known_excludes_live_session_without_record(server, tmp_path):
    """**살아 있어도 jsonl이 없으면 담기지 않는다.**

    담으면 화면이 "새 세션이 있다"고 알리는데 다시 만들어도 그 행이 서지 않는다 —
    사용자가 새로고침해도 안내가 사라지지 않는 상태가 된다.
    """
    add_live(tmp_path, "1.json", "cccccccc-0000-0000-0000-000000000000")
    response = open_live(server.server_address[1])
    try:
        assert read_event(response) == ["cccccccc-0000-0000-0000-000000000000"]
        assert read_event(response, "known") == [SESSION]
    finally:
        response.close()


# ── 현재 세션을 민다 ───────────────────────────────────────────────────────
# 창은 `/resume`으로 세션을 갈아탄다. 산출물에 굳은 값은 그 순간부터 그 창의 것이 아니고,
# 화면이 그 사실을 알 통로도 이미 열려 있는 이 연결뿐이다

MOVED = "dddddddd-0000-0000-0000-000000000000"


def test_current_sends_window_session_on_connect(server, tmp_path):
    """접속 직후 반드시 한 번 온다. 담기는 것은 창이 **지금** 보고 있는 세션이다."""
    add_live(tmp_path, "1.json", SESSION)
    set_window(tmp_path, os.getpid())
    response = open_live(server.server_address[1])
    try:
        assert read_event(response, "current") == SESSION
    finally:
        response.close()


def test_current_follows_window_across_resume(server, tmp_path):
    """창이 세션을 갈아타면 새 이벤트가 온다 — 이 스트림의 존재 이유다."""
    add_live(tmp_path, "1.json", SESSION)
    set_window(tmp_path, os.getpid())
    response = open_live(server.server_address[1])
    try:
        assert read_event(response, "current") == SESSION
        # `/resume` — 같은 pid 항목의 `sessionId`만 갈린다
        add_live(tmp_path, "1.json", MOVED)
        assert read_event(response, "current", limit=200) == MOVED
    finally:
        response.close()


# ── 수명 ───────────────────────────────────────────────────────────────────

def test_survives_while_connection_open(server):
    """연결을 열어두면 유예의 여러 배를 기다려도 살아 있다."""
    response = open_live(server.server_address[1])
    try:
        time.sleep(SHUTDOWN * 4)
        assert is_serving(server)
    finally:
        response.close()


def test_dies_after_last_connection_closes(server):
    """마지막 탭을 닫으면 종료 유예 뒤 서버가 사라지고 `.server`도 사라진다."""
    response = open_live(server.server_address[1])
    response.close()
    wait_connections(server, 0)
    time.sleep(SHUTDOWN + SETTLE)
    assert not is_serving(server)


def test_reconnect_within_grace_survives(server):
    """새로고침 — 닫고 유예 안에 다시 연결하면 산다."""
    port = server.server_address[1]
    first = open_live(port)
    first.close()
    wait_connections(server, 0)
    time.sleep(SHUTDOWN / 4)
    second = open_live(port)
    try:
        time.sleep(SHUTDOWN + SETTLE)
        assert is_serving(server)
    finally:
        second.close()


def test_one_of_two_tabs_closing_survives(server):
    """연결 두 개 중 하나만 끊으면 계속 응답한다."""
    port = server.server_address[1]
    first, second = open_live(port), open_live(port)
    try:
        wait_connections(server, 2)
        first.close()
        wait_connections(server, 1)
        time.sleep(SHUTDOWN + SETTLE)
        assert is_serving(server)
    finally:
        second.close()


def test_dies_when_no_connection_ever_opens(server):
    """브라우저가 아예 열리지 않으면 기동 유예 뒤 스스로 종료한다."""
    server.lifecycle.start()
    time.sleep(STARTUP + SETTLE)
    assert not is_serving(server)


def test_count_converges_with_many_connections(server):
    """여러 연결을 동시에 열고 닫아도 카운트가 0으로 수렴한다."""
    port = server.server_address[1]
    responses = [open_live(port) for _ in range(5)]
    wait_connections(server, 5)
    for response in responses:
        response.close()
    wait_connections(server, 0)
    assert server.lifecycle.connections == 0


# ── health가 예약을 취소한다 ───────────────────────────────────────────────

def test_health_cancels_pending_shutdown(server):
    """재사용 경로 — 종료 유예 중에 health를 받으면 서버가 죽지 않는다.

    이것이 없으면 유예 중에 재사용된 서버가 브라우저 콜드 스타트 도중에 죽고,
    사용자는 방금 실행한 명령이 실패한 것을 본다.
    """
    port = server.server_address[1]
    response = open_live(port)
    response.close()
    wait_connections(server, 0)
    # 유예가 만료되기 전에 부모가 재사용을 결정한다
    time.sleep(SHUTDOWN / 2)
    assert get(port, f"/api/health?t={TOKEN}")[0] == 200
    # 원래 예약대로라면 이미 죽었을 시점
    time.sleep(SHUTDOWN + SETTLE)
    assert is_serving(server)


def test_health_restarts_startup_grace(server):
    """health가 다시 시작한 기동 유예도 만료되면 종료한다 — 무한히 살지 않는다."""
    port = server.server_address[1]
    server.lifecycle.start()
    time.sleep(STARTUP * 0.7)
    assert get(port, f"/api/health?t={TOKEN}")[0] == 200
    # 원래 예약대로라면 이미 만료됐을 시점인데, 유예가 다시 시작됐으므로 살아 있다
    time.sleep(STARTUP * 0.5)
    assert is_serving(server)
    # 그 뒤에는 만료되어 종료한다 — health가 서버를 무한히 살리지는 않는다
    time.sleep(STARTUP + SETTLE)
    assert not is_serving(server)


# ── 종료를 요청 스레드에서 부르지 않는다 ───────────────────────────────────

def test_terminate_does_not_deadlock(server):
    """핸들러 스레드에서 shutdown을 직접 부르면 자기가 끝나기를 기다리며 멈춘다."""
    server.lifecycle.terminate()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and is_serving(server):
        time.sleep(0.02)
    assert not is_serving(server)
