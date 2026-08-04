import common.paths as paths
from session.delete import blocked_reason, delete_sessions

CURRENT = "cur00000-0000-0000-0000-000000000000"
LIVE = "liv00000-0000-0000-0000-000000000000"
OTHER = "oth00000-0000-0000-0000-000000000000"
SLUG = "test-slug"

NONE_LIVE: set[str] = set()


def _make_jsonl(tmp_path, session_id):
    directory = tmp_path / SLUG
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session_id}.jsonl"
    path.write_text('{"type":"user"}\n', encoding="utf-8")
    return path


# ── blocked_reason ─────────────────────────────────────────────────────────

def test_blocked_reason_allows_dead_session():
    assert blocked_reason(OTHER, CURRENT, {LIVE}) == ""


def test_blocked_reason_names_current_session():
    assert "현재 세션" in blocked_reason(CURRENT, CURRENT, NONE_LIVE)


def test_blocked_reason_names_running_session():
    assert "실행 중인 세션" in blocked_reason(LIVE, CURRENT, {LIVE})


def test_blocked_reason_prefers_current_over_running():
    """현재 세션은 거의 항상 살아 있다. 더 구체적인 사실이 "그건 지금 이 창이다"이다."""
    assert "현재 세션" in blocked_reason(CURRENT, CURRENT, {CURRENT, LIVE})


# ── delete_sessions ────────────────────────────────────────────────────────

def test_delete_sessions_removes_jsonl(tmp_path, monkeypatch):
    """대상은 jsonl 원본이다."""
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    jsonl = _make_jsonl(tmp_path, OTHER)
    results = delete_sessions([OTHER], SLUG, CURRENT, NONE_LIVE)
    assert results == [{"target": OTHER, "ok": True, "reason": ""}]
    assert not jsonl.exists()


def test_delete_sessions_rejects_current(tmp_path, monkeypatch):
    """현재 세션은 서버도 거부한다 — 화면 가드는 실수를, 이 가드는 우회를 막는다."""
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    jsonl = _make_jsonl(tmp_path, CURRENT)
    results = delete_sessions([CURRENT], SLUG, CURRENT, NONE_LIVE)
    assert results[0]["ok"] is False
    assert "현재 세션" in results[0]["reason"]
    assert jsonl.exists()


def test_delete_sessions_rejects_running_session(tmp_path, monkeypatch):
    """옆에서 돌고 있는 세션의 jsonl은 지금 쓰이는 파일이다. OS는 막아 주지 않는다."""
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    jsonl = _make_jsonl(tmp_path, LIVE)
    results = delete_sessions([LIVE], SLUG, CURRENT, {LIVE})
    assert results[0]["ok"] is False
    assert "실행 중인 세션" in results[0]["reason"]
    assert jsonl.exists()


def test_delete_sessions_guards_current_even_when_registry_is_empty(tmp_path, monkeypatch):
    """레지스트리를 읽지 못해도 오늘의 보호가 남는다 — 근거가 합집합인 이유다."""
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    jsonl = _make_jsonl(tmp_path, CURRENT)
    results = delete_sessions([CURRENT], SLUG, CURRENT, NONE_LIVE)
    assert results[0]["ok"] is False
    assert jsonl.exists()


def test_delete_sessions_partial_success(tmp_path, monkeypatch):
    """일부가 실패해도 나머지는 처리된다. 요청이 통째로 취소되지 않는다."""
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    keep = _make_jsonl(tmp_path, CURRENT)
    running = _make_jsonl(tmp_path, LIVE)
    gone = _make_jsonl(tmp_path, OTHER)
    results = delete_sessions([CURRENT, LIVE, OTHER], SLUG, CURRENT, {LIVE})
    assert [r["ok"] for r in results] == [False, False, True]
    assert keep.exists()
    assert running.exists()
    assert not gone.exists()


def test_delete_sessions_missing_is_failure(tmp_path, monkeypatch):
    """존재하지 않는 식별자를 조용히 성공으로 처리하지 않는다.

    화면의 식별자가 디스크와 맞지 않는 것은 산출물이 낡았다는 뜻이고, 사용자가 알아야
    하는 사실이다.
    """
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    (tmp_path / SLUG).mkdir(parents=True)
    results = delete_sessions([OTHER], SLUG, CURRENT, NONE_LIVE)
    assert results[0]["ok"] is False
    assert "없습니다" in results[0]["reason"]


def test_delete_sessions_preserves_order(tmp_path, monkeypatch):
    """결과 순서는 요청 순서와 같다 — 화면이 target으로 목록의 행을 찾는다."""
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    ids = [f"aaa0000{n}-0000-0000-0000-000000000000" for n in range(3)]
    for session_id in ids:
        _make_jsonl(tmp_path, session_id)
    results = delete_sessions(ids, SLUG, CURRENT, NONE_LIVE)
    assert [r["target"] for r in results] == ids


def test_delete_sessions_empty_target_list(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    assert delete_sessions([], SLUG, CURRENT, NONE_LIVE) == []
