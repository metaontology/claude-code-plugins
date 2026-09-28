"""UserPromptSubmit 훅. 프롬프트가 키워드 한 단어면 history 스킬 실행을 지시한다.

훅은 프롬프트를 바꿔 쓸 수 없으므로 additionalContext로 지시를 덧붙인다.
모든 프롬프트마다 돌기 때문에 어떤 입력에도 오류를 내지 않고 exit 0으로 끝난다.
"""
import json
import sys

# 앞뒤 공백을 빼고 소문자로 바꾼 프롬프트 전체가 이 중 하나일 때만 발동한다
KEYWORDS = frozenset({"hh", "history", "히스토리"})

CONTEXT = (
    "사용자가 키워드로 /history:history 를 요청했습니다. "
    "다른 응답 없이 Skill 도구로 history:history 를 인자 없이 실행하십시오."
)


def match(prompt: str) -> bool:
    """프롬프트가 키워드 한 단어인지 판정한다."""
    return prompt.strip().lower() in KEYWORDS


def main() -> None:
    # Windows 기본 stdin 인코딩은 cp949라 바이트로 읽어 UTF-8로 푼다
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return
    prompt = payload.get("prompt") if isinstance(payload, dict) else None
    if not isinstance(prompt, str) or not match(prompt):
        return
    # ensure_ascii 기본값으로 한글을 \uXXXX로 내보내 콘솔 인코딩과 무관하게 한다
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": CONTEXT,
        }
    }))


if __name__ == "__main__":
    main()
