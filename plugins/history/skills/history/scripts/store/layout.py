"""`.history/` 산출물의 경로와 갱신 판정.

산출물이 디스크에 어떻게 존재하는가를 정한다. 경로 계산에는 부작용이 없고,
디렉토리는 쓰기 직전에 `ensure_dirs`로 확보한다.
"""
from pathlib import Path


def history_dir(project_root: Path) -> Path:
    """프로젝트 루트 아래 산출물 디렉토리 경로 반환."""
    return project_root / ".history"


def data_dir(project_root: Path) -> Path:
    """런타임 파일을 두는 디렉토리 경로 반환."""
    return history_dir(project_root) / "data"


def index_path(project_root: Path) -> Path:
    """뷰어 HTML 경로 반환."""
    return history_dir(project_root) / "index.html"


def server_file(project_root: Path) -> Path:
    """서버 런타임 파일 경로 반환."""
    return data_dir(project_root) / ".server"


def ensure_dirs(project_root: Path) -> None:
    """산출물 디렉토리를 확보한다. 이미 있으면 아무 일도 하지 않는다.

    `data_dir`을 만들면 부모인 `.history/`도 함께 생기므로
    두 산출물의 부모가 이 한 호출로 확보된다.
    """
    data_dir(project_root).mkdir(parents=True, exist_ok=True)


def needs_rebuild(project_root: Path, source_paths: list[Path]) -> bool:
    """산출물을 다시 만들어야 하는지 판정한다.

    산출물이 없거나, 넘겨받은 원본 중 하나라도 산출물보다 새로우면 True.

    `source_paths`는 산출물이 embed하는 원본 전체다 — 세션 jsonl과 auto-memory의
    항목 파일·인덱스. 판정은 원본의 종류를 보지 않으므로 축이 늘어도 고칠 곳이 없다.
    목록은 호출 직전의 디렉토리 스캔 결과이므로 존재를 다시 확인하지 않는다.
    """
    index = index_path(project_root)
    if not index.exists():
        return True
    index_mtime = index.stat().st_mtime
    # max()는 빈 목록에서 ValueError를 내므로 any()로 순회한다
    return any(p.stat().st_mtime > index_mtime for p in source_paths)
