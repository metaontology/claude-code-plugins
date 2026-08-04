"""auto-memory 폐기 — 항목 파일 삭제와 인덱스 줄 제거를 함께 한다.

한쪽만 하면 실패다. 파일만 지우면 인덱스에 죽은 줄이 남고, 그 줄은 매 세션 컨텍스트에
로드되므로 폐기가 오히려 오염을 만든다.

읽기 계층(`model.py`)과 나누어 둔다. 값을 얻으려는 호출과 지우는 호출이 같은 모듈에서
나오면 실수의 표면이 넓어진다.
"""
from pathlib import Path

from auto_memory.model import INDEX_FILE, index_path, parse_index


def discard_items(directory: Path, targets: list[str]) -> list[dict]:
    """항목을 폐기하고 대상마다 결과를 돌려준다.

    인덱스를 **한 번 읽고 한 번 쓴다.** 대상마다 다시 읽고 쓰면 같은 파일에 N번 쓰게 되고,
    중간에 실패했을 때 어디까지 반영됐는지 알 수 없다.

    Args:
        directory (Path): auto-memory 디렉토리
        targets (list[str]): 폐기할 항목의 파일명 목록

    Returns:
        list[dict]: `{"target", "ok", "reason", "removed"}` 목록. 순서는 입력과 같다
    """
    index_file = index_path(directory)
    index_text = (
        index_file.read_text(encoding="utf-8", errors="replace")
        if index_file.exists()
        else ""
    )
    pointers = parse_index(index_text)
    dropped_lines: set[str] = set()

    results = []
    for target in targets:
        # 인덱스는 지울 대상이 아니라 항목을 지울 때 함께 고쳐야 하는 쪽이다
        if target == INDEX_FILE:
            results.append(_result(target, False, f"{INDEX_FILE}는 폐기할 수 없습니다"))
            continue

        item_file = directory / target
        # 경로를 벗어나는 이름을 거부한다. 대상은 이 디렉토리의 파일명이다
        if Path(target).name != target:
            results.append(_result(target, False, "항목 파일명이 아닙니다"))
            continue

        pointer = pointers.get(target)
        exists = item_file.exists()
        if not exists and pointer is None:
            results.append(_result(target, False, "해당 항목이 없습니다"))
            continue

        removed = []
        if exists:
            try:
                item_file.unlink()
            except OSError as exc:
                results.append(_result(target, False, f"파일 삭제 실패: {exc.strerror or exc}"))
                continue
            removed.append("file")
        if pointer is not None:
            dropped_lines.add(pointer)
            removed.append("index_line")

        # 끊긴 포인터는 줄 제거만, 누락된 포인터는 파일 삭제만 하고 처리됨으로 답한다.
        # 무엇이 실제로 사라졌는지는 removed가 구분한다
        results.append(_result(target, True, "", removed))

    if dropped_lines:
        _rewrite_index(index_file, index_text, dropped_lines, results)
    return results


def _rewrite_index(index_file: Path, index_text: str, dropped: set[str],
                   results: list[dict]) -> None:
    """인덱스에서 제거 대상 줄을 빼고 다시 쓴다.

    쓰기에 실패하면 인덱스 줄을 지우지 못한 것이므로, 그 줄을 기대했던 결과를 실패로
    되돌린다. 파일 삭제는 되돌릴 수 없으니 실패를 숨기지 않고 사유와 함께 보고한다.
    """
    kept = [line for line in index_text.splitlines() if line.strip() not in dropped]
    try:
        index_file.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    except OSError as exc:
        for result in results:
            if "index_line" in result.get("removed", ()):
                result["ok"] = False
                result["reason"] = f"인덱스 줄 제거 실패: {exc.strerror or exc}"
                result["removed"] = [r for r in result["removed"] if r != "index_line"]


def _result(target: str, ok: bool, reason: str, removed: list[str] | None = None) -> dict:
    """항목별 결과 하나를 만든다."""
    return {"target": target, "ok": ok, "reason": reason, "removed": removed or []}
