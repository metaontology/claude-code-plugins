from domain.monitor.status.effort import EffortData


def parse(raw: dict) -> EffortData:
    level = (raw.get('effort') or {}).get('level')
    return EffortData(level=level)


def render(data: EffortData, palette, style) -> str:
    if data.level is None:
        return ''
    return f'{palette.effort}{data.level}{palette.reset}'
