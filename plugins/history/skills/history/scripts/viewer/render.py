"""뷰어 산출물 조립 — embed 페이로드 · 자산 인라인 · 갱신 판정 결합.

데이터를 런타임에 읽어오지 않고 생성 시점에 HTML 안에 넣는다. 그래야 `file://`로 열어도
화면이 비지 않고, 파일 하나만 복사해 다른 컴퓨터에서 열 수 있고, `data/`를 지워도
표시가 살아 있다.
"""
import json
import os
import platform
import re
from pathlib import Path

import common.paths as paths
# 상수는 모듈을 통해 참조한다. 이름을 바인딩해 가져오면 테스트가 `store.config`의 속성을
# 바꿔치기해도 이 파일은 옛 경로를 계속 본다
import store.config as user_config
from auto_memory.model import load_auto_memory, memory_dir
from common.jsonl import all_jsonls_in_slug, find_project_slug
from common.skills import local_skill_names
from session.model import session_list
from store.config import load_config, with_defaults
from store.layout import ensure_dirs, index_path, needs_rebuild

# CSS·JS를 파이썬 문자열 리터럴에 넣지 않는다. 문자열 안의 코드는 편집기의 문법 지원을
# 받지 못하고, 따옴표·중괄호 충돌을 사람이 관리하게 된다
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
SHELL_FILE = "shell.html"

# 데이터를 <script type="application/json"> 안에 넣으므로 본문에 이 문자열이 있으면
# 그 자리에서 블록이 닫히고 뒤가 HTML로 해석된다. HTML 파서는 대소문자를 가리지 않는다
_CLOSE_SCRIPT_RE = re.compile(r"</(script)", re.IGNORECASE)


def source_paths(slug: str) -> list[Path]:
    """산출물이 embed하는 원본 경로 전체를 돌려준다.

    슬러그의 jsonl 전부와 auto-memory의 `*.md`, 그리고 사용자 설정이다.
    인덱스(`MEMORY.md`)도 함께 담는다 — 항목 파일만 넘기면 사람이 인덱스만 고친 경우가
    갱신 판정에서 빠진다.

    **설정 파일이 여기 있어야 하는 이유는 그것도 embed되기 때문이다.** 빠지면 저장한
    테마가 새로고침에 반영되는지가 세션 jsonl의 mtime에 따라 우연히 갈린다.

    없는 파일은 담지 않는다. 판정이 `stat()`을 부르므로 존재하지 않는 경로가 들어가면
    거기서 깨진다. 그래서 **설정을 지우는 연산은 이 목록으로 감지되지 않고**, 그쪽은
    지우는 자리가 판정을 건너뛰고 재생성한다(`server/api.py`).
    """
    found = list(all_jsonls_in_slug(slug))
    directory = memory_dir(slug)
    if directory.exists():
        found.extend(sorted(directory.glob("*.md")))
    if user_config.USER_CONFIG_FILE.exists():
        found.append(user_config.USER_CONFIG_FILE)
    return found


def recorded_ids(session_id: str) -> list[str]:
    """기록이 남은 세션 UUID 전부. 사전순 정렬. 판정할 수 없으면 빈 목록.

    **산출물을 지금 다시 만들면 목록에 무엇이 설 수 있는가**에 답한다. 화면은 이 값을
    자기 embed 목록과 견줘 아직 담기지 않은 세션이 있는지 알고, 있으면 다시 열라고
    알린다. 값이 아니라 이름만 필요하므로 jsonl을 파싱하지 않는다.

    `live.project_session_ids`를 쓰지 않는다. 살아 있어도 jsonl이 아직 없는 세션이
    있고(첫 프롬프트 전), 그것으로 안내를 띄우면 **다시 만들어도 행이 서지 않아
    안내가 사라지지 않는다.** 두 목록은 답하는 물음이 다르다.

    정렬을 갖는 이유는 스트림이 이 값을 직전 값과 견줘 보낼지 정하기 때문이다 —
    `project_session_ids`와 같다.

    **예외를 내지 않는다.** 스트림이 틱마다 부르므로 실패가 곧 연결 종료가 되고,
    그러면 탭이 살아 있는데 서버가 종료 유예에 들어간다.
    """
    if not session_id:
        return []
    try:
        slug = find_project_slug(session_id)
    except OSError:
        return []
    if slug is None:
        return []
    return sorted(path.stem for path in all_jsonls_in_slug(slug))


def embed_payload(project_root: Path, slug: str, session_id: str) -> dict:
    """화면이 필요한 값 전부를 담은 dict. 화면은 서버에 조회하지 않는다.

    `current`가 뜻하는 것은 "지금 진행 중인 세션"이 아니라 "이 파일을 만든 세션"이다.
    두 진입 경로에서 같은 뜻이므로 `file://`로 옮겨 열어도 의미가 흔들리지 않는다.
    """
    return {
        "project": str(project_root),
        # 화면이 `{sessions_dir}/{세션ID}.jsonl`로 원본 경로를 조립한다. 슬러그만 담으면
        # 절대 경로를 만들 수 없다 — 홈 디렉토리 값이 브라우저에 없다
        "sessions_dir": str(paths.PROJECTS_DIR / slug),
        "current": session_id,
        "sessions": session_list(slug),
        "memory": load_auto_memory(slug),
        # 화면이 skill의 내장 여부를 가르는 근거. 브라우저는 디스크를 볼 수 없으므로
        # **조립하는 이 자리에서 훑어 담는다**
        "local_skills": local_skill_names(project_root),
        # "탐색기에서 보기" 버튼을 그릴지의 근거. 서버가 여는 수단(explorer·open)이
        # Windows·Mac뿐이라 그 밖에서는 화면이 버튼 자체를 그리지 않는다
        "reveal_supported": _reveal_supported(),
    }


