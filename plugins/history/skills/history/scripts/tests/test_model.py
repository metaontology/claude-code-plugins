import common.paths as paths
from session.model import (
    build_session,
    extract_entries,
    input_paths,
    scan_session,
    session_list,
    tool_label,
    tool_target,
)


# ── 사용자 발언 계층 ───────────────────────────────────────────────────────

def test_extract_entries_basic():
    records = [
        {
            "type": "user",
            "timestamp": "2026-06-01T00:00:00Z",
            "message": {"role": "user", "content": "안녕하세요"},
        }
    ]
    entries = extract_entries(records)
    assert len(entries) == 1
    assert entries[0]["text"] == "안녕하세요"
    assert entries[0]["kind"] == "user"


def test_extract_entries_skips_empty_text():
    records = [{"type": "user", "message": {"role": "user", "content": ""}}]
    assert extract_entries(records) == []


def test_extract_entries_skips_context_usage():
    records = [
        {
            "type": "user",
            "message": {"role": "user", "content": "# Context Usage\nsome text"},
        }
    ]
    assert extract_entries(records) == []


def test_extract_entries_skips_skill_injection():
    """스킬 호출 시 주입되는 SKILL.md 본문은 사용자 발언이 아니다."""
    records = [
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": "Base directory for this skill: /path\n본문...",
            },
        }
    ]
    assert extract_entries(records) == []


def test_extract_entries_local_command():
    records = [
        {
            "type": "system",
            "subtype": "local_command",
            "timestamp": "2026-06-01T00:00:00Z",
            "content": "<command-name>/history</command-name>",
        }
    ]
    entries = extract_entries(records)
    assert len(entries) == 1
    assert entries[0]["kind"] == "local_command"
    assert entries[0]["text"] == "/history"


def test_extract_entries_skips_local_command_with_stdout():
    records = [
        {
            "type": "system",
            "subtype": "local_command",
            "content": "<local-command-stdout>출력</local-command-stdout>",
        }
    ]
    assert extract_entries(records) == []


def test_extract_entries_slash_command_only():
    """슬래시 커맨드만 있는 경우 명령어가 기록된다."""
    records = [
        {
            "type": "user",
            "timestamp": "2026-06-01T00:00:00Z",
            "message": {
                "role": "user",
                "content": "<command-message>history:history</command-message>\n"
                           "<command-name>/history:history</command-name>\n"
                           "<command-args></command-args>",
            },
        }
    ]
    entries = extract_entries(records)
    assert len(entries) == 1
    assert entries[0]["kind"] == "slash_command"
    assert entries[0]["text"] == "/history:history"


def test_extract_entries_slash_command_with_args():
    """슬래시 커맨드 + args가 합쳐져 기록된다."""
    records = [
        {
            "type": "user",
            "timestamp": "2026-06-01T00:00:00Z",
            "message": {
                "role": "user",
                "content": "<command-name>/history:history</command-name>\n"
                           "<command-args>all</command-args>",
            },
        }
    ]
    entries = extract_entries(records)
    assert entries[0]["text"] == "/history:history all"


def test_extract_entries_slash_command_namespace_preserved():
    """플러그인 네임스페이스가 원본 그대로 보존된다 — 어떤 스킬을 불렀는지가 정보다."""
    records = [
        {
            "type": "user",
            "timestamp": "2026-06-01T00:00:00Z",
            "message": {
                "role": "user",
                "content": "<command-name>/superpowers:brainstorming</command-name>\n"
                           "<command-args>설계 시작</command-args>",
            },
        }
    ]
    entries = extract_entries(records)
    assert entries[0]["text"] == "/superpowers:brainstorming 설계 시작"


def test_extract_entries_list_content():
    records = [
        {
            "type": "user",
            "timestamp": "2026-06-01T00:00:00Z",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "리스트 콘텐츠"}],
            },
        }
    ]
    entries = extract_entries(records)
    assert entries[0]["text"] == "리스트 콘텐츠"


def test_missing_timestamp_uses_fallback():
    records = [{"type": "user", "message": {"role": "user", "content": "시각 없음"}}]
    entries = extract_entries(records, "2026-01-01 00:00:00")
    assert entries[0]["ts"] == "2026-01-01 00:00:00"


# ── Claude 응답과 제외 대상 ────────────────────────────────────────────────

