"""레지스트리에 두 질문을 묻는다 — 무엇이 살아 있는가, 그리고 이 창이 무엇을 보고 있는가.

원본은 `~/.claude/sessions/{pid}.json`이다. 실행 중인 인스턴스마다 파일 하나가 있고,
그 안의 `sessionId`가 곧 세션 jsonl의 파일명이므로 목록의 행과 그대로 맞물린다.

`pid`는 생존 확인의 대상이면서 **창의 정체성**이다. `/resume`은 같은 pid 항목의
`sessionId`만 갈아 끼우므로, 창을 pid로 붙잡아 두면 그 창의 지금을 언제든 되물을 수 있다.

**문서화된 인터페이스가 아니다.** 디렉토리가 없거나 JSON이 깨졌거나 기대한 키가
사라져도 이 모듈은 빈 목록을 돌려주고 예외를 밖으로 내지 않는다. 판별이 실패했을 때의
최악은 "표시가 하나 사라진다"여야 하고 "스킬이 뜨지 않는다"여서는 안 된다.

파일의 존재는 생존의 증거가 되지 못한다 — 강제 종료된 인스턴스의 파일은 Claude Code가
주기적으로 청소할 때까지 남는다. 그래서 항목마다 pid의 생존을 직접 확인한다.
"""
import ctypes
import json
import os
from pathlib import Path

import common.paths as paths

# 아직 신호되지 않은 커널 객체에 WaitForSingleObject가 돌려주는 값. 프로세스 객체는
# 종료될 때 신호되므로, 시간 초과라는 것이 곧 아직 돌고 있다는 뜻이다
_WAIT_TIMEOUT = 0x102
# 프로세스 핸들을 여는 데 필요한 최소 권한. 종료·메모리 접근 권한을 요구하지 않는다
_SYNCHRONIZE = 0x00100000
# OpenProcess가 "그런 pid는 없다"라고 답하는 방식
_ERROR_INVALID_PARAMETER = 87

if os.name == "nt":
    import ctypes.wintypes as _wintypes

    _K32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # restype을 지정하지 않으면 ctypes가 반환값을 C int로 받아 64비트 핸들이 잘린다
    _K32.OpenProcess.argtypes = [_wintypes.DWORD, _wintypes.BOOL, _wintypes.DWORD]
    _K32.OpenProcess.restype = _wintypes.HANDLE
    _K32.WaitForSingleObject.argtypes = [_wintypes.HANDLE, _wintypes.DWORD]
    _K32.WaitForSingleObject.restype = _wintypes.DWORD
    _K32.CloseHandle.argtypes = [_wintypes.HANDLE]
    _K32.CloseHandle.restype = _wintypes.BOOL


def _alive_windows(pid: int) -> bool:
    """Windows에서 pid의 생존을 조회한다.

    **`os.kill(pid, 0)`을 쓰지 않는다.** CPython의 `os.kill`은 Windows에서
    `CTRL_C_EVENT`·`CTRL_BREAK_EVENT`가 아닌 모든 시그널에 대해 `TerminateProcess`를
    부른다. 즉 그 관용구는 조회가 아니라 종료이고, 대상은 사용자의 다른 세션이다.
    """
    handle = _K32.OpenProcess(_SYNCHRONIZE, False, pid)
    if not handle:
        # 열지 못한 이유가 "없는 pid"일 때만 죽었다고 단정한다. 권한 등 다른 사유는
        # 살아 있는 쪽으로 본다 — 산 세션을 지우는 오류가 반대쪽보다 훨씬 비싸다
        return ctypes.get_last_error() != _ERROR_INVALID_PARAMETER
    try:
        return _K32.WaitForSingleObject(handle, 0) == _WAIT_TIMEOUT
    finally:
        _K32.CloseHandle(handle)


def _alive_posix(pid: int) -> bool:
    """POSIX에서 pid의 생존을 조회한다. 여기서는 시그널 0이 실제로 조회다."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 내 것이 아닐 뿐 살아 있다
        return True
    except OSError:
        return True
    return True


def is_alive(pid: int) -> bool:
    """그 pid의 프로세스가 살아 있는가. 판정할 수 없으면 살아 있다고 본다."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    return _alive_windows(pid) if os.name == "nt" else _alive_posix(pid)


def _read_entry(path: Path) -> dict | None:
    """레지스트리 파일 하나를 항목으로 읽는다. 성립하지 않으면 None."""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict):
        return None
    session_id = loaded.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        return None
    if not is_alive(loaded.get("pid")):
        return None
    return loaded


def live_sessions() -> list[dict]:
    """레지스트리에서 살아 있는 항목만 골라 돌려준다. 항목은 원본 dict 그대로다."""
    try:
        files = sorted(paths.LIVE_SESSIONS_DIR.glob("*.json"))
    except OSError:
        return []
    found = [_read_entry(path) for path in files]
    return [entry for entry in found if entry is not None]


def session_for_pid(pid: int) -> str:
    """그 pid의 창이 지금 보고 있는 세션 UUID. 찾지 못하면 빈 문자열.

    `/resume`은 같은 pid 항목의 `sessionId`만 갈아 끼우므로, 이 조회가 곧 "그 창의 지금"이다.

    **반대 방향(세션 UUID로 창의 pid를 찾는 것)은 두지 않는다.** 여러 창이 같은 세션을
    열고 있으면 후보가 여럿이고, 그중 어느 것이 `/history`를 실행한 창인지 가릴 근거가
    레지스트리 안에 없다. 첫 후보를 고르면 절반의 확률로 옆 창을 추적한다 —
    모호한 근거는 없는 것보다 나쁘다. 내 창의 pid는 `app.window_pid()`가 환경에서 읽는다.

    Args:
        pid (int): 창의 pid

    Returns:
        str: 그 창이 보고 있는 세션 UUID. 없으면 빈 문자열
    """
    for entry in live_sessions():
        if entry.get("pid") == pid:
            return entry["sessionId"]
    return ""


def _same_dir(left: str, right: Path) -> bool:
    """두 경로가 같은 디렉토리를 가리키는가.

    문자열끼리 비교하지 않는다. 뒤에 붙은 구분자 하나로 같은 디렉토리가 다른 것이 된다.
    """
    try:
        return Path(left).resolve() == right
    except (OSError, ValueError):
        return False


def project_session_ids(project_root: Path) -> list[str]:
    """`project_root`의 살아 있는 창이 보고 있는 세션 UUID. **창 하나에 원소 하나.**

    정렬을 갖는 이유는 스트림이 이 값을 직전 값과 비교해 보낼지 정하기 때문이다.
    정렬이 없으면 디렉토리 열거 순서가 바뀔 때마다 변경으로 읽힌다.

    **중복을 접지 않는다.** 창 둘이 같은 세션을 열고 있으면 그 UUID가 두 번 담긴다.
    접으면 "이 세션을 몇 창이 열고 있는가"를 되살릴 방법이 없어지고, 창이 하나 붙거나
    떨어져도 값이 변하지 않아 스트림이 침묵한다. 접는 자리는 그 값을 쓰는 쪽에 둔다 —
    삭제 가드는 `set(...)`으로 감싼다. 그쪽이 묻는 것은 "살아 있는가" 하나여서 개수가
    답을 바꾸지 않는다.
    """
    try:
        root = Path(project_root).resolve()
    except (OSError, ValueError):
        return []
    found = [
        entry["sessionId"]
        for entry in live_sessions()
        if isinstance(entry.get("cwd"), str) and _same_dir(entry["cwd"], root)
    ]
    return sorted(found)
