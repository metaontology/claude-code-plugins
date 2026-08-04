"""서버가 언제 죽는가, 그리고 살아 있는 연결에 무엇을 쓰는가.

수명 계약은 한 문장이다 — **열려 있는 탭이 하나라도 있으면 살아 있고, 마지막 탭이 닫히면
곧 종료된다.** 탭 추적은 폴링이 아니라 SSE 연결 하나로 한다. 브라우저가 백그라운드 탭의
타이머를 1분에 1회로 스로틀링하므로, 타이머에 기대면 살아 있는 탭을 죽은 것으로 오판한다.

유휴 시간 초과로 종료하지 않는다. 탭이 열려 있는 한 사용자가 보고 있는 것이다.

그 연결에 세션 목록 둘도 함께 실어 보낸다 — 지금 살아 있는 것과 기록이 남은 것. 무엇이
그에 해당하는지는 `server.live`와 `viewer.render`가 알고, 이 모듈은 **그 연결에 쓰는
자리가 하나뿐이라는 것**만 지킨다 — 폴링 스레드를 따로 두고 같은 소켓에 쓰면 코멘트와
이벤트가 섞여 SSE 프레임이 깨진다.
"""
import json
import select
import socket
import threading
import time

from server.live import project_session_ids

# 마지막 연결이 끊긴 뒤 기다리는 시간. 새로고침은 `끊김 → 즉시 재연결`이므로 유예가 없으면
# 새로고침 한 번에 서버가 죽는다
SHUTDOWN_GRACE = 5.0
# 기동 후 첫 연결을 기다리는 시간. 브라우저가 아예 열리지 않은 고아 프로세스를 없앤다
STARTUP_GRACE = 30.0
# SSE 코멘트 간격. 중간 계층의 유휴 연결 차단을 막는다
PING_INTERVAL = 15.0
# 살아 있는 세션 목록을 다시 읽는 간격. 코멘트 간격과 갈라 둔다 — 코멘트는 중간 계층을
# 달래는 값이라 짧을 이유가 없고, 이쪽은 사용자가 체감하는 반영 지연이라 15초면 늦다
POLL_INTERVAL = 2.0

# SSE 코멘트. 이벤트가 아니므로 클라이언트에 핸들러가 필요 없다
_PING = b": ping\n\n"

# 이 연결에 흐르는 이름 있는 이벤트 — 이름과 그 값을 서버에서 읽는 법.
# 표로 두므로 이벤트가 늘어도 `_pump`의 루프는 그대로다
_STREAMS = (
    ("live", lambda server: project_session_ids(server.project_root)),
    ("known", lambda server: server.recorded_ids()),
)


def _event(name: str, session_ids: list[str]) -> bytes:
    """세션 목록을 이름 있는 SSE 이벤트로 만든다."""
    return f"event: {name}\ndata: {json.dumps(session_ids)}\n\n".encode("utf-8")


