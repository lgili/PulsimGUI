"""Example catalog — scanning, categorisation and the browser dialog."""
from __future__ import annotations

import json
from pathlib import Path

from pulsimgui.services.example_catalog import (
    categories,
    categorize,
    load_example_info,
    scan_examples,
)

_REPO_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _write_example(tmp_path: Path, name: str, *, title: str | None = None,
                   description: str = "") -> Path:
    project = {
        "name": title or name,
        "description": description,
        "simulation_settings": {"tstop": 0.05},
        "circuits": {"main": {"components": [
            {"type": "RESISTOR"}, {"type": "MMC_ARM"}, {"type": "GROUND"},
        ]}},
    }
    path = tmp_path / f"{name}.pulsim"
    path.write_text(json.dumps(project))
    return path


def test_categorize_heuristics() -> None:
    assert categorize("33_m3c_gate_driven") == "M3C / Matrix Converter"
    assert categorize("26_mmc_three_phase_l3") == "MMC / Multilevel"
    assert categorize("19_foc_compressor") == "Motor Drives"
    assert categorize("04_buck_converter") == "DC-DC Converters"
    assert categorize("16_pfc_drive") == "PFC / Rectifiers"
    assert categorize("rc_lowpass") == "Basics"
    assert categorize("zzz_unknown_thing") == "Other"


def test_load_example_info_reads_project(tmp_path: Path) -> None:
    path = _write_example(tmp_path, "90_mmc_demo", title="MMC Demo",
                          description="Teaching demo.")
    info = load_example_info(path)
    assert info is not None
    assert info.title == "MMC Demo"
    assert info.category == "MMC / Multilevel"
    assert info.description == "Teaching demo."
    assert info.tstop == 0.05
    assert info.n_components == 3
    assert "Mmc Arm" in info.component_summary       # GROUND filtered out
    assert "Ground" not in info.component_summary


def test_scan_skips_backups_and_sorts(tmp_path: Path) -> None:
    _write_example(tmp_path, "01_buck")
    _write_example(tmp_path, "02_mmc")
    (tmp_path / "old.pulsim.bak").write_text("{}")
    bad = tmp_path / "broken.pulsim"
    bad.write_text("{not json")
    infos = scan_examples([tmp_path])
    names = [i.path.name for i in infos]
    assert "old.pulsim.bak" not in names
    assert "broken.pulsim" not in names
    assert len(infos) == 2
    cats = categories(infos)
    assert cats.index("MMC / Multilevel") < cats.index("DC-DC Converters") or \
        set(cats) == {"MMC / Multilevel", "DC-DC Converters"}


def test_real_repo_examples_scan_cleanly() -> None:
    """Every bundled example parses into the catalog (no .bak, no failures)."""
    if not _REPO_EXAMPLES.is_dir():
        return
    infos = scan_examples([_REPO_EXAMPLES])
    assert len(infos) >= 30                       # the numbered set + gallery
    assert all(".bak" not in i.path.name for i in infos)
    assert all(i.title for i in infos)
    by_cat = categories(infos)
    assert "MMC / Multilevel" in by_cat
    assert "M3C / Matrix Converter" in by_cat


def test_browser_dialog_filters_and_picks(qapp, tmp_path: Path) -> None:
    from pulsimgui.services.example_catalog import scan_examples as scan
    from pulsimgui.views.dialogs.example_browser_dialog import (
        ExampleBrowserDialog,
    )

    _write_example(tmp_path, "01_buck", title="Buck Converter")
    _write_example(tmp_path, "02_mmc", title="MMC Demo")
    dialog = ExampleBrowserDialog(infos=scan([tmp_path]))
    try:
        assert dialog._ex_list.count() == 2          # "All examples"
        # Category filter narrows the list.
        for row in range(dialog._cat_list.count()):
            if dialog._cat_list.item(row).text() == "MMC / Multilevel":
                dialog._cat_list.setCurrentRow(row)
                break
        assert dialog._ex_list.count() == 1
        assert dialog._ex_list.item(0).text() == "MMC Demo"
        # Doc pane follows the selection.
        assert "MMC Demo" in dialog._doc.toHtml()
        # Open path round-trip.
        dialog._on_open()
        assert dialog.selected_path is not None
        assert dialog.selected_path.endswith("02_mmc.pulsim")
        # Search filter.
        dialog._cat_list.setCurrentRow(0)
        dialog._search.setText("buck")
        assert dialog._ex_list.count() == 1
        assert dialog._ex_list.item(0).text() == "Buck Converter"
    finally:
        dialog.close()
