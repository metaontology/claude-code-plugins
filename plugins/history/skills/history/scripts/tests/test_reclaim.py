"""서버 프로세스가 새지 않는다는 계약.

`test_app.py`와 가르는 기준은 **무엇이 깨지면 안 되는가**다. 여기가 깨지면 사용자의
기계에 프로세스가 쌓이거나, 살아 있는 서버가 보이지 않아 하나가 더 뜬다. 기동·라우팅
회귀와 섞이면 그 신호가 묻힌다.
"""
import os
import signal
import socket
import time

import server.app as app
from server.app import (
    HOST,
    ensure_server,
    live_server,
    read_server_info,
    write_server_info,
)
from server.live import is_alive
from store.layout import server_file


def _sse(port: int, token: str) -> socket.socket:
    """`/api/live`에 붙어 응답의 첫 바이트까지 받은 소켓.

    첫 바이트를 기다리는 이유는 그때라야 서버가 연결을 셌다는 것이 확실하기 때문이다.
    """
    sock = socket.create_connection((HOST, port), timeout=5)
    sock.sendall(f"GET /api/live?t={token} HTTP/1.1\r\nHost: {HOST}\r\n\r\n".encode())
    sock.recv(4096)
    return sock


def _died(pid: int, limit: float) -> bool:
    """`limit`초 안에 그 프로세스가 사라지는가."""
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        if not is_alive(pid):
            return True
        time.sleep(0.2)
    return False


# ── `.server`는 자기 것만 지운다 ───────────────────────────────────────────
# 파일은 프로젝트당 하나인데 종료 훅은 프로세스마다 걸린다. 내용을 보지 않고 지우면
# 먼저 죽는 서버가 살아 있는 서버의 파일을 가져간다

def test_release_server_file_removes_own_file(tmp_path):
    write_server_info(tmp_path, {"pid": os.getpid(), "port": 7391})
    app.release_server_file(tmp_path, os.getpid())
    assert not server_file(tmp_path).exists()


def test_release_server_file_keeps_another_owners_file(tmp_path):
    """다른 프로세스가 기록한 파일은 남긴다 — 그것이 이 결함의 핵심이다."""
    other = {"pid": os.getpid() + 1, "port": 7392}
    write_server_info(tmp_path, other)
    app.release_server_file(tmp_path, os.getpid())
    assert read_server_info(tmp_path) == other


def test_release_server_file_when_missing(tmp_path):
    """파일이 없어도 예외를 내지 않는다 — 종료 훅에서 나가는 예외는 갈 곳이 없다."""
    app.release_server_file(tmp_path, os.getpid())
    assert not server_file(tmp_path).exists()


def test_release_server_file_keeps_undecidable_file(tmp_path):
    """소유자를 읽을 수 없으면 남긴다.

    지우는 쪽이 위험하다 — 판정 불가는 「남의 것이 아니다」의 증거가 되지 못한다.
    남겨서 생기는 최악은 stale 파일 하나이고, 그것은 `live_server()`가 이미 처리한다.
    """
    write_server_info(tmp_path, {})
    server_file(tmp_path).write_text("{깨진 JSON", encoding="utf-8")
    app.release_server_file(tmp_path, os.getpid())
    assert server_file(tmp_path).exists()


def test_release_server_file_keeps_file_without_pid(tmp_path):
    """`pid` 키가 없는 파일도 판정 불가다."""
    write_server_info(tmp_path, {"port": 7391, "token": "t"})
    app.release_server_file(tmp_path, os.getpid())
    assert server_file(tmp_path).exists()


# ── 한 번의 실패를 사망으로 읽지 않는다 ────────────────────────────────────

def test_live_server_retries_a_failed_probe(tmp_path, monkeypatch):
    """한 번의 health 실패로 살아 있는 서버를 죽었다고 단정하지 않는다.

    오판의 대가가 대칭이 아니다 — 죽은 서버를 산 것으로 보면 다음 요청이 실패하고 끝이지만,
    산 서버를 죽은 것으로 보면 서버가 하나 더 뜨고 사용자는 탭 두 개가 서로 다른 서버를
    보는 상태를 만난다.
    """
    write_server_info(tmp_path, {"pid": 1, "port": 7391, "token": "t"})
    answers = [None, {"ok": True, "root": str(tmp_path)}]
    monkeypatch.setattr(app, "probe_health", lambda *_: answers.pop(0))

    assert live_server(tmp_path) is not None
    assert answers == []  # 두 번째 기회를 실제로 썼다


def test_live_server_stops_probing_after_the_last_attempt(tmp_path, monkeypatch):
    """찌르는 횟수는 정해져 있다 — 죽은 서버에 `/history`가 매달리지 않는다."""
    calls = []
    monkeypatch.setattr(app, "probe_health", lambda *_: calls.append(1))
    write_server_info(tmp_path, {"pid": 1, "port": 7391, "token": "t"})

    assert live_server(tmp_path) is None
    assert len(calls) == app.HEALTH_ATTEMPTS


def test_live_server_probes_once_when_the_server_answers(tmp_path, monkeypatch):
    """답하는 서버를 두 번 찌르지 않는다 — 재사용 경로에 왕복을 더하지 않는다."""
    calls = []

    def fake(port, token):
        calls.append(1)
        return {"ok": True, "root": str(tmp_path)}

    monkeypatch.setattr(app, "probe_health", fake)
    write_server_info(tmp_path, {"pid": 1, "port": 7391, "token": "t"})

    assert live_server(tmp_path) is not None
    assert len(calls) == 1


def test_live_server_does_not_retry_a_foreign_root(tmp_path, monkeypatch):
    """루트가 다르다는 답은 그것으로 결론이다 — 다시 찔러도 같은 답이 온다."""
    calls = []

    def fake(port, token):
        calls.append(1)
        return {"ok": True, "root": "C:/다른/프로젝트"}

    monkeypatch.setattr(app, "probe_health", fake)
    write_server_info(tmp_path, {"pid": 1, "port": 7391, "token": "t"})

    assert live_server(tmp_path) is None
    assert len(calls) == 1


# ── 훅이 실제로 그렇게 도는가 ──────────────────────────────────────────────

def test_exiting_child_keeps_another_servers_file(tmp_path):
    """정상 종료하는 자식이 남의 `.server`를 지우지 않는다.

    종료 훅이 실제로 그렇게 걸렸는지는 자식 프로세스가 끝나 봐야 안다 — 같은 프로세스
    안의 테스트는 `atexit`을 관측하지 못하므로 이 축은 여기서만 닫힌다.

    끝나기를 기다리는 방법이 종료 유예뿐이다. 기동 유예(30초)는 너무 길어, 연결을 붙였다
    끊어 짧은 쪽(5초)으로 들어간다.
    """
    info = ensure_server(tmp_path)
    stream = _sse(info["port"], info["token"])
    # 살아 있는 다른 서버가 파일을 가져간 상태. 이 프로세스의 pid는 확실히 자식의 것이 아니다
    foreign = {"pid": os.getpid(), "port": 1, "token": "other", "root": str(tmp_path)}
    write_server_info(tmp_path, foreign)

    stream.close()
    try:
        assert _died(info["pid"], 20), "자식이 정상 종료하지 않아 훅을 관측하지 못했습니다"
    finally:
        if is_alive(info["pid"]):
            os.kill(info["pid"], signal.SIGTERM)
    assert read_server_info(tmp_path) == foreign
