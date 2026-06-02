"""user-prompts.md 파일 생성: jsonl에서 사용자 메시지·로컬 커맨드 추출.

## jsonl 레코드 → 입력 유형 매핑

Claude Code가 세션 jsonl에 기록하는 레코드 중 사용자 입력으로 분류되는 것:

  type=user, <command-name> 없음  → 일반 텍스트 (kind="user")
  type=user, <command-name> 있음  → 슬래시 커맨드 (kind="slash_command")
  type=system, subtype=local_command, stdout 없음  → ! 로컬 커맨드 (kind="local_command")

## 슬래시 커맨드 command-name 포맷

jsonl의 command-name 값은 플러그인 네임스페이스 포함 형태로 저장된다:
  /history:history  →  /history
  /plugin:install   →  /plugin
패턴 `/[^:<\\s]+` 로 `:` 이전까지만 추출해 사용자가 입력한 것과 동일하게 표시한다.

## 제외 대상 (노이즈 필터)

  - isMeta=true 계열: skill 주입 ("Base directory for this skill:"), caveat, skill listing
  - 시스템 출력: <local-command-stdout> 포함 항목
  - Claude 컨텍스트 헤더: "# Context Usage" 로 시작하는 메시지

[유지보수 주의]
"Base directory for this skill:" 마커가 없는 새로운 스킬 주입 포맷이 생기면
SKILL.md 내용이 user-prompts.md에 그대로 기록될 수 있다 — main.py 의 유지보수 주의
섹션 참고.
"""
import re
import sys
from pathlib import Path
from common.jsonl import find_jsonl, parse_jsonl, get_session_start
from common.time_util import parse_iso, fmt_local


def extract_entries(records: list[dict]) -> list[dict]:
    """jsonl 레코드 목록에서 기록할 항목(user 메시지, 로컬 커맨드)을 추출한다.

    반환값: [{"ts": ISO문자열|None, "kind": str, "text": str}, ...]
      kind 값: "user" | "slash_command" | "local_command"
    """
    entries = []
    for d in records:
        t = d.get("type", "")

        if t == "user":
            msg = d.get("message", {})
            if msg.get("role") != "user":
                continue

            # content는 문자열 또는 텍스트 블록 리스트 두 가지 형태로 온다
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

            # ── 슬래시 커맨드 ──────────────────────────────────────────────
            # <command-name> 태그가 있으면 슬래시 커맨드로 처리한다.
            # command-name 원본을 그대로 사용한다 (/history:history, /superpowers:brainstorming 등).
            # namespace 제거를 하면 /superpowers:brainstorming → /superpowers 처럼 정보 손실 발생.
            # command-args가 있으면 공백으로 이어 붙인다: /history:history all
            if "<command-name>" in text:
                cmd_match = re.search(r"<command-name>(/\S+)</command-name>", text)
                args_match = re.search(r"<command-args>(.*?)</command-args>", text, re.DOTALL)
                if cmd_match:
                    cmd = cmd_match.group(1)
                    args = args_match.group(1).strip() if args_match else ""
                    full_cmd = f"{cmd} {args}".strip() if args else cmd
                    ts_str = d.get("timestamp") or d.get("message", {}).get("timestamp")
                    entries.append({"ts": ts_str, "kind": "slash_command", "text": full_cmd})
                # command 태그가 있으면 슬래시 커맨드든 아니든 여기서 처리 종료
                continue

            # ── 노이즈 필터 ────────────────────────────────────────────────
            if re.match(r"#{0,3}\s*Context Usage", text):
                continue

            # skill 로딩 메시지: Claude Code가 스킬 호출 시 SKILL.md 내용을 user 메시지로
            # 주입하는데, "Base directory for this skill:" 마커로 감지해 제외한다.
            # [유지보수] Claude Code가 주입 포맷을 바꾸면 이 마커가 없어질 수 있음 → main.py 참고
            if "Base directory for this skill:" in text:
                continue

            # ! 로컬 커맨드 실행 결과 출력 (type=user로 오는 stdout 케이스)
            if "<local-command-stdout>" in text:
                continue

            # local-command-caveat: 로컬 커맨드 주의 문구 태그, 제거 후 빈 텍스트면 제외
            if "<local-command-caveat>" in text:
                text = re.sub(r"<local-command-caveat>.*?</local-command-caveat>", "", text, flags=re.DOTALL).strip()
                if not text:
                    continue

            ts_str = d.get("timestamp") or d.get("message", {}).get("timestamp")
            entries.append({"ts": ts_str, "kind": "user", "text": text})

        elif t == "system" and d.get("subtype") == "local_command":
            # ── ! 로컬 커맨드 ─────────────────────────────────────────────
            # stdout이 있는 레코드는 명령 실행 결과이므로 제외, 명령 자체만 기록한다.
            content = d.get("content", "")
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
    파일 상단에 원본 jsonl 경로를 헤더로 기록한다.
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

    # 헤더: 원본 jsonl 경로를 명시해 어느 세션 데이터인지 추적 가능하게 한다
    header = f'원본 경로: `{jsonl_path}`\n\n---'
    prompt_lines = [header]
    for e in entries:
        ts = e.get("ts")
        try:
            label = fmt_local(parse_iso(ts)) if ts else fallback_ts
        except Exception:
            label = fallback_ts
        # slash_command는 / 자체가 prefix 역할을 하므로 별도 prefix 불필요
        kind_prefix = "" if e["kind"] in ("user", "slash_command") else f"[{e['kind']}] "
        prompt_lines.append(f"[{label}]\n{kind_prefix}{e['text']}")

    out_file = out_dir / "user-prompts.md"
    out_file.write_text("\n\n".join(prompt_lines), encoding="utf-8")
    return len(entries)
