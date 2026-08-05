from session.usage import (
    DEFAULT_WINDOW,
    LARGE_WINDOW,
    SMALL_WINDOW,
    session_usage,
    window_for,
)


def _assistant(read=0, creation=0, uncached=0, output=0,
               model="claude-opus-5", sidechain=False):
    """usage를 담은 assistant 레코드 하나."""
    return {
        "type": "assistant",
        "isSidechain": sidechain,
        "message": {
            "model": model,
            "usage": {
                "cache_read_input_tokens": read,
                "cache_creation_input_tokens": creation,
                "input_tokens": uncached,
                "output_tokens": output,
            },
        },
    }


# ── 집계 ───────────────────────────────────────────────────────────────────

def test_snapshot_is_sum_of_three():
    usage = session_usage([_assistant(read=100, creation=20, uncached=3)])
    assert usage["current"] == 123


def test_output_is_excluded_from_snapshot():
    """output은 다음 턴에 cache_creation으로 들어오므로 지금 더하면 이중 계상이다."""
    usage = session_usage([_assistant(read=100, creation=20, uncached=3, output=999)])
    assert usage["current"] == 123


def test_returns_only_five_keys():
    """토큰 네 갈래를 담지 않는다. 화면이 쓰지 않는 값을 반환하지 않는다."""
    usage = session_usage([_assistant(read=100, output=9)])
    assert set(usage) == {"current", "peak", "window", "window_basis", "models"}


def test_current_comes_from_last_record():
    records = [_assistant(read=100), _assistant(read=500)]
    assert session_usage(records)["current"] == 500


def test_peak_is_maximum_snapshot():
    """compaction이 일어나면 마지막이 최대가 아니다."""
    records = [_assistant(read=100), _assistant(read=500), _assistant(read=200)]
    usage = session_usage(records)
    assert usage["current"] == 200
    assert usage["peak"] == 500


def test_sidechain_records_are_not_counted():
    records = [_assistant(read=100), _assistant(read=9999, sidechain=True)]
    usage = session_usage(records)
    assert usage["current"] == 100
    assert usage["peak"] == 100


def test_records_without_usage_are_skipped():
    records = [
        {"type": "assistant", "message": {"model": "claude-sonnet-5"}},
        _assistant(read=100),
    ]
    usage = session_usage(records)
    assert usage["current"] == 100
    # usage가 없는 레코드의 모델도 취하지 않는다
    assert usage["models"] == ["claude-opus-5"]


def test_three_values_are_summed_not_just_read():
    """세 값이 모두 스냅샷에 든다 — read 하나만 세면 자투리가 빠진다."""
    records = [_assistant(read=1, creation=2, uncached=3),
               _assistant(read=10, creation=20, uncached=30)]
    usage = session_usage(records)
    assert usage["current"] == 60
    assert usage["peak"] == 60


def test_null_token_values_count_as_zero():
    """새 세션 첫 응답에 null이 오는 것이 관측된다."""
    records = [{
        "type": "assistant",
        "message": {"model": "claude-opus-5", "usage": {
            "cache_read_input_tokens": None,
            "cache_creation_input_tokens": 50,
            "input_tokens": None,
            "output_tokens": None,
        }},
    }]
    usage = session_usage(records)
    assert usage["current"] == 50


# ── 값이 없는 세션 ──────────────────────────────────────────────────────────

def test_no_assistant_records():
    records = [{"type": "user", "message": {"role": "user", "content": "안녕"}}]
    usage = session_usage(records)
    assert usage["current"] == 0
    assert usage["peak"] == 0
    assert usage["models"] == []
    assert usage["window_basis"] == "unknown"


def test_only_sidechain_records():
    usage = session_usage([_assistant(read=9999, sidechain=True)])
    assert usage["current"] == 0
    assert usage["models"] == []


def test_empty_records():
    usage = session_usage([])
    assert usage["current"] == 0
    assert usage["window"] == DEFAULT_WINDOW


# ── 윈도우 판정 ─────────────────────────────────────────────────────────────

