# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-file build for OpenSpotter Control."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


PROJECT_ROOT = Path(SPECPATH).resolve().parent
CONFIG_DIR = PROJECT_ROOT / "config"
ASSETS_DIR = PROJECT_ROOT / "assets"

datas = [
    (str(path), "config")
    for path in sorted(CONFIG_DIR.glob("*.json"))
    if path.name != "config_moonraker.json"
]
datas.extend(
    (str(path), str(path.parent.relative_to(PROJECT_ROOT)))
    for path in sorted(ASSETS_DIR.rglob("*.png"))
)

a = Analysis(
    [str(PROJECT_ROOT / "main.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("app.plugins"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OpenSpotter-Control",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
