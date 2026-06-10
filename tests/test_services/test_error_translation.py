"""Unit tests for the kernel-error → user-guidance translation layer."""
from __future__ import annotations

from pulsimgui.services.error_translation import (
    explain_backend_error,
    format_user_error,
)


def test_singular_mask_is_explained_with_actions() -> None:
    raw = "PwlStateSpaceCache: numerically singular for mask 0b000000100 N=9 (dt=2.5e-07)"
    exp = explain_backend_error(raw)
    assert exp is not None
    assert "floating" in exp.title.lower() or "switch" in exp.title.lower()
    assert exp.actions                       # concrete next steps present
    text = format_user_error(raw)
    assert "How to fix:" in text
    assert raw in text                       # raw kernel text kept for support
    assert "GROUND" in text or "ground" in text


def test_all_off_mask_is_called_out() -> None:
    raw = "PwlStateSpaceCache: numerically singular for mask 0b000000000 N=9 (dt=5e-07)"
    exp = explain_backend_error(raw)
    assert exp is not None
    assert "all switches OFF" in exp.what


def test_generic_singular_matrix() -> None:
    exp = explain_backend_error("LU decomposition failed: matrix is singular")
    assert exp is not None
    assert "floating node" in exp.title.lower() or "singular" in exp.title.lower()


def test_newton_convergence_failure() -> None:
    exp = explain_backend_error("Newton solver did not converge after 50 iterations")
    assert exp is not None
    assert any("time step" in a.lower() or "snubber" in a.lower()
               for a in exp.actions)


def test_cblock_version_error() -> None:
    exp = explain_backend_error(
        "C-Block control requires backend >= 0.7.7. Detected 1.x.")
    assert exp is not None
    assert "C-Block" in exp.title


def test_cancelled_passthrough_title() -> None:
    exp = explain_backend_error("Simulation cancelled")
    assert exp is not None
    assert exp.actions == []


def test_unknown_error_falls_back_to_raw() -> None:
    raw = "some entirely novel kernel failure xyz-42"
    assert explain_backend_error(raw) is None
    text = format_user_error(raw, context="Simulation")
    assert text == f"Simulation failed:\n{raw}"


def test_empty_message() -> None:
    assert explain_backend_error("") is None
    assert format_user_error("", context="DC analysis").startswith("DC analysis failed:")
