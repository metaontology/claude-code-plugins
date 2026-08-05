"""세션 jsonl에서 뷰어가 표시할 값만 골라내는 모델 계층.

문자열을 조립하지 않고 구조화된 값만 반환한다. 마크다운이든 HTML이든 서버 응답이든,
표현은 이 계층을 소비하는 쪽이 만든다.

담지 않는 것 — Claude의 사고 과정(`thinking`), 도구 실행 결과(`tool_result`),
서브에이전트 트랜스크립트. 세 가지 모두 "이 세션을 지워도 되는가"에 답하지 않는다.
"""
import json
import re
from pathlib import Path

from common.jsonl import (
    all_jsonls_in_slug,
    get_session_meta,
    get_session_start,
    parse_jsonl,
)
from session.usage import session_usage

# 라벨 최대 길이. 넘으면 잘린 분량을 표시한다
LABEL_LIMIT = 200

# 경로를 담는 도구 input 키. 이 값들은 절단하지 않는다
PATH_KEYS = ("file_path", "notebook_path", "path", "file_paths")

# description도 경로도 없을 때 라벨로 쓸 키. 순서가 곧 우선순위다
TEXT_KEYS = (
    "query", "pattern", "url", "skill", "command",
    "prompt", "message", "content", "args", "old_string",
)

_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")
_COMMAND_NAME_RE = re.compile(r"<command-name>(/\S+)</command-name>")
_COMMAND_ARGS_RE = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)
_CAVEAT_RE = re.compile(r"<local-command-caveat>.*?</local-command-caveat>", re.DOTALL)
_CONTEXT_USAGE_RE = re.compile(r"#{0,3}\s*Context Usage")

# 사용자 발언으로 세는 항목 종류. 화면이 이 셋에 👤 마커를 붙인다
USER_KINDS = ("user", "slash_command", "local_command")

# 무엇을 불렀는지가 라벨이 아니라 별도 키에 있는 도구. 값은 그 이름을 담은 input 키다
TARGET_KEYS = {"Agent": "subagent_type", "Skill": "skill"}


def _unescape_unicode(text: str) -> str:
    """문자열에 리터럴로 남은 유니코드 이스케이프를 실제 문자로 되돌린다.

    `__unparsedToolInput`의 `raw`는 파싱되지 않은 JSON 원문이므로 이스케이프가
    문자 그대로 들어 있다. 파싱이 아니라 치환이므로 문법이 파손된 값에도 동작한다.
    """
    out = _UNICODE_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)
    # 서로게이트 페어를 결합한다. 짝이 없는 것은 대체 문자로 바꿔 인코딩 오류를 막는다
    return out.encode("utf-16", "surrogatepass").decode("utf-16", "replace")


def _truncate(text: str) -> str:
    """LABEL_LIMIT을 넘으면 잘라내고 잘린 분량을 표시한다."""
    if len(text) <= LABEL_LIMIT:
        return text
    return f"{text[:LABEL_LIMIT]}… (+{len(text) - LABEL_LIMIT}자)"


def input_paths(tool_input: dict) -> list[str]:
    """도구 호출 input에서 파일 경로를 뽑는다. 절단하지 않는다.

    `file_paths`처럼 목록으로 오는 키도 함께 펼친다.
    """
    if not isinstance(tool_input, dict):
        return []
    found: list[str] = []
    for key in PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            found.append(value)
        elif isinstance(value, list):
            found.extend(v for v in value if isinstance(v, str) and v)
    return found


def _fallback_label(tool_input: dict) -> str:
    """1~3번 규칙이 빗나간 호출의 라벨. input 전체를 문자열로 만든다.

    `__unparsedToolInput`으로 온 호출은 그 안쪽 원문을 쓴다. 다시 파싱하지 않는다 —
    문법이 파손됐거나 절단된 값이라 파싱이 원리적으로 실패한다.
    """
    unparsed = tool_input.get("__unparsedToolInput")
    if unparsed is not None:
        raw = unparsed.get("raw") if isinstance(unparsed, dict) else unparsed
        if not isinstance(raw, str):
            raw = json.dumps(raw, ensure_ascii=False, default=str)
        return _truncate(_unescape_unicode(raw))
    return _truncate(json.dumps(tool_input, ensure_ascii=False, default=str))