def test_assistant_text_becomes_entry():
    records = [
        {
            "type": "assistant",
            "timestamp": "2026-06-01T00:00:00Z",
            "message": {"content": [{"type": "text", "text": "응답 본문"}]},
        }
    ]
    entries = extract_entries(records)
    assert len(entries) == 1
    assert entries[0]["kind"] == "assistant"
    assert entries[0]["text"] == "응답 본문"


def test_thinking_not_in_entries():
    """사고 과정은 어떤 항목에도 나타나지 않는다."""
    records = [
        {
            "type": "assistant",
            "timestamp": "2026-06-01T00:00:00Z",
            "message": {
                "content": [
                    {"type": "thinking", "thinking": "속으로 생각한 내용"},
                    {"type": "text", "text": "겉으로 한 말"},
                ]
            },
        }
    ]
    entries = extract_entries(records)
    assert len(entries) == 1
    assert all("속으로 생각한 내용" not in e["text"] for e in entries)


def test_tool_result_not_in_entries():
    """도구 실행 결과는 어떤 항목에도 나타나지 않는다."""
    records = [
        {
            "type": "user",
            "timestamp": "2026-06-01T00:00:00Z",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "content": "파일 내용 수천 줄"},
                ],
            },
        }
    ]
    assert extract_entries(records) == []


def test_entries_keep_record_order():
    """세 계층이 레코드 등장 순서 그대로 한 목록에 섞인다 — 계층별로 갈리지 않는다."""
    records = [
        {"type": "user", "timestamp": "2026-06-01T00:00:01Z",
         "message": {"role": "user", "content": "질문"}},
        {"type": "assistant", "timestamp": "2026-06-01T00:00:02Z",
         "message": {"content": [
             {"type": "text", "text": "답"},
             {"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}},
         ]}},
        {"type": "user", "timestamp": "2026-06-01T00:00:03Z",
         "message": {"role": "user", "content": "다음 질문"}},
    ]
    kinds = [e["kind"] for e in extract_entries(records)]
    assert kinds == ["user", "assistant", "tool", "user"]


def test_tool_entry_carries_tool_name():
    """도구 이름은 라벨과 섞이지 않고 따로 담긴다."""
    records = [
        {
            "type": "assistant",
            "timestamp": "2026-06-01T00:00:00Z",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}},
                ]
            },
        }
    ]
    entries = extract_entries(records)
    assert entries[0]["kind"] == "tool"
    assert entries[0]["tool"] == "Read"
    assert entries[0]["text"] == "a.py"
    assert entries[0]["target"] == ""


def test_agent_entry_carries_subagent_type():
    """Agent 호출은 서브에이전트 타입을 따로 담는다 — 라벨은 description이라 타입이 없다."""
    records = [
        {
            "type": "assistant",
            "timestamp": "2026-06-01T00:00:00Z",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Agent",
                     "input": {"subagent_type": "Explore", "description": "로컬 탐색",
                               "prompt": "훑어라"}},
                ]
            },
        }
    ]
    entries = extract_entries(records)
    assert entries[0]["target"] == "Explore"
    assert entries[0]["text"] == "로컬 탐색"


def test_skill_entry_carries_skill_name():
    """Skill 호출은 스킬 이름을 따로 담는다 — 화면이 라벨을 역파싱하지 않는다."""
    records = [
        {
            "type": "assistant",
            "timestamp": "2026-06-01T00:00:00Z",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Skill", "input": {"skill": "claude-api"}},
                ]
            },
        }
    ]
    assert extract_entries(records)[0]["target"] == "claude-api"


def test_tool_target_missing_key_is_empty():
    """대상 키가 없거나 문자열이 아니면 빈 문자열이다. 형이 하나여야 화면에 분기가 없다."""
    assert tool_target("Agent", {"prompt": "타입 없이 부른 호출"}) == ""
    assert tool_target("Skill", {"skill": ["목록으로 온 값"]}) == ""
    assert tool_target("Read", {"file_path": "a.py"}) == ""


# ── 도구 라벨 4순위 ────────────────────────────────────────────────────────

def test_tool_label_description_first():
    """description이 있으면 그것을 쓰고 경로를 뒤에 병기한다."""
    label = tool_label("Bash", {"command": "x" * 4000,
                                "description": "테스트 실행",
                                "file_path": "run.sh"})
    assert label == "테스트 실행  run.sh"


