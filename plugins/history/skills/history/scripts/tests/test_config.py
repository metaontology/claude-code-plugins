"""사용자 설정 파일의 읽기·쓰기와 검증.

경로가 모듈 상수라 픽스처가 그것을 tmp_path로 돌린다. 홈 디렉토리의 실물을 건드리면
테스트가 사용자의 설정을 지운다.
"""
import json
import os
from pathlib import Path

import pytest

import store.config as config
from store.config import (
    DEFAULTS,
    load_config,
    reset_config,
    sanitize,
    save_config,
    with_defaults,
)


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    """설정 파일 경로를 임시 디렉토리로 돌린다."""
    directory = tmp_path / "history"
    path = directory / "config.json"
    monkeypatch.setattr(config, "USER_CONFIG_DIR", directory)
    monkeypatch.setattr(config, "USER_CONFIG_FILE", path)
    return path


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ── 읽기 ─────────────────────────────────────────────────────────────────────


def test_load_missing_file(config_file):
    assert load_config() == {}


def test_load_valid(config_file):
    write(config_file, '{"theme": "dark", "paneWidth": 420}')
    assert load_config() == {"theme": "dark", "paneWidth": 420}


def test_load_broken_json(config_file):
    """사람이 고치다 깨뜨린 파일이 화면을 막지 않는다."""
    write(config_file, "{ theme: dark")
    assert load_config() == {}


def test_load_not_an_object(config_file):
    write(config_file, '["dark"]')
    assert load_config() == {}


def test_load_does_not_create_directory(config_file):
    """읽기는 디스크를 바꾸지 않는다."""
    load_config()
    assert not config_file.parent.exists()


# ── 검증 ─────────────────────────────────────────────────────────────────────


def test_sanitize_drops_unknown_key():
    assert sanitize({"theme": "dark", "colour": "red"}) == {"theme": "dark"}


def test_sanitize_drops_only_the_bad_key():
    """한 값이 틀렸다고 나머지를 버리지 않는다."""
    assert sanitize({"theme": "purple", "paneWidth": 420}) == {"paneWidth": 420}


@pytest.mark.parametrize("value", ["system", "light", "dark"])
def test_sanitize_accepts_each_theme(value):
    assert sanitize({"theme": value}) == {"theme": value}


@pytest.mark.parametrize("value", ["", "System", "auto", None, 1])
def test_sanitize_rejects_bad_theme(value):
    assert sanitize({"theme": value}) == {}


def test_sanitize_accepts_pane_width_bounds():
    assert sanitize({"paneWidth": config.PANE_MIN}) == {"paneWidth": config.PANE_MIN}
    assert sanitize({"paneWidth": config.PANE_MAX}) == {"paneWidth": config.PANE_MAX}


@pytest.mark.parametrize("value", [config.PANE_MIN - 1, config.PANE_MAX + 1, 0, -340])
def test_sanitize_rejects_pane_width_out_of_range(value):
    assert sanitize({"paneWidth": value}) == {}


@pytest.mark.parametrize("value", ["340", 340.0, None])
def test_sanitize_rejects_non_integer_pane_width(value):
    assert sanitize({"paneWidth": value}) == {}


def test_sanitize_rejects_bool_pane_width():
    """bool은 int의 하위 형이라 명시적으로 막지 않으면 True가 1로 통과한다."""
    assert sanitize({"paneWidth": True}) == {}


def test_sanitize_of_non_dict():
    assert sanitize(["dark"]) == {}


# ── 쓰기 ─────────────────────────────────────────────────────────────────────


def test_save_creates_directory(config_file):
    save_config({"theme": "dark"})
    assert config_file.exists()


def test_save_returns_merged(config_file):
    assert save_config({"theme": "dark"}) == {"theme": "dark"}


