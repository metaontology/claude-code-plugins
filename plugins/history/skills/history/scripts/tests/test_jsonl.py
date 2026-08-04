from common.jsonl import parse_jsonl, get_session_meta

def test_parse_jsonl_basic(tmp_path):
    f = tmp_path / "test.jsonl"
    f.write_text('{"type":"user"}\n{"type":"assistant"}\n', encoding="utf-8")
    records = parse_jsonl(f)
    assert len(records) == 2
    assert records[0]["type"] == "user"

def test_parse_jsonl_skips_invalid_lines(tmp_path):
    f = tmp_path / "test.jsonl"
    f.write_text('{"type":"user"}\nBAD JSON\n{"type":"ai"}\n', encoding="utf-8")
    records = parse_jsonl(f)
    assert len(records) == 2

def test_parse_jsonl_skips_empty_lines(tmp_path):
    f = tmp_path / "test.jsonl"
    f.write_text('\n{"type":"user"}\n\n', encoding="utf-8")
    records = parse_jsonl(f)
    assert len(records) == 1

def test_get_session_meta_extracts_fields():
    records = [
        {"timestamp": "2026-05-29T07:00:34Z", "type": "user"},
        {"type": "ai-title", "aiTitle": "테스트 세션"},
    ]
    meta = get_session_meta(records)
    assert meta["ts"] == "2026-05-29T07:00:34Z"
    assert meta["ai_title"] == "테스트 세션"

def test_get_session_meta_empty_records():
    meta = get_session_meta([])
    assert meta["ts"] == ""
    assert meta["ai_title"] == ""

def test_get_session_meta_fallback_to_first_user_text():
    """ai-title 없으면 첫 번째 사용자 텍스트 메시지를 fallback으로 사용한다."""
    records = [
        {"timestamp": "2026-06-01T00:00:00Z", "type": "user",
         "message": {"role": "user", "content": "SESSION.md 삭제 컬럼 개선 방법"}},
    ]
    meta = get_session_meta(records)
    assert meta["ai_title"] == "SESSION.md 삭제 컬럼 개선 방법"


def test_get_session_meta_fallback_truncates_long_text():
    """fallback 텍스트는 60자로 잘린다."""
    long_text = "가" * 80
    records = [
        {"timestamp": "2026-06-01T00:00:00Z", "type": "user",
         "message": {"role": "user", "content": long_text}},
    ]
    meta = get_session_meta(records)
    assert len(meta["ai_title"]) == 60


def test_get_session_meta_fallback_skips_noise():
    """command 태그·skill 주입 메시지는 fallback 대상에서 제외된다."""
    records = [
        {"type": "user", "message": {"role": "user",
         "content": "<command-name>/history:history</command-name>"}},
        {"type": "user", "message": {"role": "user",
         "content": "실제 사용자 질문"}},
    ]
    meta = get_session_meta(records)
    assert meta["ai_title"] == "실제 사용자 질문"


def test_get_session_meta_first_timestamp_wins():
    records = [
        {"timestamp": "2026-01-01T00:00:00Z", "type": "user"},
        {"timestamp": "2026-06-01T00:00:00Z", "type": "user"},
    ]
    meta = get_session_meta(records)
    assert meta["ts"] == "2026-01-01T00:00:00Z"
