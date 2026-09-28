"""키워드 훅(hooks/prompt_keyword.py)을 subprocess로 실제 실행해 stdin → stdout 계약을 본다."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parents[2] / "hooks"
SCRIPT = HOOKS_DIR / "prompt_keyword.py"


def run_hook(stdin: bytes) -> subprocess.CompletedProcess:
    """훅 스크립트에 바이트를 넣고 실행 결과를 돌려준다."""
    return subprocess.run(
        [sys.executable, str(SCRIPT)], input=stdin, capture_output=True, timeout=10
    )


def prompt_bytes(prompt) -> bytes:
    return json.dumps({"prompt": prompt, "hook_event_name": "UserPromptSubmit"}).encode("utf-8")


@pytest.mark.parametrize("prompt", ["hh", "history", "히스토리", "HH", "  History  ", "히스토리\n"])
def test_keyword_emits_context(prompt):
    result = run_hook(prompt_bytes(prompt))
    assert result.returncode == 0
    lines = result.stdout.decode("utf-8").strip().splitlines()
    assert len(lines) == 1
    output = json.loads(lines[0])["hookSpecificOutput"]
    assert output["hookEventName"] == "UserPromptSubmit"
    assert "history:history" in output["additionalContext"]


@pytest.mark.parametrize("prompt", ["hh 봐줘", "/history", "histories", ""])
def test_non_keyword_is_silent(prompt):
    result = run_hook(prompt_bytes(prompt))
    assert result.returncode == 0
    assert result.stdout == b""


@pytest.mark.parametrize("stdin", [b"{broken", b"[]", b"{}", b'{"prompt": 1}', b"\xff\xfe"])
def test_bad_input_is_silent(stdin):
    result = run_hook(stdin)
    assert result.returncode == 0
    assert result.stdout == b""


def test_hooks_json_points_to_script():
    config = json.loads((HOOKS_DIR / "hooks.json").read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for group in config["hooks"]["UserPromptSubmit"]
        for hook in group["hooks"]
    ]
    assert any("${CLAUDE_PLUGIN_ROOT}/skills/history/hooks/prompt_keyword.py" in c for c in commands)
