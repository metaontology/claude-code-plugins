from domain.monitor.status.thinking import ThinkingData


def parse(raw: dict) -> ThinkingData:
    """stdin JSON에서 extended thinking 활성화 여부를 파싱한다.

    thinking.enabled=True이면 Claude가 응답 전에 내부 추론(extended thinking)을 실행한다.
    Claude Code는 on/off 여부만 전달하며 budget 등 세부 정보는 포함하지 않는다.
    think / think harder / ultrathink 키워드는 effort level을 변경하지 않고
    프롬프트에 in-context instruction만 추가하는 1회성 힌트이므로 이 값에 반영되지 않는다.
    """
    enabled = (raw.get('thinking') or {}).get('enabled')
    return ThinkingData(enabled=enabled)


def render(data: ThinkingData, palette, style) -> str:
    """thinking이 활성화된 경우 'thinking on'을 표시한다."""
    if not data.enabled:
        return ''
    return f'{palette.thinking}thinking{palette.reset} on'
