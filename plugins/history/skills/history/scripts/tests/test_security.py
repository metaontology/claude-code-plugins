"""접근 경계 — 이 서버가 서빙하는 것은 사용자의 전체 대화 기록이다.

넷은 선택이 아니라 요구사항이다. 토큰 검증 · 루프백 바인딩 · CORS 헤더 없음 ·
정적 경로 열거 없음.
"""
import socket
import threading

import pytest

from server.app import HOST, Server, bind_port
from store.layout import ensure_dirs, index_path, server_file
from tests.test_app import TOKEN, get


@pytest.fixture
def running(tmp_path):
    """index.html과 `.server`를 갖춘 서버. 흘릴 것이 있는 상태로 경계를 시험한다."""
    ensure_dirs(tmp_path)
    index_path(tmp_path).write_text("<h1>대화 기록</h1>", encoding="utf-8")
    server_file(tmp_path).write_text('{"token": "비밀"}', encoding="utf-8")

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((HOST, 0))
    sock.listen(5)
    server = Server(sock, tmp_path, TOKEN)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], tmp_path
    server.shutdown()
    server.server_close()


# ── 토큰 검증은 라우팅보다 앞에 있다 ───────────────────────────────────────

@pytest.mark.parametrize("path", ["/", "/api/health", "/api/live", "/anything"])
def test_no_token_is_403_on_every_path(running, path):
    """경로를 가리지 않는다. 예외 경로를 두지 않는다."""
    port, _ = running
    assert get(port, path)[0] == 403


def test_wrong_token_is_403(running):
    port, _ = running
    assert get(port, "/?t=wrong-token")[0] == 403


def test_health_is_not_exempt(running):
    """중복 실행을 판별하는 쪽이 `.server`에서 토큰을 읽으므로 예외를 둘 이유가 없다."""
    port, _ = running
    assert get(port, "/api/health")[0] == 403
    assert get(port, f"/api/health?t={TOKEN}")[0] == 200


def test_403_body_carries_no_reason(running):
    port, _ = running
    _, _, body = get(port, "/")
    assert body == b""


def test_favicon_is_403(running):
    """브라우저가 자동으로 요청하는 경로도 규칙에 걸린다. 화면은 파비콘 없이 동작한다."""
    port, _ = running
    assert get(port, "/favicon.ico")[0] == 403


# ── CORS 헤더를 붙이지 않는다 ──────────────────────────────────────────────

@pytest.mark.parametrize("path", ["/", "/api/health", "/nope"])
def test_no_cors_header_on_any_response(running, path):
    """헤더를 열어두는 것은 토큰 하나에 모든 방어를 거는 것이다."""
    port, _ = running
    _, headers, _ = get(port, f"{path}?t={TOKEN}")
    assert not any(key.lower().startswith("access-control") for key in headers)


def test_no_cors_header_on_403(running):
    port, _ = running
    _, headers, _ = get(port, "/")
    assert not any(key.lower().startswith("access-control") for key in headers)


# ── 정적 경로를 열거하지 않는다 ────────────────────────────────────────────

@pytest.mark.parametrize("path", [
    "/../../.claude/settings.json",
    "/..%2f..%2f.claude%2fsettings.json",
    "/index.html",
    "/data/.server",
    "/.history/index.html",
])
def test_only_root_serves_a_file(running, path):
    """서빙하는 정적 파일은 `/` 요청의 index.html 하나뿐이다.

    훗날 누군가 자산 서빙을 추가하면 이 테스트가 먼저 깨진다.
    """
    port, _ = running
    status, _, body = get(port, f"{path}?t={TOKEN}")
    assert status == 404
    assert b"\xeb\x8c\x80\xed\x99\x94" not in body  # "대화"가 실려 나가지 않는다
    assert b"token" not in body


def test_root_path_does_serve_index(running):
    """경계가 정상 경로를 막지는 않는다."""
    port, _ = running
    status, _, body = get(port, f"/?t={TOKEN}")
    assert status == 200
    assert "대화 기록" in body.decode("utf-8")


# ── 루프백에만 바인딩한다 ──────────────────────────────────────────────────

def test_binds_loopback_only():
    """`0.0.0.0`으로 열면 공용 망의 다른 기기가 대화 기록에 접근한다."""
    sock, _ = bind_port()
    try:
        assert sock.getsockname()[0] == "127.0.0.1"
    finally:
        sock.close()
