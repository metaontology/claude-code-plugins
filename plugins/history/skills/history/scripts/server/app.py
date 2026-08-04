"""로컬 뷰어 서버의 기동·중복 실행 판별·라우팅·접근 경계.

표준 라이브러리만 쓴다. 기존 스킬이 외부 패키지를 하나도 쓰지 않는 성질을 유지한다.

이 서버가 서빙하는 것은 사용자의 전체 대화 기록이므로 접근 경계가 선택이 아니다 —
`127.0.0.1` 바인딩 · 토큰 검증 · CORS 헤더 없음 · 정적 경로 열거 없음.
"""
import atexit
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# `app.py`는 `python -m`으로 실행되지 않으므로 자기 부모 디렉토리를 import 경로에 넣는다.
# 실행 위치에 기대지 않는 쪽이 `/history`가 어디서 호출되어도 같게 동작한다.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from server.api import (  # noqa: E402
    handle_auto_memory_discard, handle_config_reset, handle_config_save,
    handle_session_rename, handle_sessions_delete)
from server.lifecycle import Lifecycle  # noqa: E402
from server.live import session_for_pid  # noqa: E402
from store.layout import ensure_dirs, index_path, server_file  # noqa: E402
from viewer.render import attach_rebuild, recorded_ids, refresh  # noqa: E402

HOST = "127.0.0.1"
# 고정 범위를 쓴다. 포트가 매 실행마다 달라지면 방화벽 예외와 브라우저 사이트 설정이
# 매번 새 오리진에 걸린다
PORT_START = 7391
PORT_COUNT = 20
# bind에 넘기면 OS가 빈 포트를 골라 준다. 후보가 전부 막혔을 때의 탈출구다
OS_ASSIGNED = 0
# stale 판별용. 살아 있는 서버는 즉시 답한다
HEALTH_TIMEOUT = 0.5
# 살아 있는지 판정할 때 찌르는 횟수. 한 번의 실패를 사망으로 읽지 않는다
HEALTH_ATTEMPTS = 2
# 부모가 자식의 기동을 기다리는 한계
STARTUP_TIMEOUT = 5.0
# 자기 자신을 서버로 재실행하기 위한 내부 인자. 사용자용 명령이 아니다
SERVE_FLAG = "--serve"


def read_server_info(project_root: Path) -> dict:
    """`.server`를 dict로 읽는다. 없거나 JSON이 깨졌으면 빈 dict."""
    path = server_file(project_root)
    if not path.exists():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def write_server_info(project_root: Path, info: dict) -> None:
    """`.server`에 서버 정보를 기록한다. 디렉토리를 먼저 확보한다."""
    ensure_dirs(project_root)
    server_file(project_root).write_text(
        json.dumps(info, ensure_ascii=False), encoding="utf-8"
    )


def window_pid() -> int:
    """`/history`를 실행한 Claude Code 창의 pid. 알 수 없으면 0.

    `CLAUDE_PID`는 Claude Code가 자식에게 물려주는 값이고 **문서화된 인터페이스가 아니다.**
    없거나 정수가 아니면 0을 돌려주고, 그때 현재 세션은 `.server`의 세션 UUID로 떨어진다.

    부모 프로세스 체인을 올라가지 않는다. 그러려면 Windows는 프로세스 스냅샷을, Linux는
    `/proc`을, macOS는 그 둘 다 아닌 것을 봐야 한다 — 이 스킬의 OS 분기는 전부
    `os.name == "nt"` 이분법인데 거기서 처음으로 삼분법이 생긴다. 환경변수 하나가 세
    OS에서 같은 한 줄이다.

    `main.py`가 아니라 여기 있는 이유는 그 파일에 테스트가 없기 때문이다. 검증할 수 없는
    자리에 판정을 두면 그것이 조용히 틀려도 아무것도 깨지지 않는다.

    Returns:
        int: 창의 pid. 알 수 없으면 0
    """
    raw = os.environ.get("CLAUDE_PID", "")
    return int(raw) if raw.isdigit() else 0


