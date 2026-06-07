"""Regression tests for ``examples/23_full_thermal_compressor_drive.pulsim``.

Example 23 is the thermal-instrumented variant of example 20 (1800 W
single-phase PFC + FOC VSI compressor drive). It exists to exercise EVERY
pulsim 1.7 thermal feature end-to-end through the GUI's converter:

  * Two ``HEATSINK`` components (``HS_BR``, ``HS_INV``) translating to two
    ``shared_heatsink_descriptors`` on the lowered ``Circuit``.
  * Composite expansion: the single ``BR1`` bridge becomes 4 sub-device
    rows (one per internal diode); the single ``VSI`` becomes 6 sub-device
    rows (one per IGBT). Without this expansion the kernel would
    silently zero out 3/4 of the bridge's loss and 5/6 of the inverter's.
  * Multi-stage Foster thermal stacks (3 stages each) on every power
    device — drives the kernel's ``add_foster_thermal_network`` path.
  * Cauer topology on the HS_INV devices — drives the alternative
    ``CauerStage`` path.
  * Per-device ``thermal_t_max_C`` for ``ThermalLimitMonitor``.
  * Per-device ``loss_a_cond_per_C`` / ``loss_a_sw_per_C`` tempcos for
    ``TempCoLoss`` + ``electrothermal_steady_state``.

These tests pin the file's structure so a future schema bump that
silently drops the TH pin, the tempcos field, or the composite expansion
is caught loudly. They do NOT simulate (too slow for a gate test) — they
just load the file, convert it, and assert on the resulting Circuit.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import pulsim as p

from pulsimgui.models.project import Project
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.pulsim_v0_compat import make_compat_module
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map

EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "examples" / "23_full_thermal_compressor_drive.pulsim"


@pytest.fixture(scope="module")
def example_circuit_data() -> dict:
    """Load + connectivity-resolve the ex 23 schematic, ready for
    ``CircuitConverter.build``. Module-scoped so the 29-component
    file is only parsed once across all tests in this file."""
    data = json.loads(EXAMPLE_PATH.read_text())
    project = Project.from_dict(data, path=EXAMPLE_PATH)
    circuit = project.circuits[project.active_circuit]

    node_map_raw = build_node_map(circuit)
    alias_map = build_node_alias_map(circuit, node_map_raw)

    components_list: list[dict] = []
    component_node_map: dict[str, list[str]] = {}
    for c in circuit.components.values():
        comp_id = str(c.id)
        components_list.append({
            "id": comp_id,
            "type": c.type.name,
            "name": c.name,
            "x": c.x, "y": c.y,
            "rotation": c.rotation,
            "parameters": dict(c.parameters),
            "pins": [
                {"index": pin.index, "name": pin.name, "x": pin.x, "y": pin.y}
                for pin in c.pins
            ],
        })
        pin_nodes = []
        for pin_idx in range(len(c.pins)):
            raw = node_map_raw.get((comp_id, pin_idx), f"pin_{comp_id}_{pin_idx}")
            pin_nodes.append(alias_map.get(raw, raw))
        component_node_map[comp_id] = pin_nodes

    return {
        "components": components_list,
        "node_map": component_node_map,
        "node_aliases": alias_map,
        "_raw_project": project,
    }


@pytest.fixture(scope="module")
def converted_circuit(example_circuit_data):
    """Run the converter and return the lowered ``Circuit`` object."""
    conv = CircuitConverter(make_compat_module(p))
    return conv.build({
        "components": example_circuit_data["components"],
        "node_map": example_circuit_data["node_map"],
        "node_aliases": example_circuit_data["node_aliases"],
    })


def test_file_exists() -> None:
    assert EXAMPLE_PATH.is_file(), (
        f"Example file missing: {EXAMPLE_PATH}. Rebuild with "
        "``python scripts/build_example_23.py``."
    )


def test_schematic_loads_with_expected_topology(example_circuit_data) -> None:
    """Sanity: the 27-component ex 20 + 2 new HEATSINKs = 29 components,
    and the 4 new TH wires bring wire count from 50 to 54. Catches
    accidental component drops on file regeneration."""
    components = example_circuit_data["components"]
    by_type: dict[str, int] = {}
    for c in components:
        by_type[c["type"]] = by_type.get(c["type"], 0) + 1

    assert len(components) == 29
    assert by_type.get("HEATSINK") == 2
    assert by_type.get("SINGLE_PHASE_DIODE_BRIDGE") == 1
    assert by_type.get("THREE_PHASE_VSI") == 1
    assert by_type.get("PFC_BOOST_CONTROLLER") == 1
    assert by_type.get("FOC_CONTROLLER") == 1


def test_power_devices_have_thermal_port_enabled(example_circuit_data) -> None:
    """All four power devices on the heatsinks must report
    ``enable_thermal_port=True`` — otherwise the TH pin doesn't exist
    in the model layer, the wire endpoint to the heatsink dangles, and
    the converter silently emits zero shared-heatsink descriptors."""
    by_name = {c["name"]: c for c in example_circuit_data["components"]}
    for name in ("BR1", "D_boost", "Q_boost", "VSI"):
        params = by_name[name]["parameters"]
        # BR1 came in pre-existing-pinned with explicit TH from DEFAULT_PINS,
        # so its enable_thermal_port may be None (model's auto-sync infers
        # True from the serialized TH pin). The other three are explicit.
        if name == "BR1":
            pin_names = [pin["name"] for pin in by_name[name]["pins"]]
            assert "TH" in pin_names, f"{name} missing TH pin"
        else:
            assert params.get("enable_thermal_port") is True, (
                f"{name} has enable_thermal_port={params.get('enable_thermal_port')!r}"
            )


def test_power_devices_carry_multi_stage_foster_data(example_circuit_data) -> None:
    """Every power device must have non-empty ``thermal_rth_stages`` +
    ``thermal_cth_stages`` (the kernel reads these as the per-stage
    Foster R_k / C_k arrays). Empty strings collapse to the single-RC
    fallback — silently downgrading the thermal fidelity."""
    by_name = {c["name"]: c for c in example_circuit_data["components"]}
    for name in ("BR1", "D_boost", "Q_boost", "VSI"):
        params = by_name[name]["parameters"]
        rth_csv = str(params.get("thermal_rth_stages") or "").strip()
        cth_csv = str(params.get("thermal_cth_stages") or "").strip()
        assert rth_csv, f"{name} has empty thermal_rth_stages"
        assert cth_csv, f"{name} has empty thermal_cth_stages"
        # The example targets 3-stage stacks — fewer than 3 would
        # silently round-trip but defeat the multi-stage demo intent.
        n_rth = len([v for v in rth_csv.split(",") if v.strip()])
        n_cth = len([v for v in cth_csv.split(",") if v.strip()])
        assert n_rth >= 3, f"{name} rth has {n_rth} stages, expected ≥3"
        assert n_cth >= 3, f"{name} cth has {n_cth} stages, expected ≥3"


def test_power_devices_have_t_max_and_tempcos(example_circuit_data) -> None:
    """Pin the pulsim 1.7 ``ThermalLimitMonitor`` + ``TempCoLoss``
    parameters. If these go back to 0/0/0 the example silently downgrades
    to the legacy (temperature-independent) path."""
    by_name = {c["name"]: c for c in example_circuit_data["components"]}
    # Si parts use T_jmax = 150 °C; SiC uses 175 °C.
    expected_t_max = {"BR1": 150.0, "D_boost": 175.0, "Q_boost": 150.0, "VSI": 150.0}
    for name, t_max in expected_t_max.items():
        params = by_name[name]["parameters"]
        assert params.get("thermal_t_max_C") == t_max, (
            f"{name} t_max = {params.get('thermal_t_max_C')!r}, expected {t_max}"
        )

    # At least one device must have a NON-zero tempco so the example
    # actually exercises ``TempCoLoss`` / ``electrothermal_steady_state``.
    nonzero_tempco = any(
        by_name[n]["parameters"].get("loss_a_cond_per_C") not in (0, 0.0)
        or by_name[n]["parameters"].get("loss_a_sw_per_C") not in (0, 0.0)
        for n in ("BR1", "D_boost", "Q_boost", "VSI")
    )
    assert nonzero_tempco, (
        "All four power devices have zero tempcos — the TempCoLoss path "
        "won't trigger, defeating the example's purpose."
    )


def test_converter_emits_two_heatsink_descriptors(converted_circuit) -> None:
    """The 2 HEATSINK components must produce exactly 2 descriptors."""
    descs = list(getattr(converted_circuit, "shared_heatsink_descriptors", []))
    assert len(descs) == 2
    assert {d["name"] for d in descs} == {"HS_BR", "HS_INV"}


def test_hs_br_carries_four_diode_sub_devices(converted_circuit) -> None:
    """``HS_BR`` hosts the SINGLE_PHASE_DIODE_BRIDGE. The composite
    expansion must produce 4 sub-device rows (``BR1_D1`` … ``BR1_D4``).
    A single ``BR1`` row would silently swallow 3/4 of the bridge's
    loss in the kernel."""
    descs = list(converted_circuit.shared_heatsink_descriptors)
    hs_br = next(d for d in descs if d["name"] == "HS_BR")
    names = [dev["device_name"] for dev in hs_br["devices"]]
    assert names == ["BR1_D1", "BR1_D2", "BR1_D3", "BR1_D4"]


def test_hs_inv_expands_vsi_to_six_sub_switches(converted_circuit) -> None:
    """``HS_INV`` hosts D_boost + Q_boost + VSI. The VSI composite must
    expand to 6 sub-switches (``VSI__HSa`` … ``VSI__LSc``), giving 8
    total sub-device rows on this sink. The names MUST match the
    kernel's ``device_loss_summary`` keys exactly — a typo here would
    silently zero out 5/6 of the VSI's heat."""
    descs = list(converted_circuit.shared_heatsink_descriptors)
    hs_inv = next(d for d in descs if d["name"] == "HS_INV")
    names = [dev["device_name"] for dev in hs_inv["devices"]]
    assert names == [
        "D_boost", "Q_boost",
        "VSI__HSa", "VSI__HSb", "VSI__HSc",
        "VSI__LSa", "VSI__LSb", "VSI__LSc",
    ]


