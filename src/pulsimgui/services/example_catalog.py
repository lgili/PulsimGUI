"""Example catalog — scans the bundled examples into a browsable index.

Backs the in-GUI example browser (PLECS demo-library style): every ``.pulsim``
under the bundled ``examples/`` tree (including ``gallery/``) is summarised
into an :class:`ExampleInfo` with a title, a category inferred from the
file/project name, and an auto-generated description (component mix + sim
settings + the project's own ``description`` field when present).

Pure Python (no Qt) so it unit-tests in isolation.
"""
from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

_LOG = logging.getLogger(__name__)


@dataclass
class ExampleInfo:
    """One browsable example."""

    path: Path
    title: str
    category: str
    description: str = ""
    component_summary: str = ""
    tstop: float | None = None
    n_components: int = 0
    tags: list[str] = field(default_factory=list)


# Category rules: first keyword hit (in filename OR project name) wins.
# Ordered from most to least specific.
_CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("M3C / Matrix Converter", ("m3c", "cmc", "matrix")),
    ("MMC / Multilevel", ("mmc", "multilevel", "submodule")),
    # PFC before Motor Drives: "16_pfc_drive" is a PFC front-end first.
    ("PFC / Rectifiers", ("pfc", "rectifier", "bridge")),
    ("Motor Drives", ("foc", "pmsm", "sixstep", "six_step", "motor",
                      "compressor", "drive", "induction", "bldc")),
    ("DC-DC Converters", ("buck", "boost", "flyback", "forward", "llc",
                          "dab", "sepic", "cuk", "push_pull", "half_bridge")),
    ("Inverters", ("inverter", "vsi", "spwm", "svm")),
    ("Thermal", ("thermal", "heatsink", "loss")),
    ("Control / C-Block", ("cblock", "c_block", "control", "pi_", "pid")),
    ("Basics", ("rc_", "rl_", "rlc", "divider", "diode", "mosfet_switch",
                "transient", "validation")),
]

_DEFAULT_CATEGORY = "Other"


def categorize(name: str) -> str:
    """Infer the category from a file / project name."""
    low = name.lower()
    for category, keywords in _CATEGORY_RULES:
        if any(kw in low for kw in keywords):
            return category
    return _DEFAULT_CATEGORY


def find_examples_dirs() -> list[Path]:
    """Candidate example roots: repo ``examples/`` (dev mode) and the
    PyInstaller-bundle layout. Only existing dirs are returned."""
    candidates: list[Path] = []
    try:
        from pulsimgui import __file__ as pkg_init
        pkg_root = Path(pkg_init).resolve().parent
        candidates.append((pkg_root / "../../examples").resolve())
        candidates.append(pkg_root / "examples")
    except Exception:  # noqa: BLE001 — frozen import quirks
        pass
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        candidates.append(Path(sys.executable).resolve().parent / "examples")
    seen: set[Path] = set()
    out: list[Path] = []
    for cand in candidates:
        try:
            if cand.is_dir() and cand not in seen:
                seen.add(cand)
                out.append(cand)
        except OSError:
            continue
    return out


def _summarise(project: dict) -> tuple[str, int, float | None]:
    """(component mix string, total component count, tstop)."""
    counts: Counter[str] = Counter()
    for circ in (project.get("circuits") or {}).values():
        for comp in circ.get("components", []) or []:
            ctype = str(comp.get("type") or "?")
            counts[ctype] += 1
    total = sum(counts.values())
    interesting = [
        f"{n}× {t.replace('_', ' ').title()}"
        for t, n in counts.most_common(6)
        if t not in ("GOTO_LABEL", "FROM_LABEL", "GROUND")
    ]
    tstop = None
    try:
        tstop = float((project.get("simulation_settings") or {}).get("tstop"))
    except (TypeError, ValueError):
        pass
    return ", ".join(interesting[:5]), total, tstop


def load_example_info(path: Path) -> ExampleInfo | None:
    """Build the catalog entry for one ``.pulsim`` file (None on parse error)."""
    try:
        project = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _LOG.debug("example %s unreadable: %s", path, exc)
        return None
    title = str(project.get("name") or path.stem.replace("_", " ").title())
    summary, total, tstop = _summarise(project)
    description = str(project.get("description") or "").strip()
    category = categorize(path.stem + " " + title)
    tags = [kw for _cat, kws in _CATEGORY_RULES for kw in kws
            if kw in (path.stem + " " + title).lower()]
    return ExampleInfo(
        path=path, title=title, category=category, description=description,
        component_summary=summary, tstop=tstop, n_components=total, tags=tags,
    )


def scan_examples(roots: list[Path] | None = None) -> list[ExampleInfo]:
    """Scan every root (recursively) for ``.pulsim`` files, skipping backups
    and the GUI's private workdirs. Sorted by (category, title)."""
    roots = roots if roots is not None else find_examples_dirs()
    infos: list[ExampleInfo] = []
    seen_paths: set[Path] = set()
    for root in roots:
        for path in sorted(root.rglob("*.pulsim")):
            if path in seen_paths:
                continue
            name = path.name.lower()
            if ".bak" in name or "/.pulsimgui/" in str(path).replace("\\", "/"):
                continue
            seen_paths.add(path)
            info = load_example_info(path)
            if info is not None:
                infos.append(info)
    infos.sort(key=lambda i: (i.category, i.title.lower()))
    return infos


def categories(infos: list[ExampleInfo]) -> list[str]:
    """Distinct categories present, in catalog-rule order."""
    present = {i.category for i in infos}
    ordered = [cat for cat, _kws in _CATEGORY_RULES if cat in present]
    if _DEFAULT_CATEGORY in present:
        ordered.append(_DEFAULT_CATEGORY)
    return ordered