def _session_fields(session_id: str, pid: int) -> dict:
    """`.server`에 담는 현재 세션 두 필드.

    세션 UUID와 **그것을 보고 있는 창의 pid**를 함께 적는다. UUID만으로는 `/resume` 뒤에
    그 창을 되찾을 수 없다 — 그때 UUID는 이미 다른 것으로 갈렸다.

    같은 파일의 `pid`는 서버 프로세스의 것이므로 이름을 갈라 둔다.

    Args:
        session_id (str): `/history`를 실행한 세션 UUID
        pid (int): 그 창의 pid. 알 수 없으면 0

    Returns:
        dict: `session_id`·`session_pid` 두 키
    """
    return {"session_id": session_id, "session_pid": pid}


def release_server_file(project_root: Path, pid: int) -> None:
    """`.server`가 `pid`의 것일 때만 지운다.

    파일은 프로젝트당 하나인데 종료 훅은 프로세스마다 걸린다. 내용을 보지 않고 지우면
    서버가 둘 떠 있을 때 **먼저 죽는 쪽이 살아 있는 쪽의 파일을 가져간다.** 그러면 다음
    `/history`가 그 서버를 찾지 못해 하나를 더 띄운다.

    소유자를 읽을 수 없으면 남긴다. 판정 불가는 "남의 것이 아니다"의 증거가 되지 못하고,
    남겨서 생기는 최악은 stale 파일 하나인데 그것은 `live_server()`가 이미 건다.

    여기서 읽는 `pid`는 **이 파일이 내 것인가**의 표식이지 생존 판정이 아니다. pid는
    재사용되므로 그쪽 용도로 쓰면 health로 판정한다는 `live_server()`의 성질이 무너진다.

    Args:
        project_root (Path): 프로젝트 루트
        pid (int): 지우려는 프로세스의 pid
    """
    if read_server_info(project_root).get("pid") != pid:
        return
    server_file(project_root).unlink(missing_ok=True)


def probe_health(port: int, token: str) -> dict | None:
    """`/api/health`를 찔러 응답 dict를 돌려준다. 응답이 없거나 403이면 None."""
    url = f"http://{HOST}:{port}/api/health?t={token}"
    try:
        with urllib.request.urlopen(url, timeout=HEALTH_TIMEOUT) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError):
        return None


def live_server(project_root: Path) -> dict | None:
    """살아 있고 이 프로젝트를 서빙하는 서버의 info. 없으면 None.

    `.server`가 존재한다는 사실은 서버가 살아 있다는 증거가 되지 못한다 — 프로세스가
    강제 종료되면 파일만 남는다. 따라서 파일은 어디를 찔러볼지 알려주는 힌트로만 쓰고
    판별은 health 응답으로 한다. pid로 판별하지 않는다 — pid는 재사용된다.

    **한 번의 실패를 사망으로 읽지 않는다.** 오판의 대가가 대칭이 아니다 — 죽은 서버를
    산 것으로 보면 다음 요청이 실패하고 끝이지만, 산 서버를 죽은 것으로 보면 여기서
    새 서버가 뜨고 사용자는 탭 두 개가 서로 다른 서버를 보는 상태를 만난다.

    대가는 stale 판정 비용이다. **닫힌 루프백 포트가 거부로 답한다고 가정하지 않는다** —
    이 환경은 SYN을 버리므로 실패가 곧 시간 초과이고, 판정이 `HEALTH_TIMEOUT` × 시도 횟수를
    다 쓴다. 다만 정상 종료는 `.server`를 지우고 가므로 stale 파일은 강제 종료·재부팅 뒤에만
    남고, 파일이 아예 없는 흔한 경우는 찌르기 전에 끝난다.

    `HEALTH_TIMEOUT`을 늘리는 쪽은 쓰지 않는다. 창 하나를 넓히면 **지속적으로 느린** 응답까지
    덮지만 stale 비용도 같은 만큼 늘고, 그 실패 모드는 아직 관측된 적이 없다. 짧은 창을 두 번
    두는 쪽이 일시적 실패를 덮으면서 각 창을 짧게 유지한다.

    재시도를 `probe_health`에 넣지 않는다. 그 함수는 `ensure_server`의 기동 대기 루프도
    쓰는데, 그쪽은 자식이 뜨기 전까지 실패를 **기대하며** 짧은 간격으로 도는 자리다.
    """
    info = read_server_info(project_root)
    # 기동 실패를 기록한 파일은 살아 있는 서버를 가리키지 않는다
    if not info or "error" in info:
        return None
    port, token = info.get("port"), info.get("token")
    if not isinstance(port, int) or not isinstance(token, str):
        return None
    for _ in range(HEALTH_ATTEMPTS):
        health = probe_health(port, token)
        # 답이 왔으면 그것으로 결론이다. 루트가 다른 것은 다시 찔러도 달라지지 않는다
        if health:
            return info if health.get("root") == str(project_root) else None
    return None


