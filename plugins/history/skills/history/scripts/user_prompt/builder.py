"""user-prompts.md 파일 생성: jsonl에서 사용자 메시지·로컬 커맨드 추출."""
import re
import sys
from pathlib import Path
from common.jsonl import find_jsonl, parse_jsonl, get_session_start
from common.time_util import parse_iso, fmt_local


def extract_entries(records: list[dict]) -> list[dict]:
    """jsonl 레코드 목록에서 기록할 항목(user 메시지, 로컬 커맨드)을 추출한다.

    필터링(제외) 대상:
    - role이 user가 아닌 메시지
    - 텍스트가 비어 있는 메시지
    - <command-name> 태그만 있고 나머지 텍스트 없는 메시지
    - '# Context Usage' 헤더로 시작하는 시스템 메시지
    - skill 로딩 메시지 ('Base directory for this skill:' + '다음 명령을 실행' 포함)
    - <local-command-stdout> 가 포함된 로컬 커맨드 출력 항목
    """
    entries = []
    for d in records:
        t = d.get("type", "")

        if t == "user":
            msg = d.get("message", {})
            if msg.get("role") != "user":
                continue

            # content가 문자열이거나 텍스트 블록 리스트인 경우 모두 처리
            content = msg.get("content", "")
            text = ""
            if isinstance(content, str):
                text = content.strip()
            elif isinstance(content, list):
                parts = []
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        parts.append(c.get("text", "").strip())
                text = "\n".join(p for p in parts if p)

            if not text:
                continue

            # <command-name> 태그 제거 후 나머지 텍스트만 보존
            if "<command-name>" in text:
                stripped = re.sub(r"<command[^>]*>.*?</command[^>]*>", "", text, flags=re.DOTALL).strip()
                if not stripped:
                    continue
                text = stripped

            if re.match(r"#{0,3}\s*Context Usage", text):
                continue

            # skill 로딩 시 Claude에게 전달되는 메시지 제외
            # NOTE: "Base directory for this skill:" 마커로 감지.
            # 향후 Claude Code가 스킬 주입 포맷을 변경하면 이 마커가 없는 메시지가
            # user-prompts.md에 그대로 기록될 수 있으므로 포맷 변경 시 재검토 필요.
            if "Base directory for this skill:" in text:
                continue

            # local-command-caveat 태그 제거
            if "<local-command-caveat>" in text:
                text = re.sub(r"<local-command-caveat>.*?</local-command-caveat>", "", text, flags=re.DOTALL).strip()
                if not text:
                    continue

            ts_str = d.get("timestamp") or d.get("message", {}).get("timestamp")
            entries.append({"ts": ts_str, "kind": "user", "text": text})

        elif t == "system" and d.get("subtype") == "local_command":
            content = d.get("content", "")
            # stdout 출력이 포함된 항목은 명령 실행 결과이므로 제외
            if "<local-command-stdout>" in content:
                continue
            m = re.search(r"<command-name>(/\S+)</command-name>", content)
            cmd = m.group(1) if m else content[:60]
            ts_str = d.get("timestamp")
            entries.append({"ts": ts_str, "kind": "local_command", "text": cmd})

    return entries


def write_user_prompts(session_id: str, history_dir: Path) -> int:
    """세션의 user-prompts.md를 생성하고 항목 수를 반환한다.

    출력 경로: history_dir/user-prompts/{session_id}/user-prompts.md
    jsonl 파일을 찾지 못하면 0 반환.
    """
    jsonl_path = find_jsonl(session_id)
    if not jsonl_path:
        print(f"WARN: jsonl not found for session {session_id}", file=sys.stderr)
        return 0

    records = parse_jsonl(jsonl_path)
    entries = extract_entries(records)
    fallback_ts = get_session_start(session_id)

    out_dir = history_dir / "user-prompts" / session_id
    out_dir.mkdir(parents=True, exist_ok=True)

    prompt_lines = []
    for e in entries:
        ts = e.get("ts")
        try:
            label = fmt_local(parse_iso(ts)) if ts else fallback_ts
        except Exception:
            label = fallback_ts
        kind_prefix = "" if e["kind"] == "user" else f"[{e['kind']}] "
        prompt_lines.append(f"[{label}]\n{kind_prefix}{e['text']}")

    out_file = out_dir / "user-prompts.md"
    out_file.write_text("\n\n".join(prompt_lines), encoding="utf-8")
    return len(entries)
