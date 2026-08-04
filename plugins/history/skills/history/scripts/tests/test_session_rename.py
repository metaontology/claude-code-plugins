"""세션 이름 수정의 함수 수준 규칙 — 이름 정규화와 레코드 덧붙이기.

엔드포인트 수준(상태코드·토큰·응답 형태)은 `test_api.py`가 맡는다.
같은 규칙을 두 곳에서 검증하지 않는다.
"""
import json

import pytest

import common.paths as paths
from session.rename import RECORD_TYPE, TITLE_LIMIT, normalize_title, rename_session

CURRENT = "cur00000-0000-0000-0000-000000000000"
LIVE = "liv00000-0000-0000-0000-000000000000"
OTHER = "oth00000-0000-0000-0000-000000000000"
SLUG = "rename-slug"

NONE_LIVE: set[str] = set()

# 원본에 이미 있던 줄. 덧붙인 뒤에도 그대로 남아야 한다
FIRST_LINE = '{"type":"user"}'


@pytest.fixture
def slug_dir(tmp_path, monkeypatch):
    """`PROJECTS_DIR`를 임시 디렉토리로 갈아 끼운 슬러그 디렉토리.

    실물을 보게 두면 이 테스트가 사용자의 세션 파일에 줄을 덧붙인다.
    """
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    directory = tmp_path / SLUG
    directory.mkdir()
    return directory


def _make_jsonl(slug_dir, session_id, text=FIRST_LINE + "\n"):
    path = slug_dir / f"{session_id}.jsonl"
    path.write_text(text, encoding="utf-8")
    return path


def _rename(session_id, title="새 이름", live=NONE_LIVE):
    return rename_session(session_id, SLUG, CURRENT, live, title)


def _lines(path):
    return path.read_text(encoding="utf-8").splitlines()


# ── normalize_title ────────────────────────────────────────────────────────

def test_normalize_trims_edges():
    assert normalize_title("  20-domain-model  ") == "20-domain-model"


def test_normalize_folds_newline_into_space():
    """jsonl은 한 줄이 한 레코드다. 줄바꿈이 남으면 레코드가 쪼개진다."""
    assert normalize_title("앞줄\n뒷줄") == "앞줄 뒷줄"


def test_normalize_collapses_runs_of_whitespace():
    assert normalize_title("가\t\t나   다") == "가 나 다"


@pytest.mark.parametrize("raw", ["", "   ", "\n\t "])
def test_normalize_rejects_empty(raw):
    """빈 이름으로 자동 제목에 되돌리는 길을 열지 않는다."""
    with pytest.raises(ValueError):
        normalize_title(raw)


def test_normalize_rejects_non_string():
    with pytest.raises(ValueError):
        normalize_title(None)


def test_normalize_allows_exactly_the_limit():
    assert len(normalize_title("가" * TITLE_LIMIT)) == TITLE_LIMIT


def test_normalize_rejects_over_the_limit():
    with pytest.raises(ValueError):
        normalize_title("가" * (TITLE_LIMIT + 1))


# ── rename_session — 덧붙이기 ──────────────────────────────────────────────

def test_rename_appends_custom_title_record(slug_dir):
    path = _make_jsonl(slug_dir, OTHER)
    result = _rename(OTHER, "20-domain-model 기획중")

    assert result["ok"] is True
    assert result["title"] == "20-domain-model 기획중"
    assert json.loads(_lines(path)[-1]) == {
        "type": RECORD_TYPE,
        "customTitle": "20-domain-model 기획중",
        "sessionId": OTHER,
    }


def test_rename_keeps_existing_lines(slug_dir):
    """파일을 다시 쓰지 않는다. 앞의 줄이 그대로 남는다."""
    path = _make_jsonl(slug_dir, OTHER)
    _rename(OTHER)
    lines = _lines(path)
    assert lines[0] == FIRST_LINE
    assert len(lines) == 2


def test_rename_wins_over_earlier_record(slug_dir):
    """여러 번 고치면 마지막 것이 현재 이름이다."""
    path = _make_jsonl(slug_dir, OTHER)
    _rename(OTHER, "처음")
    _rename(OTHER, "나중")
    assert json.loads(_lines(path)[-1])["customTitle"] == "나중"


def test_rename_does_not_join_a_file_without_trailing_newline(slug_dir):
    """줄 중간에 죽은 파일에 붙여도 두 줄이 한 줄로 이어지지 않는다."""
    path = _make_jsonl(slug_dir, OTHER, text=FIRST_LINE)
    _rename(OTHER)
    lines = _lines(path)
    assert lines[0] == FIRST_LINE
    assert json.loads(lines[-1])["type"] == RECORD_TYPE


def test_rename_does_not_lead_an_empty_file_with_a_blank_line(slug_dir):
    """빈 파일에는 앞에 붙일 줄이 없다. 개행을 넣으면 첫 줄이 빈 줄이 된다."""
    path = _make_jsonl(slug_dir, OTHER, text="")
    _rename(OTHER)
    assert len(_lines(path)) == 1


def test_rename_writes_utf8_as_is(slug_dir):
    """한글이 이스케이프되지 않는다 — 사람이 파일 끝을 눈으로 읽는다."""
    path = _make_jsonl(slug_dir, OTHER)
    _rename(OTHER, "한글 이름")
    assert "한글 이름" in path.read_text(encoding="utf-8")


# ── rename_session — 가드 ──────────────────────────────────────────────────

def test_rename_rejects_current_session(slug_dir):
    path = _make_jsonl(slug_dir, CURRENT)
    result = _rename(CURRENT)
    assert result["ok"] is False
    assert "현재 세션" in result["reason"]
    # 사유 문구의 동사가 삭제가 아니라 수정이다
    assert "수정" in result["reason"]
    assert len(_lines(path)) == 1


def test_rename_rejects_running_session(slug_dir):
    """실행 중인 세션은 그 창의 Claude Code가 옛 이름을 다시 덧붙여 되돌린다."""
    path = _make_jsonl(slug_dir, LIVE)
    result = _rename(LIVE, live={LIVE})
    assert result["ok"] is False
    assert "실행 중인 세션" in result["reason"]
    assert len(_lines(path)) == 1


def test_rename_reports_missing_file(slug_dir):
    """조용히 성공으로 처리하지 않는다. 산출물이 낡았다는 사실을 사용자가 알아야 한다."""
    result = _rename(OTHER)
    assert result["ok"] is False
    assert "없습니다" in result["reason"]


def test_rename_leaves_title_empty_on_failure(slug_dir):
    assert _rename(CURRENT)["title"] == ""
