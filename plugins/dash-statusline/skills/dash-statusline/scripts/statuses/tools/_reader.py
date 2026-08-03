import json
import os
import time
from datetime import datetime
from functools import lru_cache

from domain.monitor.status.tools.events import (
    ToolsEventUse,
    ToolsEventResult,
    ToolsEventTurnBoundary,
)

# 두 목록은 기억이나 세션 관측으로 채우지 않는다 — references/claude-code-main/에서 뽑는다.
#   내장 agent: grep -rn "agentType:" src/tools/AgentTool/built-in/
#   내장 skill: grep -rn "name: '" src/skills/bundled/*.ts
#   등록 조건 : src/skills/bundled/index.ts 의 initBundledSkills() 본문
# initBundledSkills()에서 feature flag 아래 등록되는 것(loop·schedule·claude-api·
# claude-in-chrome)도 목록에는 넣는다. 판정이 답하는 물음은 "이 환경에 켜져 있는가"가
# 아니라 "Claude Code가 기본 제공하는가"이고, 꺼져 있으면 그 이름이 애초에 호출되지 않는다.

# 내장 에이전트는 ඞ, 사용자 정의 에이전트는 👾 로 구분 (builtInAgents.ts 기준)
BUILTIN_AGENT_TYPES = frozenset({
    'Explore', 'Plan', 'general-purpose',
    'claude-code-guide', 'statusline-setup', 'verification',
})

