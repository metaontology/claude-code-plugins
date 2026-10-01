"""다른 Claude 세션이 이 세션에 메시지를 보낼 때 쓰는 주소(`이름 [ref]`)를 표시한다.

stdin의 `session_name`과는 다른 값이다. 그쪽은 `/rename`으로 붙인 사용자 지정 제목이고
(붙이지 않으면 키가 없다), 여기서 보이는 것은 ListAgents에 나오는 이름 = SendMessage 주소다.

출처는 `~/.claude/sessions/<pid>.json` 등록부다(Claude Code 2.1.286 기준). 공개 문서에 없는
내부 파일이라 판이 바뀌면 모양이 달라질 수 있다.

[edge case]
- 못 찾으면 줄을 빼지 않고 PLACEHOLDER(`Ⓜ️ ...`)를 낸다. 줄을 빼면 7줄↔6줄로 화면이 들썩인다.
- `/clear`·`/resume` 직후: 새 session_id가 발급되고 본체의 onSessionSwitch 콜백이 등록부의
  `sessionId`만 비동기로 고쳐 쓴다. statusline은 300ms debounce 뒤에 돌기 때문에 보통은 쓰기가
  먼저 끝나지만, 늦으면 한 번 PLACEHOLDER가 보인다. 다음 갱신(다음 답변·Shift+Tab 모드 전환·
  모델 변경)에서 맞춰진다. `/clear`로 주소는 바뀌지 않는다 — 이름은 그대로이고 ref는 프로세스마다
  하나인 소켓 경로로 계산하기 때문이다.
- 세션 시작 직후 등록이 끝나기 전의 첫 갱신도 같은 이유로 PLACEHOLDER가 보일 수 있다.
- 끝난 프로세스의 파일이 남아 같은 sessionId가 둘 이상이면 `updatedAt`이 큰 쪽을 쓴다.
- 깨진 파일·dict가 아닌 JSON은 건너뛴다. 등록부 폴더가 없어도(옛 판·등록 실패) PLACEHOLDER다.
- 기능 플래그 `tengu_session_stable_address`가 켜지면 본체의 ref 입력이 바뀌어(_ref 참조)
  여기 ref가 ListAgents와 어긋난다. 2026-10-01 기준 꺼져 있다.
- 이름은 캐시하지 않는다. `/rename` 등으로 바뀔 수 있고, 파일 몇 개를 읽는 데 1ms 남짓이다.
"""
import glob
import hashlib
import json
import os

from domain.monitor.status.cross_session_name import CrossSessionNameData

PLACEHOLDER = 'Ⓜ️ ...'

# ListAgents가 보여 주는 ref 길이. 앞자리가 겹치면 본체는 12자리까지 늘리지만
# 16진수 6자리가 겹칠 일은 드물어 고정한다.
_REF_LEN = 6


def _config_home() -> str:
    """Claude Code의 설정 홈. envUtils.ts의 getClaudeConfigHomeDir()와 같은 규칙이다."""
    return (os.environ.get('CLAUDE_CONFIG_DIR')
            or os.path.join(os.path.expanduser('~'), '.claude'))


def _ref(sock: str) -> str:
    """ListAgents의 `[ref]`를 계산한다.

    Claude Code 2.1.286 번들의 `HBe("session", sock)` = sha256(`session:<sock>`) 앞 6자리.
    기능 플래그 `tengu_session_stable_address`가 켜지면 본체는 입력을
    `session:sid:<sessionId>`로 바꾼다 — 그때는 이 값이 ListAgents와 어긋난다.
    """
    return hashlib.sha256(f'session:{sock}'.encode('utf-8')).hexdigest()[:_REF_LEN]


def _find_entry(session_id: str) -> dict | None:
    """등록부에서 sessionId가 같은 항목을 찾는다. 둘 이상이면 updatedAt이 큰 쪽."""
    best = None
    for p in glob.glob(os.path.join(_config_home(), 'sessions', '*.json')):
        try:
            with open(p, encoding='utf-8') as f:
                entry = json.load(f)
        except Exception:
            continue
        if not isinstance(entry, dict) or entry.get('sessionId') != session_id:
            continue
        if best is None or (entry.get('updatedAt') or 0) > (best.get('updatedAt') or 0):
            best = entry
    return best


def parse(raw: dict) -> CrossSessionNameData:
    session_id = raw.get('session_id') or ''
    entry = _find_entry(session_id) if session_id else None
    if entry is None:
        return CrossSessionNameData(name='', ref='')
    # ListAgents와 같은 규칙: name이 비면 cwd 폴더 이름
    name = entry.get('name') or os.path.basename(entry.get('cwd') or '')
    sock = entry.get('messagingSocketPath') or ''
    return CrossSessionNameData(name=name, ref=_ref(sock) if sock else '')


def render(data: CrossSessionNameData, palette, style) -> str:
    if not data.name:
        return PLACEHOLDER
    ref = f' {palette.dim}[{data.ref}]{palette.reset}' if data.ref else ''
    return f'Ⓜ️ {palette.accent}{data.name}{palette.reset}{ref}'