def test_save_merges_with_existing(config_file):
    """부분 갱신이므로 보내지 않은 키가 살아남는다."""
    save_config({"theme": "dark", "paneWidth": 420})
    merged = save_config({"theme": "light"})
    assert merged == {"theme": "light", "paneWidth": 420}


def test_save_drops_invalid_key(config_file):
    save_config({"theme": "dark", "colour": "red"})
    assert json.loads(config_file.read_text(encoding="utf-8")) == {"theme": "dark"}


def test_save_ignores_invalid_value_keeping_others(config_file):
    save_config({"theme": "dark"})
    save_config({"theme": "purple", "paneWidth": 420})
    assert load_config() == {"theme": "dark", "paneWidth": 420}


def test_save_result_is_readable_back(config_file):
    saved = save_config({"theme": "dark", "paneWidth": 420})
    assert load_config() == saved


def test_save_over_broken_file(config_file):
    """깨진 파일 위에 써도 성공하고, 읽을 수 없던 값은 사라진다.

    **사람이 손으로 깨뜨린 파일은 영구적이다.** 여기서 포기하면 사용자가 설정을 영원히
    바꿀 수 없으므로, 열 수 없는 것(일시적)과 갈라 이쪽은 덮어쓴다.
    """
    write(config_file, "{ broken")
    assert save_config({"theme": "dark"}) == {"theme": "dark"}


# ── 동시 저장 ────────────────────────────────────────────────────────────────
# 설정 파일은 프로젝트마다 갈리지 않고 **하나**다. 프로젝트를 여럿 열면 서버도 여럿이고
# 그것들이 같은 파일에 쓴다. 무엇을 지키고 무엇을 포기하는지는 문서가 갖는다.


def deny_reads(monkeypatch, target, times):
    """대상 파일의 읽기를 `times`번 `PermissionError`로 만든다. 그 뒤로는 정상이다.

    Windows에서 `os.replace`가 도는 순간의 리더가 받는 것이 이 예외다. 실물 경합을
    테스트로 재현할 수 없으므로 그 증상만 주입한다.
    """
    real = Path.read_text
    state = {"left": times}

    def fake(self, *args, **kwargs):
        if self == target and state["left"] > 0:
            state["left"] -= 1
            raise PermissionError(13, "access denied")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake)
    return state


