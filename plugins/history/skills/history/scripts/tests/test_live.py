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
from server.live import (
    is_alive,
    live_sessions,
    project_session_ids,
    session_for_pid,
)

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


def test_session_for_pid_empty_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LIVE_SESSIONS_DIR", tmp_path / "없는디렉토리")
    assert session_for_pid(ALIVE) == ""


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


# ── 창의 지금 ──────────────────────────────────────────────────────────────
# 창의 정체성은 pid다. 세션 UUID는 `/resume`으로 갈아탈 수 있으므로 창을 가리키지 못한다.
# 반대 방향(세션으로 창을 찾는 것)은 두지 않는다 — 여러 창이 같은 세션을 열고 있으면
# 후보가 여럿이고 어느 것이 `/history`를 실행한 창인지 가릴 근거가 레지스트리에 없다

def test_session_for_pid_finds_session(registry, tmp_path):
    registry("1.json", _entry("보고있는세션", tmp_path))
    assert session_for_pid(ALIVE) == "보고있는세션"


def test_session_for_pid_empty_for_unknown_pid(registry, tmp_path, dead_pid):
    registry("1.json", _entry("보고있는세션", tmp_path))
    assert session_for_pid(dead_pid) == ""


def test_session_for_pid_follows_resume(registry, tmp_path):
    """`/resume`은 **같은 pid 항목의 `sessionId`만** 갈아 끼운다.

    이 파일에서 pid 역조회의 이유가 전부 여기 있다. 이것이 없으면 누군가
    `session_for_pid`를 `.server`에 적힌 세션 ID를 돌려주는 것으로 "단순화"했을 때
    아무 테스트도 깨지지 않고, 대신 뷰어의 `현재`가 다시 옛 세션에 붙는다.
    """
    registry("1.json", _entry("옮기기전", tmp_path))
    assert session_for_pid(ALIVE) == "옮기기전"
    registry("1.json", _entry("옮긴뒤", tmp_path))
    assert session_for_pid(ALIVE) == "옮긴뒤"


# ── 창 수 ──────────────────────────────────────────────────────────────────
# 창 둘이 같은 세션을 열 수 있다. 집합으로 접으면 그 사실이 사라지고, 화면은 한 세션을
# 두 곳에서 쓰고 있다는 것을 영원히 말하지 못한다

def test_project_session_ids_keeps_one_per_window(registry, tmp_path):
    """**창 하나에 원소 하나다.** 같은 세션을 두 창이 열면 두 번 담긴다."""
    root = tmp_path / "proj"
    registry("1.json", _entry("함께보는세션", root))
    registry("2.json", _entry("함께보는세션", root))
    registry("3.json", _entry("혼자보는세션", root))
    assert project_session_ids(root) == ["함께보는세션", "함께보는세션", "혼자보는세션"]


def test_project_session_ids_drops_one_when_window_leaves(registry, tmp_path):
    """창이 하나 떨어지면 한 번으로 줄어든다 — 스트림이 이 차이로 이벤트를 보낸다."""
    root = tmp_path / "proj"
    registry("1.json", _entry("함께보는세션", root))
    registry("2.json", _entry("함께보는세션", root))
    assert project_session_ids(root) == ["함께보는세션", "함께보는세션"]
    (registry.dir / "2.json").unlink()
    assert project_session_ids(root) == ["함께보는세션"]
