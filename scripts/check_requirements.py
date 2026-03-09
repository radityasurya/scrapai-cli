#!/usr/bin/env python3
"""
Check that requirements files are properly sorted and don't have duplicates.
"""

import sys
from pathlib import Path


def check_requirements(filepath: str) -> bool:
    """Check a requirements file for issues."""
    path = Path(filepath)
    if not path.exists():
        print(f"✗ File not found: {filepath}")
        return False

    content = path.read_text()
    lines = [
        line.strip() for line in content.splitlines() if line.strip() and not line.startswith("#")
    ]

    issues = []

    # Check for duplicates
    seen = set()
    for line in lines:
        pkg = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].split("[")[0].lower()
        if pkg in seen:
            issues.append(f"Duplicate: {line}")
        seen.add(pkg)

    # Check if sorted
    sorted_lines = sorted(lines, key=lambda x: x.lower())
    if lines != sorted_lines:
        issues.append("Packages not sorted alphabetically")

    if issues:
        print(f"✗ Issues in {filepath}:")
        for issue in issues:
            print(f"  - {issue}")
        return False

    print(f"✓ {filepath} OK")
    return True


def main():
    """Check all requirements files."""
    req_files = [
        "requirements.txt",
        "requirements-dev.txt",
        "airflow/requirements.txt",
    ]

    all_ok = True
    for filepath in req_files:
        if Path(filepath).exists():
            if not check_requirements(filepath):
                all_ok = False

    if not all_ok:
        sys.exit(1)

    print("\n✓ All requirements files OK")


if __name__ == "__main__":
    main()
