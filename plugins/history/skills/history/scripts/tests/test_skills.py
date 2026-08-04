import common.skills as skills
from common.skills import config_home, local_skill_names, project_claude_dirs


def _skill(base, subdir, name, filename="SKILL.md"):
    """`base/.claude/{subdir}/{name}/SKILL.md`를 만든다."""
    directory = base / ".claude" / subdir / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_text("# skill", encoding="utf-8")
    return directory


def _isolate(tmp_path, monkeypatch):
    """홈과 설정 홈을 임시 디렉토리로 돌린다.

    `Path.home()`을 돌리지 않으면 실제 홈의 `~/.claude/skills/`가 user scope로 섞여
    테스트가 실행 머신의 상태에 좌우된다.

    **`tmp_path`에 `.git`을 두는 것이 그것만큼 중요하다.** 가짜 홈은 `tmp_path` 안에
    있는데 대상 프로젝트는 그 형제일 수 있어서, 경계가 없으면 상향 탐색이 가짜 홈을
    만나지 못한 채 진짜 홈까지 거슬러 올라가 그쪽 `.claude/`를 project scope로 훑는다.
    """
    home = tmp_path / "home"
    home.mkdir()
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(skills.Path, "home", staticmethod(lambda: home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    return home


# ── user scope ─────────────────────────────────────────────────────────────

def test_user_scope_skill_is_found(tmp_path, monkeypatch):
    home = _isolate(tmp_path, monkeypatch)
    _skill(home, "skills", "clip")
    project = tmp_path / "proj"
    project.mkdir()
    assert local_skill_names(project) == ["clip"]


def test_config_home_follows_env(tmp_path, monkeypatch):
    """`CLAUDE_CONFIG_DIR`이 있으면 user scope의 기준이 그쪽으로 옮겨간다."""
    _isolate(tmp_path, monkeypatch)
    elsewhere = tmp_path / "elsewhere"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(elsewhere))
    assert config_home() == elsewhere


def test_directory_without_skill_md_is_not_a_skill(tmp_path, monkeypatch):
    """`skills/` 아래의 자료 디렉토리를 skill로 세지 않는다 — 실물에서 관측된다."""
    home = _isolate(tmp_path, monkeypatch)
    (home / ".claude" / "skills" / "scripts").mkdir(parents=True)
    project = tmp_path / "proj"
    project.mkdir()
    assert local_skill_names(project) == []


# ── commands/ 두 형식 ───────────────────────────────────────────────────────

def test_commands_directory_form(tmp_path, monkeypatch):
    """`commands/{이름}/SKILL.md`도 skill이다 — 같은 엔진이 등록한다."""
    home = _isolate(tmp_path, monkeypatch)
    _skill(home, "commands", "deploy")
    project = tmp_path / "proj"
    project.mkdir()
    assert local_skill_names(project) == ["deploy"]


def test_commands_single_file_form(tmp_path, monkeypatch):
    """`commands/{이름}.md`는 폴더 없이 파일 하나로 온다."""
    home = _isolate(tmp_path, monkeypatch)
    directory = home / ".claude" / "commands"
    directory.mkdir(parents=True)
    (directory / "deploy.md").write_text("# cmd", encoding="utf-8")
    project = tmp_path / "proj"
    project.mkdir()
    assert local_skill_names(project) == ["deploy"]


def test_single_file_form_only_in_commands(tmp_path, monkeypatch):
    """`skills/{이름}.md`는 받지 않는다. 그쪽은 디렉토리 형식뿐이다."""
    home = _isolate(tmp_path, monkeypatch)
    directory = home / ".claude" / "skills"
    directory.mkdir(parents=True)
    (directory / "stray.md").write_text("# not a skill", encoding="utf-8")
    project = tmp_path / "proj"
    project.mkdir()
    assert local_skill_names(project) == []


# ── project scope와 상향 탐색 ───────────────────────────────────────────────

def test_project_scope_and_walk_up(tmp_path, monkeypatch):
    """하위 디렉토리에서 시작해도 위쪽 `.claude/`를 찾는다."""
    _isolate(tmp_path, monkeypatch)
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    _skill(root, "skills", "history")
    deep = root / "a" / "b"
    deep.mkdir(parents=True)
    assert local_skill_names(deep) == ["history"]


def test_walk_up_stops_after_git_root(tmp_path, monkeypatch):
    """repo 밖 조상의 skill은 Claude Code가 로드하지 않으므로 세지 않는다."""
    _isolate(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    _skill(outside, "skills", "outsider")
    root = outside / "repo"
    (root / ".git").mkdir(parents=True)
    _skill(root, "skills", "inside")
    assert local_skill_names(root) == ["inside"]


def test_git_file_is_a_boundary_too(tmp_path, monkeypatch):
    """worktree에서는 `.git`이 디렉토리가 아니라 파일이다."""
    _isolate(tmp_path, monkeypatch)
    outside = tmp_path / "outside"
    _skill(outside, "skills", "outsider")
    root = outside / "wt"
    root.mkdir(parents=True)
    (root / ".git").write_text("gitdir: /elsewhere", encoding="utf-8")
    assert local_skill_names(root) == []


def test_home_is_a_boundary(tmp_path, monkeypatch):
    """home에 닿으면 멈춘다. 그쪽은 user scope가 이미 본다."""
    home = _isolate(tmp_path, monkeypatch)
    _skill(home, "skills", "clip")
    project = home / "work"
    project.mkdir()
    assert local_skill_names(project) == ["clip"]
    assert home / ".claude" not in project_claude_dirs(project)


# ── 합집합과 형태 ───────────────────────────────────────────────────────────

def test_scopes_merge_without_duplicates(tmp_path, monkeypatch):
    home = _isolate(tmp_path, monkeypatch)
    _skill(home, "skills", "clip")
    _skill(home, "skills", "shared")
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    _skill(root, "skills", "shared")
    _skill(root, "skills", "history")
    assert local_skill_names(root) == ["clip", "history", "shared"]


def test_missing_directories_are_not_an_error(tmp_path, monkeypatch):
    """`.claude/`도 프로젝트도 없는 환경에서 빈 목록이 나온다."""
    _isolate(tmp_path, monkeypatch)
    assert local_skill_names(tmp_path / "nowhere") == []