def bind_port() -> tuple[socket.socket, int]:
    """후보 포트를 순서대로 실제 바인딩해 성공한 소켓과 포트를 돌려준다.

    후보가 전부 실패하면 **OS가 고르는 포트로 폴백한다.** 고정 오리진을 잃는 것보다
    스킬이 아예 뜨지 못하는 편이 나쁘다.

    "비어 있는지 먼저 확인하고 나서 연다"로 나누지 않는다 — 그 사이에 다른 프로세스가
    포트를 가져가는 경합이 생긴다.

    Raises:
        OSError: 후보와 OS 할당이 모두 실패했다
    """
    last_error: OSError | None = None
    for port in [*range(PORT_START, PORT_START + PORT_COUNT), OS_ASSIGNED]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Windows에서 SO_REUSEADDR는 POSIX와 뜻이 다르다 — 이미 다른 프로세스가 바인딩한
        # 주소에도 바인딩이 성공한다. 그러면 포트 탐색이 점유를 감지하지 못하고 두 서버가
        # 같은 포트에 붙는다. POSIX에서는 TIME_WAIT 재바인딩에 필요하므로 그쪽만 켠다
        if os.name != "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((HOST, port))
            sock.listen(5)
            # 폴백으로 왔으면 요청한 0이 아니라 OS가 배정한 번호를 써야 한다
            return sock, sock.getsockname()[1]
        except OSError as exc:
            last_error = exc
            sock.close()
    last = PORT_START + PORT_COUNT - 1
    # 사유를 그대로 붙인다. "점유"라고 단정하면 점유가 아닌 실패(OS의 포트 예약 등)에서
    # 없는 프로세스를 찾게 된다
    raise OSError(
        f"후보 포트 {PORT_START}~{last}도 OS 할당도 실패했습니다: {last_error}"
    )


def viewer_url(info: dict) -> str:
    """뷰어를 여는 URL. 토큰이 쿼리로 붙는다 — 사용자는 이 값을 보지 않는다."""
    return f"http://{HOST}:{info['port']}/?t={info['token']}"


