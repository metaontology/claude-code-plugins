from collections import Counter

from domain.monitor.status.tools.skill import SkillItemData
from domain.monitor.status.tools.events import ToolsEventUse, ToolsEventResult
from statuses.tools._reader import _skill_emoji


class SkillParser:
    def __init__(self, cwd=''):
        # 내장/비내장 판정에 project scope(.claude/skills/)를 뒤지므로 cwd가 필요하다
        self._cwd = cwd
        self._running = {}
        self._done = []

    def reset(self):
        self._running = {}
        self._done = []

    def on_use(self, ev: ToolsEventUse):
        name = ev.inp.get('skill', 'skill')
        self._running[ev.tid] = f'{_skill_emoji(name, self._cwd)} {name}'

    def on_result(self, ev: ToolsEventResult):
        item = self._running.pop(ev.tid, None)
        if item:
            self._done.append(item)

    def result(self) -> SkillItemData:
        return SkillItemData(running=list(self._running.values()), done=list(self._done))

    def render_summary(self, data: SkillItemData, palette, style) -> str:
        parts = []
        if data.running:
            parts.append(f'{palette.warn}{data.running[-1]}{palette.reset}')
        if data.done:
            top = '·'.join(n for n, _ in Counter(data.done).most_common(2))
            parts.append(f'{palette.dim}{top} \U0001f51a{palette.reset}')
        return '\U0001fa9a' + (' ' + ' '.join(parts) if parts else '')

    def render_detail(self, data: SkillItemData, palette, style) -> str:
        PS = '\U0001d412 '
        texts = (
            [f'{palette.warn}{s}{palette.reset}' for s in data.running] +
            [f'{palette.dim}{s}{palette.reset}' for s in data.done]
        )
        return PS + '·'.join(texts) if texts else ''
