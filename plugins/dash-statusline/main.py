#!/usr/bin/env python3
import json
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows 기본 코드페이지(cp949)는 이모지 등 4바이트 UTF-8 문자를 처리하지 못한다.
# Claude Code(Node.js)가 spawn한 Python 프로세스는 cp949로 초기화되므로
# stdout/stdin 모두 명시적으로 UTF-8로 재설정해야 한다.
#
# stdout: 이모지 출력 시 UnicodeEncodeError 방지
# stdin:  Claude Code가 넘기는 JSON(transcript_path, workspace 등)을 올바르게 파싱하기 위해 필수.
#         stdin을 재설정하지 않으면 cp949로 읽어 JSON 파싱이 실패하고,
#         context 사용량·tool 정보가 모두 init 기본값(0)으로 표시된다.
#
# 주의: `cmd /c chcp 65001 && python ...` 방식은 stdout 인코딩은 해결되지만
#       stdin이 cmd에서 Python으로 전달되지 않아 동일 증상이 발생한다.
#       settings.json command는 python을 직접 호출해야 한다.
if sys.platform == 'win32':
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
    sys.stdin = open(sys.stdin.fileno(), mode='r', encoding='utf-8')

from statuses import context, model, path, git, tools, report, lang
from theme import load_theme
from views import select_view

# [출력 규정]
# 4~5줄을 출력한다. 단, 5줄(🔔)은 init 상태(내용 없음)일 때 생략한다.
#
# 줄별 의존성:
#   1~3줄 (🧩/✨/📁): stdin JSON만으로 렌더링 가능. transcript 없어도 항상 실제 값 표시.
#   4~5줄 (🔧/🔔): transcript JSONL 파싱 결과. transcript 없거나 파싱 실패 시 기본값 표시.
#
# 기본값:
#   4줄: "🔧 | 😎 | 🧊 | 🪚 | 📋"
#   5줄: report 비어있으면 생략
#
# [SIGTERM 캐시]
# Claude Code는 연속 refresh 시 이전 실행에 SIGTERM을 보낸다.
# SIGTERM 수신 시 cache['output']을 재출력하고 종료.
# 출력 전에 SIGTERM이 오면 (cache 비어있으면) 아무것도 출력하지 않는다.
# → 항상 4~5줄 또는 0줄(취소)이 되어 partial 출력이 발생하지 않는다.

cache = {}


def _sigterm(sig, frame):
    out = cache.get('output')
    if out:
        sys.stdout.write(out + '\n')
        sys.stdout.flush()
    sys.exit(0)


signal.signal(signal.SIGTERM, _sigterm)

palette = load_theme('default')
view = select_view('lines')

# --- 언어(IME) 상태 ---
# stdin.read()는 Claude Code가 JSON을 쓸 때까지 블로킹된다.
# 블로킹 중에 사용자가 IME를 전환하면 읽힌 값이 틀려지므로
# stdin 읽기 전에 먼저 캡처해야 프롬프트 submit 시점의 IME 상태를 정확히 반영한다.
try:
    lang_data = lang.parse()
    rendered_lang = lang.render(lang_data, palette, view.style)
except Exception:
    rendered_lang = '🌍 EN'

# --- stdin 파싱 (실패 시 빈 dict로 계속 진행) ---
try:
    raw = json.loads(sys.stdin.read())
except Exception:
    raw = {}

transcript = raw.get('transcript_path', '')
cwd = (raw.get('workspace') or {}).get('current_dir', '')

# --- 1줄: 컨텍스트 (stdin만으로 렌더링) ---
try:
    ctx_data = context.parse(raw)
    rendered_context = context.render(ctx_data, palette, view.style)
except Exception:
    rendered_context = (
        f'🧩 {palette.ok}{"█" * 13}{palette.reset}'
        f' 0% | {palette.orange}$0.00{palette.reset} | 🕒 0m 0s'
    )

# --- 2줄: 모델 (stdin만으로 렌더링) ---
try:
    model_data = model.parse(raw, transcript)
    rendered_model = model.render(model_data, palette, view.style)
except Exception:
    model_data = None
    rendered_model = '✨ ...'

# --- 3줄: 경로 + git (stdin + subprocess로 렌더링) ---
try:
    path_data = path.parse(raw)
    git_data = git.parse()
    rendered_path = path.render(path_data, palette, view.style)
    rendered_git = git.render(git_data, palette, view.style)
except Exception:
    rendered_path = '📁 ...'
    rendered_git = ''

# --- 4~5줄: tools/report (transcript 없으면 기본값) ---
try:
    tools_data = tools.parse(transcript, cwd)
    rendered_tools = tools.render(tools_data, palette, view.style)
    rendered_report = report.render(tools_data, palette, view.style, model_data)
except Exception:
    rendered_tools = '🔧 | 😎 | 🧊 | 🪚 | 📋'
    rendered_report = ''

output = view.assemble(
    context=rendered_context,
    lang=rendered_lang,
    model=rendered_model,
    path=rendered_path,
    git=rendered_git,
    tools=rendered_tools,
    report=rendered_report,
)

# 계산 완료 후 한 번에 출력 — partial 출력 방지
sys.stdout.write(output + '\n')
sys.stdout.flush()
cache['output'] = output
