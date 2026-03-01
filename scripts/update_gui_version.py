#!/usr/bin/env python3
"""Update PulsimGui version across release-managed files.

Usage:
    python scripts/update_gui_version.py 0.5.4
    python scripts/update_gui_version.py v0.5.4 --dry-run
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
            pattern=re.compile(r'(?m)^version\s*=\s*"[^"]+"$'),
            replacement='version = "{version}"',
            description="Python package version",
        ),
    ],
    "src/pulsimgui/__init__.py": [
        Rule(
            pattern=re.compile(r'(?m)^__version__\s*=\s*"[^"]+"$'),
            replacement='__version__ = "{version}"',
            description="Application __version__",
        ),
    ],
    "scripts/build.py": [
        Rule(
            pattern=re.compile(r'(?m)^    return "\d+\.\d+\.\d+"$'),
            replacement='    return "{version}"',
            description="Build script fallback version",
        ),
    ],
    "pulsimgui.spec": [
        Rule(
            pattern=re.compile(
                r"(?m)^APP_VERSION = os\.environ\.get\('PULSIMGUI_VERSION', '[^']+'\)\.lstrip\('v'\) or '[^']+'$"
            ),
            replacement=(
                "APP_VERSION = os.environ.get('PULSIMGUI_VERSION', '{version}').lstrip('v') "
                "or '{version}'"
            ),
            description="PyInstaller spec app version",
        ),
    ],
    "packaging/windows/installer.nsi": [
        Rule(
            pattern=re.compile(r'(?m)^!define APP_VERSION "[^"]+"$'),
            replacement='!define APP_VERSION "{version}"',
            description="NSIS installer version",
        ),
    ],
    "packaging/windows/version_info.txt": [
        Rule(
            pattern=re.compile(r"(?m)^    filevers=\(\d+, \d+, \d+, \d+\),$"),
            replacement="    filevers=({version_tuple}),",
            description="Windows file version tuple",
        ),
        Rule(
            pattern=re.compile(r"(?m)^    prodvers=\(\d+, \d+, \d+, \d+\),$"),
            replacement="    prodvers=({version_tuple}),",
            description="Windows product version tuple",
        ),
        Rule(
            pattern=re.compile(r"(?m)^            StringStruct\(u'FileVersion', u'[^']+'\),$"),
            replacement="            StringStruct(u'FileVersion', u'{version}'),",
            description="Windows file version string",
        ),
        Rule(
            pattern=re.compile(r"(?m)^            StringStruct\(u'ProductVersion', u'[^']+'\)$"),
            replacement="            StringStruct(u'ProductVersion', u'{version}')",
            description="Windows product version string",
        ),
    ],
    "packaging/linux/pulsimgui.appdata.xml": [
        Rule(
            pattern=re.compile(r'(<releases>\s*\n\s*<release version=")([^"]+)(" date="[^"]+">)'),
            replacement=r"\g<1>{version}\g<3>",
            description="Latest AppStream release version",
        ),
    ],
    "docs/instalacao.md": [
        Rule(
            pattern=re.compile(r"(?m)^Expected project baseline: `\d+\.\d+\.\d+`\.$"),
            replacement="Expected project baseline: `{version}`.",
            description="Installation baseline version",
        ),
    ],
    ".github/workflows/release.yml": [
        Rule(
            pattern=re.compile(
                r'(?m)^        description: "Optional version override \(e\.g\. \d+\.\d+\.\d+\)"$'
            ),
            replacement='        description: "Optional version override (e.g. {version})"',
            description="Workflow dispatch input example version",
        ),
    ],
    "BUILD.md": [
        Rule(
            pattern=re.compile(
                r"(?m)^# Output: dist/PulsimGui\.app, dist/PulsimGui-\d+\.\d+\.\d+-macos\.dmg$"
            ),
            replacement="# Output: dist/PulsimGui.app, dist/PulsimGui-{version}-macos.dmg",
            description="macOS output example",
        ),
        Rule(
            pattern=re.compile(
                r"(?m)^2\. `PulsimGui-\d+\.\d+\.\d+-macos\.dmg` - Distributable disk image$"
            ),
            replacement="2. `PulsimGui-{version}-macos.dmg` - Distributable disk image",
            description="macOS DMG filename example",
        ),
        Rule(
            pattern=re.compile(
                r"(?m)^# Output: dist/PulsimGui-\d+\.\d+\.\d+-x86_64\.AppImage, dist/pulsimgui$"
            ),
            replacement="# Output: dist/PulsimGui-{version}-x86_64.AppImage, dist/pulsimgui",
            description="Linux output example",
        ),
        Rule(
            pattern=re.compile(
                r"(?m)^2\. `PulsimGui-\d+\.\d+\.\d+-x86_64\.AppImage` - Portable AppImage \(recommended for distribution\)$"
            ),
            replacement=(
                "2. `PulsimGui-{version}-x86_64.AppImage` - Portable AppImage "
                "(recommended for distribution)"
            ),
            description="Linux AppImage filename example",
        ),
        Rule(
            pattern=re.compile(
                r"(?m)^- Git tags starting with `v` \(e\.g\., `v\d+\.\d+\.\d+`\)$"
            ),
            replacement="- Git tags starting with `v` (e.g., `v{version}`)",
            description="Tag example version",
        ),
        Rule(
            pattern=re.compile(r"(?m)^   git tag v\d+\.\d+\.\d+$"),
            replacement="   git tag v{version}",
            description="Tag command example",
        ),
        Rule(
            pattern=re.compile(r"(?m)^   git push origin v\d+\.\d+\.\d+$"),
            replacement="   git push origin v{version}",
            description="Push tag command example",
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


def to_windows_version_tuple(version: str) -> str:
    """Convert X.Y.Z to 'X, Y, Z, 0' for Windows version resources."""
    major, minor, patch = version.split(".")
    return f"{int(major)}, {int(minor)}, {int(patch)}, 0"


def apply_rules(path: Path, rules: list[Rule], version: str) -> tuple[bool, str]:
    """Apply replacement rules to a file and return updated content."""
    content = path.read_text(encoding="utf-8")
    original = content
    version_tuple = to_windows_version_tuple(version)

    for rule in rules:
        replacement = rule.replacement.format(version=version, version_tuple=version_tuple)
        content, count = rule.pattern.subn(replacement, content)
        if count != rule.expected_count:
            desc = rule.description or rule.pattern.pattern
            raise RuntimeError(
                f"{path}: expected {rule.expected_count} replacement(s) for '{desc}', got {count}."
            )

    return content != original, content


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Update PulsimGui release version across project files."
    )
    parser.add_argument("version", help="Target GUI version (X.Y.Z or vX.Y.Z)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing files.",
    )
    args = parser.parse_args()

    try:
        version = normalize_version(args.version)
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
            changed, updated_content = apply_rules(path, rules, version)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        touched_rules += len(rules)
        if changed:
            changed_files.append(rel_path)
            if not args.dry_run:
                path.write_text(updated_content, encoding="utf-8")

    mode = "DRY-RUN" if args.dry_run else "UPDATED"
    print(f"{mode}: set GUI version to {version}")
    print(f"Checked {len(RULES)} files / {touched_rules} rules.")
    if changed_files:
        for rel_path in changed_files:
            print(f" - {rel_path}")
    else:
        print("No file content changes were necessary.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
