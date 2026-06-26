from collections import Counter

from domain.monitor.status.tools.mcp import McpItemData
from domain.monitor.status.tools.events import ToolsEventUse, ToolsEventResult


class McpParser:
    def __init__(self):
        self._running = {}
        self._done = []

    def reset(self):
        self._running = {}
        self._done = []

    def on_use(self, ev: ToolsEventUse):
        parts = ev.name.split('__')
        server = parts[1] if len(parts) >= 2 else ev.name
        tool_name = parts[2] if len(parts) >= 3 else ''
        self._running[ev.tid] = f'{server}: {tool_name}' if tool_name else server

    def on_result(self, ev: ToolsEventResult):
        item = self._running.pop(ev.tid, None)
        if item:
            self._done.append(item)

    def result(self) -> McpItemData:
        return McpItemData(running=list(self._running.values()), done=list(self._done))

    def render_summary(self, data: McpItemData, palette, style) -> str:
        parts = []
        if data.running:
            parts.append(f'{palette.warn}{data.running[-1]}{palette.reset}')
        if data.done:
            top = '·'.join(k for k, _ in Counter(data.done).most_common(3))
            parts.append(f'{palette.dim}{top} \U0001f51a{palette.reset}')
        return '\U0001f9ca' + (' ' + ' '.join(parts) if parts else '')

    def render_detail(self, data: McpItemData, palette, style) -> str:
        PM = '\U0001d40c '
        texts = (
            [f'{palette.warn}{m}{palette.reset}' for m in data.running] +
            [f'{palette.dim}{m}{palette.reset}' for m in data.done]
        )
        return PM + '·'.join(texts) if texts else ''
