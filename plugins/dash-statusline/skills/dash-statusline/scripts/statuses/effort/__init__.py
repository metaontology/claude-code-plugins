import json
import os

from domain.monitor.status.effort import EffortData

_LEVEL_SCORE = {
    'low':    'x0',
    'medium': 'x25',
    'high':   'x50',
    'xhigh':  'x75',
    'max':    '🔥100',
}


def _settings_effort_level() -> str | None:
    """~/.claude/settings.json의 effortLevel을 읽는다.

    xhigh는 Opus 4.7+ 전용 레벨이다. Sonnet 등 미지원 모델에서는
    Claude Code가 stdin JSON에 high로 폴백해 전달한다 (정상 동작).
    실제 설정값을 복원하기 위해 settings.json을 직접 참조한다.
    """
    try:
        path = os.path.expanduser('~/.claude/settings.json')
        with open(path) as f:
            return json.load(f).get('effortLevel')
    except Exception:
        return None


def parse(raw: dict) -> EffortData:
    """stdin JSON에서 effort level을 파싱한다.

    effort는 Claude의 사고 깊이를 나타내며 low/medium/high/xhigh/max 5단계다.
    /effort로 세션 전체 기본값을 변경할 수 있다.

    xhigh는 Opus 4.7+ 전용이라 미지원 모델에서는 stdin에 high로 폴백된다.
    stdin level이 'high'일 때만 settings.json을 참조해 실제 설정값으로 복원하고,
    나머지(low/medium/max)는 stdin 값을 그대로 사용한다.

    참고: think/think harder/ultrathink 키워드는 effort level을 변경하지 않으며
    프롬프트에 in-context instruction만 추가하는 1회성 힌트다.
    """
    level = (raw.get('effort') or {}).get('level')
    if level == 'high':
        # xhigh 미지원 모델의 폴백 보정: settings.json에 xhigh 이상이 저장된 경우에만 덮어씀
        settings_level = _settings_effort_level()
        if settings_level and settings_level in _LEVEL_SCORE:
            level = settings_level
    return EffortData(level=level)


def render(data: EffortData, palette, style) -> str:
    if data.level is None:
        return ''
    score = _LEVEL_SCORE.get(data.level, '')
    suffix = f' {score}' if score else ''
    return f'{palette.effort}effort{palette.reset} {data.level}{suffix}'
