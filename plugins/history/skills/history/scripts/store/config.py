"""사용자 설정 파일의 읽기·쓰기와 검증.

`~/.claude/history/config.json` 하나가 테마와 패널 폭을 담는다. 프로젝트의 `.history/`는
언제 지워도 다시 생기는 산출물이지만 이 파일은 사용자가 정한 값이라 자리가 다르다.

**사람이 손으로 고칠 수 있는 파일이므로 읽는 쪽이 무엇이든 받을 수 있다고 가정한다.**
검증은 키 단위로 하고, 한 값이 틀렸다고 나머지를 버리지 않는다.

**이 파일은 프로젝트마다 갈리지 않는다.** 프로젝트를 여럿 열면 서버도 여럿이고 그것들이
같은 파일에 쓴다. 그래서 쓰기가 원자적 교체이고 읽기가 실패를 구별한다 — 근거는
`docs/dev-plans/20-viewer/050-user-config.md`가 갖는다.
"""
import json
import os
import time

from common.paths import USER_CONFIG_DIR, USER_CONFIG_FILE

THEME_VALUES = ("system", "light", "dark")

# 읽기와 교체가 일시적으로 막혔을 때 다시 시도하는 횟수와 간격. 교체는 마이크로초 단위라
# 한 번 비켜 주면 대개 통한다. 창을 넓히는 대신 짧게 여러 번 두는 것은 `live_server()`의
# health 판정과 같은 판단이다
RETRIES = 5
RETRY_WAIT = 0.004

# 「파일이 없다」와 「열 수 없었다」를 가르는 표식. 앞은 정상이고 뒤는 병합 근거가 없다는
# 뜻이므로, 둘을 같은 값으로 돌려주면 쓰는 쪽이 그 차이를 볼 수 없다
_UNREADABLE = object()

# 뷰어의 드래그 하한과 같은 값이다(`00-app.js`의 PANE_MIN). 상한은 뷰어가 화면 폭의
# 비율로 자르므로 여기서 같은 수를 쓸 수 없다 — 손으로 적어 넣은 터무니없는 값만 거른다
PANE_MIN = 180
PANE_MAX = 4000

DEFAULTS = {
    "theme": "system",
    "paneWidth": 340,
}


def _valid_theme(value: object) -> bool:
    return value in THEME_VALUES


def _valid_pane_width(value: object) -> bool:
    # bool은 int의 하위 형이라 True가 1로 통과한다. 명시적으로 막는다
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return PANE_MIN <= value <= PANE_MAX


_VALIDATORS = {
    "theme": _valid_theme,
    "paneWidth": _valid_pane_width,
}


def sanitize(raw: object) -> dict:
    """검증을 통과한 키만 남긴다.

    객체가 아니면 빈 dict다. 모르는 키와 규약을 벗어난 값은 **그 키만** 버린다.
    """
    if not isinstance(raw, dict):
        return {}
    return {
        key: value
        for key, value in raw.items()
        if key in _VALIDATORS and _VALIDATORS[key](value)
    }


def _read_raw() -> str | None | object:
    """설정 파일의 텍스트. 없으면 `None`, 끝까지 열 수 없으면 `_UNREADABLE`.

    **셋을 가른다.** 「없다」는 정상이고 「열 수 없다」는 다른 프로세스가 그 순간 교체
    중이라는 뜻이다 — Windows에서 `os.replace`는 대상이 열려 있으면 실패하고, 그 충돌이
    읽는 쪽에 `PermissionError`로 나타난다.

    한 번의 실패를 결론으로 삼지 않는다. 교체는 순간이므로 잠깐 뒤에는 읽힌다.
    """
    for attempt in range(RETRIES):
        try:
            return USER_CONFIG_FILE.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError:
            if attempt < RETRIES - 1:
                time.sleep(RETRY_WAIT)
    return _UNREADABLE


