"""프로젝트 뼈대가 정상 import + 실행 가능한지 확인하는 smoke test."""

from __future__ import annotations

from autoblog import __version__
from autoblog.__main__ import main


def test_version_is_set() -> None:
    assert __version__ == "0.1.0"


def test_main_is_callable() -> None:
    assert callable(main)


def test_main_returns_zero(capsys) -> None:  # type: ignore[no-untyped-def]
    exit_code = main()
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "AutoBlog" in captured.out
