#!/usr/bin/env python3
"""Pre-commit guard to block generated artefacts, oversized files, and unresolved placeholders."""

from __future__ import annotations

import os
import re
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

# Placeholder pattern to detect unresolved tokens
PLACEHOLDER_PATTERN = re.compile(r"\{\{[A-Z][A-Z0-9_]*\}\}")

# Files to skip placeholder checks (these legitimately contain placeholder docs)
PLACEHOLDER_SKIP_FILES = {
    "Placeholders.md",
    "check_placeholders.py",
    "precommit_guard.py",
    "AGENTS.md",
}

# Extensions to check for placeholders
PLACEHOLDER_CHECK_EXTENSIONS = {".py", ".md", ".yml", ".yaml", ".json", ".sh", ".toml"}


def matches_any(path: Path, patterns: Iterable[str]) -> bool:
    rel = str(path).replace("\\", "/")
    return any(path.match(pattern) or rel == pattern or rel.startswith(pattern.rstrip("*"))
               or Path(rel).match(pattern)
               for pattern in patterns)


def check_placeholders(path: Path) -> list[str]:
    """Check file for unresolved placeholders. Returns list of found placeholders."""
    if path.name in PLACEHOLDER_SKIP_FILES:
        return []
    if path.suffix.lower() not in PLACEHOLDER_CHECK_EXTENSIONS:
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        return PLACEHOLDER_PATTERN.findall(content)
    except (OSError, UnicodeDecodeError):
        return []


def main() -> int:
    allow_large = os.environ.get("ALLOW_LARGE_FILE") == "1"
    skip_placeholder_check = os.environ.get("SKIP_PLACEHOLDER_CHECK") == "1"
    blocked: list[str] = []
    oversized: list[str] = []
    placeholder_issues: list[tuple[str, list[str]]] = []

    for arg in sys.argv[1:]:
        path = Path(arg)
        if not path.exists():
            continue
        if matches_any(path, BLOCK_PATTERNS):
            blocked.append(str(path))
            continue
        if not allow_large and path.is_file() and path.stat().st_size > MAX_BYTES:
            oversized.append(f"{path} ({path.stat().st_size / (1024 * 1024):.2f} MiB)")
        # Check for unresolved placeholders
        if not skip_placeholder_check and path.is_file():
            found = check_placeholders(path)
            if found:
                placeholder_issues.append((str(path), found))

    if blocked or oversized or placeholder_issues:
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
        if placeholder_issues:
            print(
                "Pre-commit: unresolved placeholders found. Export SKIP_PLACEHOLDER_CHECK=1 to override:",
                file=sys.stderr,
            )
            for filepath, placeholders in placeholder_issues:
                unique = sorted(set(placeholders))
                print(f"  - {filepath}: {', '.join(unique)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