def _parse(raw: str) -> dict:
    """텍스트를 검증된 dict로. JSON이 아니면 빈 dict다.

    여기까지 온 깨진 JSON은 **사람이 손으로 깨뜨린 것**이다. 쓰는 중이라 순간적으로 깨진
    파일은 원자적 교체 덕에 읽는 쪽에 보이지 않는다.
    """
    try:
        return sanitize(json.loads(raw))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def load_config() -> dict:
    """설정 파일을 읽어 검증을 통과한 키만 돌려준다.

    파일이 없거나 JSON이 아니거나 끝까지 열 수 없으면 빈 dict다. **조회는 화면을 막지
    않는 쪽이 옳다** — 기본값으로 열리는 것이 열리지 않는 것보다 낫다.

    **읽기는 디스크를 바꾸지 않는다** — 디렉토리를 만들면 `/history`를 한 번도 쓰지 않은
    홈에 빈 폴더가 생긴다.
    """
    raw = _read_raw()
    if raw is None or raw is _UNREADABLE:
        return {}
    return _parse(raw)


def _replace_with(text: str) -> bool:
    """임시파일에 완성한 뒤 원자적으로 교체한다. 교체했으면 True.

    대상 파일에 직접 쓰지 않는다 — `write_text`는 여는 순간 그것을 0바이트로 자르고,
    그 구간에서 읽는 쪽이 깨진 JSON을 본다(실측 6.5%).

    **임시파일 이름에 pid를 붙인다.** 고정 이름이면 두 프로세스가 같은 임시파일에 써서
    그것이 찢어지고, 원자적 교체가 찢어진 내용을 옮긴다.

    같은 디렉토리에 둔다. `os.replace`는 볼륨을 넘으면 원자성을 잃고 Windows에서는
    예외가 난다.

    `finally`가 임시파일을 반드시 지운다. 교체가 성공하면 이미 없고, 실패했으면 그것이
    쓰레기로 남는다.
    """
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = USER_CONFIG_DIR / f".config.{os.getpid()}.tmp"
    for attempt in range(RETRIES):
        try:
            tmp.write_text(text, encoding="utf-8")
            os.replace(tmp, USER_CONFIG_FILE)
            return True
        except OSError:
            if attempt < RETRIES - 1:
                time.sleep(RETRY_WAIT)
        finally:
            tmp.unlink(missing_ok=True)
    return False


def save_config(patch: dict) -> dict | None:
    """검증을 통과한 키만 기존 값에 병합해 쓰고 병합 결과를 돌려준다.

    부분 갱신인 이유는 값이 둘 이상이기 때문이다. 화면이 전체를 보내면 자기가 모르는 키까지
    실어 보내게 되고, 나중에 키가 늘면 옛 화면이 그것을 지운다.

    **읽지 못했으면 쓰지 않고 `None`을 돌려준다.** 그 상태에서 쓰면 병합 근거가 없어
    `{**{}, **patch}`가 되고, patch에 없는 키가 디스크에서 사라진다. 저장 하나를 잃는 것과
    남의 설정을 지우는 것은 대가가 다르다 — 앞은 사용자가 다시 누르면 되고 뒤는 굳는다.

    Returns:
        dict | None: 병합 결과. 읽지 못했거나 교체하지 못했으면 `None`
    """
    raw = _read_raw()
    if raw is _UNREADABLE:
        return None
    merged = {**({} if raw is None else _parse(raw)), **sanitize(patch)}
    if not _replace_with(json.dumps(merged, ensure_ascii=False, indent=2) + "\n"):
        return None
    return merged


def reset_config() -> None:
    """설정 파일을 지운다. 없으면 아무 일도 하지 않는다.

    기본값을 써 넣는 쪽을 쓰지 않는다. 그러면 파일에 남은 값이 사용자가 고른 것인지
    초기화가 남긴 것인지 구별되지 않고, 나중에 기본값을 바꿀 때 그 파일이 옛 기본값을
    사용자 선택으로 붙잡는다. **파일이 없는 상태가 곧 "정한 것이 없다"이다.**

    디렉토리는 남긴다 — 지울 이유가 없고 다음 저장이 어차피 다시 만든다.
    """
    USER_CONFIG_FILE.unlink(missing_ok=True)


def with_defaults(config: dict) -> dict:
    """빠진 키를 기본값으로 채운다. 화면에 심을 값을 만드는 자리다."""
    return {**DEFAULTS, **config}