def tool_label(name: str, tool_input: dict) -> str:
    """도구 호출을 한 줄 라벨로 만든다.

    우선순위 —
    1. `description`이 있으면 그 값. 경로도 있으면 뒤에 병기한다
    2. 경로 키가 있으면 경로 전체. **절단하지 않는다**
    3. TEXT_KEYS의 첫 매치를 절단한다
    4. input 전체를 문자열로 만들어 절단한다
    """
    if not isinstance(tool_input, dict):
        return _truncate(_unescape_unicode(str(tool_input)))

    paths = input_paths(tool_input)

    description = tool_input.get("description")
    if isinstance(description, str) and description.strip():
        label = _truncate(description.strip())
        return f"{label}  {' '.join(paths)}" if paths else label

    if paths:
        return " ".join(paths)

    for key in TEXT_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return _truncate(value.strip())

    return _fallback_label(tool_input)


def tool_target(name: str, tool_input: dict) -> str:
    """도구 호출이 **무엇을 불렀는지** — 서브에이전트 타입 또는 스킬 이름.

    라벨과 따로 담는 이유는 화면이 이 값으로 내장과 사용자 정의를 가르기 때문이다.
    `Agent`의 라벨은 `description`이라 타입이 아예 없고, `Skill`의 라벨은 스킬
    이름이지만 그것을 라벨 문자열에서 되꺼내면 라벨 규칙이 바뀔 때 조용히 깨진다.

    두 도구가 아니거나 값이 문자열이 아니면 빈 문자열이다.
    """
    key = TARGET_KEYS.get(name)
    if not key or not isinstance(tool_input, dict):
        return ""
    value = tool_input.get(key)
    return value if isinstance(value, str) else ""


