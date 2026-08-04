import json
import os
import signal
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

import server.app as app
from server.app import (
    HOST,
    Server,
    bind_port,
    ensure_server,
    live_server,
    probe_health,
    read_server_info,
    viewer_url,
    window_pid,
    windowless_python,
    write_server_info,
)
from store.layout import index_path, server_file

TOKEN = "test-token-0123456789"
SESSION = "app00000-0000-0000-0000-000000000000"


def _listen(port: int = 0) -> socket.socket:
    """127.0.0.1의 지정 포트에 바인딩된 소켓. 0이면 OS가 고른다.

    `SO_REUSEADDR`를 켜지 않는다 — Windows에서 그 옵션은 이미 바인딩된 주소에도
    바인딩을 허용하므로 점유 테스트가 성립하지 않는다.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((HOST, port))
    sock.listen(5)
    return sock


@pytest.fixture
def running(tmp_path):
    """임의 포트에 뜬 서버. `(포트, 프로젝트 루트)`를 준다."""
    server = Server(_listen(), tmp_path, TOKEN)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], tmp_path
    server.shutdown()
    server.server_close()


def get(port: int, path: str):
    """요청을 보내고 `(상태코드, 헤더, 본문)`을 돌려준다."""
    import urllib.error
    import urllib.request

    url = f"http://{HOST}:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def _spawned(project_root, session_id: str = ""):
    """자식으로 띄운 서버를 확보한다. 호출자가 pid로 정리한다."""
    return ensure_server(project_root, session_id)


@pytest.fixture
def served(tmp_path, monkeypatch):
    """산출물을 실제로 만들 수 있는 서버. `(포트, 프로젝트 루트)`.

    `PROJECTS_DIR`를 임시 디렉토리로 돌린다. 실물을 보게 두면 이 테스트가 사용자의 세션
    전량을 읽어 결과가 기계마다 달라진다.
    """
    import common.paths as paths

    projects = tmp_path / "projects"
    slug_dir = projects / "app-slug"
    slug_dir.mkdir(parents=True)
    (slug_dir / f"{SESSION}.jsonl").write_text('{"type":"user"}\n', encoding="utf-8")
    monkeypatch.setattr(paths, "PROJECTS_DIR", projects)

    root = tmp_path / "project"
    root.mkdir()
    write_server_info(root, {"pid": 1, "port": 0, "token": TOKEN,
                             "root": str(root), "session_id": SESSION})
    server = Server(_listen(), root, TOKEN)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], root
    server.shutdown()
    server.server_close()


# ── `.server` 읽고 쓰기 ────────────────────────────────────────────────────

def test_read_server_info_when_missing(tmp_path):
    assert read_server_info(tmp_path) == {}


def test_read_server_info_when_broken(tmp_path):
    """JSON이 깨져도 예외를 내지 않는다 — 판별이 죽으면 /history 전체가 죽는다."""
    write_server_info(tmp_path, {})
    server_file(tmp_path).write_text("{깨진 JSON", encoding="utf-8")
    assert read_server_info(tmp_path) == {}


def test_write_and_read_server_info(tmp_path):
    info = {"pid": 1, "port": 7391, "token": "t", "root": str(tmp_path)}
    write_server_info(tmp_path, info)
    assert read_server_info(tmp_path) == info


def test_write_server_info_creates_directory(tmp_path):
    """`.history/data/`가 없어도 기록이 성공한다."""
    write_server_info(tmp_path, {"pid": 1})
    assert server_file(tmp_path).exists()


# ── 중복 실행 판별 ─────────────────────────────────────────────────────────

def test_live_server_none_when_no_file(tmp_path):
    assert live_server(tmp_path) is None


def test_live_server_none_when_error_recorded(tmp_path):
    """기동 실패를 기록한 파일은 살아 있는 서버를 가리키지 않는다."""
    write_server_info(tmp_path, {"error": "포트가 전부 점유되어 있습니다"})
    assert live_server(tmp_path) is None


def test_live_server_none_when_nothing_answers(tmp_path):
    """파일이 있다는 사실은 서버가 살아 있다는 증거가 아니다."""
    write_server_info(tmp_path, {"pid": 999999, "port": 7999, "token": "t",
                                 "root": str(tmp_path)})
    assert live_server(tmp_path) is None


def test_live_server_finds_running_server(running):
    port, root = running
    write_server_info(root, {"pid": os.getpid(), "port": port, "token": TOKEN,
                             "root": str(root)})
    found = live_server(root)
    assert found is not None
    assert found["port"] == port


def test_live_server_none_when_root_differs(running, tmp_path_factory):
    """다른 프로젝트의 서버가 그 포트를 물려받은 경우를 루트 비교가 걸러낸다."""
    port, root = running
    other = tmp_path_factory.mktemp("other")
    write_server_info(other, {"pid": os.getpid(), "port": port, "token": TOKEN,
                              "root": str(other)})
    assert live_server(other) is None


# ── 포트 탐색 ──────────────────────────────────────────────────────────────

def test_bind_port_uses_candidate_range(monkeypatch):
    """후보 대역이 열려 있으면 그 안에서 뜬다.

    실제 `PORT_START`를 그대로 쓰지 않는다 — 그 대역이 OS에 예약되어 있으면 폴백이
    발동해 테스트가 환경에 따라 깨진다. 검증할 계약은 "열린 후보를 먼저 쓴다"이므로
    열려 있음이 확인된 포트를 후보로 지정한다.
    """
    probe = _listen()
    free_port = probe.getsockname()[1]
    # 방금까지 이 포트에 붙어 있었으므로 닫으면 다시 쓸 수 있다
    probe.close()
    monkeypatch.setattr(app, "PORT_START", free_port)
    monkeypatch.setattr(app, "PORT_COUNT", 5)
    sock, port = bind_port()
    try:
        assert free_port <= port < free_port + 5
        assert sock.getsockname()[0] == HOST
    finally:
        sock.close()


def test_bind_port_skips_occupied(monkeypatch):
    """점유된 포트를 건너뛰고 다음 포트로 뜬다."""
    taken = _listen()
    taken_port = taken.getsockname()[1]
    monkeypatch.setattr(app, "PORT_START", taken_port)
    monkeypatch.setattr(app, "PORT_COUNT", 2)
    try:
        sock, port = bind_port()
        try:
            assert port == taken_port + 1
        finally:
            sock.close()
    finally:
        taken.close()


def test_bind_port_falls_back_when_candidates_blocked(monkeypatch):
    """후보가 전부 막히면 OS가 주는 포트로 뜬다.

    Windows가 Hyper-V·WSL·Docker를 위해 동적으로 예약한 TCP 대역에 후보가 통째로
    들어가면 모든 bind가 `WSAEACCES`로 거부된다. 그 대역은 실행 중에도 새로 잡히므로
    후보 위치를 옮기는 것으로는 막을 수 없다. 폴백이 없으면 스킬 자체가 뜨지 못한다.
    """
    taken = _listen()
    taken_port = taken.getsockname()[1]
    monkeypatch.setattr(app, "PORT_START", taken_port)
    monkeypatch.setattr(app, "PORT_COUNT", 1)
    try:
        sock, port = bind_port()
        try:
            assert port != taken_port
            assert sock.getsockname()[0] == HOST
        finally:
            sock.close()
    finally:
        taken.close()


def test_bind_port_error_names_os_reason(monkeypatch):
    """후보도 OS 할당도 실패하면 예외가 OS가 준 사유를 담는다.

    "전부 점유되어 있다"고만 말하면 존재하지 않는 점유 프로세스를 찾게 된다. 실물에서
    Windows의 포트 예약은 점유(`WSAEADDRINUSE`)가 아니라 권한 거부(`WSAEACCES`)였고,
    그 문구 때문에 진단이 엉뚱한 곳으로 갔다.

    OS가 `bind`를 전부 거부하는 상태는 실제로 만들 수 없으므로 소켓을 대역한다.
    """

    class _RefusingSocket:
        def __init__(self, *args, **kwargs):
            pass

        def setsockopt(self, *args):
            pass

        def bind(self, address):
            raise OSError(13, "OS가 거부했다")

        def close(self):
            pass

    monkeypatch.setattr(socket, "socket", _RefusingSocket)
    monkeypatch.setattr(app, "PORT_COUNT", 1)
    with pytest.raises(OSError, match="OS가 거부했다"):
        bind_port()


# ── 라우팅 ─────────────────────────────────────────────────────────────────

def test_health_returns_root_and_pid(running):
    port, root = running
    status, _, body = get(port, f"/api/health?t={TOKEN}")
    assert status == 200
    payload = json.loads(body)
    assert payload["ok"] is True
    assert payload["pid"] == os.getpid()
    assert payload["root"] == str(root)


def test_root_is_404_without_index(running):
    """이 단계에서 `/`는 아직 404다 — index.html을 만드는 코드가 없다."""
    port, _ = running
    assert get(port, f"/?t={TOKEN}")[0] == 404


def test_root_serves_index_when_present(running):
    port, root = running
    index_path(root).parent.mkdir(parents=True, exist_ok=True)
    index_path(root).write_text("<h1>기록</h1>", encoding="utf-8")
    status, headers, body = get(port, f"/?t={TOKEN}")
    assert status == 200
    assert "text/html" in headers["Content-Type"]
    assert "기록" in body.decode("utf-8")


def test_root_rebuilds_stale_index(served):
    """원본이 산출물보다 새로우면 서빙 전에 다시 만든다.

    이것이 없으면 진행 중 세션의 새 대화가 새로고침으로도 화면에 오지 않는다 —
    데이터가 생성 시점에 embed되기 때문이다.
    """
    port, root = served
    index_path(root).parent.mkdir(parents=True, exist_ok=True)
    index_path(root).write_text("낡은산출물", encoding="utf-8")
    # 산출물을 원본보다 과거로 만든다. 같은 초에 쓰이면 판정이 갱신 불필요로 답한다
    past = index_path(root).stat().st_mtime - 60
    os.utime(index_path(root), (past, past))

    status, _, body = get(port, f"/?t={TOKEN}")
    text = body.decode("utf-8")
    assert status == 200
    assert "낡은산출물" not in text
    assert SESSION in text


def test_root_keeps_index_when_rebuild_fails(running):
    """재생성이 실패해도 있는 산출물을 그대로 준다.

    `running`은 세션 데이터가 없으므로 슬러그를 찾지 못해 재생성이 RuntimeError를 낸다.
    낡은 화면이 빈 화면보다 낫다 — 404로 바꾸면 실패가 화면 전체를 지운다.
    """
    port, root = running
    index_path(root).parent.mkdir(parents=True, exist_ok=True)
    index_path(root).write_text("있는산출물", encoding="utf-8")
    status, _, body = get(port, f"/?t={TOKEN}")
    assert status == 200
    assert "있는산출물" in body.decode("utf-8")


def test_root_forbids_caching(running):
    """산출물은 요청마다 바뀔 수 있는 파일이라 캐시되면 갱신이 화면에 닿지 않는다."""
    port, root = running
    index_path(root).parent.mkdir(parents=True, exist_ok=True)
    index_path(root).write_text("<h1>기록</h1>", encoding="utf-8")
    assert get(port, f"/?t={TOKEN}")[1]["Cache-Control"] == "no-store"


def test_unknown_get_path_is_404(running):
    port, _ = running
    assert get(port, f"/api/nope?t={TOKEN}")[0] == 404


def test_unknown_post_path_is_404(running):
    import urllib.error
    import urllib.request

    port, _ = running
    request = urllib.request.Request(f"http://{HOST}:{port}/api/nope?t={TOKEN}",
                                    data=b"{}", method="POST")
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=3)
    assert caught.value.code == 404


def test_viewer_url_carries_token():
    assert viewer_url({"port": 7391, "token": "abc"}) == "http://127.0.0.1:7391/?t=abc"


def test_daemon_threads_enabled():
    """열려 있는 스트리밍 연결이 종료를 무기한 막지 않아야 한다."""
    assert Server.daemon_threads is True


# ── 콘솔 창 없이 띄운다 ────────────────────────────────────────────────────
# `sys.executable`이 콘솔 앱이면 분리 실행에서 검은 창이 하나 뜬다. uv로 설치한 경우
# 그것은 실행기(trampoline)라 창이 실행기 경로를 제목으로 달고 남는다

def test_windowless_python_picks_pythonw(tmp_path):
    """콘솔이 배정되지 않는 GUI 서브시스템 바이너리를 고른다."""
    (tmp_path / "pythonw.exe").write_bytes(b"")
    assert windowless_python((tmp_path,)) == str(tmp_path / "pythonw.exe")


def test_windowless_python_prefers_earlier_directory(tmp_path):
    """앞의 디렉토리가 이긴다 — 가상환경이 있으면 그쪽 인터프리터를 써야 한다."""
    first, second = tmp_path / "a", tmp_path / "b"
    for directory in (first, second):
        directory.mkdir()
        (directory / "pythonw.exe").write_bytes(b"")
    assert windowless_python((first, second)) == str(first / "pythonw.exe")


def test_windowless_python_falls_back_to_current_interpreter(tmp_path):
    """찾지 못하면 지금 인터프리터를 그대로 쓴다. 뜨지 못하는 것보다 낫다."""
    assert windowless_python((tmp_path,)) == sys.executable


def test_windowless_python_default_search_finds_something_real():
    """기본 탐색 경로가 실재하는 파일을 가리킨다."""
    assert Path(windowless_python()).exists()


@pytest.mark.skipif(os.name != "nt", reason="창 생성은 Windows의 개념이다")
def test_spawn_asks_windows_for_no_console_window(tmp_path, monkeypatch):
    """`DETACHED_PROCESS`는 콘솔 상속만 막는다. 창을 막는 것은 `CREATE_NO_WINDOW`다."""
    seen = {}

    def fake_popen(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs

    monkeypatch.setattr(app.subprocess, "Popen", fake_popen)
    app._spawn(tmp_path, "sess-A")

    assert seen["command"][0] == windowless_python()
    flags = seen["kwargs"]["creationflags"]
    assert flags & subprocess.CREATE_NO_WINDOW
    # 둘을 함께 주면 Windows가 CREATE_NO_WINDOW를 무시한다
    assert not flags & subprocess.DETACHED_PROCESS


# ── 분리된 자식으로 띄운다 ─────────────────────────────────────────────────

def test_ensure_server_spawns_detached_child(tmp_path):
    """명령이 반환한 뒤에도 서버가 계속 응답한다."""
    info = _spawned(tmp_path)
    try:
        assert info["pid"] != os.getpid()
        health = probe_health(info["port"], info["token"])
        assert health["root"] == str(tmp_path)
    finally:
        os.kill(info["pid"], signal.SIGTERM)


def test_ensure_server_reuses_live_server(tmp_path):
    """같은 프로젝트에서 다시 실행하면 새 서버가 뜨지 않는다."""
    first = _spawned(tmp_path)
    try:
        second = ensure_server(tmp_path)
        assert (second["pid"], second["port"]) == (first["pid"], first["port"])
    finally:
        os.kill(first["pid"], signal.SIGTERM)


def test_ensure_server_reports_startup_failure(tmp_path, monkeypatch):
    """자식이 남긴 사유를 부모가 읽어 보고한다."""
    def fake_spawn(project_root, session_id="", pid=0):
        write_server_info(project_root, {"error": "후보 포트가 전부 점유되어 있습니다"})

    monkeypatch.setattr(app, "_spawn", fake_spawn)
    with pytest.raises(RuntimeError, match="후보 포트"):
        ensure_server(tmp_path)
    # 사유를 읽은 뒤 파일을 남기지 않는다
    assert not server_file(tmp_path).exists()


def test_ensure_server_times_out(tmp_path, monkeypatch):
    monkeypatch.setattr(app, "_spawn", lambda *_: None)
    monkeypatch.setattr(app, "STARTUP_TIMEOUT", 0.2)
    with pytest.raises(RuntimeError, match="응답하지 않았습니다"):
        ensure_server(tmp_path)


def test_spawned_child_records_session_id(tmp_path):
    """자식이 세션 ID를 `.server`에 기록한다 — 현재 세션 가드가 그것을 읽는다."""
    info = _spawned(tmp_path, "sess-A")
    try:
        assert read_server_info(tmp_path)["session_id"] == "sess-A"
    finally:
        os.kill(info["pid"], signal.SIGTERM)


def test_reuse_updates_session_id(tmp_path):
    """재사용할 때 세션 ID를 지금 값으로 갱신한다.

    이 갱신이 없으면 서버는 자기를 띄운 세션을 계속 현재 세션으로 보고, 진행 중인 새
    세션의 삭제 요청을 통과시킨다.
    """
    first = _spawned(tmp_path, "sess-A")
    try:
        second = ensure_server(tmp_path, "sess-B")
        assert second["pid"] == first["pid"]  # 새 서버가 뜨지 않았다
        assert read_server_info(tmp_path)["session_id"] == "sess-B"
    finally:
        os.kill(first["pid"], signal.SIGTERM)


# ── 현재 세션 추적 ─────────────────────────────────────────────────────────
# 창은 `/resume`으로 세션을 갈아탄다. 그래서 현재 세션은 `.server`에 적힌 값이 아니라
# 그 창의 pid로 레지스트리에 되물어 얻는다. 내 창의 pid는 `CLAUDE_PID`가 말한다

def test_window_pid_reads_environment(monkeypatch):
    monkeypatch.setenv("CLAUDE_PID", "12956")
    assert window_pid() == 12956


def test_window_pid_zero_when_missing(monkeypatch):
    """`CLAUDE_PID`는 문서화된 인터페이스가 아니다. 없으면 추적을 포기하고 0을 준다."""
    monkeypatch.delenv("CLAUDE_PID", raising=False)
    assert window_pid() == 0


def test_window_pid_zero_when_not_a_number(monkeypatch):
    monkeypatch.setenv("CLAUDE_PID", "열두시")
    assert window_pid() == 0


def test_spawned_child_records_window_pid(tmp_path):
    """부모가 읽은 창의 pid를 자식이 `.server`에 적는다.

    자식이 환경변수를 직접 읽지 않으므로, 이 값은 부모가 인자로 넘긴 것이어야 한다.
    """
    info = ensure_server(tmp_path, "sess-A", 4242)
    try:
        assert read_server_info(tmp_path)["session_pid"] == 4242
    finally:
        os.kill(info["pid"], signal.SIGTERM)

@pytest.fixture
def window(tmp_path, monkeypatch):
    """레지스트리를 갈아 끼운 서버 객체. `(서버, 루트, 등록함수)`를 준다.

    `serve_forever`를 돌리지 않는다 — 이 묶음이 보는 것은 요청 처리가 아니라
    `current_session_id()`의 판정 하나다.
    """
    import common.paths as paths

    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(paths, "LIVE_SESSIONS_DIR", sessions)

    root = tmp_path / "project"
    root.mkdir()
    instance = Server(_listen(), root, TOKEN)

    def register(pid: int, session_id: str) -> None:
        (sessions / f"{pid}.json").write_text(
            json.dumps({"pid": pid, "sessionId": session_id, "cwd": str(root)}),
            encoding="utf-8")

    yield instance, root, register
    instance.server_close()


def test_current_session_id_follows_window(window):
    """창이 지금 보고 있는 세션을 돌려준다 — 기록된 값이 아니다."""
    instance, root, register = window
    register(os.getpid(), "옮긴뒤")
    write_server_info(root, {"session_id": "옮기기전", "session_pid": os.getpid()})
    assert instance.current_session_id() == "옮긴뒤"


def test_current_session_id_falls_back_when_window_gone(window):
    """레지스트리에서 창을 찾지 못하면 기록된 세션으로 떨어진다.

    레지스트리는 문서화된 인터페이스가 아니므로 사라질 수 있다. 그때 최악은
    `/resume`을 따라가지 못하는 것이어야 하고, 가드가 없어지는 것이어서는 안 된다.
    """
    instance, root, _ = window
    write_server_info(root, {"session_id": "기록된세션", "session_pid": os.getpid()})
    assert instance.current_session_id() == "기록된세션"


def test_current_session_id_falls_back_without_session_pid(window):
    """`session_pid`가 없는 `.server`도 같다."""
    instance, root, register = window
    register(os.getpid(), "다른세션")
    write_server_info(root, {"session_id": "기록된세션"})
    assert instance.current_session_id() == "기록된세션"


def test_reuse_updates_session_pid(tmp_path):
    """재사용이 창의 pid도 갱신한다.

    세션 ID만 갱신하면 다음 요청이 옛 창에 되묻는다. 두 창이 같은 세션을 열고 있을 때는
    세션 ID가 같은데 창이 다를 수도 있으므로, 두 필드를 함께 견줘야 한다.
    """
    first = ensure_server(tmp_path, "sess-A", 4242)
    try:
        ensure_server(tmp_path, "sess-B", 7777)
        assert read_server_info(tmp_path)["session_pid"] == 7777
    finally:
        os.kill(first["pid"], signal.SIGTERM)
