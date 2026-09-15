"""
사용자 scope의 settings.json을 검사해 텔레메트리(OTEL) 수집이 실제로
켜져 있는지 판단한다.

[판단 조건]
Claude Code 본체의 판정을 그대로 옮긴 것이다.
  · CLAUDE_CODE_ENABLE_TELEMETRY 가 truthy — 마스터 스위치.
    `isTelemetryEnabled()`(instrumentation.ts:324)가 보는 유일한 키다
  · OTEL_{LOGS,METRICS,TRACES}_EXPORTER 중 'none'이 아닌 익스포터가 하나 이상.
    스위치만 켜고 익스포터가 없으면 아무것도 전송되지 않으므로 off로 본다.
    'none'을 걸러내는 규칙은 `parseExporterTypes()`(instrumentation.ts:121)와 같다

엔드포인트·프로토콜·프롬프트 로깅 여부·mTLS 인증서는 수집의 범위와 전송 방식을
정할 뿐 활성 여부를 가르지 않으므로 판정에 넣지 않는다. 넣으면 다른 백엔드를 쓰는
사용자가 수집이 정상인데도 off로 표시된다.

CLAUDE_CODE_ENHANCED_TELEMETRY_BETA 도 보지 않는다. 그 키는 세션 트레이싱(BETA)
전용이고(sessionTracing.ts:126), OTLP 익스포터 생성과 무관하다.

파일이 없거나 JSON 파싱 실패 등 어떤 예외에서도 False로 처리해
statusline 전체 렌더링을 막지 않는다.
"""
import json
import os


# isEnvTruthy(envUtils.ts:36)가 받는 값
_TRUTHY = frozenset(('1', 'true', 'yes', 'on'))

# 익스포터를 지정하는 키 — 하나라도 살아 있으면 전송이 일어난다
_EXPORTER_KEYS = (
    'OTEL_LOGS_EXPORTER',
    'OTEL_METRICS_EXPORTER',
    'OTEL_TRACES_EXPORTER',
)


def _config_home() -> str:
    """Claude Code의 설정 홈. envUtils.ts의 getClaudeConfigHomeDir()와 같은 규칙이다."""
    return (os.environ.get('CLAUDE_CONFIG_DIR')
            or os.path.join(os.path.expanduser('~'), '.claude'))


def _settings_path() -> str:
    """사용자 scope settings.json 경로."""
    return os.path.join(_config_home(), 'settings.json')


def _is_truthy(value) -> bool:
    """isEnvTruthy(envUtils.ts:32)와 같은 판정."""
    return str(value or '').strip().lower() in _TRUTHY


def _has_live_exporter(env: dict) -> bool:
    """'none'을 걸러내고 남는 익스포터가 하나라도 있으면 True."""
    for key in _EXPORTER_KEYS:
        for exporter in (env.get(key) or '').split(','):
            exporter = exporter.strip()
            if exporter and exporter != 'none':
                return True
    return False


def parse() -> bool:
    """텔레메트리가 실제로 수집 중이면 True."""
    try:
        with open(_settings_path(), encoding='utf-8') as f:
            env = (json.load(f) or {}).get('env') or {}

        # 마스터 스위치가 꺼져 있으면 익스포터 설정과 무관하게 아무것도 전송되지 않는다
        if not _is_truthy(env.get('CLAUDE_CODE_ENABLE_TELEMETRY')):
            return False

        return _has_live_exporter(env)
    except Exception:
        return False


def render(is_on: bool, palette, style) -> str:
    """텔레메트리 상태를 statusline 문자열로 렌더링한다.

    on이면 '📡 telemetry on'(#A2D8F7), 그 외에는 빈 문자열(라인에서 생략)."""
    if not is_on:
        return ''
    return f'📡 {palette.telemetry}telemetry on{palette.reset}'
