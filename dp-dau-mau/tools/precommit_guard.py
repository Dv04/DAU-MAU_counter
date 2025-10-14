#!/usr/bin/env python3
"""Pre-commit guard to block generated artefacts and oversized files."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable


BLOCK_PATTERNS = [
    "data/*",
    "*.sqlite*",
    "__pycache__/*",
    ".pytest_cache/*",
    ".mypy_cache/*",
    ".ruff_cache/*",
    "*.coverage",
    "coverage.xml",
    "reports/*",
    "*.aux",
    "*.log",
    "*.synctex.gz",
    "*.out",
    "*.pdf",
    "*.toc",
    "*.bbl",
    "*.blg",
]

MAX_BYTES = 5 * 1024 * 1024  # 5 MiB


def matches_any(path: Path, patterns: Iterable[str]) -> bool:
    rel = str(path).replace("\\", "/")
    return any(path.match(pattern) or rel == pattern or rel.startswith(pattern.rstrip("*"))
               or Path(rel).match(pattern)
               for pattern in patterns)


def main() -> int:
    allow_large = os.environ.get("ALLOW_LARGE_FILE") == "1"
    blocked: list[str] = []
    oversized: list[str] = []

    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.exists():
            continue
        if matches_any(path, BLOCK_PATTERNS):
            blocked.append(str(path))
            continue
        if not allow_large and path.is_file() and path.stat().st_size > MAX_BYTES:
            oversized.append(f"{path} ({path.stat().st_size / (1024 * 1024):.2f} MiB)")

    if blocked or oversized:
        if blocked:
            print("Pre-commit: blocked generated artefacts:", file=sys.stderr)
            for item in blocked:
                print(f"  - {item}", file=sys.stderr)
        if oversized:
            print(
                "Pre-commit: file(s) exceed 5 MiB. Export ALLOW_LARGE_FILE=1 to override:",
                file=sys.stderr,
            )
            for item in oversized:
                print(f"  - {item}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
