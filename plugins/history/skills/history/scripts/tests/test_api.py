"""엔드포인트 수준 검증 — 토큰·상태코드·응답 형태.

함수 수준 규칙은 `test_session_delete.py`·`test_auto_memory_discard.py`가 맡는다.
같은 규칙을 두 곳에서 검증하지 않는다.
"""
import json
import os
import platform
import socket
import threading
import urllib.error
import urllib.request

import pytest

import common.paths as paths
import server.api as api_module
import store.config as user_config
from auto_memory.model import memory_dir
from server.api import parse_rename, parse_targets
from server.app import HOST, Server, write_server_info
from store.layout import index_path
from tests.test_app import TOKEN

CURRENT = "cur00000-0000-0000-0000-000000000000"
OTHER = "oth00000-0000-0000-0000-000000000000"
SLUG = "api-slug"

DELETE = "/api/sessions/delete"
RENAME = "/api/sessions/rename"
DISCARD = "/api/auto-memory/discard"
CONFIG = "/api/config"
CONFIG_RESET = "/api/config/reset"
REVEAL = "/api/reveal"


@pytest.fixture
def api(tmp_path, monkeypatch):
    """서버와 프로젝트 데이터를 갖춘 환경. `(서버, 슬러그 디렉토리)`.

    살아 있는 세션 레지스트리도 `tmp_path/live`로 갈아 끼운다. 실물을 보게 두면 이 테스트가
    실행 중인 Claude Code 인스턴스의 수에 따라 결과를 바꾼다. 그 디렉토리에 항목을 넣는
    테스트는 `tmp_path`를 함께 받으면 된다 — 같은 테스트 안에서 같은 경로다.
    """
    projects = tmp_path / "projects"
    monkeypatch.setattr(paths, "PROJECTS_DIR", projects)
    live_dir = tmp_path / "live"
    live_dir.mkdir()
    monkeypatch.setattr(paths, "LIVE_SESSIONS_DIR", live_dir)
    # 설정 파일도 갈아 끼운다. 실물을 보게 두면 이 테스트가 사용자의 테마를 덮어쓴다.
    # 모듈이 상수를 바인딩 시점에 가져오므로 paths가 아니라 store.config를 패치한다
    user_dir = tmp_path / "userconfig"
    monkeypatch.setattr(user_config, "USER_CONFIG_DIR", user_dir)
    monkeypatch.setattr(user_config, "USER_CONFIG_FILE", user_dir / "config.json")
    slug_dir = projects / SLUG
    slug_dir.mkdir(parents=True)
    # find_project_slug가 현재 세션 jsonl로 슬러그를 찾는다
    (slug_dir / f"{CURRENT}.jsonl").write_text('{"type":"user"}\n', encoding="utf-8")

    root = tmp_path / "project"
    root.mkdir()
    write_server_info(root, {"pid": 1, "port": 0, "token": TOKEN,
                             "root": str(root), "session_id": CURRENT})

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((HOST, 0))
    sock.listen(5)
    server = Server(sock, root, TOKEN)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server, slug_dir
    server.shutdown()
    server.server_close()