def test_tool_label_path_not_truncated():
    """경로는 200자를 넘어도 절단되지 않는다 — 잘리면 산출물 추적이 불가능해진다."""
    long_path = "C:/tmp/" + "d" * 300 + "/x.py"
    label = tool_label("Write", {"file_path": long_path, "content": "y" * 5000})
    assert label == long_path


def test_tool_label_text_key_truncated():
    """경로도 description도 없으면 TEXT_KEYS의 첫 매치를 절단한다."""
    label = tool_label("Grep", {"pattern": "z" * 250})
    assert label == "z" * 200 + "… (+50자)"


def test_tool_label_fallback_serializes_input():
    """어느 규칙에도 걸리지 않는 도구도 빈 껍데기가 되지 않는다."""
    label = tool_label("TaskUpdate", {"task_id": "t1", "state": "completed"})
    assert "t1" in label
    assert "completed" in label


def test_tool_label_unparsed_input_is_readable():
    """__unparsedToolInput은 다시 파싱하지 않고 이스케이프만 되돌린다."""
    raw = '{"questions": [{"question": "\\uc9c8\\ubb38\\uc785\\ub2c8\\ub2e4"'
    label = tool_label("AskUserQuestion",
                       {"__unparsedToolInput": {"raw": raw, "len": 999}})
    assert "질문입니다" in label
    assert "\\u" not in label


def test_tool_label_unparsed_input_as_string():
    """__unparsedToolInput이 dict가 아니라 문자열로 오는 호출이 있다."""
    label = tool_label("SendMessage",
                       {"__unparsedToolInput": '{"to": "agent-1", "message": "\\uc548\\ub155"}'})
    assert "안녕" in label


def test_tool_label_surrogate_pair_survives():
    """서로게이트 페어로 표기된 문자가 홀로 남지 않는다."""
    label = tool_label("AskUserQuestion",
                       {"__unparsedToolInput": {"raw": '{"q": "\\ud83d\\ude00"}', "len": 20}})
    assert "\U0001f600" in label
    label.encode("utf-8")  # 인코딩 오류 없이 출력 가능하다


# ── 파일 경로 집합 ─────────────────────────────────────────────────────────

def _tool_use(name, tool_input, ts="2026-06-01T00:00:00Z"):
    return {
        "type": "assistant",
        "timestamp": ts,
        "message": {"content": [{"type": "tool_use", "name": name, "input": tool_input}]},
    }


def test_files_deduplicated():
    records = [
        _tool_use("Edit", {"file_path": "a.py"}),
        _tool_use("Edit", {"file_path": "a.py"}),
        _tool_use("Read", {"file_path": "b.py"}),
    ]
    assert scan_session(records, "")["files"] == ["a.py", "b.py"]


def test_files_not_truncated():
    long_path = "C:/tmp/" + "e" * 300 + "/x.py"
    records = [_tool_use("Write", {"file_path": long_path})]
    assert scan_session(records, "")["files"] == [long_path]


def test_input_paths_expands_list_key():
    """file_paths처럼 목록으로 오는 키도 펼쳐 수집한다."""
    assert input_paths({"file_paths": ["a.py", "b.py"]}) == ["a.py", "b.py"]


def test_files_empty_when_no_tool_use():
    records = [{"type": "user", "message": {"role": "user", "content": "대화만 했다"}}]
    assert scan_session(records, "")["files"] == []


def test_unparsed_input_contributes_no_path():
    """파싱되지 않은 input에서는 경로를 꺼내지 않는다 — 문자열을 역파싱하지 않는다."""
    raw = '{"file_path": "C:/a.py", "offset": 680, 760}'
    records = [_tool_use("Read", {"__unparsedToolInput": {"raw": raw, "len": 43}})]
    assert scan_session(records, "")["files"] == []


# ── 통계 ───────────────────────────────────────────────────────────────────

def test_user_count_counts_three_kinds():
    """발언 수는 화면에서 👤 마커가 붙는 세 종류를 함께 센다."""
    records = [
        {"type": "user", "timestamp": "t", "message": {"role": "user", "content": "말"}},
        {"type": "user", "timestamp": "t",
         "message": {"role": "user",
                     "content": "<command-name>/history</command-name>"}},
        {"type": "system", "subtype": "local_command", "timestamp": "t",
         "content": "<command-name>/ls</command-name>"},
        _tool_use("Read", {"file_path": "a.py"}),
    ]
    assert scan_session(records, "")["user_count"] == 3


