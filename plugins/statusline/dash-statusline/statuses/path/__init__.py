import os

from domain.monitor.status.path import PathData


def parse(raw: dict) -> PathData:
    full = (raw.get('workspace') or {}).get('current_dir', '')
    return PathData(full=full, parent=os.path.dirname(full), last=os.path.basename(full))


def render(data: PathData, palette, style) -> str:
    return f'📁 {data.parent}/{palette.highlight}{data.last}{palette.reset}'