class Handler(BaseHTTPRequestHandler):
    """요청 핸들러. 경로를 보기 전에 토큰을 검사한다.

    `project_root`와 `token`은 서버 객체에서 읽는다. 클래스를 인자로 감싸 만들면
    뒤따르는 문서가 이 클래스를 확장하기 어려워진다.
    """

    # 브라우저에 노출되는 서버 이름을 줄인다
    server_version = "history"
    sys_version = ""

    def do_GET(self) -> None:
        """GET 라우팅. 토큰 검증을 통과한 요청만 분기에 닿는다."""
        parsed = self._authorized()
        if parsed is None:
            return
        if parsed.path == "/":
            self._serve_index()
        elif parsed.path == "/api/health":
            # health는 곧 연결이 온다는 예고다. 예약된 종료를 취소한다
            self.server.lifecycle.touch()
            self._send_json(200, self._health())
        elif parsed.path == "/api/live":
            self.server.lifecycle.stream(self)
        else:
            self._send_empty(404)

    def do_POST(self) -> None:
        """POST 라우팅. 처리는 `api.py`에 넘긴다."""
        # 응답 전에 본문을 반드시 읽는다. 읽지 않고 응답하면 클라이언트가 남은 본문을
        # 보내는 동안 연결이 끊겨(Windows에서 WinError 10053) 응답이 전달되지 않는다
        body = self._read_body()
        parsed = self._authorized()
        if parsed is None:
            return
        handler = _POST_ROUTES.get(parsed.path)
        if handler is None:
            self._send_empty(404)
            return
        status, payload = handler(self.server, body)
        self._send_json(status, payload)

    def _read_body(self) -> bytes:
        """요청 본문을 끝까지 읽어 돌려준다. 본문이 없으면 빈 바이트열."""
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length > 0 else b""

    def log_message(self, fmt: str, *args) -> None:
        """접근 로그를 남기지 않는다. 자식의 출력은 어디로도 가지 않는다."""

    # ── 접근 경계 ──────────────────────────────────────────────────────────

    def _authorized(self):
        """토큰을 검증한다. 통과하면 파싱된 URL, 실패하면 403을 보내고 None.

        경로를 가리지 않는다. `/api/health`도 예외가 아니다 — 중복 실행을 판별하는 쪽이
        `.server`에서 토큰을 읽을 수 있으므로 예외를 둘 이유가 없다. 예외를 하나라도
        두면 "그 경로는 무엇을 흘리는가"를 엔드포인트마다 판단해야 한다.
        """
        parsed = urlparse(self.path)
        given = parse_qs(parsed.query).get("t", [""])[0]
        if not secrets.compare_digest(given, self.server.token):
            # 본문에 사유를 담지 않는다
            self._send_empty(403)
            return None
        return parsed

    # ── 응답 ───────────────────────────────────────────────────────────────

    def _serve_index(self) -> None:
        """`.history/index.html` 하나만 서빙한다. 서빙 전에 갱신 판정을 거친다.

        요청 경로를 파일 경로로 바꾸는 코드를 두지 않는다. 경로 탈출 방어가 있어야 하는
        상황 자체를 만들지 않는 것이 `..` 필터보다 강하다.
        """
        self._rebuild_if_stale()
        path = index_path(self.server.project_root)
        if not path.exists():
            self._send_empty(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # 이 파일은 요청마다 새로 만들어질 수 있다. 브라우저가 캐시하면 위의 갱신이
        # 화면에 닿지 않는다. `Last-Modified`를 주는 쪽은 쓰지 않는다 — 그러면 조건부
        # 요청을 처리하는 코드가 필요해지고 얻는 것은 전송 절약뿐이다
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _rebuild_if_stale(self) -> None:
        """원본이 산출물보다 새로우면 다시 만든다. 판정은 `refresh`가 안에서 한다.

        **이 화면의 데이터는 생성 시점에 embed된다.** 그래서 재생성이 없으면 진행 중
        세션에 대화가 쌓여도 새로고침이 같은 화면을 다시 그린다 — 서버가 낡은 응답을
        주는 것이 아니라 파일이 그대로인 것이다.

        재생성 실패를 404나 500으로 바꾸지 않는다. 낡은 화면은 읽을 수 있고 빈 화면은
        읽을 수 없다. 실패 사유는 다음 `/history` 실행이 stderr로 보고한다.

        `rebuild=True`를 쓰지 않는다. 그것은 원본이 그대로인데 만드는 코드가 바뀐
        경우의 탈출구이고, 그 판단은 사용자가 `/history rebuild`로 내린다.
        """
        try:
            refresh(self.server.project_root, self.server.current_session_id())
        except (RuntimeError, OSError):
            pass

    def _health(self) -> dict:
        """health 응답. 루트를 담아 그 포트의 서버가 이 프로젝트의 것임을 증명한다."""
        return {"ok": True, "pid": os.getpid(), "root": str(self.server.project_root)}

    def _send_json(self, status: int, payload: dict) -> None:
        """JSON 응답. CORS 헤더를 붙이지 않는다."""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(self, status: int) -> None:
        """본문 없는 응답."""
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()


_POST_ROUTES = {
    "/api/sessions/delete": handle_sessions_delete,
    "/api/sessions/rename": handle_session_rename,
    "/api/auto-memory/discard": handle_auto_memory_discard,
    "/api/config": handle_config_save,
    "/api/config/reset": handle_config_reset,
}


class Server(ThreadingHTTPServer):
    """뷰어 서버. 핸들러가 읽을 상태를 갖는다."""

    # 이 속성이 없으면 열려 있는 요청 스레드가 끝날 때까지 프로세스가 매달린다.
    # 오래 열려 있는 스트리밍 연결이 종료를 무기한 막는다
    daemon_threads = True

    def __init__(self, sock: socket.socket, project_root: Path, token: str, **grace):
        # 이미 바인딩한 소켓을 물린다. 바인딩과 서버 생성을 나누면 그 사이에 포트를
        # 빼앗기는 경합이 생긴다
        super().__init__((HOST, 0), Handler, bind_and_activate=False)
        self.socket.close()
        self.socket = sock
        self.server_address = sock.getsockname()
        self.project_root = project_root
        self.token = token
        # 산출물 재생성 콜백. 뷰어 셸이 채운다. 없으면 재생성이 일어나지 않는다
        self.rebuild = None
        # 유예 시간은 테스트가 짧은 값으로 주입한다
        self.lifecycle = Lifecycle(self, **grace)

    def current_session_id(self) -> str:
        """이 창이 지금 보고 있는 세션 UUID.

        `.server`의 `session_pid`로 **레지스트리에 되묻는다.** 그 파일의 `session_id`를
        그대로 쓰지 않는 이유는 `/resume`이다 — 같은 창이 세션을 갈아타면 그 값은 이미
        그 창의 것이 아니고, 뷰어의 `현재`가 옛 세션에 남고 가드는 그 창이 쓰지 않는
        세션을 계속 보호한다. 창의 정체성은 pid이므로 pid를 붙잡아 요청마다 되묻는다.

        환경변수를 쓰지 않는다. 서버는 분리된 자식이고 환경변수를 기동 시점에 상속하므로
        그 값은 서버를 띄운 세션의 것으로 고정된다. 서버는 탭이 열려 있는 동안 재사용되니
        다음 세션에서 `/history`를 실행하면 가드가 낡은 세션을 보호하게 된다.

        요청 본문의 값을 쓰지 않는 이유는 그것이 가드의 근거를 요청자가 제공하는 값으로
        만들어 우회 방어를 없애기 때문이다.

        레지스트리에서 창을 찾지 못하면 `session_id`로 떨어진다. 그 원본은 문서화된
        인터페이스가 아니므로 사라질 수 있고, 그때 최악은 `/resume`을 따라가지 못하는
        것이어야 하며 가드가 없어지는 것이어서는 안 된다.
        """
        info = read_server_info(self.project_root)
        pid = info.get("session_pid")
        if isinstance(pid, int) and not isinstance(pid, bool):
            moved = session_for_pid(pid)
            if moved:
                return moved
        return info.get("session_id", "")

    def recorded_ids(self) -> list[str]:
        """기록이 남은 세션 UUID. 스트림이 화면에 밀어 보낸다.

        `rebuild`처럼 콜백으로 꽂지 않고 메서드로 둔다. 그쪽이 콜백인 이유는 부모가
        서버 객체에 닿지 못해 **자식 안에서** 꽂아야 하기 때문인데, 이 값은 세션 ID만
        있으면 나오고 그 세션 ID를 읽는 자리가 바로 위에 있다.
        """
        return recorded_ids(self.current_session_id())


def serve(project_root: Path, session_id: str = "", pid: int = 0) -> None:
    """자식 프로세스가 하는 일. 바인딩부터 `serve_forever`까지.

    기동에 실패하면 `.server`에 `error` 키만 기록하고 비정상 종료한다. 자식의 표준 출력은
    어디로도 가지 않으므로, 부모가 사유를 읽을 자리가 그 파일이다.
    """
    try:
        sock, port = bind_port()
    except OSError as exc:
        write_server_info(project_root, {"error": str(exc)})
        sys.exit(1)

    token = secrets.token_urlsafe(32)
    server = Server(sock, project_root, token)
    # 재생성 콜백은 자식 프로세스 안에서 꽂는다. 부모는 dict만 돌려받으므로 서버 객체에
    # 닿지 못하고, 함수를 인자로 넘길 수도 없다 — 자식은 새로 실행되는 별개 프로세스다
    attach_rebuild(server)
    write_server_info(project_root, {
        "pid": os.getpid(),
        "port": port,
        "token": token,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(project_root),
        # 현재 세션 가드가 읽는 값. 부모가 재사용할 때 이 둘만 갱신한다.
        # 창의 pid를 환경에서 직접 읽지 않고 인자로 받는다 — 그 값을 만드는 경로가
        # 부모와 자식으로 둘이 되면 어느 쪽이 옳은지가 새 판단거리가 된다
        **_session_fields(session_id, pid),
    })

    # 종료 경로가 여럿이므로(유예 만료·기동 유예·시그널) 파일 삭제를 한 곳에 모은다.
    # 각 경로에서 지우면 하나를 빠뜨리고, 남은 파일은 다음 실행에서 판정을 한 번 더 돌린다.
    # Windows는 SIGTERM 처리가 제한적이므로 시그널 핸들러에만 의존하지 않는다
    atexit.register(lambda: release_server_file(project_root, os.getpid()))
    for signal_name in ("SIGINT", "SIGTERM"):
        received = getattr(signal, signal_name, None)
        if received is not None:
            signal.signal(received, lambda *_: server.lifecycle.terminate())

    server.lifecycle.start()
    server.serve_forever()


def windowless_python(search: tuple[Path, ...] | None = None) -> str:
    """콘솔 창을 만들지 않는 인터프리터의 경로.

    `sys.executable`을 그대로 쓰면 서버를 띄울 때 **검은 콘솔 창이 하나 남는다.**
    그것은 콘솔 서브시스템 바이너리이고, uv로 설치한 환경에서는 실제 인터프리터도 아닌
    실행기(trampoline)라 창 제목이 실행기 경로가 된다.

    `pythonw.exe`는 GUI 서브시스템 바이너리다. Windows는 그런 프로세스에 콘솔을 배정하지
    않으므로 창이 생길 여지가 자체가 없다.

    찾는 순서는 **지금 인터프리터 옆 → `sys.base_prefix`**다. 앞쪽이 가상환경이고,
    뒤쪽은 앞이 실행기뿐일 때의 실체다. 뒤로 내려가면 가상환경의 `site-packages`를
    잃는데, 자식이 표준 라이브러리만 쓰므로 지금은 동작이 달라지지 않는다 —
    **서버가 서드파티 패키지를 쓰게 되면 이 폴백이 깨진다.**

    POSIX에는 `pythonw.exe`가 없으므로 저절로 `sys.executable`로 떨어진다. 그쪽에는
    콘솔 창이라는 개념이 없어 고칠 것도 없다.

    Args:
        search (tuple[Path, ...] | None): 탐색할 디렉토리. 없으면 기본 순서를 쓴다

    Returns:
        str: 자식으로 띄울 인터프리터 경로
    """
    if search is None:
        search = (Path(sys.executable).parent, Path(sys.base_prefix))
    for directory in search:
        candidate = directory / "pythonw.exe"
        if candidate.exists():
            return str(candidate)
    # 못 찾으면 창을 감수한다. 창이 하나 뜨는 것보다 서버가 아예 못 뜨는 편이 나쁘다
    return sys.executable


def _spawn(project_root: Path, session_id: str = "", pid: int = 0) -> None:
    """서버를 부모와 수명이 분리된 자식으로, 창 없이 띄운다.

    `/history`를 실행하는 것은 Claude Code다. 명령이 반환하지 않으면 도구 호출이 블록되고,
    그 호출의 타임아웃이 오면 사용자가 브라우저를 보고 있는 도중에 서버가 죽는다.

    Windows 플래그로 `DETACHED_PROCESS`를 쓰지 않는다. 그것은 **부모의 콘솔을 물려받지
    않는다**는 뜻일 뿐이라, 자식이 콘솔 앱이면 새 콘솔이 배정되어 창이 뜬다. 창을 막는
    플래그는 `CREATE_NO_WINDOW`이고, 그 둘을 함께 주면 Windows가 후자를 무시한다.

    수명 분리는 `CREATE_NO_WINDOW`로도 유지된다 — 자식이 부모의 콘솔이 아니라 자기
    콘솔(보이지 않는)을 가지므로 부모 쪽 콘솔이 닫혀도 종료 신호가 닿지 않는다.
    """
    command = [windowless_python(), str(Path(__file__).resolve()), SERVE_FLAG,
               str(project_root), session_id, str(pid)]
    kwargs = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)


