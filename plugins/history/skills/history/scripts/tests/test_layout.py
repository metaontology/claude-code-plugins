import os
from store.layout import (
    data_dir,
    ensure_dirs,
    history_dir,
    index_path,
    needs_rebuild,
    server_file,
)


def test_index_path(tmp_path):
    assert index_path(tmp_path) == tmp_path / ".history" / "index.html"


def test_server_file(tmp_path):
    assert server_file(tmp_path) == tmp_path / ".history" / "data" / ".server"


def test_path_functions_have_no_side_effect(tmp_path):
    """경로 계산은 디스크를 건드리지 않는다."""
    history_dir(tmp_path)
    data_dir(tmp_path)
    index_path(tmp_path)
    server_file(tmp_path)
    assert not (tmp_path / ".history").exists()


def test_ensure_dirs_creates(tmp_path):
    ensure_dirs(tmp_path)
    assert (tmp_path / ".history" / "data").is_dir()


def test_ensure_dirs_idempotent(tmp_path):
    """이미 있는 상태에서 다시 불러도 예외가 없다."""
    ensure_dirs(tmp_path)
    ensure_dirs(tmp_path)
    assert (tmp_path / ".history" / "data").is_dir()


def _write(path, mtime):
    """지정한 mtime을 가진 파일을 만든다.

    파일을 쓴 순서에 기대면 파일시스템의 시각 해상도에 따라 두 파일이 같은 mtime을
    가질 수 있으므로 명시적으로 준다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def test_needs_rebuild_when_index_missing(tmp_path):
    jsonl = _write(tmp_path / "slug" / "a.jsonl", 1000)
    assert needs_rebuild(tmp_path, [jsonl]) is True


def test_needs_rebuild_when_source_newer(tmp_path):
    _write(index_path(tmp_path), 1000)
    jsonl = _write(tmp_path / "slug" / "a.jsonl", 2000)
    assert needs_rebuild(tmp_path, [jsonl]) is True


def test_no_rebuild_when_index_newer(tmp_path):
    _write(index_path(tmp_path), 2000)
    a = _write(tmp_path / "slug" / "a.jsonl", 1000)
    b = _write(tmp_path / "slug" / "b.jsonl", 1500)
    assert needs_rebuild(tmp_path, [a, b]) is False


def test_needs_rebuild_when_any_source_newer(tmp_path):
    """여러 개 중 하나만 새로워도 갱신 필요다."""
    _write(index_path(tmp_path), 2000)
    a = _write(tmp_path / "slug" / "a.jsonl", 1000)
    b = _write(tmp_path / "slug" / "b.jsonl", 3000)
    c = _write(tmp_path / "slug" / "c.jsonl", 1500)
    assert needs_rebuild(tmp_path, [a, b, c]) is True


def test_no_rebuild_when_no_source(tmp_path):
    """목록이 비어도 예외 없이 갱신 불필요를 돌려준다."""
    _write(index_path(tmp_path), 2000)
    assert needs_rebuild(tmp_path, []) is False


def test_needs_rebuild_when_memory_file_newer(tmp_path):
    """판정은 원본의 종류를 보지 않는다 — auto-memory 항목 파일만 넘겨도 성립한다."""
    _write(index_path(tmp_path), 2000)
    memory = _write(tmp_path / "slug" / "memory" / "some-fact.md", 3000)
    assert needs_rebuild(tmp_path, [memory]) is True
