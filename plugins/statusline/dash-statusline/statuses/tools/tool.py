from collections import Counter

from domain.monitor.status.tools.tool import ToolItemData
from domain.monitor.status.tools.events import ToolsEventUse, ToolsEventResult
from statuses.tools._reader import _tool_target


class ToolParser:
    def __init__(self):
        self._running = {}
        self._done = []

    def reset(self):
        self._running = {}
        self._done = []

    def on_use(self, ev: ToolsEventUse):
        self._running[ev.tid] = {'name': ev.name, 'target': _tool_target(ev.name, ev.inp)}

    def on_result(self, ev: ToolsEventResult):
        item = self._running.pop(ev.tid, None)
        if item:
            self._done.append(item)

    def result(self) -> ToolItemData:
        return ToolItemData(running=list(self._running.values()), done=list(self._done))

    def render_summary(self, data: ToolItemData, palette, style) -> str:
        parts = []
        if data.running:
            parts.append(f'{palette.warn}{data.running[-1]["name"]}{palette.reset}')
        if data.done:
            top = '·'.join(n for n, _ in Counter(t['name'] for t in data.done).most_common(3))
            parts.append(f'{palette.dim}{top} \U0001f51a{palette.reset}')
        return '\U0001f527' + (' ' + ' '.join(parts) if parts else '')

    def render_detail(self, data: ToolItemData, palette, style) -> str:
        PT = '\U0001d413 '
        texts = []
        for t in data.running:
            txt = f'{t["name"]}: {t["target"]}' if t.get('target') else t['name']
            texts.append(f'{palette.warn}{txt}{palette.reset}')
        for t in data.done:
            txt = f'{t["name"]}: {t["target"]}' if t.get('target') else t['name']
            texts.append(f'{palette.dim}{txt}{palette.reset}')
        return PT + '·'.join(texts) if texts else ''
