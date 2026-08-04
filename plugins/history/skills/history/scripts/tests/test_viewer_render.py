"""뷰어 산출물 조립 검증 — 무엇을 담고 언제 다시 만들어지는가.

브라우저가 필요한 것은 여기서 검증하지 않는다. 마크다운 렌더 결과와 화면 동작은
실물 관측 몫이다(`docs/dev-plans/20-viewer/000-embed.md`의 「이 단계의 관측 한계」).
"""
import json
import os
import re
import shutil

import pytest

import common.paths as paths
import store.config as user_config
import viewer.render as render
from auto_memory.model import load_auto_memory
from session.model import session_list
from store.layout import index_path
from viewer.render import (
    ASSETS_DIR,
    SHELL_FILE,
    attach_rebuild,
    build,
    embed_payload,
    recorded_ids,
    refresh,
    render_html,
    source_paths,
)

SESSION = "aaaaaaaa-0000-0000-0000-000000000000"
SLUG = "viewer-slug"
DATA_OPEN = 'id="data">'


def write_session(path, text, ts="2026-08-01T09:00:00Z"):
    """사용자 발언 하나짜리 세션 jsonl을 만든다."""
    record = {"type": "user", "timestamp": ts,
              "message": {"role": "user", "content": text}}
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")


def write_memory(slug_dir, name="note", body="본문"):
    """auto-memory 항목 하나와 인덱스를 만든다. 메모리 디렉토리 경로 반환."""
    directory = slug_dir / "memory"
    directory.mkdir(exist_ok=True)
    (directory / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: 설명\nmetadata:\n"
        f"  node_type: memory\n  type: project\n---\n\n{body}\n",
        encoding="utf-8",
    )
    (directory / "MEMORY.md").write_text(
        f"- [{name}]({name}.md) — 요약\n", encoding="utf-8")
    return directory


def data_section(html):
    """산출물에서 embed 데이터 구획만 잘라낸다."""
    start = html.index(DATA_OPEN) + len(DATA_OPEN)
    return html[start:html.index("</script>", start)]


def age(path, seconds):
    """mtime을 명시적으로 준다. 연달아 쓴 파일은 같은 mtime을 가질 수 있다."""
    stamp = os.stat(path).st_mtime + seconds
    os.utime(path, (stamp, stamp))


@pytest.fixture
def env(tmp_path, monkeypatch):
    """임시 projects와 프로젝트 루트. `(프로젝트 루트, 슬러그 디렉토리)`.

    사용자 설정 경로도 임시 디렉토리로 돌린다. 산출물은 그 파일을 읽어 심고 원본 목록에도
    담으므로, 실물을 보게 두면 이 테스트가 **사용자의 테마에 따라 결과를 바꾼다.**
    """
    projects = tmp_path / "projects"
    monkeypatch.setattr(paths, "PROJECTS_DIR", projects)
    user_dir = tmp_path / "userconfig"
    monkeypatch.setattr(user_config, "USER_CONFIG_DIR", user_dir)
    monkeypatch.setattr(user_config, "USER_CONFIG_FILE", user_dir / "config.json")
    slug_dir = projects / SLUG
    slug_dir.mkdir(parents=True)
    write_session(slug_dir / f"{SESSION}.jsonl", "첫 발언")
    root = tmp_path / "project"
    root.mkdir()
    return root, slug_dir


class FakeServer:
    """`attach_rebuild`가 받는 서버 객체의 최소 형태."""

    def __init__(self, project_root, session_id):
        self.project_root = project_root
        self._session_id = session_id
        self.rebuild = None

    def current_session_id(self):
        return self._session_id


# ── 원본 목록 ───────────────────────────────────────────────────────────────

def test_source_paths_includes_jsonl(env):
    _, slug_dir = env
    assert slug_dir / f"{SESSION}.jsonl" in source_paths(SLUG)


def test_source_paths_includes_memory_and_index(env):
    """인덱스만 고친 경우가 판정에서 빠지지 않아야 한다."""
    _, slug_dir = env
    directory = write_memory(slug_dir)
    found = source_paths(SLUG)
    assert directory / "note.md" in found
    assert directory / "MEMORY.md" in found


def test_source_paths_without_memory_dir(env):
    """메모리 디렉토리가 없어도 오류가 아니다."""
    _, slug_dir = env
    assert source_paths(SLUG) == [slug_dir / f"{SESSION}.jsonl"]


