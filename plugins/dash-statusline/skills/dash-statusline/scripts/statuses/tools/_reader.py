import json
import os
import time
from datetime import datetime

from domain.monitor.status.tools.events import (
    ToolsEventUse,
    ToolsEventResult,
    ToolsEventTurnBoundary,
)

# 내장 에이전트는 ඞ, 사용자 정의 에이전트는 👾 로 구분 (builtInAgents.ts 기준)
BUILTIN_AGENT_TYPES = frozenset({
    'Explore', 'Plan', 'general-purpose',
    'claude-code-guide', 'statusline-setup', 'verification',
})

# 내장 skill은 𓌜, 비내장(plugin/custom)은 🪓 로 구분
BUILTIN_SKILLS = frozenset({
    'update-config', 'keybindings-help', 'simplify',
    'fewer-permission-prompts', 'loop', 'claude-api',
    'init', 'review', 'security-review',
})


def _parse_ts(ts_str):
    if not ts_str:
        return time.time()
    try:
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00')).timestamp()
    except Exception:
        return time.time()


def fmt_elapsed(secs):
    if secs < 1:
        return '<1s'
    if secs < 60:
        return f'{int(secs)}s'
    m, s = divmod(int(secs), 60)
    return f'{m}m{s:02d}s'


def _tool_target(name, inp):
    for key in ('file_path', 'path', 'pattern'):
        val = inp.get(key, '')
        if val:
            return os.path.basename(str(val))[:20]
    cmd = inp.get('command', '')
    if cmd:
        return str(cmd).split()[0][:20]
    return ''


def _agent_emoji(subagent_type):
    return 'ඞ' if subagent_type in BUILTIN_AGENT_TYPES else '👾'


def _skill_emoji(skill_name):
    return '𓌜' if skill_name in BUILTIN_SKILLS else '🪓'


def _classify(name):
    if name == 'Agent':
        return 'agent'
    if name == 'Skill':
        return 'skill'
    if name == 'TodoWrite':
        return 'todo'
    if name.startswith('mcp__'):
        return 'mcp'
    return 'tool'


def read_events(path):
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.readlines()[-500:]
    except Exception:
        return
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get('isSidechain'):
            continue
        ev_type = ev.get('type', '')
        ts = _parse_ts(ev.get('timestamp', ''))
        msg = ev.get('message') or {}
        content = msg.get('content', [])

        if ev_type == 'user':
            if ev.get('isMeta'):
                continue
            if isinstance(content, str):
                # 사람이 직접 입력한 턴 — 문자열 content는 새 대화 시작
                yield ToolsEventTurnBoundary()
                continue
            if not isinstance(content, list):
                continue
            has_text = any(b.get('type') == 'text' for b in content if isinstance(b, dict))
            has_result = any(b.get('type') == 'tool_result' for b in content if isinstance(b, dict))
            if has_text and not has_result:
                # tool_result 없는 text-only user 메시지도 새 턴으로 간주
                yield ToolsEventTurnBoundary()
            else:
                for b in content:
                    if isinstance(b, dict) and b.get('type') == 'tool_result':
                        yield ToolsEventResult(tid=b.get('tool_use_id', ''), ts=ts)
        elif ev_type == 'assistant':
            if not isinstance(content, list):
                continue
            for b in content:
                if not isinstance(b, dict) or b.get('type') != 'tool_use':
                    continue
                name = b.get('name', '')
                inp = b.get('input') or {}
                yield ToolsEventUse(
                    tid=b.get('id', ''),
                    name=name,
                    inp=inp,
                    ts=ts,
                    kind=_classify(name),
                )
