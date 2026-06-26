import glob
import json
import os
import time

from domain.monitor.status.tools.agent import AgentItemData
from domain.monitor.status.tools.events import ToolsEventUse, ToolsEventResult
from statuses.tools._reader import _agent_emoji, fmt_elapsed, _parse_ts


# subagent JSONL의 message.model은 API 레벨 ID ("claude-sonnet-4-6")로 기록됨.
# Claude Code 설정의 "[1m]" suffix는 subagent 단에서 판별 불가 — 모델 미지정 에이전트도 동일.
def _load_subagent_models(transcript_path):
    session_dir = transcript_path.replace('.jsonl', '')
    subagents_dir = os.path.join(session_dir, 'subagents')
    if not os.path.isdir(subagents_dir):
        return {}
    result = {}
    for f in glob.glob(os.path.join(subagents_dir, 'agent-*.jsonl')):
        agentId = os.path.basename(f).replace('agent-', '').replace('.jsonl', '')
        try:
            with open(f, encoding='utf-8', errors='replace') as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    ev = json.loads(line)
                    model = (ev.get('message') or {}).get('model', '')
                    if model:
                        is_1m = '[1m]' in model
                        parts = model.replace('[1m]', '').split('-')
                        if len(parts) >= 4:
                            short = f'{parts[1]}-{parts[2]}.{parts[3]}'
                        elif len(parts) >= 2:
                            short = parts[1]
                        else:
                            short = model
                        if is_1m:
                            short += '[1m]'
                        result[agentId] = short
                        break
        except Exception:
            continue
    return result


# tid(tool_use id)와 agentId는 직접 연결되지 않아 타임스탬프 근접도로 매칭.
# subagent 첫 메시지 ts - Agent tool_use ts 가 0 이상 5초 미만인 가장 가까운 쌍을 연결.
def _build_agent_id_map(transcript_path):
    if not transcript_path or not os.path.exists(transcript_path):
        return {}
    agent_uses = []
    try:
        with open(transcript_path, encoding='utf-8', errors='replace') as f:
            for line in f:
                try:
                    ev = json.loads(line.strip())
                    if ev.get('isSidechain') or ev.get('type') != 'assistant':
                        continue
                    ts = _parse_ts(ev.get('timestamp', ''))
                    for b in (ev.get('message') or {}).get('content') or []:
                        if isinstance(b, dict) and b.get('name') == 'Agent':
                            agent_uses.append({'tid': b['id'], 'ts': ts})
                            break
                except Exception:
                    continue
    except Exception:
        return {}
    session_dir = transcript_path.replace('.jsonl', '')
    subagents_dir = os.path.join(session_dir, 'subagents')
    if not os.path.isdir(subagents_dir):
        return {}
    tid_map = {}
    for f in glob.glob(os.path.join(subagents_dir, 'agent-*.jsonl')):
        agentId = os.path.basename(f).replace('agent-', '').replace('.jsonl', '')
        try:
            with open(f, encoding='utf-8', errors='replace') as fh:
                first = fh.readline().strip()
            agent_ts = _parse_ts(json.loads(first).get('timestamp', ''))
        except Exception:
            continue
        best_tid, best_diff = None, float('inf')
        for au in agent_uses:
            diff = agent_ts - au['ts']
            if 0 <= diff < best_diff:
                best_diff = diff
                best_tid = au['tid']
        if best_tid and best_diff < 5.0:
            tid_map[best_tid] = agentId
    return tid_map


class AgentParser:
    def __init__(self, transcript_path='', cwd=''):
        self._tid_to_agentid = _build_agent_id_map(transcript_path)
        self._agentid_to_model = _load_subagent_models(transcript_path)
        self._running = {}
        self._done = []

    def _agent_model(self, tid):
        return self._agentid_to_model.get(self._tid_to_agentid.get(tid, ''), '')

    def reset(self):
        self._running = {}
        self._done = []

    def on_use(self, ev: ToolsEventUse):
        atype = ev.inp.get('subagent_type', 'agent')
        self._running[ev.tid] = {
            'type': atype,
            'description': (ev.inp.get('description') or '')[:40],
            'start_ts': ev.ts,
            'model': self._agent_model(ev.tid),
            'emoji': _agent_emoji(atype),
        }

    def on_result(self, ev: ToolsEventResult):
        a = self._running.pop(ev.tid, None)
        if a:
            self._done.append({**a, 'elapsed': ev.ts - a['start_ts']})

    def result(self) -> AgentItemData:
        return AgentItemData(running=list(self._running.values()), done=list(self._done))

    def render_summary(self, data: AgentItemData, palette, style) -> str:
        parts = []
        if data.running:
            items = [
                f'{a["emoji"]} {a["type"]} {fmt_elapsed(time.time() - a["start_ts"])}'
                for a in data.running[-2:]
            ]
            parts.append(f'{palette.warn}' + '·'.join(items) + f'{palette.reset}')
        if data.done and not data.running:
            items = [
                f'{a["emoji"]} {a["type"]} {fmt_elapsed(a["elapsed"])}'
                for a in data.done[-2:]
            ]
            parts.append(f'{palette.dim}' + '·'.join(items) + f' \U0001f51a{palette.reset}')
        return '\U0001f60e' + (' ' + ' '.join(parts) if parts else '')

    def render_detail(self, data: AgentItemData, palette, style) -> str:
        PA = '\U0001d400 '
        texts = []
        for a in data.running:
            elapsed = fmt_elapsed(time.time() - a['start_ts'])
            model = a.get('model', '')
            desc = a['description']
            txt = (f'{a["emoji"]} {a["type"]}({model}):{desc} {elapsed}'
                   if model else f'{a["emoji"]} {a["type"]} {desc} {elapsed}')
            texts.append(f'{palette.warn}{txt}{palette.reset}')
        for a in data.done:
            elapsed = fmt_elapsed(a['elapsed'])
            model = a.get('model', '')
            desc = a['description']
            txt = (f'{a["emoji"]} {a["type"]}({model}):{desc} {elapsed}'
                   if model else f'{a["emoji"]} {a["type"]} {desc} {elapsed}')
            texts.append(f'{palette.dim}{txt}{palette.reset}')
        return PA + '·'.join(texts) if texts else ''
