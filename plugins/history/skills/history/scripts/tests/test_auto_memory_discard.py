from auto_memory.discard import discard_items

ITEM = """---
name: 이름
description: 설명
metadata:
  node_type: memory
  type: feedback
---

본문
"""


def _write_item(directory, filename):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(ITEM, encoding="utf-8")
    return directory / filename


def _write_index(directory, lines):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "MEMORY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return directory / "MEMORY.md"


def _index_text(directory):
    return (directory / "MEMORY.md").read_text(encoding="utf-8")


# ── 두 곳을 함께 고친다 ────────────────────────────────────────────────────

def test_discard_removes_file_and_index_line(tmp_path):
    """항목 파일 삭제와 인덱스 줄 제거를 함께 한다."""
    item = _write_item(tmp_path, "a.md")
    _write_index(tmp_path, ["- [가](a.md) — 요약 가", "- [나](b.md) — 요약 나"])
    results = discard_items(tmp_path, ["a.md"])
    assert results[0]["ok"] is True
    assert results[0]["removed"] == ["file", "index_line"]
    assert not item.exists()
    assert "a.md" not in _index_text(tmp_path)
    assert "b.md" in _index_text(tmp_path)


def test_discard_keeps_other_lines_intact(tmp_path):
    """포인터가 아닌 줄은 건드리지 않는다."""
    _write_item(tmp_path, "a.md")
    _write_index(tmp_path, ["# 인덱스", "", "- [가](a.md) — 요약"])
    discard_items(tmp_path, ["a.md"])
    assert _index_text(tmp_path).startswith("# 인덱스")


# ── 편측 처리 ──────────────────────────────────────────────────────────────

def test_broken_pointer_removes_line_only(tmp_path):
    """항목 파일이 없고 줄만 있으면 줄 제거만 하고 처리됨으로 답한다."""
    _write_index(tmp_path, ["- [사라진](gone.md) — 요약"])
    results = discard_items(tmp_path, ["gone.md"])
    assert results[0]["ok"] is True
    assert results[0]["removed"] == ["index_line"]
    assert "gone.md" not in _index_text(tmp_path)


def test_missing_pointer_removes_file_only(tmp_path):
    """인덱스 줄이 없고 파일만 있으면 파일 삭제만 하고 처리됨으로 답한다."""
    item = _write_item(tmp_path, "a.md")
    _write_index(tmp_path, ["- [다른 것](b.md) — 요약"])
    results = discard_items(tmp_path, ["a.md"])
    assert results[0]["ok"] is True
    assert results[0]["removed"] == ["file"]
    assert not item.exists()
    assert "b.md" in _index_text(tmp_path)


def test_no_index_file_at_all(tmp_path):
    """인덱스가 아예 없어도 파일 삭제는 성공한다."""
    item = _write_item(tmp_path, "a.md")
    results = discard_items(tmp_path, ["a.md"])
    assert results[0]["removed"] == ["file"]
    assert not item.exists()


# ── 거부 ───────────────────────────────────────────────────────────────────

def test_index_itself_is_rejected(tmp_path):
    """MEMORY.md는 지울 대상이 아니라 항목을 지울 때 함께 고쳐야 하는 쪽이다."""
    index = _write_index(tmp_path, ["- [가](a.md) — 요약"])
    results = discard_items(tmp_path, ["MEMORY.md"])
    assert results[0]["ok"] is False
    assert "MEMORY.md" in results[0]["reason"]
    assert index.exists()


def test_missing_target_is_failure(tmp_path):
    """파일도 줄도 없으면 실패다. 조용히 성공으로 처리하지 않는다."""
    _write_index(tmp_path, ["- [가](a.md) — 요약"])
    results = discard_items(tmp_path, ["nowhere.md"])
    assert results[0]["ok"] is False
    assert "없습니다" in results[0]["reason"]


def test_path_traversal_is_rejected(tmp_path):
    """대상은 이 디렉토리의 파일명이다. 경로를 벗어나는 이름을 거부한다."""
    outside = tmp_path.parent / "밖의파일.md"
    outside.write_text("건드리면 안 된다", encoding="utf-8")
    results = discard_items(tmp_path, ["../밖의파일.md"])
    assert results[0]["ok"] is False
    assert outside.exists()


# ── 여러 대상 ──────────────────────────────────────────────────────────────

def test_partial_success(tmp_path):
    """일부가 실패해도 나머지는 처리된다."""
    kept = _write_item(tmp_path, "a.md")
    gone = _write_item(tmp_path, "b.md")
    _write_index(tmp_path, ["- [가](a.md) — 요약", "- [나](b.md) — 요약"])
    results = discard_items(tmp_path, ["MEMORY.md", "b.md"])
    assert [r["ok"] for r in results] == [False, True]
    assert kept.exists()
    assert not gone.exists()


def test_index_written_once_for_many_targets(tmp_path):
    """여러 대상의 줄이 한 번의 쓰기로 함께 사라진다."""
    for name in ("a.md", "b.md", "c.md"):
        _write_item(tmp_path, name)
    _write_index(tmp_path, [f"- [{n}]({n}.md) — 요약" for n in ("a", "b", "c")])
    results = discard_items(tmp_path, ["a.md", "c.md"])
    assert all(r["ok"] for r in results)
    text = _index_text(tmp_path)
    assert "a.md" not in text and "c.md" not in text
    assert "b.md" in text


def test_preserves_order(tmp_path):
    _write_item(tmp_path, "a.md")
    targets = ["MEMORY.md", "a.md", "nowhere.md"]
    assert [r["target"] for r in discard_items(tmp_path, targets)] == targets


def test_empty_target_list(tmp_path):
    _write_index(tmp_path, ["- [가](a.md) — 요약"])
    assert discard_items(tmp_path, []) == []
    assert "a.md" in _index_text(tmp_path)