def test_source_paths_includes_user_config(env):
    """설정도 산출물에 심기므로 원본이다.

    이것이 빠지면 저장한 테마가 새로고침에 반영되는지가 **세션 jsonl의 mtime에 따라
    우연히 갈린다** — 판정이 설정 파일을 아예 보지 않기 때문이다.
    """
    user_config.save_config({"theme": "dark"})
    assert user_config.USER_CONFIG_FILE in source_paths(SLUG)


# ── 페이로드 ────────────────────────────────────────────────────────────────

def test_payload_keys(env):
    root, _ = env
    payload = embed_payload(root, SLUG, SESSION)
    assert set(payload) == {"project", "sessions_dir", "current", "sessions",
                            "memory", "local_skills"}


def test_payload_carries_current_session(env):
    """〈현재〉 배지와 체크박스 부재가 이 값을 요구하고, embed 말고 얻을 곳이 없다."""
    root, _ = env
    payload = embed_payload(root, SLUG, SESSION)
    assert payload["current"] == SESSION
    assert payload["sessions_dir"].endswith(SLUG)


def test_payload_sessions_match_model(env):
    root, _ = env
    assert embed_payload(root, SLUG, SESSION)["sessions"] == session_list(SLUG)


def test_payload_memory_matches_model(env):
    root, slug_dir = env
    write_memory(slug_dir)
    assert embed_payload(root, SLUG, SESSION)["memory"] == load_auto_memory(SLUG)


# ── HTML 조립 ───────────────────────────────────────────────────────────────

def test_html_has_no_placeholder_left(env):
    root, _ = env
    html = render_html(embed_payload(root, SLUG, SESSION))
    for placeholder in ("{{STYLE}}", "{{SCRIPT}}", "{{DATA}}"):
        assert placeholder not in html


def test_close_script_is_escaped(env):
    """본문의 `</script>`가 그대로 실리면 그 자리에서 데이터 구획이 닫힌다."""
    root, slug_dir = env
    write_session(slug_dir / f"{SESSION}.jsonl", "코드: </script> 그리고 </SCRIPT>")
    section = data_section(render_html(embed_payload(root, SLUG, SESSION)))
    assert "</script" not in section.lower()
    # JSON에서 `\/`는 `/`로 파싱되므로 원문은 손실 없이 복원된다
    text = json.loads(section)["sessions"][0]["entries"][0]["text"]
    assert "</script>" in text and "</SCRIPT>" in text


def test_css_and_js_inlined(env):
    root, _ = env
    html = render_html(embed_payload(root, SLUG, SESSION))
    assert "--pane-width" in html
    assert "App.provide" in html
    assert "renderMarkdown" in html


def test_assets_inlined_in_filename_order(env):
    """파일명 앞의 두 자리 숫자가 로드 순서다."""
    root, _ = env
    html = render_html(embed_payload(root, SLUG, SESSION))
    assert html.index("App.provide") < html.index("window.renderMarkdown")


def test_new_asset_is_picked_up(env, tmp_path, monkeypatch):
    """뒤따르는 문서가 자산을 더할 때 렌더러를 고치지 않아도 된다."""
    root, _ = env
    staged = tmp_path / "assets"
    shutil.copytree(ASSETS_DIR, staged)
    (staged / "90-probe.js").write_text("var PROBE_MARKER = 1;", encoding="utf-8")
    monkeypatch.setattr(render, "ASSETS_DIR", staged)
    assert "PROBE_MARKER" in render_html(embed_payload(root, SLUG, SESSION))


# ── 쓰기 ────────────────────────────────────────────────────────────────────

def test_build_creates_history_dir(env):
    """경로 계산에 부작용이 없으므로 디렉토리는 쓰기 직전에 확보된다."""
    root, _ = env
    assert not (root / ".history").exists()
    build(root, SESSION)
    assert index_path(root).is_file()


def test_build_returns_index_path(env):
    root, _ = env
    assert build(root, SESSION) == index_path(root)


# ── 판정 결합 ───────────────────────────────────────────────────────────────

def test_refresh_builds_when_missing(env):
    root, _ = env
    assert refresh(root, SESSION) is True
    assert index_path(root).exists()


def test_refresh_rebuilds_when_source_newer(env):
    root, slug_dir = env
    build(root, SESSION)
    age(slug_dir / f"{SESSION}.jsonl", 60)
    assert refresh(root, SESSION) is True


def test_refresh_skips_when_up_to_date(env):
    root, slug_dir = env
    build(root, SESSION)
    age(slug_dir / f"{SESSION}.jsonl", -60)
    assert refresh(root, SESSION) is False