def post(port: int, path: str, body, token: str = TOKEN):
    """POST 요청을 보내고 `(상태코드, 응답 dict)`를 돌려준다."""
    raw = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    url = f"http://{HOST}:{port}{path}"
    if token is not None:
        url += f"?t={token}"
    request = urllib.request.Request(url, data=raw, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        return exc.code, (json.loads(payload) if payload else {})


# ── parse_targets ──────────────────────────────────────────────────────────

def test_parse_targets_reads_list():
    assert parse_targets(b'{"targets": ["a", "b"]}') == ["a", "b"]


@pytest.mark.parametrize("body", [
    b"not json",
    b'["a"]',
    b'{"targets": "a"}',
    b'{"targets": [1, 2]}',
    b"{}",
])
def test_parse_targets_rejects_bad_body(body):
    with pytest.raises(ValueError):
        parse_targets(body)


# ── 토큰 ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [DELETE, RENAME, DISCARD, CONFIG, REVEAL])
def test_no_token_is_rejected(api, path):
    server, _ = api
    status, _ = post(server.server_address[1], path, {"targets": []}, token=None)
    assert status == 403


@pytest.mark.parametrize("path", [DELETE, RENAME, DISCARD, CONFIG, REVEAL])
def test_wrong_token_is_rejected(api, path):
    server, _ = api
    status, _ = post(server.server_address[1], path, {"targets": []}, token="wrong")
    assert status == 403


# ── 요청 형식 ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", [DELETE, RENAME, DISCARD, CONFIG, REVEAL])
def test_malformed_body_is_400_with_error(api, path):
    """대상별 결과를 만들 수 없으므로 results가 아니라 error를 돌려준다."""
    server, _ = api
    status, payload = post(server.server_address[1], path, b"{")
    assert status == 400
    assert "error" in payload
    assert "results" not in payload


# ── 세션 삭제 ──────────────────────────────────────────────────────────────

def test_delete_returns_per_target_results(api):
    server, slug_dir = api
    (slug_dir / f"{OTHER}.jsonl").write_text("{}", encoding="utf-8")
    status, payload = post(server.server_address[1], DELETE,
                           {"targets": [OTHER, CURRENT]})
    assert status == 200
    assert [r["target"] for r in payload["results"]] == [OTHER, CURRENT]
    assert [r["ok"] for r in payload["results"]] == [True, False]
    assert not (slug_dir / f"{OTHER}.jsonl").exists()


def test_delete_rejects_current_session_from_server_file(api):
    """현재 세션 판정은 `.server`에서 읽는다 — 요청 본문의 값이 아니다."""
    server, slug_dir = api
    status, payload = post(server.server_address[1], DELETE, {"targets": [CURRENT]})
    assert status == 200
    assert payload["results"][0]["ok"] is False
    assert (slug_dir / f"{CURRENT}.jsonl").exists()


def test_delete_rejects_running_session(api, tmp_path):
    """옆에서 돌고 있는 세션도 거부한다. 판정은 요청 시점에 레지스트리를 다시 읽는다."""
    server, slug_dir = api
    jsonl = slug_dir / f"{OTHER}.jsonl"
    jsonl.write_text("{}", encoding="utf-8")
    (tmp_path / "live" / "1.json").write_text(
        json.dumps({"pid": os.getpid(), "sessionId": OTHER,
                    "cwd": str(server.project_root)}), encoding="utf-8")

    status, payload = post(server.server_address[1], DELETE, {"targets": [OTHER]})
    assert status == 200
    assert payload["results"][0]["ok"] is False
    assert "실행 중인 세션" in payload["results"][0]["reason"]
    assert jsonl.exists()


def test_delete_sees_updated_session_id(api):
    """재사용된 서버도 갱신된 세션 ID를 판정에 쓴다.

    `.server`의 `session_id`를 바꾸면 서버는 다음 요청에서 새 값을 읽는다. 환경변수를
    쓰면 이 갱신이 반영되지 않아 낡은 세션을 계속 보호한다.
    """
    server, slug_dir = api
    (slug_dir / f"{OTHER}.jsonl").write_text("{}", encoding="utf-8")
    # 다음 세션에서 /history를 다시 실행한 상태를 만든다
    info = {"pid": 1, "port": 0, "token": TOKEN,
            "root": str(server.project_root), "session_id": OTHER}
    write_server_info(server.project_root, info)

    status, payload = post(server.server_address[1], DELETE, {"targets": [OTHER]})
    assert status == 200
    assert payload["results"][0]["ok"] is False
    assert (slug_dir / f"{OTHER}.jsonl").exists()


# ── 세션 이름 수정 ─────────────────────────────────────────────────────────
# 정규화와 덧붙이기의 규칙은 `test_session_rename.py`가 맡는다


def _last_line(path):
    return path.read_text(encoding="utf-8").splitlines()[-1]


def test_parse_rename_reads_target_and_title():
    """대상이 하나이므로 `targets` 목록이 아니라 `target` 하나를 읽는다."""
    assert parse_rename(b'{"target": "a", "title": "  \\uc774\\ub984  "}') == ("a", "이름")


@pytest.mark.parametrize("body", [
    b"not json",
    b'["a"]',
    b'{"title": "\\uc774\\ub984"}',
    b'{"target": 1, "title": "\\uc774\\ub984"}',
    b'{"target": "a"}',
    b'{"target": "a", "title": "   "}',
])
def test_parse_rename_rejects_bad_body(body):
    with pytest.raises(ValueError):
        parse_rename(body)


def test_rename_returns_normalized_title_and_appends(api):
    server, slug_dir = api
    jsonl = slug_dir / f"{OTHER}.jsonl"
    jsonl.write_text('{"type":"user"}\n', encoding="utf-8")

    status, payload = post(server.server_address[1], RENAME,
                           {"target": OTHER, "title": "  새 이름  "})
    assert status == 200
    assert payload == {"ok": True, "title": "새 이름"}
    assert json.loads(_last_line(jsonl))["customTitle"] == "새 이름"


def test_rename_rebuilds_on_success(api):
    """화면이 새 이름을 보려고 한 번 더 왕복하지 않게 여기서 다시 만든다."""
    server, slug_dir = api
    (slug_dir / f"{OTHER}.jsonl").write_text("{}\n", encoding="utf-8")
    called = []
    server.rebuild = lambda: called.append(1)
    post(server.server_address[1], RENAME, {"target": OTHER, "title": "새 이름"})
    assert called == [1]


def test_rename_rejects_empty_title_with_400(api):
    """요청을 고치면 통과하는 사유이므로 400이다."""
    server, slug_dir = api
    jsonl = slug_dir / f"{OTHER}.jsonl"
    jsonl.write_text('{"type":"user"}\n', encoding="utf-8")

    status, payload = post(server.server_address[1], RENAME,
                           {"target": OTHER, "title": "   "})
    assert status == 400
    assert "error" in payload
    assert jsonl.read_text(encoding="utf-8") == '{"type":"user"}\n'


def test_rename_rejects_current_session_with_409(api):
    """요청은 옳은데 지금 상태가 거부하는 사유이므로 409다."""
    server, slug_dir = api
    status, payload = post(server.server_address[1], RENAME,
                           {"target": CURRENT, "title": "새 이름"})
    assert status == 409
    assert "현재 세션" in payload["error"]
    assert (slug_dir / f"{CURRENT}.jsonl").read_text(encoding="utf-8") == '{"type":"user"}\n'


def test_rename_rejects_running_session_with_409(api, tmp_path):
    """판정은 요청 시점에 레지스트리를 다시 읽는다 — 화면이 보낸 값이 아니다."""
    server, slug_dir = api
    jsonl = slug_dir / f"{OTHER}.jsonl"
    jsonl.write_text('{"type":"user"}\n', encoding="utf-8")
    (tmp_path / "live" / "1.json").write_text(
        json.dumps({"pid": os.getpid(), "sessionId": OTHER,
                    "cwd": str(server.project_root)}), encoding="utf-8")

    status, payload = post(server.server_address[1], RENAME,
                           {"target": OTHER, "title": "새 이름"})
    assert status == 409
    assert "실행 중인 세션" in payload["error"]
    assert jsonl.read_text(encoding="utf-8") == '{"type":"user"}\n'


def test_rename_reports_missing_file_with_409(api):
    server, _ = api
    status, payload = post(server.server_address[1], RENAME,
                           {"target": "no-such-session", "title": "새 이름"})
    assert status == 409
    assert "error" in payload


# ── auto-memory 폐기 ───────────────────────────────────────────────────────

def test_discard_returns_removed_key(api):
    """응답이 무엇이 실제로 지워졌는지 구분해 답한다."""
    server, _ = api
    directory = memory_dir(SLUG)
    directory.mkdir(parents=True)
    (directory / "a.md").write_text("---\nname: 가\n---\n본문", encoding="utf-8")
    (directory / "MEMORY.md").write_text("- [가](a.md) — 요약\n", encoding="utf-8")

    status, payload = post(server.server_address[1], DISCARD, {"targets": ["a.md"]})
    assert status == 200
    assert payload["results"][0]["removed"] == ["file", "index_line"]


def test_delete_response_has_no_removed_key(api):
    """세션 삭제는 지울 것이 하나뿐이므로 `ok`가 이미 답한다."""
    server, slug_dir = api
    (slug_dir / f"{OTHER}.jsonl").write_text("{}", encoding="utf-8")
    _, payload = post(server.server_address[1], DELETE, {"targets": [OTHER]})
    assert "removed" not in payload["results"][0]


# ── 재생성 ─────────────────────────────────────────────────────────────────

def test_rebuild_called_when_something_processed(api):
    server, slug_dir = api
    (slug_dir / f"{OTHER}.jsonl").write_text("{}", encoding="utf-8")
    called = []
    server.rebuild = lambda: called.append(1)
    post(server.server_address[1], DELETE, {"targets": [OTHER]})
    assert called == [1]


def test_rebuild_not_called_when_nothing_processed(api):
    """전부 실패하면 산출물을 다시 만들 이유가 없다."""
    server, _ = api
    called = []
    server.rebuild = lambda: called.append(1)
    post(server.server_address[1], DELETE, {"targets": [CURRENT]})
    assert called == []


def test_failed_rebuild_drops_index(api):
    """재생성이 실패하면 산출물을 지운다 — 다음 실행이 전량 생성으로 복구한다.

    남겨두면 mtime 판정이 "갱신 불필요"라 답하고 지워진 세션이 보이는 화면이 열린다.
    """
    server, slug_dir = api
    (slug_dir / f"{OTHER}.jsonl").write_text("{}", encoding="utf-8")
    index_path(server.project_root).write_text("낡은 산출물", encoding="utf-8")

    def broken():
        raise RuntimeError("생성 실패")

    server.rebuild = broken
    status, payload = post(server.server_address[1], DELETE, {"targets": [OTHER]})
    # 삭제 결과는 사실대로 보고된다
    assert status == 200
    assert payload["results"][0]["ok"] is True
    assert not index_path(server.project_root).exists()


# ── 사용자 설정 ────────────────────────────────────────────────────────────

def test_config_save_returns_merged(api):
    server, _ = api
    status, payload = post(server.server_address[1], CONFIG, {"theme": "dark"})
    assert status == 200
    assert payload["ok"] is True
    assert payload["config"] == {"theme": "dark"}


def test_config_save_reports_failure_as_200(api, monkeypatch):
    """저장하지 못한 것을 **4xx로 알리지 않는다.**

    화면이 잠시 뒤 다시 보내므로 재시도가 이 경로의 정상 동작인데, 4xx면 브라우저가 그것을
    콘솔에 ERROR로 남겨 정상 동작이 매번 빨간 줄을 만든다.
    """
    server, _ = api
    monkeypatch.setattr("server.api.save_config", lambda patch: None)
    status, payload = post(server.server_address[1], CONFIG, {"theme": "dark"})
    assert status == 200
    assert payload["ok"] is False
    # 쓰지 않았으므로 디스크가 지금 무엇인지 말할 수 없다
    assert "config" not in payload


def test_config_save_writes_file(api, tmp_path):
    server, _ = api
    post(server.server_address[1], CONFIG, {"theme": "dark"})
    saved = json.loads((tmp_path / "userconfig" / "config.json").read_text(encoding="utf-8"))
    assert saved == {"theme": "dark"}


def test_config_save_is_partial(api):
    """보내지 않은 키가 살아남는다."""
    server, _ = api
    post(server.server_address[1], CONFIG, {"theme": "dark", "paneWidth": 420})
    _, payload = post(server.server_address[1], CONFIG, {"theme": "light"})
    assert payload["config"] == {"theme": "light", "paneWidth": 420}


def test_config_save_drops_invalid_key(api):
    server, _ = api
    _, payload = post(server.server_address[1], CONFIG, {"theme": "purple", "paneWidth": 420})
    assert payload["config"] == {"paneWidth": 420}


def test_config_rejects_non_object_body(api):
    server, _ = api
    status, payload = post(server.server_address[1], CONFIG, b'["dark"]')
    assert status == 400
    assert "error" in payload


def test_config_does_not_rebuild(api):
    """설정은 화면이 이미 반영한 값을 뒤따라 저장하는 것이라 산출물을 다시 만들지 않는다."""
    server, _ = api
    called = []
    server.rebuild = lambda: called.append(1)
    post(server.server_address[1], CONFIG, {"theme": "dark"})
    assert called == []


def test_config_reset_clears_file(api):
    server, _ = api
    port = server.server_address[1]
    post(port, CONFIG, {"theme": "dark"})
    assert user_config.USER_CONFIG_FILE.exists()

    status, payload = post(port, CONFIG_RESET, {})
    assert status == 200
    # 화면이 기본값을 다시 물어보지 않아도 되게 병합 결과를 돌려준다
    assert payload["config"] == {"theme": "system", "paneWidth": 340}
    assert not user_config.USER_CONFIG_FILE.exists()


def test_config_reset_rebuilds(api):
    """초기화는 파일이 **사라지는** 연산이라 어떤 mtime도 올리지 않는다.

    `GET /`의 갱신 판정은 mtime 비교이므로, 여기서 다시 만들지 않으면 지워진 설정이 심긴
    화면이 그대로 다시 열린다. 삭제 API가 판정을 건너뛰는 것과 같은 이유다.
    """
    server, _ = api
    called = []
    server.rebuild = lambda: called.append(1)
    post(server.server_address[1], CONFIG_RESET, {})
    assert called == [1]


def test_config_reset_requires_token(api):
    server, _ = api
    status, _ = post(server.server_address[1], CONFIG_RESET, {}, token=None)
    assert status == 403


# ── 탐색기에서 보기 ────────────────────────────────────────────────────────
# 경로 문자열은 요청에서 받지 않는다 — target 열거값 둘만 서버가 고른다

def test_reveal_project_opens_project_root_on_windows(api, monkeypatch):
    server, _ = api
    monkeypatch.setattr(os, "name", "nt")
    calls = []
    monkeypatch.setattr(api_module.subprocess, "Popen", lambda cmd: calls.append(cmd))

    status, payload = post(server.server_address[1], REVEAL, {"target": "project"})
    assert status == 200
    assert payload == {"ok": True}
    assert calls == [["explorer", str(server.project_root)]]


def test_reveal_sessions_dir_opens_slug_directory(api, monkeypatch):
    server, slug_dir = api
    monkeypatch.setattr(os, "name", "nt")
    calls = []
    monkeypatch.setattr(api_module.subprocess, "Popen", lambda cmd: calls.append(cmd))

    status, payload = post(server.server_address[1], REVEAL, {"target": "sessions_dir"})
    assert status == 200
    assert payload == {"ok": True}
    assert calls == [["explorer", str(slug_dir)]]


def test_reveal_opens_with_open_on_mac(api, monkeypatch):
    server, _ = api
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    calls = []
    monkeypatch.setattr(api_module.subprocess, "Popen", lambda cmd: calls.append(cmd))

    status, payload = post(server.server_address[1], REVEAL, {"target": "project"})
    assert status == 200
    assert payload == {"ok": True}
    assert calls == [["open", str(server.project_root)]]


def test_reveal_unsupported_os_returns_ok_false(api, monkeypatch):
    """리눅스 등에서는 버튼 자체가 그려지지 않지만, 서버도 스스로 답을 거부한다."""
    server, _ = api
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(platform, "system", lambda: "Linux")

    status, payload = post(server.server_address[1], REVEAL, {"target": "project"})
    assert status == 200
    assert payload == {"ok": False, "reason": "unsupported_os"}


def test_reveal_rejects_invalid_target_with_400(api):
    """요청을 고치면 통과하는 사유이므로 400이다."""
    server, _ = api
    status, payload = post(server.server_address[1], REVEAL, {"target": "etc"})
    assert status == 400
    assert "error" in payload


def test_reveal_sessions_dir_without_slug_returns_409(api):
    """요청은 옳은데 현재 세션의 슬러그를 찾을 수 없어 거부하는 것이므로 409다."""
    server, _ = api
    write_server_info(server.project_root, {"pid": 1, "port": 0, "token": TOKEN,
                                             "root": str(server.project_root),
                                             "session_id": "no-such-session"})
    status, payload = post(server.server_address[1], REVEAL, {"target": "sessions_dir"})
    assert status == 409
    assert "error" in payload
