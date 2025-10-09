#!/usr/bin/env python3
"""Validate that all placeholder tokens are tracked in Placeholders.md."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, Set

PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def collect_placeholders(paths: Iterable[Path]) -> Set[str]:
    tokens: set[str] = set()
    for path in paths:
        if path.is_dir():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in PLACEHOLDER_PATTERN.finditer(text):
            tokens.add(match.group(0))
    return tokens


def repo_files(root: Path) -> Iterable[Path]:
    excluded_dirs = {".git", ".ruff_cache", ".mypy_cache", ".pytest_cache", "__pycache__", ".venv"}
    for path in root.rglob("*"):
        if any(part in excluded_dirs for part in path.parts):
            continue
        yield path


def parse_manifest(manifest: Path) -> Set[str]:
    tokens: set[str] = set()
    try:
        text = manifest.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"Manifest not found: {manifest}")
    row_pattern = re.compile(r"\|\s*(\{\{[A-Z0-9_]+\}\})\s*\|")
    for line in text.splitlines():
        match = row_pattern.match(line.strip())
        if match:
            tokens.add(match.group(1))
    return tokens


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."), help="Repository root to scan.")
    parser.add_argument("--manifest", type=Path, required=True, help="Path to Placeholders.md manifest.")
    args = parser.parse_args()

    root = args.root.resolve()
    manifest_path = args.manifest.resolve()

    repo_tokens = collect_placeholders(repo_files(root))
    manifest_tokens = parse_manifest(manifest_path)

    missing = sorted(repo_tokens - manifest_tokens)
    extras = sorted(manifest_tokens - repo_tokens)

    if missing or extras:
        if missing:
            print("ERROR: Undocumented placeholders found:", file=sys.stderr)
            for token in missing:
                print(f"  - {token}", file=sys.stderr)
        if extras:
            print("ERROR: Manifest lists placeholders not present in repository:", file=sys.stderr)
            for token in extras:
                print(f"  - {token}", file=sys.stderr)
        sys.exit(1)

    print(f"Placeholder ledger OK ({len(repo_tokens)} tokens tracked).")


if __name__ == "__main__":
    main()
