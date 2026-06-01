import json
import os

from domain.monitor.status.model import ModelData


def _convert_display_name(model_full: str) -> str:
    parts = model_full.split()
    if len(parts) >= 2:
        short = f'{parts[0].lower()}-{parts[1]}'
    elif parts:
        short = parts[0].lower()
    else:
        short = ''
    if '1M' in model_full:
        short += '[1m]'
    return short


def _read_permission_mode(transcript_path: str) -> str:
    if not transcript_path or not os.path.exists(transcript_path):
        return ''
    try:
        with open(transcript_path, encoding='utf-8', errors='replace') as f:
            lines = f.readlines()[-500:]
        mode = ''
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if 'permissionMode' in ev:
                mode = ev['permissionMode']
            if ev.get('type') == 'permission-mode':
                # 구 포맷 호환: 별도 "permission-mode" 타입 이벤트로 기록되던 시기
                mode = ev.get('permissionMode', '')
        return mode
    except Exception:
        return ''


def parse(raw: dict, transcript_path: str = '') -> ModelData:
    model_full = (raw.get('model') or {}).get('display_name', '')
    return ModelData(
        display_name=model_full,
        display_name_short=_convert_display_name(model_full),
        permission_mode=_read_permission_mode(transcript_path),
    )


def render(data: ModelData, palette, style) -> str:
    return f'✨ {palette.accent}[{data.display_name}]{palette.reset}'