# 내장 skill은 𓌜, 비내장(plugin/custom)은 🪓 로 구분.
#
# 판정은 이 목록을 뒤지는 것이 아니라 **여집합**으로 한다(_skill_emoji 참조).
# 비내장 skill은 셋 중 하나에서 오고 셋 모두 실물 파일을 가지기 때문이다.
#   1. plugin      → 이름에 네임스페이스가 붙는다: plugin:skill
#   2. user scope  → ~/.claude/skills/<name>/SKILL.md
#   3. project scope → <프로젝트>/.claude/skills/<name>/SKILL.md
# 내장만 파일이 없다 — initBundledSkills()가 바이너리에 등록하기 때문이다.
# 그래서 이 상수는 **파일 탐색이 불가능할 때만 쓰는 fallback**이다. 목록이 낡아도
# 평소 판정은 틀리지 않는다. src/commands/ 에 있는 것(/init·/review·/security-review)은
# 슬래시 커맨드라 넣지 않는다 — Skill 호출의 input.skill로 오지 않는다.
BUILTIN_SKILLS = frozenset({
    # 위 grep으로 확인한 것
    'batch', 'claude-api', 'claude-in-chrome', 'debug', 'keybindings-help',
    'loop', 'lorem-ipsum', 'remember', 'schedule', 'simplify', 'skillify',
    'stuck', 'update-config', 'verify',
    # 실물 세션의 skill 목록에서만 관측된 것 — 네임스페이스가 없고 디스크에도 없으니
    # 내장이다(~/.claude/skills/·프로젝트 .claude/skills/ 어디에도 파일이 없다).
    # references를 새로 받아 대조할 때는 이 묶음만 확인하면 된다(2026-08-03).
    # 'run'은 index.ts의 RUN_SKILL_GENERATOR 플래그가 등록하는 것으로 보이나
    # runSkillGenerator.js가 스냅샷에 없어 확정 근거는 관측뿐이다
    'fewer-permission-prompts', 'dataviz', 'artifact-design',
    'artifact-capabilities', 'run',
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


# 판정의 전문은 docs/guides/스킬-내장-구분.md 에 있다.
# 탐색 경로는 loadSkillsDir.ts의 getSkillDirCommands()와 markdownConfigLoader.ts의
# loadMarkdownFilesForSubdir()이 단일 진실이다. 비내장 출처는 여섯이고 아래 넷을 본다.
#   1. plugin              → 이름에 네임스페이스(:)가 붙는다. 파일을 볼 필요가 없다
#   2. user scope          → <config home>/skills/·commands/
#   3. project scope       → <dir>/.claude/skills/·commands/ (git root까지 상향)
#   4. legacy commands     → 위 두 곳의 commands/. 내부적으로 같은 skill 엔진을 쓴다
# 보지 못하는 둘은 아래와 같다. 둘 다 statusline이 알 수 없는 정보라 원리적 한계다.
#   - managed(정책) — getManagedFilePath()/.claude/skills. 플랫폼별 경로이고
#     getManagedFilePath()가 references 스냅샷에 없어 확정할 수 없다
#   - --add-dir — <dir>/.claude/skills. 그 목록이 statusline stdin에 오지 않는다
_WALK_UP_LIMIT = 40  # 무한 루프 방지 상한. 정상 종료는 git root 또는 home이다


def _config_home():
    """Claude Code의 설정 홈. envUtils.ts의 getClaudeConfigHomeDir()와 같은 규칙이다."""
    return (os.environ.get('CLAUDE_CONFIG_DIR')
            or os.path.join(os.path.expanduser('~'), '.claude'))


def _has_skill_under(claude_dir, skill_name):
    """<claude_dir>의 skills/·commands/ 에서 skill 실물을 찾는다.

    commands/ 도 보는 이유는 그것도 skill이기 때문이다 — loadSkillsFromCommandsDir()가
    같은 엔진으로 등록하고 input.skill로 온다. 디렉토리 형식과 단일 .md 형식을 모두 받는다.
    """
    return (
        os.path.isfile(os.path.join(claude_dir, 'skills', skill_name, 'SKILL.md'))
        or os.path.isfile(os.path.join(claude_dir, 'commands', skill_name, 'SKILL.md'))
        or os.path.isfile(os.path.join(claude_dir, 'commands', skill_name + '.md'))
    )


def _project_claude_dirs(cwd):
    """cwd에서 위로 올라가며 <dir>/.claude 를 넘긴다.

    getProjectDirsUpToHome()·resolveStopBoundary()와 같이 **git root에서 멈춘다.**
    경계를 넘어가면 Claude Code가 로드하지 않는 것까지 비내장으로 오판한다.
    home은 user scope로 따로 보므로 도달하면 멈춘다.
    """
    home = os.path.normcase(os.path.abspath(os.path.expanduser('~')))
    d = os.path.abspath(cwd)
    for _ in range(_WALK_UP_LIMIT):
        if os.path.normcase(d) == home:
            return
        yield os.path.join(d, '.claude')
        git = os.path.join(d, '.git')
        if os.path.isdir(git) or os.path.isfile(git):  # worktree는 .git이 파일이다
            return
        parent = os.path.dirname(d)
        if parent == d:
            return
        d = parent


@lru_cache(maxsize=256)
def _skill_file_on_disk(skill_name, cwd):
    """비내장 skill의 실물 파일을 찾는다.

    Returns:
        True: 찾았다(=비내장). False: 없다(=내장). None: 판정 불가.
    """
    if not skill_name or skill_name in ('.', '..'):
        return False
    if any(c in skill_name for c in ('/', '\\', ':')):
        # 네임스페이스가 붙은 이름은 _skill_emoji에서 이미 걸러진다. 경로 조각이 섞인
        # 이름은 JSONL에서 온 외부 입력이므로 탐색하지 않는다
        return False
    # user scope — 설정 홈은 항상 조회 가능하다
    if _has_skill_under(_config_home(), skill_name):
        return True
    if not cwd or not os.path.isdir(cwd):
        # 프로젝트가 지워졌거나 남의 세션을 재생하는 중이다. 파일이 없다고 단정할 수 없다
        return None
    for claude_dir in _project_claude_dirs(cwd):
        if _has_skill_under(claude_dir, skill_name):
            return True
    return False


def _skill_emoji(skill_name, cwd=''):
    if ':' in skill_name:
        # 네임스페이스가 붙었다 = 파일에서 온 것이다. plugin(`superpowers:brainstorming`)
        # 뿐 아니라 중첩 디렉토리도 이렇게 온다 — buildNamespace()가 상대경로를
        # ':'로 이어붙이므로 .claude/skills/git/git-commit/ 은 `git:git-commit`이다.
        # 어느 쪽이든 비내장이고, 내장 skill에는 네임스페이스가 붙지 않는다.
        return '🪓'
    found = _skill_file_on_disk(skill_name, cwd)
    if found is None:
        return '𓌜' if skill_name in BUILTIN_SKILLS else '🪓'
    return '🪓' if found else '𓌜'


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
