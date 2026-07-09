"""
사용자 scope의 ~/.claude/settings.json을 검사해 텔레메트리(OTEL) 설정이
올바르게 활성화되어 있는지 판단한다.

[판단 조건]
settings.json의 env 객체에 아래 9개 KEY가 모두 존재하고,
  · 상위 7개는 KEY 존재 + VALUE가 지정 값과 정확히 일치
  · 하위 2개(CLIENT_CERT/CLIENT_KEY)는 KEY 존재 + VALUE 경로에 실제 파일 존재
위 조건을 모두 만족하면 True를 반환한다.

파일이 없거나 JSON 파싱 실패 등 어떤 예외에서도 False로 처리해
statusline 전체 렌더링을 막지 않는다.
"""
import json
import os


# VALUE까지 정확히 일치해야 하는 7개 항목
_REQUIRED_VALUES = {
    'CLAUDE_CODE_ENABLE_TELEMETRY': '1',
    'CLAUDE_CODE_ENHANCED_TELEMETRY_BETA': '1',
    'OTEL_LOGS_EXPORTER': 'otlp',
    'OTEL_METRICS_EXPORTER': 'none',
    'OTEL_LOG_USER_PROMPTS': '0',
    'OTEL_EXPORTER_OTLP_PROTOCOL': 'http/protobuf',
    'OTEL_EXPORTER_OTLP_ENDPOINT': 'https://llm-ot.openub.com',
}

# VALUE 경로에 실제 파일이 존재해야 하는 2개 항목
_REQUIRED_FILES = (
    'CLAUDE_CODE_CLIENT_CERT',
    'CLAUDE_CODE_CLIENT_KEY',
)


def _settings_path() -> str:
    """사용자 scope settings.json 경로."""
    return os.path.expanduser(os.path.join('~', '.claude', 'settings.json'))


def parse() -> bool:
    """텔레메트리 설정이 조건을 모두 충족하면 True."""
    try:
        with open(_settings_path(), encoding='utf-8') as f:
            env = (json.load(f) or {}).get('env') or {}

        # 상위 7개: KEY 존재 + VALUE 일치
        for key, expected in _REQUIRED_VALUES.items():
            if env.get(key) != expected:
                return False

        # 하위 2개: KEY 존재 + VALUE 경로에 실제 파일 존재
        for key in _REQUIRED_FILES:
            path = env.get(key)
            if not path or not os.path.isfile(os.path.expanduser(path)):
                return False

        return True
    except Exception:
        return False


def render(is_on: bool, palette, style) -> str:
    """텔레메트리 상태를 statusline 문자열로 렌더링한다.

    on이면 '📡 telemetry on'(#A2D8F7), 그 외에는 빈 문자열(라인에서 생략)."""
    if not is_on:
        return ''
    return f'📡 {palette.telemetry}telemetry on{palette.reset}'
