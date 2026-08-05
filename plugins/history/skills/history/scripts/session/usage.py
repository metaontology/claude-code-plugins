"""세션 하나의 컨텍스트 사용량과 모델을 세는 계층.

문자열을 만들지 않는다 — 숫자와 모델 ID 원문만 돌려주고 `437.1k`·`Opus 5` 같은 표기는
화면이 만든다. `session/model.py`가 시각을 ISO 문자열로 넘기는 것과 같은 경계다.

컨텍스트 윈도우 크기는 세션 jsonl에 없다. `[1m]` 접미사가 붙은 모델 문자열이 그것을 정하는데
그 문자열은 런타임 상태이고 어디에도 저장되지 않는다. 확인한 자리 전부와 근거는
`docs/dev-plans/00-core/040-context-usage.md`의 「윈도우는 세션에 기록되지 않는다」가 갖는다.
"""

# 1M을 지원하지 않는 모델의 윈도우. 스냅샷이 이 값을 넘었다면 그 세션은 1M으로 돌았다
SMALL_WINDOW = 200_000
LARGE_WINDOW = 1_000_000

# 표에 없는 모델의 윈도우. 과대평가가 아니라 과소 표시이므로 안전한 쪽으로 빗나간다
DEFAULT_WINDOW = SMALL_WINDOW

# @[모델 출시] 새 모델이 나오면 여기에 한 줄 더한다. 잊으면 그 모델이 DEFAULT_WINDOW로
# 떨어지고 window_basis가 "unknown"이 되어 뷰어에 ⚠ 가 선다.
# `python tools/정합/모델표점검.py`가 실제로 쓰인 모델 중 여기 없는 것을 열거한다.
#
# 셋째 값은 그 크기가 확정인가다. 1M을 지원하지 않는 모델만 확정이며("table"),
# 지원하는 모델은 설정에 따라 200,000으로 돌 수 있고 그 여부가 기록되지 않는다("assumed").
MODEL_WINDOWS = (
    ("claude-haiku-4-5", SMALL_WINDOW, "table"),
    ("claude-opus-5", LARGE_WINDOW, "assumed"),
    ("claude-sonnet-5", LARGE_WINDOW, "assumed"),
    ("claude-fable-5", LARGE_WINDOW, "assumed"),
    ("claude-opus-4", LARGE_WINDOW, "assumed"),
    ("claude-sonnet-4", LARGE_WINDOW, "assumed"),
)


def _is_real_model(value) -> bool:
    """실제 모델 ID인가.

    Claude Code는 자기가 만든 가짜 응답에 `<synthetic>`을 싣는다 — 본문이
    `"No response requested."`이고 `usage`가 전부 0인 레코드다(실측 49건). 그것을 세면
    **그 레코드가 세션의 마지막일 때 `current`가 0으로 떨어져 실제 사용량이 지워지고**,
    `models`의 마지막이 `<synthetic>`이 되어 윈도우 판정도 `unknown`으로 빗나간다.

    `<`로 시작하는 것을 전부 배제한다. 관측된 값은 `<synthetic>` 하나이지만, 모델 ID에
    꺾쇠가 쓰이는 일은 없으므로 자리표시자가 더 생겨도 같은 규칙에 걸린다.
    """
    return isinstance(value, str) and bool(value) and not value.startswith("<")


def _tokens(value) -> int:
    """usage의 토큰 값을 정수로 만든다.

    새 세션의 첫 응답에서 `null`이 오는 것이 관측되므로 정수가 아닌 값은 0으로 본다.
    `bool`은 `int`의 하위형이라 따로 뺀다 — `True`가 1로 세어지면 그 자리가 조용히 틀린다.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def window_for(model_id: str, peak: int) -> tuple[int, str]:
    """(윈도우 크기, 근거)를 돌려준다.

    관측이 표보다 앞선다 — 스냅샷이 `SMALL_WINDOW`를 넘었다는 사실이 그 세션의 윈도우를
    **증명**하므로 표가 무엇이라 하든 이쪽이 이긴다.

    표는 접두사로 맞춘다. `claude-opus-5-20260401`처럼 날짜가 붙은 ID도 걸린다.
    """
    if peak > SMALL_WINDOW:
        return LARGE_WINDOW, "observed"
    for prefix, window, basis in MODEL_WINDOWS:
        if model_id.startswith(prefix):
            return window, basis
    return DEFAULT_WINDOW, "unknown"


def session_usage(records: list[dict]) -> dict:
    """레코드 목록에서 컨텍스트 사용량과 모델을 센다.

    세는 레코드는 `type == "assistant"`이고 `isSidechain`이 참이 아니며 `message.usage`가
    객체인 것뿐이다. 사이드체인은 서브에이전트의 것이고 **별도 컨텍스트에서 돌므로**
    합치면 한 화면에 존재하지 않는 값이 표시된다.

    반환값의 키 — `current` · `peak` · `window` · `window_basis` · `models`

    토큰 네 갈래(read · creation · uncached · output)를 따로 담지 않는다. 화면이 쓰지 않고,
    쓰지 않기로 한 근거는 `docs/dev-plans/20-viewer/080-context-gauge.md`의
    「분해를 보여주지 않는다」가 갖는다.
    """
    snapshots: list[int] = []
    models: list[str] = []

    for record in records:
        if record.get("type") != "assistant" or record.get("isSidechain"):
            continue
        message = record.get("message") or {}
        usage = message.get("usage")
        # usage가 없는 레코드는 모델도 취하지 않는다. 모델만 취하면 게이지와 모델 표시가
        # 서로 다른 레코드에서 와서, 마지막 응답의 모델이 아닌 것이 「현시점 모델」로 선다
        if not isinstance(usage, dict):
            continue

        model = message.get("model")
        # 가짜 응답은 레코드 전체를 건너뛴다. usage가 0이라 그 값이 current를 덮어쓴다
        if not _is_real_model(model):
            continue
        if model not in models:
            models.append(model)

        # output_tokens는 더하지 않는다. 이번 턴의 출력은 다음 턴에 cache_creation으로
        # 들어오므로 지금 더하면 같은 토큰을 두 번 센다
        snapshots.append(
            _tokens(usage.get("cache_read_input_tokens"))
            + _tokens(usage.get("cache_creation_input_tokens"))
            + _tokens(usage.get("input_tokens"))
        )

    current = snapshots[-1] if snapshots else 0
    peak = max(snapshots) if snapshots else 0
    # 「현시점 모델」이 윈도우를 정한다. 세션 중간에 /model로 바꾼 경우 마지막 것이 현재다
    window, basis = window_for(models[-1] if models else "", peak)

    return {
        "current": current,
        "peak": peak,
        "window": window,
        "window_basis": basis,
        "models": models,
    }
