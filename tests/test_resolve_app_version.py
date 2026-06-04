"""Pin the splash-screen / app-branding version resolver.

The resolver in ``pulsimgui.__main__._resolve_app_version`` is the only
public path that maps "what version does the running app report?" to
a string. The contract pinned here:

  1. ``PULSIMGUI_VERSION`` env override beats everything. Installer
     CI sets this when the dist isn't built from a working tree.
  2. ``pulsimgui.__version__`` from ``src/pulsimgui/__init__.py`` —
     the LIVE source of truth — comes next. Picked up immediately
     after a version bump in dev (``pip install -e .`` doesn't
     refresh ``importlib.metadata``).
  3. ``importlib.metadata.version("pulsimgui")`` — the
     installed-package dist-info — is the LAST fallback. Without
     putting step 2 BEFORE step 3, the splash silently lagged the
     working tree's actual version on every bump-without-reinstall.

The user's bug report ("vi que a splash screen mostra a versao antiga")
was exactly this: ``__init__.py`` said ``1.2.0`` but the splash
showed the dist-info snapshot from the last reinstall. Tests in this
file guarantee that path stays correct.
"""
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    """``pulsimgui.__main__`` imports PySide6 widgets at module load
    time, so a QApplication has to exist before we can ``from
    pulsimgui.__main__ import _resolve_app_version``. The function
    itself never touches Qt at runtime, but the module guard does."""
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication(sys.argv)


def test_env_override_wins_when_set() -> None:
    """``PULSIMGUI_VERSION=2.99.0`` makes the splash report ``2.99.0``
    regardless of ``__version__`` or installed metadata. Used by the
    installer CI to stamp release candidates without touching source."""
    from pulsimgui.__main__ import _resolve_app_version

    with patch.dict("os.environ", {"PULSIMGUI_VERSION": "2.99.0"}):
        assert _resolve_app_version() == "2.99.0"


def test_env_override_strips_leading_v_prefix() -> None:
    """Git-tag-style ``PULSIMGUI_VERSION=v1.2.3`` shouldn't double up
    the ``v`` prefix on the splash badge (the badge prepends its own)."""
    from pulsimgui.__main__ import _resolve_app_version

    with patch.dict("os.environ", {"PULSIMGUI_VERSION": "v1.2.3"}):
        assert _resolve_app_version() == "1.2.3"


def test_blank_env_falls_through_to_package_version() -> None:
    """An empty or whitespace ``PULSIMGUI_VERSION`` shouldn't lock the
    splash to an empty string — the env path is opt-in."""
    from pulsimgui.__main__ import _resolve_app_version
    from pulsimgui import __version__ as live_version

    with patch.dict("os.environ", {"PULSIMGUI_VERSION": "   "}):
        result = _resolve_app_version()

    # Should resolve to the live __version__ (priority 2), not the
    # blank env value or an empty string.
    assert result == live_version


def test_live_init_version_beats_stale_dist_info() -> None:
    """The headline regression test. Simulate the dev workflow:
    ``__init__.py`` was bumped to a new version but ``pip install -e
    .`` hasn't been re-run, so ``importlib.metadata`` still reports
    the OLD version. The resolver MUST return the new live value.
    """
    from pulsimgui.__main__ import _resolve_app_version

    fake_live = "9.9.9"
    fake_stale_dist_info = "0.0.1"

    with patch.dict("os.environ", {"PULSIMGUI_VERSION": ""}), \
         patch("pulsimgui.__version__", fake_live), \
         patch("importlib.metadata.version", return_value=fake_stale_dist_info):
        result = _resolve_app_version()

    assert result == fake_live, (
        "live __version__ should win over metadata.version. If this "
        "test fails, the splash is back to silently showing the "
        "stale dist-info version after every dev version bump."
    )


def test_dist_info_fallback_when_init_unavailable() -> None:
    """If ``pulsimgui.__version__`` is somehow missing (broken install,
    legacy entry-point), the resolver still falls back to the
    installed-metadata version — better than returning an empty
    string and showing ``dev`` on a tagged release."""
    from pulsimgui.__main__ import _resolve_app_version

    # Simulate a missing __version__ by making the import raise.
    fake_dist_info = "1.1.1"

    with patch.dict("os.environ", {"PULSIMGUI_VERSION": ""}), \
         patch.dict(sys.modules, {"pulsimgui": None}), \
         patch("importlib.metadata.version", return_value=fake_dist_info):
        result = _resolve_app_version()

    # The patched ``pulsimgui`` is None → the inner ``from pulsimgui
    # import __version__`` raises an AttributeError, falls through to
    # the metadata branch.
    assert result == fake_dist_info


def test_resolver_returns_current_package_version() -> None:
    """Integration: in the normal dev test environment (where the
    working tree's ``__init__.py`` is importable), the resolver must
    return the same string the package self-reports. Pins the
    contract that any version bump in ``__init__.py`` is immediately
    visible to the splash without a reinstall."""
    from pulsimgui import __version__ as live_version
    from pulsimgui.__main__ import _resolve_app_version

    assert _resolve_app_version() == live_version
