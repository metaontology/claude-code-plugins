from domain.monitor.status.rate_limits import RateLimitsData


def _pct(raw_rl: dict, key: str) -> int | None:
    try:
        v = (raw_rl.get(key) or {}).get('used_percentage')
        return int(v) if v is not None else None
    except Exception:
        return None


def _pct_color(pct: int, palette) -> str:
    if pct >= 90:
        return palette.crit
    if pct >= 70:
        return palette.warn
    return palette.ok


def parse(raw: dict) -> RateLimitsData:
    rl = raw.get('rate_limits')
    if not rl:
        return RateLimitsData(five_hour_pct=None, seven_day_pct=None)
    return RateLimitsData(
        five_hour_pct=_pct(rl, 'five_hour'),
        seven_day_pct=_pct(rl, 'seven_day'),
    )


def render(data: RateLimitsData, palette, style) -> str:
    parts = []
    if data.five_hour_pct is not None:
        col = _pct_color(data.five_hour_pct, palette)
        parts.append(
            f'{palette.blue}\U0001d7d3hr{palette.reset}'
            f' {col}{data.five_hour_pct}%{palette.reset}'
        )
    if data.seven_day_pct is not None:
        col = _pct_color(data.seven_day_pct, palette)
        parts.append(
            f'{palette.purple_red}\U0001d7d5day{palette.reset}'
            f' {col}{data.seven_day_pct}%{palette.reset}'
        )
    if not parts:
        return ''
    return ' | ' + ' | '.join(parts)
