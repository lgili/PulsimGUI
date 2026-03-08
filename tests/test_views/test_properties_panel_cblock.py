"""Tests for C-Block editing actions in the properties panel."""

from __future__ import annotations

import sys
import types
from pathlib import Path

from pulsimgui.models.component import Component, ComponentType
from pulsimgui.views.properties import PropertiesPanel


def _install_fake_cblock_module(monkeypatch, compile_fn, compile_error_cls) -> None:
    fake_module = types.ModuleType("pulsim.cblock")
    fake_module.compile_cblock = compile_fn
    fake_module.CBlockCompileError = compile_error_cls

    fake_pkg = types.ModuleType("pulsim")
    fake_pkg.cblock = fake_module

    monkeypatch.setitem(sys.modules, "pulsim", fake_pkg)
    monkeypatch.setitem(sys.modules, "pulsim.cblock", fake_module)


def test_test_compilation_uses_source_file_and_flags(qapp, monkeypatch, tmp_path) -> None:
    class FakeCompileError(RuntimeError):
        pass

    source_path = tmp_path / "cb1.c"
    built_path = tmp_path / "cb1.so"
    calls: list[dict[str, object]] = []

    def _compile(source, *, name, extra_cflags):  # noqa: ANN001
        calls.append(
            {
                "source": Path(source),
                "name": name,
                "extra_cflags": list(extra_cflags),
            }
        )
        return built_path

    _install_fake_cblock_module(monkeypatch, _compile, FakeCompileError)

    comp = Component(type=ComponentType.C_BLOCK, name="CB1")
    comp.parameters["source"] = source_path.as_posix()
    comp.parameters["extra_cflags"] = ["-O3", "-DGAIN=2"]

    panel = PropertiesPanel()
    panel.set_component(comp)
    assert panel._cblock_source_editor is not None
    panel._cblock_source_editor.setPlainText("int x(void){return 0;}\n")

    messages: list[dict[str, object]] = []
    monkeypatch.setattr(
        panel,
        "_show_cblock_build_message",
        lambda **kwargs: messages.append(kwargs),
    )

    panel._on_test_cblock_compilation()

    assert len(calls) == 1
    assert calls[0]["source"] == source_path
    assert calls[0]["name"] == "cb1"
    assert calls[0]["extra_cflags"] == ["-O3", "-DGAIN=2"]
    assert source_path.exists()
    assert messages
    assert messages[-1]["title"] == "C-Block Build"


def test_test_compilation_maps_compile_error_to_diagnostics(
    qapp, monkeypatch, tmp_path
) -> None:
    class FakeCompileError(RuntimeError):
        def __init__(
            self,
            message: str,
            *,
            compiler_path: str = "",
            stderr_output: str = "",
            source: str = "",
        ) -> None:
            super().__init__(message)
            self.compiler_path = compiler_path
            self.stderr_output = stderr_output
            self.source = source

    source_path = tmp_path / "cb_err.c"
    source_path.write_text("broken", encoding="utf-8")

    def _compile(source, *, name, extra_cflags):  # noqa: ANN001
        raise FakeCompileError(
            "compile failed",
            compiler_path="/usr/bin/cc",
            stderr_output="error: missing ';'",
            source=str(source),
        )

    _install_fake_cblock_module(monkeypatch, _compile, FakeCompileError)

    comp = Component(type=ComponentType.C_BLOCK, name="CB_ERR")
    comp.parameters["source"] = source_path.as_posix()
    panel = PropertiesPanel()
    panel.set_component(comp)
    assert panel._cblock_source_editor is not None
    panel._cblock_source_editor.setPlainText("broken")

    messages: list[dict[str, object]] = []
    monkeypatch.setattr(
        panel,
        "_show_cblock_build_message",
        lambda **kwargs: messages.append(kwargs),
    )

    panel._on_test_cblock_compilation()

    assert messages
    error_message = messages[-1]
    assert error_message["title"] == "C-Block Build Error"
    assert "missing ';'" in str(error_message["details"])
    assert "/usr/bin/cc" in str(error_message["details"])


def test_library_mode_validation_requires_existing_file(qapp, monkeypatch, tmp_path) -> None:
    comp = Component(type=ComponentType.C_BLOCK, name="CB_LIB")
    comp.parameters["implementation"] = "library"
    comp.parameters["lib_path"] = (tmp_path / "missing_cb.so").as_posix()

    panel = PropertiesPanel()
    panel.set_component(comp)
    assert panel._cblock_mode_combo is not None
    panel._cblock_mode_combo.setCurrentIndex(1)

    messages: list[dict[str, object]] = []
    monkeypatch.setattr(
        panel,
        "_show_cblock_build_message",
        lambda **kwargs: messages.append(kwargs),
    )

    panel._on_test_cblock_compilation()

    assert messages
    msg = messages[-1]
    assert msg["title"] == "C-Block Validation Error"
    assert "not found" in str(msg["message"]).lower()


def test_cblock_path_editor_normalizes_windows_separators(qapp) -> None:
    comp = Component(type=ComponentType.C_BLOCK, name="CB_PATH")
    panel = PropertiesPanel()
    panel.set_component(comp)
    assert panel._cblock_path_edit is not None

    panel._cblock_path_edit.setText(r"C:\workspace\blocks\ctrl.c")
    panel._on_cblock_path_changed()

    assert comp.parameters["source"] == "C:/workspace/blocks/ctrl.c"

