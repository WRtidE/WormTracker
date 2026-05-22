# -*- mode: python ; coding: utf-8 -*-
"""WormTracker PyInstaller 跨平台打包规格文件

支持平台:
    - macOS:  生成 .app 应用包
    - Windows: 生成 .exe 单文件

用法:
    pyinstaller wormtracker.spec          # 打包
    pyinstaller --clean wormtracker.spec  # 清理后重新打包
    python build.py                       # 通过 build.py 调用 (推荐)
"""

import sys
import os
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    collect_dynamic_libs,
)

# ── 项目根目录 ──────────────────────────────────────────
_root = Path(SPECPATH)  # SPECPATH 是 spec 文件所在目录

# ── 图标 (平台自适应) ───────────────────────────────────
_icon_map = {
    "darwin": str(_root / "icon.icns"),
    "win32":  str(_root / "icon.ico"),
}
icon_file = _icon_map.get(sys.platform, None)
if icon_file and not os.path.exists(icon_file):
    print(f"WARNING: Icon file not found: {icon_file}, skipping icon")
    icon_file = None

# ── 数据文件 ────────────────────────────────────────────
datas = [
    (str(_root / "config.yaml"), "."),
]

# matplotlib 字体/样式数据
datas += collect_data_files("matplotlib")

# ── 隐藏导入 ────────────────────────────────────────────
hiddenimports = [
    # PyQt6
    "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets",
    "PyQt6.sip",
    # matplotlib 后端
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_qt5agg",
    "matplotlib.backends.backend_agg",
    "matplotlib.backends.backend_svg",
    # openpyxl (pandas Excel 导出)
    "openpyxl", "openpyxl.styles", "openpyxl.utils",
    "openpyxl.cell._writer", "openpyxl.cell.cell",
    # 项目模块
    "wormtracker", "wormtracker.config", "wormtracker.core",
    "wormtracker.core.counter", "wormtracker.core.grid",
    "wormtracker.core.tracker", "wormtracker.core.visualize",
    "wormtracker.engine", "wormtracker.engine.base",
    "wormtracker.engine.mog2",
    "wormtracker.ui", "wormtracker.ui.styles",
    "wormtracker.ui.thread", "wormtracker.ui.window",
    # numpy / cv2 全量收集
    "numpy", "cv2",
    # yaml
    "yaml",
]

# ── 排除不必要的重型模块 ───────────────────────────────
excluded = [
    "torch", "torchvision", "ultralytics",
    "scipy", "sympy", "networkx",
    "polars", "fsspec", "jinja2",
    "IPython", "jupyter", "notebook",
    "tkinter", "tcl", "tk",
    "test", "tests",
    "pytest",
    "pip", "setuptools", "wheel",
]

# ── PyInstaller Analysis ───────────────────────────────
a = Analysis(
    [str(_root / "main.py")],
    pathex=[str(_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded,
    noarchive=False,
)

# ── 过滤掉被排除模块的二进制 ──────────────────────────
_exclude_set = set(excluded)
a.binaries = [
    (name, path, typ)
    for name, path, typ in a.binaries
    if not any(name.startswith(prefix + '.') or name == prefix
               for prefix in _exclude_set)
]

# ── 打包 ───────────────────────────────────────────────
pyz = PYZ(a.pure, a.zipped_data)

if sys.platform == "win32":
    # Windows: onefile 单文件 .exe
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="WormTracker",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_file,
    )
else:
    # macOS: onedir + .app 包 (推荐方式)
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="WormTracker",
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
        icon=icon_file,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="WormTracker_Data",
    )
    app = BUNDLE(
        coll,
        name="WormTracker.app",
        icon=icon_file,
        bundle_identifier="com.wormtracker.app",
        info_plist={
            "CFBundleName": "WormTracker",
            "CFBundleDisplayName": "WormTracker",
            "CFBundleShortVersionString": "6.0.0",
            "CFBundleVersion": "6.0.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "10.15",
            "LSBackgroundOnly": False,
        },
    )
