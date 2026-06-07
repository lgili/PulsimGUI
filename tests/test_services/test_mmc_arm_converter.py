"""Tests for the MMC_ARM component expansion in CircuitConverter.

Each ``model_fidelity`` level must dispatch to the corresponding
``pulsim.mmc.add_mmc_arm_*`` helper with the right params class and a
correctly-populated parameters object. A recording fake backend stands
in for pulsim so the tests stay pure unit-level (no real simulation).
"""
from __future__ import annotations

from typing import Any

import pytest

from pulsimgui.models.component import (
    DEFAULT_PARAMETERS,
    DEFAULT_PINS,
    ComponentType,
)
from pulsimgui.services.circuit_converter import (
    CircuitConversionError,
    CircuitConverter,
)


# ---------------------------------------------------------------------------
# Recording fakes — mimic the pulsim.mmc surface the converter calls
# ---------------------------------------------------------------------------
class _Enum:
    def __init__(self, name): self.name = name
    def __repr__(self): return f"<Enum {self.name}>"


class _SubmoduleType:
    HalfBridge = _Enum("HalfBridge")
    FullBridge = _Enum("FullBridge")


class _ModulationScheme:
    PSC  = _Enum("PSC")
    PD   = _Enum("PD")
    POD  = _Enum("POD")
    APOD = _Enum("APOD")


class _Params:
    """Generic params bag — accepts any attribute via setattr.

    Pre-populates the union of fields the real pulsim params classes
    expose so the converter's ``hasattr(...)`` checks succeed for the
    optional per-level fields.
    """

    _DEFAULTS = {
        # Common
        "c_arm": 0.0, "v_c0": 0.0, "r_p": 0.0,
        "m_max": 1.0, "m_min": -1.0, "sm_type": None,
        # L1/L2/L3
        "f_carrier": 0.0, "f_switch": 0.0,
        "modulation_scheme": None,
        # L2-only
        "t_dead": 0.0, "t_min": 0.0,
        # L3-only
        "balancing": True,
    }

    def __init__(self, **kwargs):
        # Seed the defaults so the converter's ``hasattr`` checks pass
        for k, v in self._DEFAULTS.items():
            object.__setattr__(self, k, v)
        for k, v in kwargs.items():
            object.__setattr__(self, k, v)


def _make_params_factory(name: str):
    return lambda **kw: _Params(_class_name=name, **kw)


