"""history 스킬 진입점. CLAUDE_SESSION_ID와 argv로 명령을 해석한다.

사용법:
    python main.py              # 기록을 갱신하고 뷰어를 연다
    python main.py rebuild      # 갱신 판정을 무시하고 전 세션을 다시 만든 뒤 뷰어를 연다

명령은 이 둘뿐이다. `rebuild`는 CLI가 받는 유일한 인자이며, 자연어 표현(`refresh`,
`전체 갱신`, `다시 빌드` 등)을 이 토큰으로 바꾸는 일은 SKILL.md가 맡는다.
"""
import os
import sys
from pathlib import Path
from typing import NoReturn

from server.app import ensure_server, open_viewer, viewer_url, window_pid
from viewer.render import refresh

# CLI가 인식하는 유일한 인자. 별칭을 두지 않는다.
REBUILD = "rebuild"


def fail(message: str) -> NoReturn:
    """오류 메시지를 stderr에 쓰고 비정상 종료한다."""
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def parse_command(args: list[str]) -> bool:
    """argv 나머지를 rebuild 여부로 해석한다.

    Args:
        args (list[str]): `sys.argv[1:]`

    Returns:
        bool: `rebuild` 명령이면 True, 인자가 없으면 False

    Raises:
        SystemExit: 그 밖의 인자면 알 수 없는 명령으로 거부한다
    """
    if not args:
        return False
    if args == [REBUILD]:
        return True
    fail(f"알 수 없는 명령: {' '.join(args)}")


def run(session_id: str, rebuild: bool) -> None:
    """산출물을 갱신하고 서버를 확보한 뒤 뷰어를 연다.

    프로젝트 루트는 현재 작업 디렉토리다. 산출물이 그 아래 `.history/`에 생기므로
    프로젝트 루트에서 실행해야 한다.

    갱신이 서버 확보보다 앞인 이유는 서버가 `/`로 `index.html`을 서빙하는데 없으면
    404이기 때문이다. 브라우저가 열리기 전에 파일이 있어야 한다.

    `rebuild` bool과 갱신 판정을 `or`로 합치는 자리는 `refresh` 안이다. 원본 목록을
    만드는 것이 뷰어의 지식이므로 진입점이 판정 함수를 직접 부르지 않는다 — 그렇게 하면
    embed 축이 늘 때마다 진입점을 고쳐야 한다.

    Args:
        session_id (str): 현재 세션 UUID
        rebuild (bool): 갱신 판정을 무시하고 전량 재생성할지 여부
    """
    project_root = Path.cwd()
    try:
        refresh(project_root, session_id, rebuild)
        # 세션 ID와 **이 창의 pid**를 넘겨 `.server`에 기록·갱신한다. 서버는 그 pid로
        # 레지스트리에 되물어 창이 지금 보고 있는 세션을 안다 — `/resume`을 따라가는 근거다
        info = ensure_server(project_root, session_id, window_pid())
    except RuntimeError as exc:
        fail(str(exc))
    open_viewer(info)
    print(f"뷰어: {viewer_url(info)}")


def main() -> None:
    """환경변수와 argv를 확인한 뒤 명령을 실행한다."""
    # 출력을 UTF-8로 고정한다. Windows 기본값(cp949)으로 내보내면 이 스크립트를 호출하는
    # Claude Code가 한글 메시지를 깨진 바이트로 읽어 사용자에게 전달할 수 없다.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    if not session_id:
        fail("CLAUDE_SESSION_ID가 설정되지 않았습니다. 현재 세션을 특정할 수 없습니다.")

    run(session_id, rebuild=parse_command(sys.argv[1:]))


if __name__ == "__main__":
    main()