class Lifecycle:
    """연결 수와 종료 타이머를 갖는다. 서버 객체가 하나를 소유한다."""

    def __init__(self, server, shutdown_grace: float = SHUTDOWN_GRACE,
                 startup_grace: float = STARTUP_GRACE,
                 ping_interval: float = PING_INTERVAL,
                 poll_interval: float = POLL_INTERVAL):
        self._server = server
        self._shutdown_grace = shutdown_grace
        self._startup_grace = startup_grace
        self._ping_interval = ping_interval
        self._poll_interval = poll_interval
        # 핸들러가 스레드마다 돌므로 증감을 락으로 보호한다. 카운트가 어긋나면 서버가
        # 영원히 살거나 살아 있는 채로 죽는다
        self._lock = threading.Lock()
        self.connections = 0
        self._timer: threading.Timer | None = None

    # ── 예약 ───────────────────────────────────────────────────────────────

    def start(self) -> None:
        """기동 유예를 예약한다."""
        self._arm(self._startup_grace)

    def touch(self) -> None:
        """예약된 종료를 취소하고 기동 유예를 다시 시작한다.

        health 요청 경로다. 부모가 health를 찌르는 유일한 이유가 이 서버를 쓸지 결정하는
        것이므로, 그 요청은 사실상 "곧 연결이 온다"는 예고다. 이것이 없으면 종료 유예
        중에 재사용된 서버가 브라우저 콜드 스타트 도중에 죽는다.
        """
        self._arm(self._startup_grace)

    def _arm(self, delay: float) -> None:
        """종료 타이머를 다시 건다. 기존 예약은 반드시 취소한다."""
        with self._lock:
            self._cancel_locked()
            self._timer = threading.Timer(delay, self._expire)
            self._timer.daemon = True
            self._timer.start()

    def _cancel_locked(self) -> None:
        """예약을 취소한다. 호출자가 락을 갖고 있어야 한다.

        취소하지 않으면 `연결 → 끊김 → 연결`이 반복될 때 예약이 쌓이고, 먼저 예약된
        타이머가 살아 있는 연결을 무시하고 서버를 죽인다.
        """
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _expire(self) -> None:
        """유예가 만료됐다. 카운트를 다시 확인하는 것이 마지막 방어선이다."""
        with self._lock:
            if self.connections > 0:
                return
        self.terminate()

    # ── 연결 ───────────────────────────────────────────────────────────────

    def stream(self, handler) -> None:
        """SSE 응답을 열고 연결이 끊길 때까지 유지한다.

        카운트 증감을 이 함수가 함께 갖는다 — 증가와 감소가 같은 `try/finally`에 있어야
        예외 경로에서 카운트가 새지 않는다. 새면 서버가 영원히 살아남는다.
        """
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("X-Accel-Buffering", "no")
        handler.end_headers()

        self._opened()
        try:
            self._pump(handler)
        except (OSError, ValueError):
            # 끊긴 연결에 쓰면 여기로 온다. 정상 종료 경로다
            pass
        finally:
            self._closed()

    def _pump(self, handler) -> None:
        """끊길 때까지 코멘트와 두 세션 목록을 쓴다.

        `sleep`으로 기다리지 않는다 — 그러면 그 사이에 탭이 닫혀도 다음 쓰기까지 모른다.
        `select`로 소켓을 감시하면 클라이언트가 닫는 순간 읽기 가능이 되어 그 자리에서
        끊김을 안다. SSE는 클라이언트가 아무것도 보내지 않으므로 읽기 가능은 곧 종료다.

        각 목록은 **직전에 보낸 것과 다를 때만** 보낸다. 매 틱 보내면 화면이 아무것도
        변하지 않았는데 계속 다시 그려진다. `sent`가 비어 시작하는 덕에 접속 직후 한 번은
        반드시 나간다 — 빈 목록도 사실이므로 알려야 한다.
        """
        connection = handler.connection
        sent: dict[str, list[str]] = {}
        next_ping = 0.0
        while True:
            now = time.monotonic()
            if now >= next_ping:
                handler.wfile.write(_PING)
                next_ping = now + self._ping_interval
            for name, read in _STREAMS:
                current = read(self._server)
                if name not in sent or current != sent[name]:
                    handler.wfile.write(_event(name, current))
                    sent[name] = current
            handler.wfile.flush()
            ready, _, _ = select.select([connection], [], [], self._poll_interval)
            if ready and not connection.recv(1, socket.MSG_PEEK):
                return

    def _opened(self) -> None:
        """연결이 열렸다. 예약된 종료를 취소한다."""
        with self._lock:
            self.connections += 1
            self._cancel_locked()

    def _closed(self) -> None:
        """연결이 닫혔다. 마지막 연결이었으면 종료 유예를 예약한다."""
        with self._lock:
            self.connections -= 1
            remaining = self.connections
        if remaining <= 0:
            self._arm(self._shutdown_grace)

    # ── 종료 ───────────────────────────────────────────────────────────────

    def terminate(self) -> None:
        """서버를 종료한다.

        `shutdown()`은 `serve_forever` 루프가 끝나기를 기다린다. 요청 핸들러 스레드가 그
        루프에 속하므로 핸들러 안에서 직접 부르면 자기가 끝나기를 기다리며 멈춘다.
        따라서 항상 별도 스레드에서 부른다.
        """
        with self._lock:
            self._cancel_locked()
        threading.Thread(target=self._server.shutdown, daemon=True).start()
