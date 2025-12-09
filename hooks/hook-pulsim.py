"""PyInstaller hook for pulsim - Power electronics simulation backend."""

from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_dynamic_libs

# Collect all pulsim submodules
hiddenimports = collect_submodules('pulsim')

# Collect data files and binaries
datas, binaries, hiddenimports_extra = collect_all('pulsim')
hiddenimports.extend(hiddenimports_extra)

# Ensure the native extension is included
binaries.extend(collect_dynamic_libs('pulsim'))