def _message_text(content) -> str:
    """message.content에서 텍스트만 이어 붙인다.

    content는 문자열 또는 블록 목록으로 온다. 블록 목록에서는 `text` 블록만 모으므로
    `tool_result`와 `thinking`은 여기서 저절로 빠진다.
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            (c.get("text") or "").strip()
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        return "\n".join(p for p in parts if p)
    return ""


def scan_session(records: list[dict], fallback_ts: str) -> dict:
    """레코드 목록을 한 번 훑어 3계층 항목과 파생값을 함께 만든다.

    경로·스킬을 항목과 같은 순회에서 모으는 이유는, 경로를 라벨 문자열에서 되꺼내지
    않고 도구 호출의 input에서 직접 꺼내기 때문이다. 그 input을 손에 들고 있는 자리가
    라벨을 만드는 자리다.

    반환값의 키 — `entries` · `files` · `skills` · `commands` · `user_count`
    """
    entries: list[dict] = []
    files: set[str] = set()
    skills: set[str] = set()
    commands: set[str] = set()

    for record in records:
        record_type = record.get("type", "")

        if record_type == "user":
            entry = _user_entry(record, fallback_ts)
            if entry:
                entries.append(entry)
                if entry["kind"] == "slash_command":
                    commands.add(entry["text"].split()[0])

        elif record_type == "assistant":
            ts = record.get("timestamp") or fallback_ts
            content = record.get("message", {}).get("content")
            if isinstance(content, str):
                text = content.strip()
                if text:
                    entries.append(_entry(ts, "assistant", text))
                continue
            for block in content or []:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "text":
                    text = (block.get("text") or "").strip()
                    if text:
                        entries.append(_entry(ts, "assistant", text))
                elif block_type == "tool_use":
                    name = block.get("name") or ""
                    tool_input = block.get("input") or {}
                    target = tool_target(name, tool_input)
                    entries.append(
                        _entry(ts, "tool", tool_label(name, tool_input),
                               tool=name, target=target)
                    )
                    files.update(input_paths(tool_input))
                    if name == "Skill" and target:
                        skills.add(target)
                # thinking 블록은 담지 않는다

        elif record_type == "system" and record.get("subtype") == "local_command":
            content = record.get("content", "")
            # stdout이 있는 레코드는 명령 실행 결과이므로 제외, 명령 자체만 기록한다
            if "<local-command-stdout>" in content:
                continue
            match = _COMMAND_NAME_RE.search(content)
            command = match.group(1) if match else content[:60]
            entries.append(_entry(record.get("timestamp") or fallback_ts,
                                  "local_command", command))

    return {
        "entries": entries,
        "files": sorted(files),
        "skills": sorted(skills),
        "commands": sorted(commands),
        "user_count": sum(1 for e in entries if e["kind"] in USER_KINDS),
    }


def _entry(ts: str, kind: str, text: str, tool: str = "", target: str = "") -> dict:
    """항목 하나를 만든다. `tool`·`target`은 도구 항목에서만 채워진다."""
    return {"ts": ts, "kind": kind, "text": text, "tool": tool, "target": target}


def _user_entry(record: dict, fallback_ts: str) -> dict | None:
    """user 레코드에서 항목 하나를 만든다. 노이즈면 None.

    슬래시 커맨드는 네임스페이스를 보존한다 — `/superpowers:brainstorming`을
    `/superpowers`로 줄이면 어떤 스킬을 불렀는지가 사라진다.
    """
    message = record.get("message", {})
    if message.get("role") != "user":
        return None

    text = _message_text(message.get("content", ""))
    if not text:
        return None

    ts = record.get("timestamp") or message.get("timestamp") or fallback_ts

    # command 태그가 있으면 슬래시 커맨드다. 태그가 있는 한 여기서 처리가 끝난다
    if "<command-name>" in text:
        name_match = _COMMAND_NAME_RE.search(text)
        if not name_match:
            return None
        args_match = _COMMAND_ARGS_RE.search(text)
        args = args_match.group(1).strip() if args_match else ""
        command = name_match.group(1)
        full = f"{command} {args}".strip() if args else command
        return _entry(ts, "slash_command", full)

    # ── 노이즈 필터 ────────────────────────────────────────────────────────
    if _CONTEXT_USAGE_RE.match(text):
        return None
    # 스킬 주입: Claude Code가 스킬 호출 시 SKILL.md 본문을 user 메시지로 넣는다.
    # [유지보수] 이 마커가 바뀌면 스킬 문서가 사용자 발언으로 기록된다
    if "Base directory for this skill:" in text:
        return None
    if "<local-command-stdout>" in text:
        return None
    if "<local-command-caveat>" in text:
        text = _CAVEAT_RE.sub("", text).strip()
        if not text:
            return None

    return _entry(ts, "user", text)


def extract_entries(records: list[dict], fallback_ts: str = "") -> list[dict]:
    """레코드 목록에서 3계층 항목만 시간순으로 추출한다."""
    return scan_session(records, fallback_ts)["entries"]


def build_session(jsonl_path: Path) -> dict:
    """jsonl 하나를 세션 값으로 만든다.

    파싱을 한 번만 한다 — 뷰어는 목록 메타와 대화 항목을 둘 다 필요로 하므로,
    두 함수로 갈라 두면 같은 파일을 두 번 파싱하게 된다.
    """
    session_id = jsonl_path.stem
    records = parse_jsonl(jsonl_path)
    meta = get_session_meta(records)
    scanned = scan_session(records, get_session_start(session_id))
    return {
        "id": session_id,
        "ts": meta["ts"],
        "title": meta["ai_title"],
        "files": scanned["files"],
        "user_count": scanned["user_count"],
        "skills": scanned["skills"],
        "commands": scanned["commands"],
        "entries": scanned["entries"],
        "usage": session_usage(records),
    }


def session_list(slug: str) -> list[dict]:
    """프로젝트 슬러그의 전 세션을 생성시각 내림차순으로 돌려준다.

    세션이 목록에 들어가는 조건은 없다. 슬러그 디렉토리에 jsonl이 있으면 전부 들어간다.
    생성시각이 빈 세션은 내림차순에서 끝으로 밀리지만 빠지지는 않는다.
    """
    sessions = [build_session(path) for path in all_jsonls_in_slug(slug)]
    sessions.sort(key=lambda s: s["ts"], reverse=True)
    return sessions