def test_refresh_forced_by_rebuild_flag(env):
    """원본은 그대로인데 산출물을 만드는 코드가 바뀐 경우의 탈출구다."""
    root, slug_dir = env
    build(root, SESSION)
    age(slug_dir / f"{SESSION}.jsonl", -60)
    assert refresh(root, SESSION, rebuild=True) is True


# ── 재생성 콜백 ─────────────────────────────────────────────────────────────

def test_attach_rebuild_sets_callback(env):
    root, _ = env
    server = FakeServer(root, SESSION)
    attach_rebuild(server)
    assert callable(server.rebuild)


def test_rebuild_callback_writes_index(env):
    """삭제가 하나라도 처리되면 서버가 이 콜백으로 산출물을 다시 만든다."""
    root, _ = env
    server = FakeServer(root, SESSION)
    attach_rebuild(server)
    server.rebuild()
    assert index_path(root).is_file()


# ── 기록된 세션 목록 ────────────────────────────────────────────────────────
# 화면이 이 값을 자기 embed 목록과 견줘 "다시 만들면 늘어날 행이 있는가"를 안다

def test_recorded_ids_lists_slug_sessions(env):
    """슬러그의 jsonl 파일명이 곧 세션 UUID다."""
    assert recorded_ids(SESSION) == [SESSION]


def test_recorded_ids_includes_sessions_added_later(env):
    """뷰어가 열려 있는 동안 생긴 세션도 담긴다. 그것이 이 값의 존재 이유다."""
    _, slug_dir = env
    later = "bbbbbbbb-0000-0000-0000-000000000000"
    write_session(slug_dir / f"{later}.jsonl", "나중 발언")
    assert recorded_ids(SESSION) == sorted([SESSION, later])


def test_recorded_ids_sorted(env):
    """정렬을 갖는다. 스트림이 직전 값과 견줘 보낼지 정하므로, 열거 순서가 바뀌는
    것만으로 변경으로 읽히면 안 된다."""
    _, slug_dir = env
    for name in ("cccccccc", "bbbbbbbb"):
        write_session(slug_dir / f"{name}-0000-0000-0000-000000000000.jsonl", "발언")
    found = recorded_ids(SESSION)
    assert found == sorted(found)


def test_recorded_ids_unknown_session(env):
    """슬러그를 모르면 빈 목록이다. **예외를 내지 않는다** — 스트림이 틱마다 부르므로
    예외가 곧 연결 종료가 된다."""
    assert recorded_ids("ffffffff-0000-0000-0000-000000000000") == []


def test_recorded_ids_without_session_id(env):
    """세션 ID가 비어 있어도 마찬가지다. `.server`가 아직 갱신되지 않은 창이다."""
    assert recorded_ids("") == []


# ── 슬러그 없음 ─────────────────────────────────────────────────────────────

def test_unknown_session_raises(env):
    """빈 산출물을 쓰면 원본 목록이 비어 다음 판정이 "갱신 불필요"로 굳는다."""
    root, _ = env
    with pytest.raises(RuntimeError):
        build(root, "ffffffff-0000-0000-0000-000000000000")


def test_shell_comments_have_no_placeholder():
    """주석 안에 자리표시자 **문자열**을 두지 않는다.

    `replace`는 주석을 가리지 않으므로 그 자리에도 데이터가 들어가고, 데이터에 `-->`가
    있으면 주석이 거기서 닫혀 나머지 JSON이 본문 텍스트로 노출된다.
    """
    shell = (ASSETS_DIR / SHELL_FILE).read_text(encoding="utf-8")
    for comment in re.findall(r"<!--.*?-->", shell, re.S):
        assert not re.search(r"\{\{[A-Z]+\}\}", comment), f"주석에 자리표시자가 있다: {comment[:80]}"


def test_arrow_in_data_does_not_break_head(env):
    """대화에 `-->`가 있어도 `<head>`에 데이터가 새지 않는다.

    주석 안으로 데이터가 들어가면 그 자리에서 주석이 닫히고 나머지 JSON이 본문 텍스트가
    된다. 화면 전체가 날것의 JSON으로 보이는 형태로 드러난다.
    """
    root, slug_dir = env
    write_session(slug_dir / f"{SESSION}.jsonl", "화살표 --> 가 든 발언")
    html = render_html(embed_payload(root, SLUG, SESSION))
    head = html[:html.index("</head>")]
    assert "화살표" not in head
