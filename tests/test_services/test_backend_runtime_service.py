"""Tests for backend runtime provisioning service."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pulsimgui.services.backend_runtime_service import (
    DEFAULT_BACKEND_TARGET_VERSION,
    BackendRuntimeConfig,
    BackendRuntimeService,
    normalize_backend_version,
)


def test_normalize_backend_version() -> None:
    assert normalize_backend_version("v0.3.0") == "0.3.0"
    assert normalize_backend_version(" 0.2.1 ") == "0.2.1"
    assert normalize_backend_version("") == ""
    assert normalize_backend_version(None) == ""


def test_default_target_version() -> None:
    config = BackendRuntimeConfig()
    assert config.target_version == DEFAULT_BACKEND_TARGET_VERSION
    assert config.normalized_target_version == "0.5.3"
    assert config.auto_sync is True


def test_build_install_command_for_pypi_target() -> None:
    service = BackendRuntimeService(python_executable="/usr/bin/python3")
    config = BackendRuntimeConfig(target_version="v0.3.0", source="pypi")

    command = service.build_install_command(config)

    assert command == [
        "/usr/bin/python3",
        "-m",
        "pip",
        "install",
        "--upgrade",
        "pulsim==0.3.0",
    ]


def test_build_install_command_for_local_path(tmp_path) -> None:
    service = BackendRuntimeService(python_executable="/usr/bin/python3")
    config = BackendRuntimeConfig(source="local", local_path=str(tmp_path))

    command = service.build_install_command(config)

    assert command[:5] == ["/usr/bin/python3", "-m", "pip", "install", "--upgrade"]
    assert command[-1] == str(tmp_path.resolve())


def test_build_install_command_local_without_path_raises() -> None:
    service = BackendRuntimeService()
    config = BackendRuntimeConfig(source="local", local_path="")

    with pytest.raises(ValueError):
        service.build_install_command(config)


def test_ensure_target_version_noop_when_already_matching(monkeypatch) -> None:
    service = BackendRuntimeService()
    config = BackendRuntimeConfig(target_version="0.3.0", source="pypi")

    monkeypatch.setattr(service, "query_installed_version", lambda: "0.3.0")

    result = service.ensure_target_version(config, force=False)

    assert result.success
    assert not result.changed
    assert "already matches target version" in result.message


def test_install_reports_subprocess_failure(monkeypatch) -> None:
    service = BackendRuntimeService(python_executable="/usr/bin/python3")
    config = BackendRuntimeConfig(target_version="0.3.0", source="pypi")

    def _run(*args, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="pip failed")

    monkeypatch.setattr("pulsimgui.services.backend_runtime_service.subprocess.run", _run)

    result = service.install(config)

    assert not result.success
    assert "pip failed" in result.message


def test_install_success_sets_installed_version(monkeypatch) -> None:
    service = BackendRuntimeService(python_executable="/usr/bin/python3")
    config = BackendRuntimeConfig(target_version="0.3.0", source="pypi")

    def _run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("pulsimgui.services.backend_runtime_service.subprocess.run", _run)
    monkeypatch.setattr(service, "query_installed_version", lambda: "0.3.0")

    result = service.install(config)

    assert result.success
    assert result.changed
    assert result.installed_version == "0.3.0"
