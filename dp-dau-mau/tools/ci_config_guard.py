#!/usr/bin/env python3
"""CI guard to ensure required environment variables are configured.

Run this in CI pipelines to fail early if critical configuration is missing.
Exit codes:
  0 - All checks passed
  1 - Configuration issues found
"""

from __future__ import annotations

import os
import re
import sys
from typing import NamedTuple


class ConfigCheck(NamedTuple):
    name: str
    required: bool
    description: str


# Configuration checks to perform
CHECKS: list[ConfigCheck] = [
    ConfigCheck(
        name="SERVICE_API_KEY",
        required=True,
        description="API authentication key for protected endpoints",
    ),
    ConfigCheck(
        name="HASH_SALT_SECRET",
        required=False,
        description="Root secret for HMAC-based hashing (optional in dev)",
    ),
    ConfigCheck(
        name="DATA_DIR",
        required=False,
        description="Root directory for writable artifacts",
    ),
]

# Pattern to detect placeholder values
PLACEHOLDER_PATTERN = re.compile(r"^\{\{[A-Z][A-Z0-9_]*\}\}$")


def is_placeholder(value: str | None) -> bool:
    """Check if a value is an unresolved placeholder."""
    if value is None:
        return False
    return PLACEHOLDER_PATTERN.fullmatch(value.strip()) is not None


def check_config() -> list[str]:
    """Run all configuration checks. Returns list of error messages."""
    errors: list[str] = []
    warnings: list[str] = []

    for check in CHECKS:
        value = os.environ.get(check.name)
        
        if value is None or value.strip() == "":
            if check.required:
                errors.append(f"MISSING: {check.name} - {check.description}")
            else:
                warnings.append(f"UNSET: {check.name} - {check.description}")
        elif is_placeholder(value):
            if check.required:
                errors.append(f"PLACEHOLDER: {check.name} is set to '{value}' - must be a real value")
            else:
                warnings.append(f"PLACEHOLDER: {check.name} is set to '{value}'")
        elif check.name == "SERVICE_API_KEY":
            # Additional validation for API key
            if len(value) < 16:
                warnings.append(f"WEAK: {check.name} is less than 16 characters")
            if value in ("changeme", "secret", "test", "dev"):
                errors.append(f"INSECURE: {check.name} is set to a common default value")

    # Print warnings
    for warning in warnings:
        print(f"⚠️  {warning}", file=sys.stderr)

    return errors


def main() -> int:
    print("=" * 60)
    print("CI Configuration Guard")
    print("=" * 60)
    
    # Check for CI environment
    is_ci = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"
    
    if is_ci:
        print("Running in CI environment - enforcing strict checks")
    else:
        print("Running locally - warnings only for optional items")
    
    print()
    
    errors = check_config()
    
    if errors:
        print("\n❌ Configuration errors found:", file=sys.stderr)
        for error in errors:
            print(f"   {error}", file=sys.stderr)
        print("\nFix these issues before proceeding.", file=sys.stderr)
        return 1
    
    print("\n✅ All required configuration checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
