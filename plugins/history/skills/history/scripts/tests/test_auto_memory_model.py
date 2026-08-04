import common.paths as paths
from auto_memory.model import load_auto_memory, memory_dir, parse_index, parse_item

FRONTMATTER = """---
name: {name}
description: {desc}
metadata:
  node_type: memory
  type: {type}
  originSessionId: d2212c02-38cf-4414-997a-b9a94802624f
---

{body}
"""


def _write_item(directory, filename, name="이름", desc="설명", type_="feedback",
                body="본문 내용"):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text(
        FRONTMATTER.format(name=name, desc=desc, type=type_, body=body),
        encoding="utf-8",
    )
    return directory / filename


def _write_index(directory, lines):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "MEMORY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── 항목 파싱 ──────────────────────────────────────────────────────────────

def test_parse_item_reads_frontmatter(tmp_path):
    path = _write_item(tmp_path, "a.md", name="긴 검토 자료", desc="요약문",
                       type_="feedback", body="본문\n두 줄")
    item = parse_item(path)
    assert item["file"] == "a.md"
    assert item["path"] == str(path)
    assert item["name"] == "긴 검토 자료"
    assert item["description"] == "요약문"
    assert item["type"] == "feedback"
    assert item["body"] == "본문\n두 줄"


def test_parse_item_type_ignores_node_type(tmp_path):
    """metadata 블록의 node_type이 type 파싱을 가로채지 않는다.

    앵커 없는 정규식은 `node_type: memory`의 뒷부분에 먼저 매치해 유형을 memory로 읽는다.
    실측에서 항목 55개 전부가 그렇게 틀렸다.
    """
    path = _write_item(tmp_path, "a.md", type_="project")
    assert parse_item(path)["type"] == "project"


def test_parse_item_without_frontmatter(tmp_path):
    """frontmatter가 없는 파일도 항목으로 남는다."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "bare.md"
    path.write_text("frontmatter 없는 그냥 글\n둘째 줄", encoding="utf-8")
    item = parse_item(path)
    assert item["name"] == "bare"
    assert item["type"] == ""
    assert item["body"] == "frontmatter 없는 그냥 글\n둘째 줄"


def test_parse_item_with_malformed_frontmatter(tmp_path):
    """형식이 어긋난 frontmatter도 항목에서 빠지지 않는다."""
    path = tmp_path / "broken.md"
    path.write_text("---\nname: 이름\n닫는 구분자가 없다\n본문", encoding="utf-8")
    item = parse_item(path)
    assert item["name"] == "broken"
    assert "닫는 구분자가 없다" in item["body"]


def test_parse_item_body_not_truncated(tmp_path):
    """본문은 절단하지 않는다 — 승격 판정은 본문을 읽어야 답할 수 있다."""
    long_body = "가" * 5000
    path = _write_item(tmp_path, "long.md", body=long_body)
    assert parse_item(path)["body"] == long_body


# ── 인덱스 파싱 ────────────────────────────────────────────────────────────

def test_parse_index_extracts_link_target():
    text = "- [긴 검토 자료는 tmp/ 파일로](long-review.md) — 채팅 출력은 생략된다"
    assert parse_index(text) == {"long-review.md": text}


def test_parse_index_ignores_non_pointer_lines():
    """포인터 형태가 아닌 줄은 무시한다 — 사람이 머리말을 넣을 수 있다."""
    text = "# 인덱스\n\n메모\n- [항목](a.md) — 요약\n"
    assert list(parse_index(text)) == ["a.md"]


# ── 항목과 인덱스의 분리 ───────────────────────────────────────────────────

def test_index_not_in_items(tmp_path, monkeypatch):
    """MEMORY.md가 항목 목록에 섞이면 폐기 후보로 화면에 오른다."""
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    directory = memory_dir("slug")
    _write_item(directory, "a.md")
    _write_index(directory, ["- [항목](a.md) — 요약"])
    result = load_auto_memory("slug")
    assert [i["file"] for i in result["items"]] == ["a.md"]
    assert result["index_lines"] == ["- [항목](a.md) — 요약"]


def test_item_carries_matching_index_line(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    directory = memory_dir("slug")
    _write_item(directory, "a.md")
    _write_index(directory, ["- [항목 가](a.md) — 요약 가"])
    item = load_auto_memory("slug")["items"][0]
    assert item["index_line"] == "- [항목 가](a.md) — 요약 가"


# ── 불일치 ─────────────────────────────────────────────────────────────────

def test_broken_pointer_detected(tmp_path, monkeypatch):
    """인덱스에 줄이 있는데 가리키는 항목 파일이 없다."""
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    directory = memory_dir("slug")
    _write_item(directory, "a.md")
    _write_index(directory, ["- [있음](a.md) — 요약", "- [없음](gone.md) — 요약"])
    result = load_auto_memory("slug")
    assert result["broken"] == [{"target": "gone.md", "line": "- [없음](gone.md) — 요약"}]
    assert result["missing"] == []


def test_missing_pointer_detected(tmp_path, monkeypatch):
    """항목 파일이 있는데 인덱스에 줄이 없다."""
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    directory = memory_dir("slug")
    _write_item(directory, "a.md")
    _write_item(directory, "b.md")
    _write_index(directory, ["- [있음](a.md) — 요약"])
    result = load_auto_memory("slug")
    assert result["missing"] == ["b.md"]
    assert result["broken"] == []


def test_no_index_makes_every_item_missing(tmp_path, monkeypatch):
    """인덱스 자체가 없으면 모든 항목이 누락된 포인터다."""
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    directory = memory_dir("slug")
    _write_item(directory, "a.md")
    result = load_auto_memory("slug")
    assert result["missing"] == ["a.md"]
    assert result["index_lines"] == []


# ── 빈 상태 ────────────────────────────────────────────────────────────────

def test_no_memory_dir_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    result = load_auto_memory("없는-슬러그")
    assert result["items"] == []
    assert result["broken"] == []
    assert result["missing"] == []


def test_empty_memory_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    memory_dir("slug").mkdir(parents=True)
    assert load_auto_memory("slug")["items"] == []


def test_index_only_yields_no_items(tmp_path, monkeypatch):
    """인덱스만 있고 항목이 없으면 항목 목록은 비고 끊긴 포인터만 남는다."""
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    directory = memory_dir("slug")
    _write_index(directory, ["- [사라진 항목](gone.md) — 요약"])
    result = load_auto_memory("slug")
    assert result["items"] == []
    assert len(result["broken"]) == 1


def test_items_sorted_by_filename(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    directory = memory_dir("slug")
    for name in ("c.md", "a.md", "b.md"):
        _write_item(directory, name)
    assert [i["file"] for i in load_auto_memory("slug")["items"]] == ["a.md", "b.md", "c.md"]
