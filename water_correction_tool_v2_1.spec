# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules


hiddenimports = (
    collect_submodules("PIL")
    + collect_submodules("numpy")
    + collect_submodules("numpy._core")
    + collect_submodules("scipy.ndimage")
    + collect_submodules("pyproj")
    + [
        "numpy._core._exceptions",
        "scipy._cyutility",
        "scipy.linalg._cythonized_array_utils",
    ]
)

datas = collect_data_files("pyproj")

binaries = (
    collect_dynamic_libs("numpy")
    + collect_dynamic_libs("scipy")
    + collect_dynamic_libs("pyproj")
)

a = Analysis(
    ["water_correction_tool.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="水系订正工具_V2.1.0",
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
)
