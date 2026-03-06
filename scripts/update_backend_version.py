#!/usr/bin/env python3
"""Update Pulsim backend target/minimum version across PulsimGui files.

Usage:
    python scripts/update_backend_version.py 0.6.4
    python scripts/update_backend_version.py v0.6.4 --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


@dataclass(frozen=True)
class Rule:
    pattern: re.Pattern[str]
    replacement: str
    expected_count: int = 1
    description: str = ""


RULES: dict[str, list[Rule]] = {
    "pyproject.toml": [
        Rule(
            pattern=re.compile(r'(?m)^    "pulsim>=\d+\.\d+\.\d+",$'),
            replacement='    "pulsim>={backend_version}",',
            expected_count=2,
            description="Runtime/build pulsim minimum version",
        ),
    ],
    "scripts/build.py": [
        Rule(
            pattern=re.compile(r'(?m)^        "pulsim>=\d+\.\d+\.\d+",$'),
            replacement='        "pulsim>={backend_version}",',
            description="Build dependency pulsim minimum version",
        ),
    ],
    "src/pulsimgui/services/backend_runtime_service.py": [
        Rule(
            pattern=re.compile(r'(?m)^DEFAULT_BACKEND_TARGET_VERSION = "v\d+\.\d+\.\d+"$'),
            replacement='DEFAULT_BACKEND_TARGET_VERSION = "{backend_tag}"',
            description="Default backend target version",
        ),
    ],
    "tests/test_services/test_backend_runtime_service.py": [
        Rule(
            pattern=re.compile(r'(?m)^    assert config\.normalized_target_version == "\d+\.\d+\.\d+"$'),
            replacement='    assert config.normalized_target_version == "{backend_version}"',
            description="Backend runtime service default target test",
        ),
    ],
    "README.md": [
        Rule(
            pattern=re.compile(
                r"(?m)^For reproducible behavior, use \*\*`pulsim v\d+\.\d+\.\d+`\*\*\.$"
            ),
            replacement="For reproducible behavior, use **`pulsim v{backend_version}`**.",
            description="README backend recommendation",
        ),
    ],
    "docs/index.md": [
        Rule(
            pattern=re.compile(
                r"(?m)^The recommended runtime baseline is \*\*`pulsim v\d+\.\d+\.\d+`\*\*\.$"
            ),
            replacement="The recommended runtime baseline is **`pulsim v{backend_version}`**.",
            description="Docs backend baseline",
        ),
        Rule(
            pattern=re.compile(r"(?m)^(    .*`Target version = )v\d+\.\d+\.\d+(`.*)$"),
            replacement=r"\g<1>{backend_tag}\g<2>",
            description="Docs recommended target setting",
        ),
    ],
    "docs/backend-adapter.md": [
        Rule(
            pattern=re.compile(r"(?m)^- Pin backend to `v\d+\.\d+\.\d+` for reproducibility\.$"),
            replacement="- Pin backend to `{backend_tag}` for reproducibility.",
            description="Backend adapter reproducibility note",
        ),
    ],
    "docs/user-manual.md": [
        Rule(
            pattern=re.compile(r"(?m)^- Keep backend pinned to `v\d+\.\d+\.\d+` in shared environments\.$"),
            replacement="- Keep backend pinned to `{backend_tag}` in shared environments.",
            description="User manual backend recommendation",
        ),
    ],
    "docs/instalacao.md": [
        Rule(
            pattern=re.compile(r"(?m)^- `Target version`: `v\d+\.\d+\.\d+`$"),
            replacement="- `Target version`: `{backend_tag}`",
            description="Installation recommended target setting",
        ),
    ],
    "docs/gui/configuracao-simulacao.md": [
        Rule(
            pattern=re.compile(r"(?m)^- Backend target: `v\d+\.\d+\.\d+`$"),
            replacement="- Backend target: `{backend_tag}`",
            description="Simulation config backend target",
        ),
    ],
    "docs/faq.md": [
        Rule(
            pattern=re.compile(r"(?m)^3\. Reinstall/update backend to `v\d+\.\d+\.\d+` from runtime settings\.$"),
            replacement="3. Reinstall/update backend to `{backend_tag}` from runtime settings.",
            description="FAQ backend update guidance",
        ),
    ],
    "BUILD.md": [
        Rule(
            pattern=re.compile(r"(?m)^pip install pulsim>=\d+\.\d+\.\d+$"),
            replacement="pip install pulsim>={backend_version}",
            description="Build guide pulsim dependency example",
        ),
    ],
}


def normalize_version(raw: str) -> str:
    """Normalize version string and validate semantic version format."""
    version = raw[1:] if raw.startswith("v") else raw
    if not SEMVER_RE.fullmatch(version):
        raise ValueError(
            f"Invalid version '{raw}'. Expected format X.Y.Z (optionally prefixed with 'v')."
        )
    return version


def apply_rules(path: Path, rules: list[Rule], backend_version: str) -> tuple[bool, str]:
    """Apply backend version replacement rules to a file."""
    content = path.read_text(encoding="utf-8")
    original = content
    backend_tag = f"v{backend_version}"

    for rule in rules:
        replacement = rule.replacement.format(
            backend_version=backend_version,
            backend_tag=backend_tag,
        )
        content, count = rule.pattern.subn(replacement, content)
        if count != rule.expected_count:
            desc = rule.description or rule.pattern.pattern
            raise RuntimeError(
                f"{path}: expected {rule.expected_count} replacement(s) for '{desc}', got {count}."
            )

    return content != original, content


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update Pulsim backend target/minimum version across project files."
    )
    parser.add_argument("version", help="Target backend version (X.Y.Z or vX.Y.Z)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files.",
    )
    args = parser.parse_args()

    try:
        backend_version = normalize_version(args.version)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    changed_files: list[str] = []
    touched_rules = 0

    for rel_path, rules in RULES.items():
        path = ROOT / rel_path
        if not path.exists():
            print(f"ERROR: Missing file: {path}", file=sys.stderr)
            return 1

        try:
            changed, updated_content = apply_rules(path, rules, backend_version)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        touched_rules += len(rules)
        if changed:
            changed_files.append(rel_path)
            if not args.dry_run:
                path.write_text(updated_content, encoding="utf-8")

    mode = "DRY-RUN" if args.dry_run else "UPDATED"
    print(f"{mode}: set backend version to {backend_version}")
    print(f"Checked {len(RULES)} files / {touched_rules} rules.")
    if changed_files:
        for rel_path in changed_files:
            print(f" - {rel_path}")
    else:
        print("No file content changes were necessary.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
