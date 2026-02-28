import json, copy, sys
sys.path.insert(0, '/Users/lgili/Documents/01 - Codes/01 - Github/PulsimGui/src')

import pulsim as ps
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.services.backend_adapter import PulsimBackend, BackendInfo, BackendCallbacks
from pulsimgui.services.simulation_service import SimulationSettings
from pulsimgui.utils.net_utils import build_node_map, build_node_alias_map
from pulsimgui.models.project import Project

# Build buck circuit data
with open('/Users/lgili/Documents/01 - Codes/01 - Github/PulsimGui/examples/buck_converter.pulsim') as f:
    data = json.load(f)

project = Project.from_dict(data)
gui_circuit = project.get_active_circuit()
node_map_raw = build_node_map(gui_circuit)
alias_map = build_node_alias_map(gui_circuit, node_map_raw)

circuit_data = {'components': [], 'node_map': {}, 'node_aliases': alias_map}
for comp in gui_circuit.components.values():
    d = comp.to_dict(); d['parameters'] = copy.deepcopy(comp.parameters)
    cid = str(comp.id)
    d['pin_nodes'] = [node_map_raw.get((cid, i)) or '' for i in range(len(comp.pins))]
    circuit_data['components'].append(d); circuit_data['node_map'][cid] = d['pin_nodes']

# Test A: Low-level SimulationOptions path (manual)
print("=== Test A: Low-level with updated settings (gate=20V in example) ===")
ckt = CircuitConverter(ps).build(circuit_data)
print(f"Circuit: {ckt.num_nodes()} nodes, {ckt.num_branches()} branches")

opts = ps.SimulationOptions()
opts.tstop = 500e-6
opts.dt = 0.2e-6
opts.dt_max = 0.8e-6
opts.adaptive_timestep = False
opts.integrator = ps.Integrator.BDF1
opts.newton_options.num_nodes = int(ckt.num_nodes())
opts.newton_options.num_branches = int(ckt.num_branches())
opts.newton_options.max_iterations = 100
opts.newton_options.initial_damping = 0.5
opts.newton_options.min_damping = 1e-4
opts.newton_options.auto_damping = True
opts.max_step_retries = 8
fp = opts.fallback_policy
fp.enable_transient_gmin = True; fp.gmin_retry_threshold = 1
fp.gmin_initial = 1e-8; fp.gmin_max = 1e-4; fp.gmin_growth = 10; fp.trace_retries = True

result = ps.Simulator(ckt, opts).run_transient(ckt.initial_state())
print(f"A: success={result.success}, steps={result.total_steps}, msg={result.message}")
if result.success:
    print(f"   time: {result.time[0]:.3e} to {result.time[-1]:.3e}")

# Test B: Full backend path (through PulsimBackend)
print("\n=== Test B: Full PulsimBackend path ===")
info = BackendInfo(
    identifier="pulsim", name="pulsim", version="0.5.1", status="available",
    capabilities={"transient"}, message=""
)
backend = PulsimBackend(ps, info)

noop_callbacks = BackendCallbacks(
    progress=lambda pct, msg: None,
    data_point=lambda t, d: None,
    check_cancelled=lambda: False,
    wait_if_paused=lambda: None,
)

settings = SimulationSettings()
settings.t_start = 0.0
settings.t_stop = 500e-6
settings.t_step = 0.2e-6
settings.solver = "bdf1"  # Use explicit BDF1
settings.step_mode = "fixed"
settings.max_newton_iterations = 100
settings.enable_events = True
settings.max_step_retries = 8

run_result = backend.run_transient(circuit_data, settings, noop_callbacks)
print(f"B: error='{run_result.error_message}', time_pts={len(run_result.time)}")
if not run_result.error_message:
    print(f"   time: {run_result.time[0]:.3e} to {run_result.time[-1]:.3e}")
    print(f"   signals: {list(run_result.signals.keys())[:5]}")
    print("SUCCESS!")