def test_save_writes_through_a_temp_file(config_file, monkeypatch):
    """대상 파일에 직접 쓰지 않는다 — 여는 순간 그것이 0바이트가 된다."""
    seen = []
    real = Path.write_text

    def spy(self, *args, **kwargs):
        seen.append(Path(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", spy)
    save_config({"theme": "dark"})
    assert config_file not in seen


def test_save_replaces_atomically(config_file, monkeypatch):
    """교체 직전에 읽으면 **옛 내용이 온전하다.** 찢어진 상태가 존재하지 않는다."""
    save_config({"theme": "dark", "paneWidth": 420})
    during = []
    real = os.replace

    def spy(src, dst):
        during.append(json.loads(config_file.read_text(encoding="utf-8")))
        return real(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    save_config({"theme": "light"})
    assert during == [{"theme": "dark", "paneWidth": 420}]


def test_save_leaves_no_temp_file(config_file):
    save_config({"theme": "dark"})
    assert [p.name for p in config_file.parent.iterdir()] == [config_file.name]


def test_temp_file_is_removed_when_replace_fails(config_file, monkeypatch):
    """교체가 실패해도 쓰레기를 남기지 않는다."""
    monkeypatch.setattr(os, "replace", lambda src, dst: (_ for _ in ()).throw(
        PermissionError(13, "access denied")))
    save_config({"theme": "dark"})
    leftovers = [p.name for p in config_file.parent.iterdir()]
    assert leftovers == [] or leftovers == [config_file.name]


def test_temp_file_name_carries_the_pid(config_file, monkeypatch):
    """임시파일 이름이 프로세스마다 다르다.

    고정 이름이면 두 프로세스가 같은 임시파일에 써서 **그것이 찢어지고**, 원자적 교체가
    찢어진 내용을 옮긴다.
    """
    seen = []
    real = Path.write_text

    def spy(self, *args, **kwargs):
        seen.append(Path(self).name)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", spy)
    save_config({"theme": "dark"})
    assert any(str(os.getpid()) in name for name in seen)


def test_save_gives_up_when_the_file_cannot_be_read(config_file, monkeypatch):
    """열 수 없으면 **쓰지 않고 None을 돌려준다.**

    여기서 쓰면 병합 근거가 없으므로 patch에 없는 키가 디스크에서 사라진다.
    """
    save_config({"theme": "dark", "paneWidth": 420})
    deny_reads(monkeypatch, config_file, 999)
    assert save_config({"theme": "light"}) is None


def test_giving_up_keeps_the_other_keys(config_file, monkeypatch):
    """포기의 요점은 이것이다 — 파일이 그대로 남는다.

    주입만 거두고 `monkeypatch.undo()`는 쓰지 않는다. 그것은 픽스처가 건 경로 패치까지
    되돌려 **실물 홈의 설정을 읽게 만든다.**
    """
    save_config({"theme": "dark", "paneWidth": 420})
    state = deny_reads(monkeypatch, config_file, 999)
    save_config({"theme": "light"})
    state["left"] = 0
    assert load_config() == {"theme": "dark", "paneWidth": 420}


def test_save_retries_a_transient_read_failure(config_file, monkeypatch):
    """한 번의 실패는 포기 사유가 아니다. 교체는 순간이므로 곧 읽힌다."""
    save_config({"theme": "dark", "paneWidth": 420})
    deny_reads(monkeypatch, config_file, 1)
    assert save_config({"theme": "light"}) == {"theme": "light", "paneWidth": 420}


def test_load_retries_a_transient_read_failure(config_file, monkeypatch):
    """조회 경로도 같이 막는다. 이것이 없으면 뷰어가 기본 테마로 한 번 열린다."""
    save_config({"theme": "dark"})
    deny_reads(monkeypatch, config_file, 1)
    assert load_config() == {"theme": "dark"}


def test_load_gives_up_and_returns_empty(config_file, monkeypatch):
    """끝까지 읽지 못하면 빈 dict다. 조회는 화면을 막지 않는 쪽이 옳다."""
    save_config({"theme": "dark"})
    deny_reads(monkeypatch, config_file, 999)
    assert load_config() == {}


# ── 기본값 ───────────────────────────────────────────────────────────────────


def test_with_defaults_fills_missing():
    assert with_defaults({}) == DEFAULTS


def test_with_defaults_keeps_given():
    filled = with_defaults({"theme": "dark"})
    assert filled["theme"] == "dark"
    assert filled["paneWidth"] == DEFAULTS["paneWidth"]


def test_defaults_pass_validation():
    """기본값 자체가 규약 안이어야 저장했다 읽을 때 사라지지 않는다."""
    assert sanitize(DEFAULTS) == DEFAULTS


# ── 초기화 ───────────────────────────────────────────────────────────────────


def test_reset_removes_file(config_file):
    save_config({"theme": "dark"})
    assert config_file.exists()
    reset_config()
    assert not config_file.exists()


def test_reset_when_missing_is_not_an_error(config_file):
    """지울 것이 없는 것은 실패가 아니다. 초기화를 두 번 눌러도 같아야 한다."""
    reset_config()
    assert not config_file.exists()


def test_load_after_reset_is_empty(config_file):
    """기본값을 써 넣지 않고 지운다. 파일이 없으면 읽기가 빈 dict를 돌려주므로
    `with_defaults`가 기본값을 세운다 — 사용자가 정한 값과 구별된다."""
    save_config({"theme": "dark", "paneWidth": 500})
    reset_config()
    assert load_config() == {}
    assert with_defaults(load_config()) == DEFAULTS
