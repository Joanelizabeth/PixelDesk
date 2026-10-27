# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Pixel Desk.  Build with:  pyinstaller --noconfirm --clean pixeldesk.spec
import sys

excluded = [
    "tkinter", "unittest", "pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtBluetooth", "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtPositioning", "PySide6.QtSql", "PySide6.QtDesigner",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    datas=[("assets/icons/pixeldesk.png", "assets/icons"), ("assets/icons/pixeldesk.ico", "assets/icons")],
    hiddenimports=["PySide6.QtNetwork"],
    excludes=excluded,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PixelDesk",
    icon="assets/icons/pixeldesk.ico" if sys.platform == "win32" else None,
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="PixelDesk", upx=False)