def test_skills_from_skill_tool():
    records = [
        _tool_use("Skill", {"skill": "superpowers:brainstorming", "args": "시작"}),
        _tool_use("Skill", {"skill": "history"}),
        _tool_use("Skill", {"skill": "history"}),
    ]
    assert scan_session(records, "")["skills"] == ["history", "superpowers:brainstorming"]


def test_commands_exclude_args():
    """커맨드 목록에는 이름만 담긴다 — args는 항목 본문에 남아 본문 검색으로 걸린다."""
    records = [
        {"type": "user", "timestamp": "t",
         "message": {"role": "user",
                     "content": "<command-name>/history:history</command-name>\n"
                                "<command-args>전체 갱신</command-args>"}},
    ]
    scanned = scan_session(records, "")
    assert scanned["commands"] == ["/history:history"]
    assert scanned["entries"][0]["text"] == "/history:history 전체 갱신"


def test_commands_exclude_local_command():
    """! 로컬 커맨드는 슬래시 커맨드가 아니다."""
    records = [
        {"type": "system", "subtype": "local_command", "timestamp": "t",
         "content": "<command-name>/git status</command-name>"},
    ]
    assert scan_session(records, "")["commands"] == []


# ── 세션 값과 목록 ─────────────────────────────────────────────────────────

def _write_jsonl(proj_dir, sid, date, title="", extra=()):
    proj_dir.mkdir(parents=True, exist_ok=True)
    lines = [f'{{"timestamp":"{date}T00:00:00Z","type":"user",'
             f'"message":{{"role":"user","content":"발언"}}}}']
    if title:
        lines.append(f'{{"type":"ai-title","aiTitle":"{title}"}}')
    lines.extend(extra)
    (proj_dir / f"{sid}.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_build_session_shape(tmp_path):
    sid = "abcd1234-0000-0000-0000-000000000000"
    _write_jsonl(tmp_path, sid, "2026-06-01", "테스트 세션")
    session = build_session(tmp_path / f"{sid}.jsonl")
    assert session["id"] == sid
    assert session["ts"].startswith("2026-06-01")
    assert session["title"] == "테스트 세션"
    assert session["user_count"] == 1
    assert session["files"] == []
    assert session["skills"] == []
    assert session["commands"] == []
    assert len(session["entries"]) == 1


def test_build_session_without_title(tmp_path):
    """제목이 없어도 표시 문자열을 끼워 넣지 않는다 — 없음의 표현은 화면이 정한다."""
    sid = "bbbb2222-0000-0000-0000-000000000000"
    proj = tmp_path / "slug"
    proj.mkdir()
    (proj / f"{sid}.jsonl").write_text(
        '{"timestamp":"2026-06-01T00:00:00Z","type":"assistant",'
        '"message":{"content":[{"type":"text","text":"응답"}]}}\n',
        encoding="utf-8")
    assert build_session(proj / f"{sid}.jsonl")["title"] == ""


def test_session_list_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    proj = tmp_path / "test-slug"
    _write_jsonl(proj, "aaaa1111-0000-0000-0000-000000000000", "2026-01-01")
    _write_jsonl(proj, "bbbb2222-0000-0000-0000-000000000000", "2026-06-01")
    ids = [s["id"][:4] for s in session_list("test-slug")]
    assert ids == ["bbbb", "aaaa"]


def test_session_list_includes_every_session(tmp_path, monkeypatch):
    """파일을 건드리지 않은 세션도, 제목이 없는 세션도 빠지지 않는다."""
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    proj = tmp_path / "test-slug"
    _write_jsonl(proj, "aaaa1111-0000-0000-0000-000000000000", "2026-01-01")
    _write_jsonl(proj, "bbbb2222-0000-0000-0000-000000000000", "2026-06-01", "제목 있음")
    sessions = session_list("test-slug")
    assert len(sessions) == 2
    assert all(s["files"] == [] for s in sessions)


def test_session_list_empty_when_slug_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "PROJECTS_DIR", tmp_path)
    assert session_list("없는-슬러그") == []