def _reveal_supported() -> bool:
    """OS 탐색기를 여는 수단이 있는가. 함수로 떼어 둔 것은 테스트가 `os.name`을 바꿔도
    이 판정만 격리해 검증하기 위해서다 — `embed_payload` 전체를 부르면 `local_skill_names`가
    그 사이에 `Path`를 만들다 `os.name`과 실제 플랫폼의 불일치로 깨진다.
    """
    return os.name == "nt" or platform.system() == "Darwin"


def _assets(pattern: str) -> str:
    """`assets/`의 자산을 파일명 순서로 읽어 이어 붙인다.

    목록을 열거하지 않고 훑는 이유는, 뒤따르는 문서가 자산을 추가할 때 이 파일을 고치지
    않게 하는 것이다. 파일명 앞의 두 자리 숫자가 로드 순서다.
    """
    files = sorted(ASSETS_DIR.glob(pattern), key=lambda path: path.name)
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


def render_html(payload: dict) -> str:
    """셸에 자산과 데이터를 채워 완성된 HTML 문자열을 만든다.

    `str.format`을 쓰지 않는다 — CSS와 JS는 중괄호로 가득하므로 전부 이스케이프해야 하고,
    그 요구를 자산 파일 쪽에 두면 자산이 파이썬의 사정을 알게 된다.

    치환 순서가 `STYLE` → `SCRIPT` → `CONFIG` → `DATA`인 것은 데이터에 사용자의 대화 본문이
    들어 있기 때문이다. 거기에 `{{SCRIPT}}` 같은 문자열이 그대로 있을 수 있고, 데이터를 먼저
    넣으면 그것이 다음 치환에서 자산으로 바뀐다. `CONFIG`는 검증을 통과한 문자열과 정수뿐이라
    그런 문자열을 담지 못하므로 `DATA`보다 앞이어도 된다.

    설정을 `DATA`에 싣지 않는 이유는 위치다. 그 자리는 `<body>` 끝이고, 테마 부트는
    `<head>`에서 실행돼야 하므로 자기보다 뒤에 있는 값을 읽을 수 없다.
    """
    shell = (ASSETS_DIR / SHELL_FILE).read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False)
    data = _CLOSE_SCRIPT_RE.sub(r"<\\/\1", data)
    config = json.dumps(with_defaults(load_config()), ensure_ascii=False)
    return (
        shell
        .replace("{{STYLE}}", _assets("*.css"))
        .replace("{{SCRIPT}}", _assets("*.js"))
        .replace("{{CONFIG}}", config)
        .replace("{{DATA}}", data)
    )


def _require_slug(session_id: str) -> str:
    """세션이 속한 프로젝트 슬러그. 찾지 못하면 오류다.

    빈 산출물을 쓰지 않는다. 그 파일이 곧 캐시가 되는데 원본 목록이 비어 있으므로 다음
    판정이 "갱신 불필요"라고 답한다. 즉 빈 화면이 굳어 `rebuild` 없이는 벗어날 수 없다.
    """
    slug = find_project_slug(session_id)
    if slug is None:
        raise RuntimeError(
            f"세션 {session_id}의 프로젝트 디렉토리를 찾을 수 없습니다"
        )
    return slug


def _write(project_root: Path, slug: str, session_id: str) -> Path:
    """산출물을 쓰고 그 경로를 돌려준다. 디렉토리는 쓰기 직전에 확보한다."""
    html = render_html(embed_payload(project_root, slug, session_id))
    ensure_dirs(project_root)
    target = index_path(project_root)
    target.write_text(html, encoding="utf-8")
    return target


def build(project_root: Path, session_id: str) -> Path:
    """판정 없이 산출물을 만든다. 산출물 경로 반환.

    Raises:
        RuntimeError: 세션이 속한 프로젝트 디렉토리를 찾을 수 없다
    """
    return _write(project_root, _require_slug(session_id), session_id)


def refresh(project_root: Path, session_id: str, rebuild: bool = False) -> bool:
    """갱신 판정과 `rebuild`를 합쳐 필요할 때만 산출물을 만든다.

    `rebuild`는 사용자용 범위 옵션이 아니라 탈출구다 — 원본은 그대로인데 산출물을 만드는
    코드가 바뀐 경우(스킬 업데이트 직후) mtime 비교는 "갱신 불필요"라고 답한다.

    Returns:
        bool: 실제로 다시 만들었으면 True

    Raises:
        RuntimeError: 세션이 속한 프로젝트 디렉토리를 찾을 수 없다
    """
    slug = _require_slug(session_id)
    if not rebuild and not needs_rebuild(project_root, source_paths(slug)):
        return False
    _write(project_root, slug, session_id)
    return True


def attach_rebuild(server) -> None:
    """서버의 재생성 콜백을 채운다. 자식 프로세스 안에서 불린다.

    부모는 서버 객체에 닿지 못한다 — `ensure_server`는 dict만 돌려받고 서버는 별개
    프로세스에 있다. 따라서 이 함수를 부르는 자리는 자식이 실행하는 `serve()` 안이다.

    세션 ID를 인자로 굳히지 않고 호출 시점에 다시 읽는다. 서버는 탭이 열려 있는 동안
    재사용되고 그때 `.server`의 세션 ID가 갱신되므로, 굳히면 재사용된 서버가 낡은
    슬러그로 산출물을 만든다.
    """
    def rebuild() -> None:
        build(server.project_root, server.current_session_id())

    server.rebuild = rebuild
