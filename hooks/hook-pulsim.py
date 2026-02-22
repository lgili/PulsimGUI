"""PyInstaller hook for pulsim - Power electronics simulation backend."""

from importlib.util import find_spec

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

# Core backend modules always needed by the desktop app.
hiddenimports = ["pulsim", "pulsim._pulsim", "pulsim.netlist"]

# Collect optional pulsim submodules, but skip remote stack when grpc is absent.
if find_spec("grpc") is not None and find_spec("google.protobuf") is not None:
    hiddenimports.extend(collect_submodules("pulsim.remote"))

# Collect data files and binaries from pulsim package.
datas = collect_data_files("pulsim")
binaries = collect_dynamic_libs("pulsim")