def ensure_server(project_root: Path, session_id: str = "", pid: int = 0) -> dict:
    """서버를 확보한다 — 살아 있으면 재사용, 아니면 새로 띄운다.

    부모는 health 하나만 본다. 판정 지점이 둘이면 한쪽만 갱신된다.

    재사용할 때 `.server`의 현재 세션 두 필드를 지금 값으로 갱신한다. 서버는 요청마다 그
    파일을 다시 읽으므로, 이 갱신이 없으면 현재 세션 가드가 서버를 띄운 세션을 계속 보호한다.

    Raises:
        RuntimeError: STARTUP_TIMEOUT 안에 기동이 확인되지 않았다
    """
    alive = live_server(project_root)
    if alive:
        fields = _session_fields(session_id, pid)
        # 세션 UUID가 같아도 창이 다를 수 있다 — 두 창이 같은 세션을 열고 있으면 그렇다.
        # 둘을 함께 견주지 않으면 그때 갱신이 일어나지 않는다
        if any(alive.get(key) != value for key, value in fields.items()):
            alive.update(fields)
            write_server_info(project_root, alive)
        return alive

    # stale 파일을 지운다. 남겨 두면 다음 판별이 죽은 포트를 다시 찔러본다
    server_file(project_root).unlink(missing_ok=True)
    _spawn(project_root, session_id, pid)

    deadline = time.monotonic() + STARTUP_TIMEOUT
    while time.monotonic() < deadline:
        info = read_server_info(project_root)
        if "error" in info:
            server_file(project_root).unlink(missing_ok=True)
            raise RuntimeError(f"서버 기동 실패: {info['error']}")
        if info.get("port") and probe_health(info["port"], info["token"]):
            return info
        time.sleep(0.05)
    raise RuntimeError(f"서버가 {STARTUP_TIMEOUT}초 안에 응답하지 않았습니다")


def open_viewer(info: dict) -> None:
    """뷰어를 브라우저로 연다.

    부모가 연다 — 이래야 재사용 경로와 신규 기동 경로가 같은 코드로 URL을 조립한다.
    """
    webbrowser.open(viewer_url(info))


if __name__ == "__main__":
    # 인자는 뒤에서부터 생략할 수 있다. 부모는 늘 셋을 넘기지만, 손으로 실행해 볼 때
    # 세션 ID와 창 pid 없이도 서버가 뜨는 쪽이 낫다
    if len(sys.argv) in (3, 4, 5) and sys.argv[1] == SERVE_FLAG:
        given = sys.argv[3:]
        serve(Path(sys.argv[2]),
              given[0] if given else "",
              int(given[1]) if len(given) > 1 and given[1].isdigit() else 0)
    else:
        print(f"사용법: {Path(__file__).name} {SERVE_FLAG} {{프로젝트 루트}} "
              f"[{{세션 ID}} [{{창 pid}}]]", file=sys.stderr)
        sys.exit(2)
