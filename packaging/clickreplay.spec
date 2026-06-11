# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for ClickReplay.

Builds a single-file, windowed (no console) executable that launches the GUI.

Build from the repo root with:

    pip install -e ".[build]"
    pyinstaller packaging/clickreplay.spec

The result is ``dist/ClickReplay.exe``. A ``config.ini`` placed next to the
exe is picked up automatically (portable install).
"""

import os

from PyInstaller.utils.hooks import collect_submodules

# SPECPATH is injected by PyInstaller — the directory containing this spec.
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")
ENTRY = os.path.join(SRC, "clickreplay", "gui.py")
EXAMPLE_INI = os.path.join(ROOT, "config.example.ini")

# pynput and pyautogui load platform backends dynamically; pull them all in.
hiddenimports = collect_submodules("pynput") + collect_submodules("pyautogui")

a = Analysis(
    [ENTRY],
    pathex=[SRC],
    binaries=[],
    datas=[(EXAMPLE_INI, ".")],
    hiddenimports=hiddenimports,
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
    name="ClickReplay",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # windowed app — no console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
