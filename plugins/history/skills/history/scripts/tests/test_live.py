"""살아 있는 세션 판별의 검증.

원본은 Claude Code의 내부 파일이므로 실물을 읽지 않는다. 레지스트리 디렉토리를
`tmp_path`로 갈아 끼우고 판정만 본다.

이 파일에서 가장 중요한 테스트는 「생존 확인이 대상을 죽이지 않는다」이다. 그것이 없으면
누군가 `is_alive`를 `os.kill(pid, 0)` 한 줄로 줄였을 때 아무것도 깨지지 않고, 대신
사용자의 다른 Claude Code 세션이 조용히 죽는다.
"""
import json
import os
import subprocess
import sys

import pytest

import common.paths as paths
from server.live import is_alive, live_sessions, project_session_ids

ALIVE = os.getpid()


@pytest.fixture
def registry(tmp_path, monkeypatch):
    """레지스트리 디렉토리를 tmp_path로 갈아 끼운다. 항목을 넣는 함수를 돌려준다."""
    directory = tmp_path / "sessions"
    directory.mkdir()
    monkeypatch.setattr(paths, "LIVE_SESSIONS_DIR", directory)

    def add(name: str, payload) -> None:
        text = payload if isinstance(payload, str) else json.dumps(payload)
        (directory / name).write_text(text, encoding="utf-8")

    add.dir = directory
    return add


@pytest.fixture
def dead_pid():
    """확실히 끝난 프로세스의 pid."""
    process = subprocess.Popen([sys.executable, "-c", ""])
    process.wait()
    return process.pid


def _entry(session_id: str, cwd, pid: int = ALIVE) -> dict:
    return {"pid": pid, "sessionId": session_id, "cwd": str(cwd),
            "status": "idle", "kind": "interactive"}


# ── 열화 ───────────────────────────────────────────────────────────────────
# 원본은 문서화된 인터페이스가 아니다. 없거나 깨져도 예외가 밖으로 나가지 않는다

def test_live_sessions_empty_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LIVE_SESSIONS_DIR", tmp_path / "없는디렉토리")
    assert live_sessions() == []


def test_live_sessions_empty_when_dir_empty(registry):
    assert live_sessions() == []


def test_live_sessions_skips_broken_json(registry):
    registry("1.json", "{이건 JSON이 아니다")
    registry("2.json", _entry("keep", "/p"))
    assert [item["sessionId"] for item in live_sessions()] == ["keep"]


def test_live_sessions_skips_non_object_json(registry):
    registry("1.json", [1, 2, 3])
    assert live_sessions() == []


def test_live_sessions_skips_entry_without_session_id(registry):
    registry("1.json", {"pid": ALIVE, "cwd": "/p"})
    assert live_sessions() == []


def test_live_sessions_skips_entry_without_pid(registry):
    registry("1.json", {"sessionId": "no-pid", "cwd": "/p"})
    assert live_sessions() == []


def test_live_sessions_skips_non_integer_pid(registry):
    registry("1.json", {"pid": "열두시", "sessionId": "bad-pid", "cwd": "/p"})
    assert live_sessions() == []


def test_project_session_ids_empty_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LIVE_SESSIONS_DIR", tmp_path / "없는디렉토리")
    assert project_session_ids(tmp_path) == []


# ── 생존 ───────────────────────────────────────────────────────────────────

def test_is_alive_true_for_self():
    assert is_alive(ALIVE) is True


def test_is_alive_false_for_finished_process(dead_pid):
    assert is_alive(dead_pid) is False


def test_is_alive_does_not_kill_the_process():
    """생존 확인은 조회다. Windows의 `os.kill(pid, 0)`은 대상을 종료시킨다."""
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert is_alive(process.pid) is True
        # 확인 뒤에도 살아 있어야 한다. 죽었다면 확인 행위가 죽인 것이다
        assert process.poll() is None
        assert is_alive(process.pid) is True
    finally:
        process.kill()
        process.wait()


def test_live_sessions_excludes_dead_pid(registry, dead_pid):
    registry("1.json", _entry("gone", "/p", pid=dead_pid))
    registry("2.json", _entry("here", "/p"))
    assert [item["sessionId"] for item in live_sessions()] == ["here"]


# ── 프로젝트 한정 ──────────────────────────────────────────────────────────

def test_project_session_ids_keeps_same_cwd(registry, tmp_path):
    root = tmp_path / "proj"
    registry("1.json", _entry("mine", root))
    assert project_session_ids(root) == ["mine"]


def test_project_session_ids_drops_other_cwd(registry, tmp_path):
    registry("1.json", _entry("elsewhere", tmp_path / "다른프로젝트"))
    assert project_session_ids(tmp_path / "proj") == []


def test_project_session_ids_ignores_trailing_separator(registry, tmp_path):
    """경로 문자열 뒤의 구분자 하나로 같은 디렉토리가 달라지지 않는다."""
    root = tmp_path / "proj"
    registry("1.json", _entry("mine", str(root) + os.sep))
    assert project_session_ids(root) == ["mine"]


def test_project_session_ids_skips_entry_without_cwd(registry, tmp_path):
    registry("1.json", {"pid": ALIVE, "sessionId": "no-cwd"})
    assert project_session_ids(tmp_path) == []


def test_project_session_ids_sorted(registry, tmp_path):
    """정렬이 없으면 열거 순서가 바뀔 때마다 스트림이 변경으로 읽는다."""
    root = tmp_path / "proj"
    for name, session_id in (("30.json", "ccc"), ("10.json", "aaa"), ("20.json", "bbb")):
        registry(name, _entry(session_id, root))
    assert project_session_ids(root) == ["aaa", "bbb", "ccc"]
