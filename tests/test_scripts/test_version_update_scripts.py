"""CLI smoke tests for version update helper scripts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _run_script(script_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / script_name), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_update_gui_version_dry_run() -> None:
    result = _run_script("update_gui_version.py", "0.5.3", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "DRY-RUN: set GUI version to 0.5.3" in result.stdout


def test_update_backend_version_dry_run() -> None:
    result = _run_script("update_backend_version.py", "0.5.2", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert "DRY-RUN: set backend version to 0.5.2" in result.stdout


def test_update_gui_version_rejects_invalid_semver() -> None:
    result = _run_script("update_gui_version.py", "0.5", "--dry-run")
    assert result.returncode == 2
    assert "Invalid version" in result.stderr


def test_update_backend_version_rejects_invalid_semver() -> None:
    result = _run_script("update_backend_version.py", "v0.5", "--dry-run")
    assert result.returncode == 2
    assert "Invalid version" in result.stderr