def test_hs_inv_devices_all_use_cauer_topology(converted_circuit) -> None:
    """The example sets ``thermal_network="cauer"`` on D_boost,
    Q_boost, and VSI so the HS_INV sink exercises the ``CauerStage``
    code path. HS_BR stays on Foster — together they cover both
    topologies in one example."""
    descs = list(converted_circuit.shared_heatsink_descriptors)
    hs_br = next(d for d in descs if d["name"] == "HS_BR")
    hs_inv = next(d for d in descs if d["name"] == "HS_INV")
    assert {dev["thermal_stage_kind"] for dev in hs_br["devices"]} == {"foster"}
    assert {dev["thermal_stage_kind"] for dev in hs_inv["devices"]} == {"cauer"}


def test_t_amb_is_hot_compressor_value(converted_circuit) -> None:
    """The schematic is set to T_amb = 50 °C (sealed compressor housing
    ambient). If this drops back to 25 °C the thermal margins shown by
    the example are misleadingly relaxed."""
    descs = list(converted_circuit.shared_heatsink_descriptors)
    for d in descs:
        assert d["T_amb_C"] == 50.0, (
            f"{d['name']} has T_amb_C={d['T_amb_C']}, expected 50.0 (compressor housing)."
        )


def test_simulation_settings_target_thermal_window(example_circuit_data) -> None:
    """The schematic's ``simulation_settings`` must request the long
    (1 s) integration window — anything shorter doesn't give the τ ≈
    80 ms Foster stages time to charge."""
    project = example_circuit_data["_raw_project"]
    settings = project.simulation_settings
    assert settings.tstop == pytest.approx(1.0), (
        f"tstop={settings.tstop}; ex 23 needs ≥1 s to reach thermal steady-state."
    )
    assert settings.thermal_ambient == pytest.approx(50.0), (
        f"thermal_ambient={settings.thermal_ambient}; ex 23 targets 50 °C."
    )
    assert settings.enable_losses is True