class _FakeArm:
    """Stand-in for a pulsim MMC arm handle (carries live ``v_C`` state)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.v_C = 0.0


class _FakeBuilder:
    def __init__(self):
        self.arm_calls: list[dict[str, Any]] = []


class _FakeMmcModule:
    SubmoduleType = _SubmoduleType
    ModulationScheme = _ModulationScheme
    # Params classes — exposed as factories that record their type
    MmcArmAverageParams     = _make_params_factory("Average")
    MmcArmMultilevelParams  = _make_params_factory("Multilevel")
    MmcArmEquivalentParams  = _make_params_factory("Equivalent")
    MmcArmDetailedParams    = _make_params_factory("Detailed")

    @staticmethod
    def _record_call(label: str):
        def fn(builder, *, name, node_a, node_b, params, **kw):
            # Real pulsim uses ``m_b`` for L0 (branch modulation) and
            # ``m_ref`` for L1/L2/L3 — accept either via **kw.
            mod_val = kw.get("m_ref", kw.get("m_b"))
            builder.arm_calls.append({
                "helper": label,
                "name": name, "node_a": node_a, "node_b": node_b,
                "params": params, "m_ref": mod_val,
                "mod_kwarg": "m_b" if "m_b" in kw else "m_ref",
            })
            # Real pulsim helpers return the arm handle; the converter
            # records it on ``nonlinear_observer_specs`` for the backend.
            return _FakeArm(name)
        return fn

    add_mmc_arm_average     = _record_call.__func__("L0")
    add_mmc_arm_multilevel  = _record_call.__func__("L1")
    add_mmc_arm_equivalent  = _record_call.__func__("L2")
    add_mmc_arm_detailed    = _record_call.__func__("L3")


class _FakeCircuit:
    @staticmethod
    def ground() -> int: return -1

    def __init__(self) -> None:
        self.nodes: dict[str, int] = {}
        self._builder = _FakeBuilder()
        self.nonlinear_observer_specs: list[dict[str, Any]] = []

    def add_node(self, name: str) -> int:
        if name in self.nodes:
            return self.nodes[name]
        idx = len(self.nodes)
        self.nodes[name] = idx
        return idx

    def _name_of(self, node_id: int) -> str:
        if node_id == -1:
            return "gnd"
        for nm, idx in self.nodes.items():
            if idx == node_id:
                return nm
        raise KeyError(node_id)


class _FakeBackend:
    Circuit = _FakeCircuit
    # Expose pulsim.mmc via the ``mmc`` attribute on the backend
    mmc = _FakeMmcModule


# ---------------------------------------------------------------------------
# Component definition sanity
# ---------------------------------------------------------------------------
def test_mmc_arm_pins_and_default_parameters() -> None:
    pins = DEFAULT_PINS[ComponentType.MMC_ARM]
    assert {p.name for p in pins} == {"TOP", "BOT", "M_REF"}
    params = DEFAULT_PARAMETERS[ComponentType.MMC_ARM]
    # Required keys (match pulsim 1.5 MmcArmDetailedParams surface)
    for key in ("model_fidelity", "submodule_type", "n_submodules",
                "c_sm", "v_c0", "r_arm",
                "f_carrier", "modulation_scheme"):
        assert key in params, f"missing default for {key!r}"
    # Sensible defaults
    assert params["model_fidelity"] == "L3 Detailed"
    assert params["submodule_type"] == "Half-Bridge"
    assert params["n_submodules"] == 4


def test_mmc_arm_in_catalog() -> None:
    from pulsimgui.models.component_catalog import (
        COMPONENT_LIBRARY,
        QUICK_ADD_COMPONENTS,
    )
    pc = COMPONENT_LIBRARY.get("Power Conversion", [])
    assert any(it["type"] == ComponentType.MMC_ARM for it in pc)
    assert any(entry[0] == ComponentType.MMC_ARM
               for entry in QUICK_ADD_COMPONENTS)


# ---------------------------------------------------------------------------
# Fidelity dispatch
# ---------------------------------------------------------------------------
def _arm_component(fidelity: str, **overrides: Any) -> dict[str, Any]:
    params = dict(DEFAULT_PARAMETERS[ComponentType.MMC_ARM])
    params["model_fidelity"] = fidelity
    params.update(overrides)
    return {
        "id": "arm-1", "name": "ARM1",
        "type": "MMC_ARM",
        "parameters": params,
    }


@pytest.mark.parametrize("fidelity,expected_helper,expected_params_class", [
    ("L0 Average",    "L0", "Average"),
    ("L1 Multilevel", "L1", "Multilevel"),
    ("L2 Equivalent", "L2", "Equivalent"),
    ("L3 Detailed",   "L3", "Detailed"),
])
def test_each_fidelity_dispatches_to_matching_helper(
    fidelity, expected_helper, expected_params_class,
) -> None:
    converter = CircuitConverter(_FakeBackend)
    circuit = converter.build({
        "components": [_arm_component(fidelity)],
        "node_map": {"arm-1": ["TOP_NODE", "BOT_NODE", "MREF_NODE"]},
        "node_aliases": {},
    })
    calls = circuit._builder.arm_calls
    assert len(calls) == 1
    call = calls[0]
    assert call["helper"] == expected_helper
    assert call["params"]._class_name == expected_params_class
    assert call["name"] == "ARM1"


def test_mmc_arm_recorded_for_observer_and_telemetry() -> None:
    """Each MMC arm must be recorded on ``nonlinear_observer_specs`` (with
    its pulsim handle + fidelity level) so the backend can attach the
    observer that advances the cap-voltage dynamics and publish the
    ``<arm>.v_C`` telemetry channel. Without this the arm is a static
    source frozen at ``m_ref·v_c0``."""
    converter = CircuitConverter(_FakeBackend)
    circuit = converter.build({
        "components": [_arm_component("L0 Average")],
        "node_map": {"arm-1": ["TOP_NODE", "BOT_NODE", "MREF_NODE"]},
        "node_aliases": {},
    })
    specs = [s for s in circuit.nonlinear_observer_specs if s.get("kind") == "mmc_arm"]
    assert len(specs) == 1
    spec = specs[0]
    assert spec["name"] == "ARM1"
    assert spec["level"] == "L0"
    assert spec["handle"] is not None  # the recorded pulsim arm handle


def _mmc_ctrl_and_arms() -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """An MMC_CONTROLLER whose 6 outputs are wired to 6 arm M_REF pins."""
    ctrl = {
        "id": "c1", "name": "MMCC1", "type": "MMC_CONTROLLER",
        "parameters": {
            "m_ref_offset": 0.5, "modulation_index": 0.6,
            "frequency": 60.0, "phase_deg": 0.0,
        },
    }
    arms = [
        {"id": i, "name": n, "type": "MMC_ARM",
         "parameters": {"model_fidelity": "L0 Average"}}
        for i, n in [("au", "ARM_Au"), ("al", "ARM_Al"),
                     ("bu", "ARM_Bu"), ("bl", "ARM_Bl"),
                     ("cu", "ARM_Cu"), ("cl", "ARM_Cl")]
    ]
    node_map = {
        "c1": ["nAU", "nAL", "nBU", "nBL", "nCU", "nCL"],  # 6 output pins
        "au": ["dcp", "mu_a", "nAU"], "al": ["ml_a", "dcn", "nAL"],
        "bu": ["dcp", "mu_b", "nBU"], "bl": ["ml_b", "dcn", "nBL"],
        "cu": ["dcp", "mu_c", "nCU"], "cl": ["ml_c", "dcn", "nCL"],
    }
    return [ctrl, *arms], node_map


def test_mmc_controller_drives_arm_mref_sinusoid() -> None:
    """A wired MMC_CONTROLLER yields a per-arm callable m_ref(t): upper/lower
    complementary about the offset, A/B/C shifted 120°, differential equal to
    the modulation index (the AC output amplitude)."""
    import math

    converter = CircuitConverter(_FakeBackend)
    components, node_map = _mmc_ctrl_and_arms()
    ov = converter._infer_mmc_arm_mref_overrides(components, node_map)

    assert set(ov) == {"ARM_Au", "ARM_Al", "ARM_Bu", "ARM_Bl", "ARM_Cu", "ARM_Cl"}
    assert all(callable(f) for f in ov.values())

    t_quarter = 0.25 / 60.0
    # Upper arm dips, lower arm rises by amp = index/2 = 0.3 about offset 0.5.
    assert abs(ov["ARM_Au"](0.0) - 0.5) < 1e-9
    assert abs(ov["ARM_Au"](t_quarter) - 0.2) < 1e-9
    assert abs(ov["ARM_Al"](t_quarter) - 0.8) < 1e-9
    # Phase-leg differential equals the modulation index.
    assert abs((ov["ARM_Al"](t_quarter) - ov["ARM_Au"](t_quarter)) - 0.6) < 1e-9
    # Phase B is shifted -120°.
    expected_bu0 = 0.5 - 0.3 * math.sin(math.radians(-120.0))
    assert abs(ov["ARM_Bu"](0.0) - expected_bu0) < 1e-9


def test_mmc_arms_without_controller_keep_constant_mref() -> None:
    """No MMC_CONTROLLER ⇒ empty override map (arms keep ``m_ref_constant``)."""
    converter = CircuitConverter(_FakeBackend)
    arms = [{"id": "au", "name": "ARM_Au", "type": "MMC_ARM", "parameters": {}}]
    ov = converter._infer_mmc_arm_mref_overrides(arms, {"au": ["dcp", "bot", "nAU"]})
    assert ov == {}


def test_arm_params_carry_common_fields() -> None:
    """n_sm, c_sm, v_c0, r_p, sm_type must propagate to the params
    instance handed to the pulsim helper."""
    converter = CircuitConverter(_FakeBackend)
    circuit = converter.build({
        "components": [_arm_component(
            "L3 Detailed",
            n_submodules=8,
            c_sm=2.0e-3, v_c0=400.0, r_arm=0.05,
            submodule_type="Full-Bridge",
        )],
        "node_map": {"arm-1": ["TOP_NODE", "BOT_NODE", "MREF_NODE"]},
        "node_aliases": {},
    })
    p = circuit._builder.arm_calls[0]["params"]
    assert p.n_sm == 8
    assert p.c_sm == pytest.approx(2.0e-3)
    assert p.v_c0 == pytest.approx(400.0)
    assert p.r_p == pytest.approx(0.05)
    # sm_type is a Literal string in pulsim 1.5
    assert p.sm_type == "full_bridge"


def test_l3_carries_balancing_strategy() -> None:
    """L3 ``balancing`` is a Literal ('sort_and_select' | 'none')."""
    converter = CircuitConverter(_FakeBackend)
    circuit = converter.build({
        "components": [_arm_component(
            "L3 Detailed", balancing="sort_and_select"
        )],
        "node_map": {"arm-1": ["TOP_NODE", "BOT_NODE", "MREF_NODE"]},
        "node_aliases": {},
    })
    p = circuit._builder.arm_calls[0]["params"]
    assert p.balancing == "sort_and_select"


def test_l1_l2_l3_carry_carrier_and_modulation() -> None:
    """f_carrier + modulation_scheme apply to L1/L2/L3 (not L0)."""
    for level in ("L1 Multilevel", "L2 Equivalent", "L3 Detailed"):
        converter = CircuitConverter(_FakeBackend)
        circuit = converter.build({
            "components": [_arm_component(
                level, f_carrier=20e3,
                modulation_scheme="IPD",
            )],
            "node_map": {"arm-1": ["TOP_NODE", "BOT_NODE", "MREF_NODE"]},
            "node_aliases": {},
        })
        p = circuit._builder.arm_calls[0]["params"]
        assert p.f_carrier == pytest.approx(20e3), f"{level} f_carrier"
        # modulation_scheme is a Literal string in pulsim 1.5
        assert p.modulation_scheme == "ipd", f"{level} modulation_scheme"


def test_l0_uses_m_b_kwarg_others_use_m_ref() -> None:
    """pulsim's add_mmc_arm_average takes ``m_b`` (branch modulation)
    while the other 3 helpers take ``m_ref``. The converter must
    dispatch the right keyword per level."""
    for fid, expected in (
        ("L0 Average",    "m_b"),
        ("L1 Multilevel", "m_ref"),
        ("L2 Equivalent", "m_ref"),
        ("L3 Detailed",   "m_ref"),
    ):
        converter = CircuitConverter(_FakeBackend)
        circuit = converter.build({
            "components": [_arm_component(fid)],
            "node_map": {"arm-1": ["TOP_NODE", "BOT_NODE", "MREF_NODE"]},
            "node_aliases": {},
        })
        assert circuit._builder.arm_calls[0]["mod_kwarg"] == expected, fid


def test_l3_balancing_accepts_legacy_bool_and_new_literal() -> None:
    """The GUI initially exposed ``balancing`` as a boolean; pulsim
    expects a Literal['sort_and_select', 'none']. The converter must
    accept both forms for backward compat."""
    # Legacy bool form
    converter = CircuitConverter(_FakeBackend)
    circuit = converter.build({
        "components": [_arm_component("L3 Detailed", balancing=False)],
        "node_map": {"arm-1": ["T", "B", "M"]},
        "node_aliases": {},
    })
    assert circuit._builder.arm_calls[0]["params"].balancing == "none"

    # Modern literal form
    converter = CircuitConverter(_FakeBackend)
    circuit = converter.build({
        "components": [_arm_component(
            "L3 Detailed", balancing="sort_and_select"
        )],
        "node_map": {"arm-1": ["T", "B", "M"]},
        "node_aliases": {},
    })
    assert (circuit._builder.arm_calls[0]["params"].balancing
            == "sort_and_select")


def test_unknown_fidelity_raises() -> None:
    converter = CircuitConverter(_FakeBackend)
    with pytest.raises(CircuitConversionError, match="model_fidelity"):
        converter.build({
            "components": [_arm_component("L9 Bogus")],
            "node_map": {"arm-1": ["TOP_NODE", "BOT_NODE", "MREF_NODE"]},
            "node_aliases": {},
        })


def test_arm_top_bot_resolved_to_kernel_node_names() -> None:
    """The helper is called with ``node_a``/``node_b`` set to the
    kernel-side node names (normalized N-prefixed form)."""
    converter = CircuitConverter(_FakeBackend)
    circuit = converter.build({
        "components": [_arm_component("L0 Average")],
        "node_map": {"arm-1": ["DC_PLUS", "DC_MINUS", "MOD_REF"]},
        "node_aliases": {},
    })
    call = circuit._builder.arm_calls[0]
    # The converter prepends "N" to user node names
    assert call["node_a"] == "NDC_PLUS"
    assert call["node_b"] == "NDC_MINUS"


def test_arm_missing_mmc_module_raises() -> None:
    """If pulsim < 1.5 (no ``mmc`` module), the converter must raise
    a clear error rather than fail silently."""
    class _NoMmc:
        Circuit = _FakeCircuit
        # NO ``mmc`` attribute → simulates pre-1.5 pulsim

    converter = CircuitConverter(_NoMmc)
    with pytest.raises(CircuitConversionError, match="pulsim.*1\\.5"):
        converter.build({
            "components": [_arm_component("L0 Average")],
            "node_map": {"arm-1": ["A", "B", "C"]},
            "node_aliases": {},
        })