def test_observation_beats_table():
    """스냅샷이 200k를 넘었다는 사실이 그 세션의 윈도우를 증명한다."""
    usage = session_usage([_assistant(read=SMALL_WINDOW + 1, model="claude-haiku-4-5")])
    assert usage["window"] == LARGE_WINDOW
    assert usage["window_basis"] == "observed"


def test_haiku_window_is_certain():
    usage = session_usage([_assistant(read=1000, model="claude-haiku-4-5")])
    assert usage["window"] == SMALL_WINDOW
    assert usage["window_basis"] == "table"


def test_opus_window_is_assumed():
    usage = session_usage([_assistant(read=1000, model="claude-opus-5")])
    assert usage["window"] == LARGE_WINDOW
    assert usage["window_basis"] == "assumed"


def test_dated_model_id_matches_by_prefix():
    usage = session_usage([_assistant(read=1000, model="claude-opus-5-20260401")])
    assert usage["window"] == LARGE_WINDOW
    assert usage["window_basis"] == "assumed"


def test_unregistered_model_falls_back():
    usage = session_usage([_assistant(read=1000, model="claude-newmodel-9")])
    assert usage["window"] == DEFAULT_WINDOW
    assert usage["window_basis"] == "unknown"


def test_window_for_boundary_is_exclusive():
    """정확히 200,000이면 아직 증명되지 않았다 — 그 값은 200k 윈도우에서도 가능하다."""
    assert window_for("claude-haiku-4-5", SMALL_WINDOW) == (SMALL_WINDOW, "table")
    assert window_for("claude-haiku-4-5", SMALL_WINDOW + 1) == (LARGE_WINDOW, "observed")


def test_window_uses_last_model():
    """세션 중간에 /model로 바꾸면 마지막 것이 현시점 모델이다."""
    records = [_assistant(read=100, model="claude-opus-5"),
               _assistant(read=100, model="claude-haiku-4-5")]
    usage = session_usage(records)
    assert usage["window"] == SMALL_WINDOW
    assert usage["window_basis"] == "table"


# ── 모델 목록 ───────────────────────────────────────────────────────────────

def test_models_keep_first_seen_order():
    records = [_assistant(model="claude-sonnet-5"), _assistant(model="claude-opus-5")]
    assert session_usage(records)["models"] == ["claude-sonnet-5", "claude-opus-5"]


def test_models_are_deduplicated():
    records = [_assistant(model="claude-opus-5")] * 3
    assert session_usage(records)["models"] == ["claude-opus-5"]


def test_models_records_a_mid_session_switch():
    records = [_assistant(model="claude-opus-5"),
               _assistant(model="claude-haiku-4-5"),
               _assistant(model="claude-opus-5")]
    # 되돌아온 모델을 두 번 담지 않는다. 목록은 「무엇이 쓰였나」이지 순서 이력이 아니다
    assert session_usage(records)["models"] == ["claude-opus-5", "claude-haiku-4-5"]


def test_record_without_model_field_is_skipped():
    """모델을 모르는 레코드는 세지 않는다. 실제로 관측되지 않는 형태다."""
    records = [{"type": "assistant", "message": {"usage": {"input_tokens": 5}}}]
    usage = session_usage(records)
    assert usage["models"] == []
    assert usage["current"] == 0


# ── 가짜 응답 ───────────────────────────────────────────────────────────────

def test_synthetic_record_does_not_erase_current():
    """`<synthetic>`은 usage가 전부 0이라, 세면 마지막 자리에서 current를 지운다."""
    records = [_assistant(read=500), _assistant(model="<synthetic>")]
    usage = session_usage(records)
    assert usage["current"] == 500
    assert usage["peak"] == 500


def test_synthetic_model_is_not_listed():
    records = [_assistant(model="claude-opus-5"), _assistant(model="<synthetic>")]
    usage = session_usage(records)
    assert usage["models"] == ["claude-opus-5"]
    assert usage["window_basis"] == "assumed"


def test_only_synthetic_records():
    usage = session_usage([_assistant(model="<synthetic>")])
    assert usage["current"] == 0
    assert usage["models"] == []
