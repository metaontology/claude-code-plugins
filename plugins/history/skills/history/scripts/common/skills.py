"""디스크에 실물이 있는 skill 이름을 모은다 — 내장/비내장 판정의 근거.

Claude Code는 내장 skill을 바이너리에 등록하므로 **파일이 없다.** 사람이 가져온 것만
파일을 가지므로 판정은 **여집합**으로 한다 — 여기서 찾지 못한 이름이 내장이다.
내장 이름을 열거하는 방식은 릴리스마다 낡지만 이 방식은 낡지 않는다.

근거와 한계의 전문은 이웃 작업공간의
`dev/skills/dash-statusline/docs/guides/스킬-내장-구분.md`가 갖는다.

**네임스페이스가 붙은 이름(`plugin:skill`·`git:git-commit`)은 모으지 않는다.** 콜론은
파일에서 왔다는 충분조건이라 화면이 이름만 보고 판정할 수 있고, 그쪽이 디스크 상태와
무관하게 언제나 옳다.
"""
import os
from pathlib import Path

# 상향 탐색의 무한 루프 방지 상한. 종료 조건이 아니다 — 경계는 git root와 home이다
_WALK_UP_LIMIT = 40

# skill 파일이 사는 하위 디렉토리. `commands/`도 같은 엔진이 skill로 등록한다
_SUBDIRS = ("skills", "commands")


def config_home() -> Path:
    """user scope의 기준 디렉토리.

    `CLAUDE_CONFIG_DIR`이 있으면 그쪽이다 — Claude Code의 `getClaudeConfigHomeDir()`와
    같은 규칙이다. 이 프로젝트 자신의 설정을 담는 `paths.USER_CONFIG_DIR`과는 별개다.
    """
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(override) if override else Path.home() / ".claude"


def _is_repo_root(directory: Path) -> bool:
    """git root인가. worktree에서는 `.git`이 디렉토리가 아니라 **파일**이다."""
    return (directory / ".git").exists()


def project_claude_dirs(start: Path) -> list[Path]:
    """`start`에서 위로 올라가며 만나는 `.claude/` 디렉토리들.

    **git root를 처리한 뒤 멈춘다.** repo 밖 조상의 skill은 Claude Code가 로드하지
    않으므로, 넘어가면 없는 파일을 근거로 비내장이라 판정하게 된다.

    **home에서도 멈춘다.** 그쪽은 `config_home()`이 user scope로 따로 보므로 여기서
    또 훑으면 같은 디렉토리를 두 번 읽는다.
    """
    home = Path.home()
    found: list[Path] = []
    current = start
    for _ in range(_WALK_UP_LIMIT):
        # home은 담기 **전에** 멈춘다. `config_home()`이 이미 보므로 담으면 같은
        # 디렉토리를 두 번 읽는다
        if current == home:
            break
        candidate = current / ".claude"
        if candidate.is_dir():
            found.append(candidate)
        if _is_repo_root(current) or current == current.parent:
            break
        current = current.parent
    return found


def _names_in(base: Path) -> set[str]:
    """`.claude/` 하나에서 skill 이름을 모은다.

    세 형태를 받는다 — `skills/{이름}/SKILL.md` · `commands/{이름}/SKILL.md` ·
    `commands/{이름}.md`. 마지막은 폴더 없이 파일 하나로 오는 legacy 형태다.

    **`SKILL.md`가 없는 디렉토리는 skill이 아니다.** 실물에서 그런 디렉토리가 관측된다
    (`skills/` 아래에 스크립트나 자료만 둔 것).
    """
    names: set[str] = set()
    for subdir in _SUBDIRS:
        directory = base / subdir
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if (entry / "SKILL.md").is_file():
                    names.add(entry.name)
            elif subdir == "commands" and entry.suffix == ".md":
                names.add(entry.stem)
    return names


def local_skill_names(project_root: Path) -> list[str]:
    """디스크에 실물이 있는 skill 이름. 정렬된 목록이다.

    user scope를 먼저 보고 프로젝트에서 위로 올라가며 만나는 `.claude/`를 더한다.
    집합이 아니라 정렬된 목록으로 돌려주는 이유는 세션 값과 같다 — `set`은 JSON으로
    직렬화되지 않고, 순서가 정해지지 않으면 원본이 그대로인데도 산출물의 바이트가
    실행마다 달라진다.
    """
    names = _names_in(config_home())
    for base in project_claude_dirs(project_root):
        names |= _names_in(base)
    return sorted(names)
