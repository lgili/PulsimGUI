"""Runtime management for the Python simulation backend package.

This service centralizes backend version pinning and installation logic so the
GUI can keep the active backend aligned with a configured target version.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path

DEFAULT_BACKEND_TARGET_VERSION = "v0.4.0"


def normalize_backend_version(version: str | None) -> str:
    """Normalize backend version strings like ``v0.3.0`` to ``0.3.0``."""
    if not version:
        return ""
    value = version.strip()
    if value.lower().startswith("v"):
        value = value[1:]
    return value.strip()


@dataclass
class BackendRuntimeConfig:
    """Persistent configuration for runtime backend provisioning."""

    target_version: str = DEFAULT_BACKEND_TARGET_VERSION
    source: str = "pypi"  # pypi | local
    local_path: str = ""
    auto_sync: bool = False

    @property
    def normalized_target_version(self) -> str:
        return normalize_backend_version(self.target_version)

    @property
    def normalized_source(self) -> str:
        source = (self.source or "").strip().lower()
        return source if source in {"pypi", "local"} else "pypi"

    def to_dict(self) -> dict[str, str | bool]:
        """Serialize config for settings persistence."""
        return {
            "target_version": self.target_version,
            "source": self.normalized_source,
            "local_path": self.local_path,
            "auto_sync": self.auto_sync,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BackendRuntimeConfig:
        """Build a config object from persisted settings data."""
        target_version = str(data.get("target_version", "") or DEFAULT_BACKEND_TARGET_VERSION)
        return cls(
            target_version=target_version,
            source=str(data.get("source", "pypi") or "pypi"),
            local_path=str(data.get("local_path", "") or ""),
            auto_sync=bool(data.get("auto_sync", False)),
        )


@dataclass
class BackendInstallResult:
    """Result of a backend installation/synchronization action."""

    success: bool
    message: str
    command: list[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    installed_version: str | None = None
    changed: bool = False


class BackendRuntimeService:
    """Install and synchronize the Python backend package version."""

    def __init__(self, python_executable: str | None = None) -> None:
        self._python_executable = python_executable or sys.executable

    def query_installed_version(self) -> str | None:
        """Return installed ``pulsim`` version if available."""
        try:
            return metadata.version("pulsim")
        except metadata.PackageNotFoundError:
            return None
        except Exception:
            return None

    def build_install_command(
        self,
        config: BackendRuntimeConfig,
        *,
        upgrade: bool = True,
    ) -> list[str]:
        """Build ``pip install`` command for the configured source."""
        command = [self._python_executable, "-m", "pip", "install"]
        if upgrade:
            command.append("--upgrade")

        source = config.normalized_source
        if source == "local":
            path_text = (config.local_path or "").strip()
            if not path_text:
                raise ValueError("Local backend source selected but no path was provided.")
            local_path = Path(path_text).expanduser().resolve()
            if not local_path.exists():
                raise ValueError(f"Local backend path does not exist: {local_path}")
            command.append(str(local_path))
            return command

        target = config.normalized_target_version
        requirement = f"pulsim=={target}" if target else "pulsim"
        command.append(requirement)
        return command

    def install(
        self,
        config: BackendRuntimeConfig,
        *,
        upgrade: bool = True,
        timeout_seconds: int = 600,
    ) -> BackendInstallResult:
        """Install backend according to configuration."""
        try:
            command = self.build_install_command(config, upgrade=upgrade)
        except ValueError as exc:
            return BackendInstallResult(success=False, message=str(exc))

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return BackendInstallResult(
                success=False,
                message=f"Backend installation timed out after {timeout_seconds}s.",
                command=command,
            )
        except Exception as exc:
            return BackendInstallResult(
                success=False,
                message=f"Failed to execute backend installation: {exc}",
                command=command,
            )

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        if completed.returncode != 0:
            detail = stderr or stdout or "unknown pip error"
            return BackendInstallResult(
                success=False,
                message=f"Backend installation failed: {detail}",
                command=command,
                stdout=stdout,
                stderr=stderr,
            )

        installed_version = self.query_installed_version()
        message = (
            f"Backend installed successfully (pulsim {installed_version})."
            if installed_version
            else "Backend installed successfully."
        )
        return BackendInstallResult(
            success=True,
            message=message,
            command=command,
            stdout=stdout,
            stderr=stderr,
            installed_version=installed_version,
            changed=True,
        )

    def ensure_target_version(
        self,
        config: BackendRuntimeConfig,
        *,
        force: bool = False,
    ) -> BackendInstallResult:
        """Ensure installed backend matches the configured target."""
        source = config.normalized_source
        installed_version = normalize_backend_version(self.query_installed_version())
        target = config.normalized_target_version

        if source == "pypi":
            if not target and not force:
                return BackendInstallResult(
                    success=True,
                    message="No backend target version configured.",
                    installed_version=installed_version or None,
                    changed=False,
                )
            if target and installed_version == target and not force:
                return BackendInstallResult(
                    success=True,
                    message=f"Backend already matches target version ({target}).",
                    installed_version=installed_version,
                    changed=False,
                )
            result = self.install(config, upgrade=True)
            if not result.success:
                return result
            actual = normalize_backend_version(result.installed_version)
            if target and actual != target:
                return BackendInstallResult(
                    success=False,
                    message=(
                        f"Installed backend version {result.installed_version or 'unknown'} "
                        f"does not match configured target {target}."
                    ),
                    command=result.command,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    installed_version=result.installed_version,
                    changed=result.changed,
                )
            return result

        # Local source: avoid reinstall loops unless forced or explicit target mismatch.
        if not force:
            if target and installed_version == target:
                return BackendInstallResult(
                    success=True,
                    message=f"Backend already matches target version ({target}).",
                    installed_version=installed_version,
                    changed=False,
                )
            if not target:
                return BackendInstallResult(
                    success=True,
                    message="Local backend source configured (no version target).",
                    installed_version=installed_version or None,
                    changed=False,
                )

        return self.install(config, upgrade=True)

    @staticmethod
    def invalidate_backend_import_cache() -> None:
        """Clear loaded backend modules so the next import can pick updates."""
        keys = [
            module_name
            for module_name in list(sys.modules)
            if module_name == "pulsim"
            or module_name.startswith("pulsim.")
            or module_name == "_pulsim"
        ]
        for module_name in keys:
            sys.modules.pop(module_name, None)
        importlib.invalidate_caches()
