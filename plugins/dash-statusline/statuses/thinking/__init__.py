from domain.monitor.status.thinking import ThinkingData


def parse(raw: dict) -> ThinkingData:
    enabled = (raw.get('thinking') or {}).get('enabled')
    return ThinkingData(enabled=enabled)


def render(data: ThinkingData, palette, style) -> str:
    if not data.enabled:
        return ''
    return f'{palette.thinking}thinking{palette.reset} on'
