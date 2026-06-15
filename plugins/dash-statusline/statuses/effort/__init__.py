from domain.monitor.status.effort import EffortData

_LEVEL_SCORE = {
    'low':    'x0',
    'medium': 'x25',
    'high':   'x50',
    'xhigh':  'x75',
    'max':    '🔥100',
}


def parse(raw: dict) -> EffortData:
    level = (raw.get('effort') or {}).get('level')
    return EffortData(level=level)


def render(data: EffortData, palette, style) -> str:
    if data.level is None:
        return ''
    score = _LEVEL_SCORE.get(data.level, '')
    suffix = f' {score}' if score else ''
    return f'{palette.effort}effort{palette.reset} {data.level}{suffix}'
