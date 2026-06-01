import subprocess

from domain.monitor.status.git import GitData


def parse() -> GitData:
    try:
        r = subprocess.run(
            ['git', 'branch', '--show-current'],
            capture_output=True, text=True, timeout=5,
        )
        branch = r.stdout.strip() if r.returncode == 0 else ''
    except Exception:
        branch = ''
    return GitData(branch=branch)


def render(data: GitData, palette, style) -> str:
    return f'🌿 {data.branch}' if data.branch else ''
