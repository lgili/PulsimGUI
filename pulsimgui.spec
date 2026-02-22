# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for PulsimGui - Cross-platform power electronics simulator GUI.

This spec file creates a standalone application that includes:
- All frontend dependencies (PySide6, pyqtgraph, numpy, qtawesome)
- Backend simulation engine (pulsim with native extensions)
- All required Qt plugins and resources
"""

import sys
import os
from pathlib import Path
import site

# Determine platform
is_windows = sys.platform == 'win32'
is_macos = sys.platform == 'darwin'
is_linux = sys.platform.startswith('linux')

# Application metadata
APP_NAME = 'PulsimGui'
APP_VERSION = os.environ.get('PULSIMGUI_VERSION', '0.1.0').lstrip('v') or '0.1.0'
APP_BUNDLE_ID = 'com.pulsim.pulsimgui'

# Paths
SPEC_DIR = Path(SPECPATH)
SRC_DIR = SPEC_DIR / 'src'
PACKAGING_DIR = SPEC_DIR / 'packaging'
ICONS_DIR = PACKAGING_DIR / 'icons'

# Find site-packages to locate pulsim
site_packages = site.getsitepackages()
if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
    # Virtual environment
    site_packages = [str(Path(sys.prefix) / 'lib' / f'python{sys.version_info.major}.{sys.version_info.minor}' / 'site-packages')]

# Icon paths per platform
if is_windows:
    ICON_FILE = ICONS_DIR / 'pulsimgui.ico'
elif is_macos:
    ICON_FILE = ICONS_DIR / 'pulsimgui.icns'
else:
    ICON_FILE = ICONS_DIR / 'pulsimgui.png'

# Convert to string (PyInstaller expects strings)
ICON_FILE = str(ICON_FILE) if ICON_FILE.exists() else None

# Hidden imports required for PySide6, pyqtgraph, and pulsim backend
hidden_imports = [
    # PySide6 core modules
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtSvg',
    'PySide6.QtSvgWidgets',
    'PySide6.QtOpenGL',
    'PySide6.QtOpenGLWidgets',
    'PySide6.QtPrintSupport',

    # pyqtgraph modules
    'pyqtgraph',
    'pyqtgraph.graphicsItems',
    'pyqtgraph.graphicsItems.PlotItem',
    'pyqtgraph.graphicsItems.PlotDataItem',
    'pyqtgraph.graphicsItems.ViewBox',
    'pyqtgraph.graphicsItems.AxisItem',
    'pyqtgraph.graphicsItems.GridItem',
    'pyqtgraph.graphicsItems.LegendItem',
    'pyqtgraph.graphicsItems.InfiniteLine',
    'pyqtgraph.graphicsItems.TextItem',
    'pyqtgraph.graphicsItems.ScatterPlotItem',

    # numpy modules
    'numpy',
    'numpy.core._methods',
    'numpy.lib.format',
    'numpy.fft',
    'numpy.linalg',

    # qtawesome for icons
    'qtawesome',
    'qtawesome.iconic_font',

    # pulsim backend - simulation engine
    'pulsim',
    'pulsim._pulsim',
    'pulsim.devices',
    'pulsim.remote',
    'pulsim.remote.client',
    'pulsim.remote.simulator_pb2',
    'pulsim.remote.simulator_pb2_grpc',
    'pulsim.remote.widgets',

    # grpc for remote simulation (if used)
    'grpc',
    'grpc._cython',
    'google.protobuf',
]

# Collect data files
datas = [
    # Include pulsimgui resources
    (str(SRC_DIR / 'pulsimgui' / 'resources'), 'pulsimgui/resources'),
]

# Collect binaries - pulsim native extension
binaries = []
for sp in site_packages:
    pulsim_native = Path(sp) / 'pulsim'
    if pulsim_native.exists():
        # Find the native extension (.so on Unix, .pyd on Windows)
        for ext in ['*.so', '*.pyd', '*.dylib']:
            for native_file in pulsim_native.glob(f'_pulsim*{ext.replace("*", "")}'):
                binaries.append((str(native_file), 'pulsim'))
                break

# Analysis
a = Analysis(
    [str(SRC_DIR / 'pulsimgui' / '__main__.py')],
    pathex=[str(SRC_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[str(SPEC_DIR / 'hooks')],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # GUI toolkits we don't use
        'tkinter',
        '_tkinter',
        'Tkinter',

        # Scientific libraries not needed
        'matplotlib',
        'scipy',
        'pandas',
        'PIL',
        'Pillow',

        # Development tools
        'IPython',
        'jupyter',
        'notebook',
        'pytest',

    ],
    noarchive=False,
    optimize=0,  # Don't optimize - numpy requires docstrings
)

# Remove unnecessary PySide6 modules to reduce size
pyside6_excludes = [
    'PySide6.QtBluetooth',
    'PySide6.QtDBus',
    'PySide6.QtDesigner',
    'PySide6.QtHelp',
    'PySide6.QtMultimedia',
    'PySide6.QtMultimediaWidgets',
    'PySide6.QtNetwork',
    'PySide6.QtNfc',
    'PySide6.QtPositioning',
    'PySide6.QtQml',
    'PySide6.QtQuick',
    'PySide6.QtQuick3D',
    'PySide6.QtRemoteObjects',
    'PySide6.QtScxml',
    'PySide6.QtSensors',
    'PySide6.QtSerialPort',
    'PySide6.QtSql',
    'PySide6.QtTest',
    'PySide6.QtWebChannel',
    'PySide6.QtWebEngine',
    'PySide6.QtWebEngineCore',
    'PySide6.QtWebEngineWidgets',
    'PySide6.QtWebSockets',
    'PySide6.QtXml',
    'PySide6.Qt3DAnimation',
    'PySide6.Qt3DCore',
    'PySide6.Qt3DExtras',
    'PySide6.Qt3DInput',
    'PySide6.Qt3DLogic',
    'PySide6.Qt3DRender',
]

a.binaries = [b for b in a.binaries if not any(excl in b[0] for excl in pyside6_excludes)]

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# Platform-specific executable configuration
if is_macos:
    # macOS: Create .app bundle
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,  # UPX doesn't work well on macOS
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=True,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=ICON_FILE,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=APP_NAME,
    )

    app = BUNDLE(
        coll,
        name=f'{APP_NAME}.app',
        icon=ICON_FILE,
        bundle_identifier=APP_BUNDLE_ID,
        version=APP_VERSION,
        info_plist={
            'CFBundleName': APP_NAME,
            'CFBundleDisplayName': APP_NAME,
            'CFBundleVersion': APP_VERSION,
            'CFBundleShortVersionString': APP_VERSION,
            'CFBundleIdentifier': APP_BUNDLE_ID,
            'NSHighResolutionCapable': True,
            'NSRequiresAquaSystemAppearance': False,  # Support dark mode
            'LSMinimumSystemVersion': '10.15',
            'CFBundleDocumentTypes': [
                {
                    'CFBundleTypeName': 'Pulsim Project',
                    'CFBundleTypeExtensions': ['pulsim'],
                    'CFBundleTypeRole': 'Editor',
                    'LSHandlerRank': 'Owner',
                }
            ],
        },
    )

elif is_windows:
    # Windows: Create single executable with console hidden
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=ICON_FILE,
        version_file=str(PACKAGING_DIR / 'windows' / 'version_info.txt') if (PACKAGING_DIR / 'windows' / 'version_info.txt').exists() else None,
    )

else:
    # Linux: Create executable
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name=APP_NAME.lower(),
        debug=False,
        bootloader_ignore_signals=False,
        strip=True,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=ICON_FILE,
    )
