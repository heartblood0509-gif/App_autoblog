"""CLI 진입점: `python -m autoblog` 또는 `uv run autoblog`."""

from __future__ import annotations

import sys

from autoblog import __version__


def main() -> int:
    print(f"AutoBlog v{__version__}")
    print("Phase 0 Day 1 — 개발 환경 셋팅 완료.")
    print("다음 단계: viruagent-cli 분석 및 PoC 실행.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
