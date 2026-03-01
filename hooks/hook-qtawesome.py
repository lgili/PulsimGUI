"""PyInstaller hook for qtawesome - Icon fonts for Qt."""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect all qtawesome data files (font files)
datas = collect_data_files('qtawesome')

# Collect submodules
hiddenimports = collect_submodules('qtawesome')
